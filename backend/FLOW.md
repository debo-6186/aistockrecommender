# End-to-End Flow

How a chat message travels from the browser to a stock allocation report in the
user's inbox, and which file owns each step.

Traced against branch `gemini_model_upgrade`. Line numbers move; the file and
function names are the durable part.

---

## Contents

1. [The five processes](#1-the-five-processes)
2. [One chat turn, stage by stage](#2-one-chat-turn-stage-by-stage)
3. [Choosing the question](#3-choosing-the-question)
4. [Reading a document](#4-reading-a-document)
5. [The dispatch gate](#5-the-dispatch-gate)
6. [Research to a priced report](#6-research-to-a-priced-report)
   - [6b. The report generator](#6b-the-report-generator)
7. [Where state lives](#7-where-state-lives)
8. [Adding a document type](#8-adding-a-document-type)
9. [Sharp edges](#9-sharp-edges)
10. [File map](#10-file-map)

---

## 1. The five processes

The browser only ever talks to the Host Agent. Everything else is reached over
the A2A protocol, or over MCP on stdio for market data.

```
                                      ┌──────────────────────────┐
                          ┌──A2A─────▶│  Stock Analyser  :10002  │
                          │           │  research + allocation   │
                          │           └────────────┬─────────────┘
                          │                        │ A2A
                          │                        ▼
┌─────────┐   HTTPS  ┌────┴─────┐     ┌──────────────────────────┐
│ Browser │─────────▶│   Host   │     │ Report Generator  :10004 │
│  :3000  │          │  :10001  │     │  covering note + email   │
└─────────┘          └────┬─┬───┘     └────────────┬─────────────┘
                          │ │                      │
                          │ └──A2A───▶┌────────────┴─────────────┐
                          │           │ Document Analyser :10003 │
                          │ stdio     │    OCR + extraction      │
                          │           └────────────┬─────────────┘
                          │     ┌──────────────┐   │
                          ├────▶│  MCP server  │   │
                          │     │  (yfinance)  │   │
                          │     └──────────────┘   │
                          ▼                        ▼
                    ┌───────────────────────────────────┐
                    │            PostgreSQL             │
                    │  sessions · state · results       │
                    └───────────────────────────────────┘
```

**A2A messages carry only text.** Anything structured — a holdings list, a
recommendation — is written to Postgres and read back by the receiver, so
nothing depends on a model echoing JSON accurately.

| Process | Owns | Entry point |
|---|---|---|
| Host Agent | REST API, auth, credits, the conversation, dispatch | `host_agent/__main__.py` |
| Stock Analyser | Market research, allocation, pricing, the database write | `stockanalyser_agent/__main__.py` |
| Report Generator | The covering note, HTML rendering, email delivery | `stockreport_generator_agent/__main__.py` |
| Document Analyser | Reading uploads: OCR plus schema-validated extraction | `document_analyser_agent/__main__.py` |
| MCP server | Quotes, news, price history, analyst consensus | `mcp/server.py` |

### Shared building blocks

`backend/agent_core/` is imported by all three agents:

| Module | Purpose |
|---|---|
| `models.py` | The one place the Gemini model id and generation config are decided |
| `sessions.py` | Postgres-backed ADK session service |
| `schemas.py` | Every Pydantic response schema, so structured output is valid by construction |
| `callbacks.py` | Tool and agent tracing applied uniformly |
| `a2a_client.py` | Minimal A2A client for an agent calling one known downstream service |

---

## 2. One chat turn, stage by stage

### Stage 1 — The request arrives

`host_agent/__main__.py:684` · `POST /api/chats`

Accepts `application/json` or `multipart/form-data`, so a message can arrive
with a file attached. A Firebase ID token is verified by `get_current_user`.
Rate limited to 40 requests a minute.

### Stage 2 — Gatekeeping

```
get_or_create_user
  └─▶ can_user_send_message_credits   (429 if out of credits)
        └─▶ report-generation limit    (new sessions only)
              └─▶ decrement_user_credits
```

Credits are decremented **before** the model runs, not after.

### Stage 3 — The upload is stored, if there is one

`host/agent.py:934` · `store_portfolio_file`

Written to `LOCAL_STORAGE_PATH` or S3 under a name derived from the session:

```
{user_id}_{session_id}_portfolio_statement.pdf
```

The session row is flagged `portfolio_statement_uploaded`. Nothing is read at
this point — the file sits there until the coordinator decides to look at it.

### Stage 4 — The coordinator turn begins

`host/agent.py:270` · `HostAgent.stream`

The ADK session is fetched or created against Postgres. The previous value of
`analysis_dispatched` is recorded, so the end of the conversation can be
detected from state rather than from what the model says.

### Stage 5 — The instruction is rebuilt from state

`host/prompts.py` · `coordinator_instruction`

The agent's instruction is a **function**, not a string, so ADK calls it fresh
before every model call:

```python
def instruction(context: ReadonlyContext) -> str:
    merged = dict(context.state or {})
    merged["available_agents"] = self.agents or "none connected"
    return coordinator_instruction(_StateView(merged))
```

It renders two things out of current session state: the directive for this turn
(see [part 3](#3-choosing-the-question)) and the list of what is already
settled. The model never has to remember anything across turns.

### Stage 6 — The model acts

Each `record_*` tool writes straight into `tool_context.state`, which ADK
persists to Postgres:

| Tool | Writes |
|---|---|
| `record_market` | `market_preference` — normalises "USA", "Indian", "NSE" etc. |
| `record_holdings` | `existing_portfolio_stocks` |
| `record_share_count` | `share_counts` |
| `record_budget` | `investment_amount` |
| `record_strategy` | `diversification_preference` — stored verbatim |
| `record_email` | `receiver_email_id` |
| `add_candidate_stocks` | `new_stocks`, after market-checked ticker resolution |

Each returns what is still outstanding, so the model gets a nudge toward the
next gap without being handed a script.

Off-workflow stock questions ("what is a P/E ratio") go to a `market_researcher`
sub-agent exposed as an `AgentTool`, which queries Perplexity. The conversation
is not handed off — the coordinator answers and continues.

### Stage 7 — A document is read, if one is involved

`host/agent.py:638` · `analyse_portfolio_document`

An A2A round trip to the Document Analyser. See [part 4](#4-reading-a-document).

### Stage 8 — Dispatch, when the brief is complete

`host/agent.py:727` · `request_full_analysis`

See [part 5](#5-the-dispatch-gate).

### Stage 9 — State is read back and the reply goes out

`host/agent.py:333` · `_refresh_snapshot`

Session state is re-read after the turn. If `analysis_dispatched` flipped from
false to true during this turn, the response carries `end_session: true`:

```python
if final_state.get("analysis_dispatched") and not dispatched_before:
    yield {"is_task_complete": True,
           "content": json.dumps({"message": response_text, "end_session": True})}
```

The session ends because a dispatch actually happened — not because the model
said "your report is on its way".

### Stage 10 — Later: portfolio performance

`host_agent/__main__.py:2295` · `GET /api/portfolio-performance/{session_id}`

Reads the saved recommendation and calls MCP tools directly from the API layer
for current prices. No agent is involved.

---

## 3. Choosing the question

The coordinator does **not** decide what to ask next. That is computed in Python
and handed to the model as a directive.

`REQUIRED_FACTS` in `host/prompts.py` is an ordered tuple. Each rung carries a
predicate saying whether state already holds it:

```python
Fact(
    key="budget",
    label="Budget",
    is_set=lambda s: float(s.get("investment_amount") or 0) > 0,
    ask="Ask how much new money they want to invest.",
)
```

`next_fact(state)` returns the first rung whose predicate is false.
`render_next_step` turns that into the `NEXT:` block in the instruction.

### The ladder in action

```
User: "I hold 50 AAPL and 30 MSFT, US market, $10k to invest"
          │
          ▼  record_market, record_holdings, record_share_count, record_budget
     ┌────────┬──────────┬────────┬──────────┬───────┐
     │ Market │ Holdings │ Budget │ Strategy │ Email │
     │  set   │   set    │  set   │  UNSET   │ unset │
     └────────┴──────────┴────────┴────┬─────┴───────┘
                                       │ first unset
                                       ▼
              NEXT: Ask what kind of investor they are —
                    time horizon, appetite for risk, sectors.
```

The order is fixed, so behaviour is testable. The skipping is what keeps it
conversational: three rungs were satisfied by one message, and none of them get
asked again.

| State | Computed next step |
|---|---|
| Empty session | `NEXT: market` — outstanding: Holdings, Budget, Strategy, Email |
| Four facts volunteered | `NEXT: strategy` — outstanding: Email |
| Only email missing | `NEXT: email` — dispatch after this |
| All five set | `EVERYTHING IS COLLECTED. Call request_full_analysis now.` |
| Already dispatched | `NOTHING LEFT TO COLLECT. Do not dispatch again.` |

Share counts ride along with the holdings question rather than forming their own
rung, so the ladder stays at five steps while still collecting the counts that
SELL advice depends on.

**Why not a state machine.** A rigid script would ask "which market do you
invest in?" to a user who opened by saying "US market". Deriving the next
question from state instead of a step counter gives the same predictable order
without that failure.

---

## 4. Reading a document

One agent handles every document type. The pipeline is identical for all of them
— find bytes, get text, classify, extract — and what varies per type is a
registry entry, not a code path.

### What crosses the wire

A2A messages are plain text, so the document type is passed as a **line in the
brief**, not as a typed parameter. Built at `host/agent.py:663`:

```
Read the portfolio statement uploaded for this session.

SESSION ID: 8f2c...
USER NAME: firebase-uid-123
EXPECTED DOCUMENT TYPE: portfolio_statement
The user invests in the US market. Note anything that does not belong there.

Use `read_document` with that session id and user name, then extract it as a
portfolio_statement. If it turns out to be a different kind of document, say
which.
```

> **The prompt never crosses the wire.**
> The host sends a type *name*. The extraction instruction for that type lives
> in the registry inside the Document Analyser and is resolved locally by
> `doc_types.get(name)`. A caller has to know a string, not carry prompt
> engineering.
>
> The hint is an optimisation, not a requirement. If the line is absent or
> wrong, the agent's instruction routes it to `classify_document`, which infers
> the type from content instead.

This is a **soft contract** — nothing enforces that the model reads the line or
passes a valid type. Enforcement is downstream: `doc_types.get()` returns `None`
for an unknown name and the tool replies with the supported list. It
self-corrects, but it is not a typed interface, and cannot be while A2A carries
text.

### The round trip

```
HOST :10001                          DOCUMENT ANALYSER :10003
───────────                          ────────────────────────

_clear_state_row(session)
      │
      │  (stops a previous document's
      │   result being read as this one's)
      ▼
_send_with_retry(brief) ──A2A text──▶ read_document()
                                            │
                                            ▼
                                      fetch_upload()  ── local disk or S3
                                            │
                                            ▼
                                   text layer >= 120 chars?
                                       │           │
                                   yes │           │ no
                                       ▼           ▼
                              use the PDF's   rasterise 2x →
                                own text      Gemini Vision
                                       │           │
                                       └─────┬─────┘
                                             ▼
                                   classify_document()
                                   (skipped if type given)
                                             │
                                             ▼
                                   extract_document(type)
                                   spec.instruction + spec.schema
                                             │
                                             ▼
                     ┌───────────────────────────────────────────┐
                     │ agent_states[session_id, "document_analyser"] │
                     └───────────────────────────────────────────┘
                                             │
_read_state_row() ◀──────────────────────────┘
      │
      ▼                    ◀──A2A prose reply──
_merge_intake() → state
```

### The OCR fork

`document_analyser_agent/reader.py`. The route is chosen from the file's
**contents**, not its extension:

| Input | Route |
|---|---|
| PDF with a text layer (≥ 120 chars) | `fitz` text extraction |
| PDF with no usable text layer (a scan) | Rasterise pages at 2× → Gemini Vision |
| Image (jpg, png, webp, …) | Gemini Vision directly |

Capped at 20 pages for OCR. Swapping Gemini Vision for another backend is a
change behind `reader.py` — the agent, the registry and the host do not notice.

### What each side gets back

The full extraction goes to the database. The model gets a summary, because a
forty-position holdings list repeated into context is pure waste.

| Reader | Receives |
|---|---|
| Postgres row | Full `PortfolioExtraction` dump, plus lifted `tickers`, `share_counts`, `missing_share_counts` |
| Analyser's model | `holdings_count`, ticker list, which positions lack a count, how it was read |
| Host's model | Counts and ticker names only, plus "already saved to state" |
| Host's state | `existing_portfolio_stocks` and `share_counts`, merged by `_merge_intake` |

A position with **no share count** is carried through every layer deliberately.
Without a count the analyst cannot size a sale, so that position can only ever be
rated HOLD — a constraint restated in the extraction prompt, the brief, and the
allocation instruction.

### The typed-text path

`analyse_portfolio_text` sends the user's typed holdings inline instead of
pointing at a file. The agent calls `record_document_text` rather than
`read_document`; no OCR is involved. Everything downstream is identical.

---

## 5. The dispatch gate

Nothing watches the conversation for readiness. The model calls
`request_full_analysis` when it believes the brief is complete, and the tool
decides whether that is true.

The raw A2A transport is deliberately **not** a tool. `send_message` exists on
the class but is not in the tools list, so the model can *ask* to dispatch and
cannot dispatch directly.

| Check | Reads | On failure |
|---|---|---|
| Market known | `market_preference` | `status: incomplete` with the list of what is missing. Nothing is sent. |
| Something to analyse | `existing_portfolio_stocks` or `new_stocks` | ” |
| Budget positive | `investment_amount` | ” |
| Strategy recorded | `diversification_preference` | ” |
| Email recorded | `receiver_email_id` | ” |
| Not already sent | `analysis_dispatched` | `already_dispatched` — idempotence lives in state |
| Analyser reachable | `remote_agent_connections` | Error telling the model to say the service is down |

A premature call is not an error — it returns **what is still needed**, straight
back into the model's context. "Called too early" self-corrects into "now knows
to ask for the email".

Past all seven checks, `_build_brief` assembles one message — market, currency,
budget, holdings with counts, the strategy verbatim, the parsed statement — and
`send_message_background` fires it on a daemon thread so the user gets an
immediate reply.

**Two rules exist because of this gate:**

- The coordinator must never claim analysis is underway unless the tool returned
  successfully.
- `record_email`'s docstring says recording an address does not start anything.
  Handing over an email is the most natural-looking "we're done" signal in the
  conversation, and it is explicitly not one.

---

## 6. Research to a priced report

The Stock Analyser receives the brief over A2A and works out its own route
through the toolbox. What stays as plain Python is the part that must not be
improvised.

```
 Record brief          MCP research         allocation_agent      deliver_report
 context, stocks,  ──▶ info, news,      ──▶ output_schema     ──▶ plain Python
 share counts          history              enforced               │
                            │                                      │
                            ▼                                      │
                  ┌─────────────────────────┐                      │
                  │   capture_market_data   │  after_tool_callback  │
                  │  full payload → state   │                       │
                  │  price      → state ────┼──── live prices ─────▶│
                  └───────────┬─────────────┘                      │
                              ▼                                    ▼
                  model sees 1200-char digest       shares = amount / price
                                                    save to Postgres
                                                    hand off for delivery
```

### The digest boundary

`capture_market_data` is an `after_tool_callback` on every MCP `get_*` call. It
stores the full payload in `state["research"]` and the current price in
`state["prices"]`, then returns only a 1200-character digest to the model.
Research accumulates without flooding the context.

### The arithmetic boundary

`deliver_report` computes every share count in Python from the captured prices:

```python
if rating == "BUY":
    amount = _parse_money(line.get("investment_amount"))
    if amount > 0 and price > 0:
        line["number_of_shares"] = f"{amount / price:.4f} shares"
```

The analyst's instruction forbids computing share counts, allocation percentages
or currency conversions, and forbids recommending a sale for a position whose
count was not given. Those are constraints on the answer, not steps in a
procedure — which stock to research with which tool is left to the model.

### Where the analyser stops

`deliver_report` ends by saving the recommendation and handing the priced report
to the Report Generator:

```python
_hand_off_for_delivery(session_id, report, email, strategy, could_not_price)
    # → agent_states[session_id, "priced_report"]
_request_report(session_id)
    # → A2A to stock_report_generator_agent
```

**The database write happens before the handoff, deliberately.** Analysis and
delivery fail for different reasons and should not fail together — a webhook
outage must not cost the user the analysis they paid for. If the handoff itself
fails, the tool returns `saved_but_not_sent` rather than pretending the report
went out.

---

## 6b. The report generator

`stockreport_generator_agent`, port 10004. The numbers are settled by the time
it runs; its job is turning the record into something a person will read.

```
STOCK ANALYSER :10002                 REPORT GENERATOR :10004
─────────────────────                 ───────────────────────

price + save
      │
      ▼
agent_states["priced_report"] ◀───────────── load_report(session_id)
      │                                             │
      │                                             ▼
      └──A2A: "SESSION ID: ..." ─────▶      write_narrative
                                        (output_schema=ReportNarrative)
                                                    │
                                                    ▼
                                              send_report()
                                          render HTML + POST webhook
                                                    │
                                                    ▼
                                        delivery outcome written back
                                        to the same handoff row
```

### The three tools

| Tool | Does |
|---|---|
| `load_report` | Reads the handoff row, puts the report in state, returns a tally — verdict counts, positions, what could not be priced |
| `write_narrative` | An `AgentTool` sub-agent with `output_schema=ReportNarrative`: subject line, headline, summary, what changed, caveats |
| `send_report` | Renders HTML with the note above the tables, posts to the webhook, records whether it went out |

### What the narrative is for

The tables carry the numbers; the note says what they mean. Its instruction
holds it to what is already recorded:

> Every figure you quote must match the report exactly. Do not recompute
> anything, do not convert currencies, and do not round differently.

Caveats are mandatory where they exist — a position that could not be priced, a
holding with no share count, a stock excluded for want of data. Each one changes
what the investor can act on.

### Failure semantics

| Situation | Result |
|---|---|
| No handoff row | `load_report` errors; the agent says so and stops |
| No email in the report | `send_report` errors; nothing is sent anywhere else |
| Webhook rejects the post | `delivery_failed`, recorded on the handoff row; the recommendation is still saved |
| No narrative written | Sends anyway, logging a warning — the tables alone are still a report |

## 7. Where state lives

Four stores, with different durability guarantees.

| Store | Holds | Survives restart |
|---|---|---|
| **ADK session state**<br>`DatabaseSessionService` | Market, holdings, share counts, budget, strategy, email, `analysis_dispatched`. Every `record_*` write lands here. | Yes — Postgres |
| **`agent_states` table** | Two handoffs — document extraction under `document_analyser`, the priced report under `priced_report` — plus a legacy mirror of host state under `host_agent`. | Yes — Postgres |
| **Domain tables** | Users, sessions, messages, saved recommendations, `market_preference`, `portfolio_statement_uploaded`. | Yes — Postgres |
| **In-process** | `current_session_id`, `_state_snapshots`, `InMemoryArtifactService`, `InMemoryMemoryService`. | No — and not shared across workers |

The conversation itself is durable. What is not durable is the request-scoped
bookkeeping in the fourth row, which is where the sharp edges come from.

`agent_core/sessions.py` falls back to `InMemorySessionService` only when no
`DATABASE_URL` is configured, and logs a warning when it does.

---

## 8. Adding a document type

Every field on `DocType` has exactly one consumer. Nothing dispatches on the
type name beyond a single dict lookup.

| Field | Consumed by | Effect |
|---|---|---|
| `hint` | `classifier_hints()` | Interpolated into the agent instruction and classifier prompt at import, so a new type becomes recognisable automatically |
| `instruction` | `extract_document` | Passed as `system_instruction` — **this is your per-type system prompt** |
| `schema` | `extract_document` | Passed as `response_schema`, so the model returns valid JSON by construction |
| `validity_field` | `extract_document` | Separates "wrong kind of document" from "extraction failed" — they need different messages |
| `summary_fields` | `_summarise` | Chooses what the model is told about after extraction |
| `name` | — | Currently redundant with the dict key; keeps a `DocType` self-describing |

### The two files you touch

```python
# 1. agent_core/schemas.py — the shape of the answer
class PortfolioSummary(BaseModel):
    is_portfolio_summary: bool
    rejection_reason: str = ""
    period: str = ""
    total_value: str = ""
    returns: str = ""

# 2. document_analyser_agent/doc_types.py — pair it with a prompt
"portfolio_summary": DocType(
    name="portfolio_summary",
    schema=PortfolioSummary,
    instruction=PORTFOLIO_SUMMARY_INSTRUCTION,
    hint="a period-end summary of portfolio value and returns",
    validity_field="is_portfolio_summary",
    summary_fields=("period", "total_value", "returns"),
),
```

That is all. `classify_document` can now return the new type, `extract_document`
resolves it, and the host needs no change.

> **One coupling that fails quietly.**
> `DocumentType` in `agent_core/schemas.py` is a `Literal[...]` used as the
> response schema for `classify_document`. A new type name must be added there
> too, or the classifier is structurally unable to emit it — and the failure
> looks like the classifier simply never choosing your type.

### Currently registered

| Type | Schema | Extracts |
|---|---|---|
| `portfolio_statement` | `PortfolioExtraction` | Holdings, tickers, allocations, share counts, positions lacking a count |
| `contract_note` | `ContractNote` | Per-execution side, quantity, price, date; total charges |
| `annual_report` | `AnnualReportSummary` | Company, period, revenue, net income, EPS, highlights, stated risks |

### When a type deserves its own agent

Not when its *prompt* differs — when its *processing* does:

- A 200-page annual report needing chunking and map-reduce rather than one call
- Handwriting needing a different vision backend
- A type with a compliance requirement that its documents never leave a region

The first two are a different **tool inside the same agent**, not a different
service. Only the third genuinely needs process separation.

---

## 9. Sharp edges

### Request data on a shared singleton

`host_agent_instance` is one global object, and `current_session_id` is a
mutable dict on it, overwritten per request (`__main__.py:847`, `1154`, `1573`,
and again in `stream()`). FastAPI runs these endpoints on one event loop, so a
request that hits an `await` can have that dict overwritten before it resumes:

```
Request A (alice) → current_session_id = {alice, session_a}
                  → await _get_or_create_session(...)   ← yields
Request B (bob)   → current_session_id = {bob, session_b}
Request A resumes → _build_brief reads self.current_session_id → BOB
```

Two consequential readers during a turn:

- **`_build_brief`** stamps the user and session id into the analysis brief. The
  analyser saves the recommendation under them — a cross-user **write**.
- **`analyse_portfolio_document`** builds the upload filename from them — a
  cross-user file **read**.

Reachable without multiple workers; concurrent requests in one process suffice.

**The fix has a precedent in this codebase.** The Stock Analyser keeps its ids in
session state and reads them from `tool_context` in `deliver_report`, which is
per-invocation. Doing the same in the host removes the race.

### Dispatch on a daemon thread

`send_message_background` fires the analysis on a daemon thread, so an in-flight
dispatch dies silently on shutdown. A restart mid-analysis loses the run with no
record it was owed. Redis is already in the stack for async chat tasks.

Splitting delivery out narrows the blast radius but does not close it: once the
analyser has written `priced_report` and saved the recommendation, a crash costs
only the email, and the row is still there to retry from. A crash *before* that
point still loses everything.

### Two agents now call out over A2A

The host keeps `RemoteAgentConnections` because it talks to several agents and
resolves their cards at startup. The analyser calls exactly one downstream
service, so it uses `agent_core/a2a_client.py` instead. The two overlap, and the
host could be moved onto the shared client — that was left alone to avoid
touching the working dispatch path.

### The state mirror can write blanks

`__main__.py:940` mirrors `_load_state()` into the `agent_states` table after
each turn. `_load_state()` returns `_blank_state()` when no in-process snapshot
exists, and the exception path in `stream()` returns without writing one — so a
turn that throws can write blanks over the stored row. The ADK session is
untouched, so nothing is truly lost, but the mirror is legacy and could be
dropped.

### Two dead readers in the host

`host/document_analyzer.py` and `host/pdf_analyzer.py` have no callers left —
`document_analyser_agent/reader.py` replaced both. They still carry uncommitted
local edits, so they were left in place rather than deleted.

---

## 10. File map

### Host Agent

| File | Contains |
|---|---|
| `__main__.py` | FastAPI app, every endpoint, auth, credits, Redis task tracking |
| `host/agent.py` | `HostAgent` — the coordinator, its tools, A2A transport |
| `host/prompts.py` | Coordinator instruction, `REQUIRED_FACTS`, `next_fact`, state brief |
| `host/specialists.py` | `market_researcher` sub-agent and its Perplexity tool |
| `host/tickers.py` | Ticker resolution against the user's market, one structured call |
| `host/remote_agent_connection.py` | A2A connection wrapper |
| `database.py`, `db_utils.py` | SQLAlchemy models and helpers |
| `config.py` | Environment-driven config, local vs production |

### Stock Analyser

| File | Contains |
|---|---|
| `agent.py` | Analyst agent, `capture_market_data`, `deliver_report`, allocation sub-agent |
| `analysis_prompts.py` | Analyst instruction and the allocation policy brief |
| `agent_executor.py` | A2A executor with retry |

### Report Generator

| File | Contains |
|---|---|
| `agent.py` | `load_report`, the narrative sub-agent, `send_report` |
| `report.py` | HTML rendering and the webhook that sends the email |

### Document Analyser

| File | Contains |
|---|---|
| `agent.py` | `read_document`, `record_document_text`, `classify_document`, `extract_document` |
| `doc_types.py` | The type registry — schema, instruction, hint per type |
| `reader.py` | Storage fetch, PDF text layer, vision OCR fallback |

### Shared

| File | Contains |
|---|---|
| `agent_core/models.py` | Model id, generation config, genai client |
| `agent_core/sessions.py` | Postgres-backed ADK session service |
| `agent_core/schemas.py` | All Pydantic response schemas |
| `agent_core/callbacks.py` | Tool and agent tracing |
| `agent_core/a2a_client.py` | Minimal A2A client for agent-to-agent calls |
