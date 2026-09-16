"""
The document types this agent knows how to read.

Adding a type is adding an entry here: a schema saying what the answer looks
like, an instruction saying how to read it, and a hint the classifier uses to
recognise it. Nothing in the agent, the reader or the host needs to change.

The schema is the load-bearing half. A per-type instruction gets better text
out of the model; a per-type schema is what lets the caller use the result
without parsing prose back apart.
"""

from dataclasses import dataclass
from typing import Type

from pydantic import BaseModel

from agent_core.schemas import (
    AnnualReportSummary,
    ContractNote,
    PortfolioExtraction,
)


@dataclass(frozen=True)
class DocType:
    """Everything that differs between one document type and the next."""

    name: str
    schema: Type[BaseModel]
    instruction: str
    hint: str
    # The schema field that says "this really was that kind of document".
    validity_field: str
    summary_fields: tuple[str, ...]


PORTFOLIO_INSTRUCTION = """
You read portfolio statements into structured holdings.

Work out whether the text really is a portfolio or holdings statement, which
market its positions are listed on, and for each position the ticker, company
name, allocation percentage and share count.

Convert company names to tickers. Indian listings keep their exchange suffix
(RELIANCE.NS, TCS.BO); US listings have none (AAPL, VOO). All positions on one
statement belong to one exchange - if you see a genuine mix, say so in `notes`
rather than silently picking one.

Record a share count only where the statement shows one. Never derive it from a
percentage and a total, and never estimate. Every ticker without a share count
goes in `holdings_missing_share_counts`, because those positions cannot be sold
down later without one.

If the text is not a portfolio statement, set `is_portfolio` to false and
explain why in `rejection_reason`.
""".strip()


CONTRACT_NOTE_INSTRUCTION = """
You read broker contract notes - the confirmations issued after trades execute.

For each trade on the note record the ticker, whether it was a buy or a sell,
the quantity, the price per share and the trade date. Indian listings keep
their exchange suffix (RELIANCE.NS, TCS.BO); US listings have none.

A contract note lists executions, not positions. Do not merge two rows for the
same ticker into one - each execution is its own entry, because they may have
filled at different prices.

Record charges only where the note totals them. Never reconstruct a total from
a percentage, and never estimate a price the note does not print.

If the text is not a contract note - a holdings statement, an invoice, a bank
statement - set `is_contract_note` to false and explain why in
`rejection_reason`.
""".strip()


ANNUAL_REPORT_INSTRUCTION = """
You read company annual and quarterly reports, and pull out what would change
an investment view.

Record the company, its ticker if the report names one, the fiscal period, and
the headline figures - revenue, net income, earnings per share - exactly as
reported, with their units ("$4.2 billion", "₹1,240 crore"). Do not convert
currencies and do not rescale figures.

`key_highlights` is for findings that move a view: margin direction, segment
growth or decline, guidance changes, buybacks, major one-offs. Skip the
boilerplate. `stated_risks` is for risks the report itself names, not risks you
infer.

If a figure is not in the text, leave its field empty. An empty field is a
usable answer; an invented one is not.

If the text is not a company financial report, set `is_annual_report` to false
and explain why in `rejection_reason`.
""".strip()


REGISTRY: dict[str, DocType] = {
    "portfolio_statement": DocType(
        name="portfolio_statement",
        schema=PortfolioExtraction,
        instruction=PORTFOLIO_INSTRUCTION,
        hint="a list of held positions with tickers, quantities or allocation percentages",
        validity_field="is_portfolio",
        summary_fields=("detected_market", "holdings", "holdings_missing_share_counts"),
    ),
    "contract_note": DocType(
        name="contract_note",
        schema=ContractNote,
        instruction=CONTRACT_NOTE_INSTRUCTION,
        hint="executed trades for a single day, with buy/sell sides, prices and brokerage charges",
        validity_field="is_contract_note",
        summary_fields=("broker_name", "detected_market", "trades"),
    ),
    "annual_report": DocType(
        name="annual_report",
        schema=AnnualReportSummary,
        instruction=ANNUAL_REPORT_INSTRUCTION,
        hint="a company reporting its own results - revenue, income, EPS, segments, risks",
        validity_field="is_annual_report",
        summary_fields=("company_name", "fiscal_period", "revenue", "net_income"),
    ),
}


def get(document_type: str) -> DocType | None:
    return REGISTRY.get(document_type)


def supported() -> list[str]:
    return list(REGISTRY)


def classifier_hints() -> str:
    """The type menu, rendered for the classification call."""
    return "\n".join(f"- {name}: {spec.hint}" for name, spec in REGISTRY.items())
