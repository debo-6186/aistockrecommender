# AI Stock Recommender

A multi-agent AI system for stock analysis and portfolio recommendations. The platform uses Google's Agent Development Kit (ADK) with the A2A (Agent-to-Agent) protocol, where a Host Agent orchestrates specialized sub-agents to provide stock analysis, portfolio report analysis, and investment recommendations.

Every agent is model-driven rather than script-driven: each is given a goal, a set of tools and a live view of what it already knows, and decides for itself what to do next. Conversation history and collected facts live in ADK session state, persisted to PostgreSQL. See [Agent Design](#agent-design) for the shape of that.

## Components

| Component | Tech Stack | Port | Purpose |
|---|---|---|---|
| **Frontend** | React 19, TypeScript, Tailwind CSS, Firebase Auth | 3000 | User interface with chat, auth, profile, and portfolio views |
| **Host Agent** | FastAPI, Google ADK, A2A SDK, SQLAlchemy | 10001 | Orchestrates agents, serves REST API, manages sessions |
| **Stock Analyser Agent** | Google ADK, A2A SDK, yfinance, Perplexity AI | 10002 | Analyzes stocks, fetches market data, prices and saves the allocation |
| **Report Generator Agent** | Google ADK, A2A SDK | 10004 | Writes the covering note for a finished allocation and emails it |
| **Document Analyser Agent** | Google ADK, A2A SDK, PyMuPDF, Gemini Vision | 10003 | Reads uploaded documents of any supported type - OCR plus schema-validated extraction |
| **MCP Server** | FastMCP, yfinance, pandas_ta | stdio | Provides stock data tools (prices, news, technicals) to agents |
| **PostgreSQL** | PostgreSQL 15 | 5432 | Users, sessions, messages, recommendations |
| **Redis** | Redis | 6379 | Async task tracking for long-running agent operations |

## Prerequisites

- **Python** >= 3.12
- **Node.js** >= 18
- **Docker & Docker Compose** (for PostgreSQL)
- **Redis** (local install or Docker)
- **Google API Key** (Gemini API for ADK agents)
- **Firebase Project** (for authentication)

---

## 1. Database Setup

Start PostgreSQL via Docker Compose:

```bash
cd backend
docker-compose up -d
```

This starts a PostgreSQL 15 instance with:
- **Database:** `finance_a2a`
- **User:** `postgres`
- **Password:** `password`
- **Port:** `5432`

The `init.sql` script runs automatically and creates: `users`, `conversation_sessions`, `conversation_messages`, and `agent_states` tables.

### Apply Migrations (if needed)

```bash
cd backend/host_agent
python apply_migration.py
```

---

## 2. MCP Server Setup

The MCP Server provides stock market data tools to the agents via the [Model Context Protocol](https://modelcontextprotocol.io/). It runs as a **stdio subprocess** spawned by the Host Agent and Stock Analyser Agent -- it does not need to be started separately.

### Environment Variables

```bash
cd mcp
cp .env.example .env
```

| Variable | Description |
|---|---|
| `FINNHUB_API_KEY` | Finnhub API key (optional, currently unused -- data comes via yfinance) |
| `ANTHROPIC_API_KEY` | Only needed if running the standalone MCP client test |

### MCP Tools Exposed

| Tool | Description |
|---|---|
| `get_stock_symbol_lookup(query)` | Searches for best-matching stock ticker symbol |
| `get_stock_news(symbol)` | Fetches recent news articles for a stock |
| `get_price_history(symbol, period, interval)` | Historical prices with RSI, MACD, Bollinger Bands |
| `search(query, search_type)` | Yahoo Finance search for quotes or news |
| `get_stock_info(symbol)` | Comprehensive stock info (valuations, financials, balance sheet) |
| `get_stock_recommendations(symbol)` | Analyst recommendations for a stock |
| `get_US_market_news()` | Latest US market news summary |

### MCP Prompts

| Prompt | Description |
|---|---|
| `stock_analysis` | Full stock analysis workflow (symbol lookup, info, technicals, recommendation) |
| `market_overview` | Comprehensive market overview |

### How Agents Call MCP

Both the **Host Agent** and **Stock Analyser Agent** spawn the MCP server as a subprocess using Google ADK's `MCPToolset` with `StdioConnectionParams`:

```python
from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset, StdioConnectionParams
from mcp import StdioServerParameters

connection_params = StdioConnectionParams(
    server_params=StdioServerParameters(
        command=sys.executable,          # current Python interpreter
        args=["/path/to/mcp/server.py"], # path to MCP server script
        env=mcp_env,
    )
)
stock_mcp_tool = MCPToolset(connection_params=connection_params)
```

The `MCP_DIRECTORY` config variable (in Host Agent and Stock Analyser Agent) points to the `mcp/` folder. The Host Agent uses MCP tools directly for portfolio performance price lookups, while the Stock Analyser Agent uses them within its ADK agent for comprehensive stock analysis.

---

## 3. Backend Setup

### 3a. Host Agent (port 10001)

The central FastAPI server that the frontend talks to. It orchestrates the other agents via the A2A protocol.

```bash
cd backend/host_agent

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r ../requirements.txt
pip install google-adk a2a-sdk python-dotenv uvicorn firebase-admin \
            sqlalchemy psycopg2-binary redis slowapi httpx nest_asyncio \
            boto3 PyMuPDF requests

# Configure environment
cp env.example .env
# Edit .env with your values (see table below)

# Run
python __main__.py
```

#### Host Agent Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GOOGLE_API_KEY` | Yes | -- | Google Gemini API key |
| `GEMINI_MODEL` | No | `gemini-3.7-flash` | Model every agent runs on |
| `GEMINI_THINKING_BUDGET` | No | (unset) | Thinking token budget. Left unset, no thinking config is sent |
| `DATABASE_URL` | Yes | `postgresql://postgres:password@localhost:5432/finance_a2a` | PostgreSQL connection string. Also backs ADK session state |
| `FIREBASE_PROJECT_ID` | Yes | -- | Firebase project ID for auth verification |
| `FIREBASE_SERVICE_ACCOUNT_PATH` | Yes | -- | Path to Firebase service account JSON |
| `HOST_AGENT_PORT` | No | `10001` | Port for the Host Agent API |
| `STOCK_ANALYSER_AGENT_URL` | No | `http://localhost:10002` | Stock Analyser Agent URL |
| `DOCUMENT_ANALYSER_AGENT_URL` | No | `http://localhost:10003` | Document Analyser Agent URL (falls back to `STOCK_REPORT_ANALYSER_AGENT_URL`) |
| `MCP_DIRECTORY` | No | (local path) | Path to the `mcp/` directory |
| `STOCK_REPORT_GENERATOR_AGENT_URL` | No | `http://localhost:10004` | Report Generator URL (set on the Stock Analyser) |
| `REDIS_URL` | No | `redis://localhost:6379` | Redis URL for async task tracking |
| `ENVIRONMENT` | No | `local` | `local` or `production` |

#### Key API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/login` | Firebase ID token login, returns/creates user |
| `POST` | `/api/chats/init` | Initialize a new chat session |
| `POST` | `/api/chats` | Send a message and get a response |
| `POST` | `/api/chats/stream` | Send a message with streaming response |
| `POST` | `/api/chats/async` | Submit a message for async processing |
| `GET` | `/api/chats/tasks/{task_id}` | Poll async task status |
| `GET` | `/api/profile` | Get current user profile |
| `PUT` | `/api/users/{user_id}/profile` | Update user profile |
| `GET` | `/api/users/{user_id}/statistics` | Get user usage statistics |
| `GET` | `/api/sessions/{session_id}/messages` | Get chat history for a session |
| `GET` | `/api/portfolio-performance/{session_id}` | Get portfolio performance data |
| `GET` | `/api/latest-portfolio-performance/{user_id}` | Latest portfolio performance for a user |
| `GET` | `/api/user-recommendations/{user_id}` | Get all stock recommendations for a user |
| `GET` | `/agents/status` | Check status of connected remote agents |
| `GET` | `/health` | Health check |

---

### 3b. Stock Analyser Agent (port 10002)

Runs as a standalone A2A-compatible agent that performs stock analysis using Google ADK + MCP tools.

```bash
cd backend/stockanalyser_agent

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies (uses pyproject.toml)
pip install -e .

# Configure environment
cp .env.example .env
# Edit .env with your GOOGLE_API_KEY and PERPLEXITY_API_KEY

# Run
python __main__.py
```

#### Stock Analyser Agent Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_API_KEY` | Yes | Google Gemini API key |
| `PERPLEXITY_API_KEY` | Yes | Perplexity AI API key for research queries |
| `GOOGLE_GENAI_USE_VERTEXAI` | No | Set to `TRUE` to use Vertex AI instead of API key |

The agent starts on **port 10002** and exposes the A2A protocol endpoint. It registers with the skill `stock_analyse` -- "Do a detailed analysis of a stock ticker. Give recommendations for buying or selling."

---

### 3c. Document Analyser Agent (port 10003)

Reads every uploaded document the product accepts. One agent handles all types;
what differs per type is an entry in `doc_types.py`, not a code path.

```bash
cd backend/document_analyser_agent

python -m venv .venv
source .venv/bin/activate
pip install -e .

# Create a .env file with GOOGLE_API_KEY and DATABASE_URL
python __main__.py
```

The agent starts on **port 10003** with the skill `document_analyse`.

#### Supported document types

| Type | Schema | What it extracts |
|---|---|---|
| `portfolio_statement` | `PortfolioExtraction` | Holdings, tickers, allocations, share counts, and which positions lack a count |
| `contract_note` | `ContractNote` | Individual executions with side, quantity, price and date, plus total charges |
| `annual_report` | `AnnualReportSummary` | Company, period, revenue, net income, EPS, highlights and stated risks |

**Adding a type** means adding a Pydantic schema to `agent_core/schemas.py` and a
`DocType` entry to `document_analyser_agent/doc_types.py` - a schema, an
extraction instruction, and a hint the classifier recognises it by. The agent,
the reader and the host need no changes.

#### How a document is read

One agent does both halves - getting text out of the file, and making sense of
that text. The route through the first half is chosen from the file's contents,
not its extension:

1. `fetch_upload` finds the bytes in local storage or S3.
2. A PDF is opened and its text layer read. If that yields under 120 characters
   the file is treated as a scan: pages are rasterised at 2x and transcribed by
   Gemini Vision.
3. An image goes straight to Gemini Vision.
4. `classify_document` establishes the type, `extract_document` extracts it
   against that type's schema.

Swapping Gemini Vision for another OCR backend is a change behind
`reader.py` - the agent, the registry and the host do not notice.

#### How the result gets back

A2A carries text, and asking a model to echo a long holdings list back as JSON
invites truncation. So the structured extraction is written to the
`agent_states` table under `document_analyser`, keyed by session, and the host
reads it from there after the call returns. The A2A reply itself is prose.

### 3d. Report Generator Agent (port 10004)

Turns a finished allocation into a report someone will read, and sends it.

```bash
cd backend/stockreport_generator_agent

python -m venv .venv
source .venv/bin/activate
pip install -e .

# Create a .env with GOOGLE_API_KEY, DATABASE_URL,
# ACTIVEPIECES_USERNAME and ACTIVEPIECES_PASSWORD
python __main__.py
```

Starts on **port 10004** with the skill `generate_stock_report`.

The Stock Analyser calls it once the allocation is priced and saved. The report
itself travels through the `agent_states` table under `priced_report`; the A2A
message carries only the session id.

**Why it is separate.** Analysis and delivery fail for different reasons and
should not fail together. By the time this agent runs, the recommendation is
already in the database — so a webhook outage costs the email, not the analysis.

---

## 4. Frontend Setup

The frontend is a React + TypeScript app with Firebase Authentication and Tailwind CSS.

```bash
cd frontend

# Install dependencies
npm install

# Configure environment
cp env.example .env
# Edit .env with your Firebase config and API URL

# Run development server
npm start
```

The app starts on **http://localhost:3000**.

#### Frontend Environment Variables

| Variable | Required | Description |
|---|---|---|
| `REACT_APP_API_BASE_URL` | Yes | Host Agent API URL (default: `http://localhost:10001/api`) |
| `REACT_APP_FIREBASE_API_KEY` | Yes | Firebase Web API key |
| `REACT_APP_FIREBASE_AUTH_DOMAIN` | Yes | Firebase auth domain |
| `REACT_APP_FIREBASE_PROJECT_ID` | Yes | Firebase project ID |
| `REACT_APP_FIREBASE_STORAGE_BUCKET` | Yes | Firebase storage bucket |
| `REACT_APP_FIREBASE_MESSAGING_SENDER_ID` | Yes | Firebase messaging sender ID |
| `REACT_APP_FIREBASE_APP_ID` | Yes | Firebase app ID |

### Firebase Setup

1. Create a Firebase project at [Firebase Console](https://console.firebase.google.com/)
2. Enable **Email/Password** and **Google** sign-in providers under Authentication
3. Get the web app config and fill in the frontend `.env`
4. Download a service account JSON key and set `FIREBASE_SERVICE_ACCOUNT_PATH` in the Host Agent `.env`

---

## 5. Start Everything (Local Development)

Start services in this order:

```bash
# Terminal 1 - Database
cd backend && docker-compose up -d

# Terminal 2 - Redis (if not using Docker)
redis-server

# Terminal 3 - Stock Analyser Agent
cd backend/stockanalyser_agent && source .venv/bin/activate && python __main__.py

# Terminal 4 - Document Analyser Agent
cd backend/document_analyser_agent && source .venv/bin/activate && python __main__.py

# Terminal 5 - Report Generator Agent
cd backend/stockreport_generator_agent && source .venv/bin/activate && python __main__.py

# Terminal 6 - Host Agent (start after remote agents are up)
cd backend/host_agent && source .venv/bin/activate && python __main__.py

# Terminal 7 - Frontend
cd frontend && npm start
```

### Verify

- Frontend: http://localhost:3000
- Host Agent API: http://localhost:10001/health
- Stock Analyser Agent: http://localhost:10002/health
- Document Analyser Agent: http://localhost:10003/.well-known/agent-card.json
- Report Generator Agent: http://localhost:10004/health
- Agent connectivity: http://localhost:10001/agents/status

---

## Agent Communication Flow

1. Frontend sends a chat message with Firebase auth token to Host Agent (`POST /api/chats`)
2. Host Agent validates the token, manages the session in PostgreSQL
3. Based on user intent, Host Agent delegates to the appropriate sub-agent via the A2A protocol
4. Sub-agents use MCP tools (stock data via yfinance) and Google Gemini (LLM reasoning) to generate analysis
5. Results flow back through A2A to Host Agent, which persists them to the database and returns the response to the frontend
6. For portfolio performance tracking, Host Agent calls MCP tools directly to fetch current stock prices

---

## Agent Design

The agents are given goals and constraints, not procedures. There is no scripted
step order anywhere in the backend; what each agent does next is the model's
decision, bounded by what its tools will let it do.

### Shared foundations (`backend/agent_core/`)

| Module | Purpose |
|---|---|
| `models.py` | The one place the Gemini model id and generation config are decided |
| `sessions.py` | PostgreSQL-backed ADK session service, shared by all three agents |
| `schemas.py` | Pydantic response schemas, so structured model output is valid by construction |
| `callbacks.py` | Tool and agent tracing applied uniformly across agents |

### Host Agent - the coordinator

A conversational agent that collects what an analysis needs: market, holdings,
share counts, budget, strategy and an email address. Its instruction states the
objective and the rules, and ends with a live fact sheet rendered from session
state, so the model can see on every turn what is already settled and never
re-asks. It chooses the order of questions, takes facts the user volunteers out
of order, and groups questions when that saves a round trip.

Dispatch is an explicit tool, `request_full_analysis`. It checks that the brief
is complete and, when it is not, tells the agent exactly what is missing rather
than failing quietly. Providing an email address does not by itself start an
analysis.

### Report Generator Agent - the writer

Receives a session id once the allocation is priced and saved, collects the
report from Postgres, and writes the covering note that goes above the tables -
what was analysed, what the allocation does, and what the investor should know
before acting. The note is produced by a sub-agent with a Pydantic output
schema; rendering and delivery are plain Python.

It is a separate service because analysis and delivery fail for different
reasons. The recommendation is saved before this agent is called, so a delivery
outage never costs the analysis.

### Stock Analyser Agent - the analyst

Receives a brief over A2A, records it, then researches the stocks using the full
MCP toolset - quotes, news, price history and analyst consensus - deciding for
itself which calls are worth making for which stock. An `after_tool_callback`
captures every market data payload into session state and hands the model back a
digest, so the research accumulates without flooding the context.

The allocation itself is produced by a specialist sub-agent with a Pydantic
output schema, invoked as a tool. Money arithmetic - share counts from live
prices - is plain Python in `deliver_report`, never the model's job. That tool
prices the report, saves it, and hands it to the Report Generator; it does not
send anything itself.

### Document Analyser Agent - the reader

Locates an uploaded file, gets text out of it - by text layer where there is
one, by vision OCR where there is not - and extracts it against the schema for
its type. One agent covers every document type because the pipeline is
identical and only the schema differs; a new type is a registry entry in
`doc_types.py`.

The structured result travels back to the coordinator through Postgres rather
than through the A2A reply, so nothing depends on a model echoing a long
extraction accurately.

### How question order is decided

The coordinator does not choose what to ask. `next_fact` in
`host_agent/host/prompts.py` walks a fixed priority order - market, holdings,
budget, strategy, email - and returns the first one session state does not yet
hold. That becomes a `NEXT:` directive in the instruction, rebuilt every turn.

The order is fixed, so the conversation is predictable and testable. The
skipping is what keeps it from feeling like a form: a user who opens with *"I
hold 50 AAPL and 30 MSFT, US market, $10k to invest"* has four facts recorded
in one turn and is asked about strategy next, not marched through questions
they already answered.

The model still chooses the wording, still handles whatever the user actually
says, and still takes facts out of order. It just does not decide which gap to
close next.
