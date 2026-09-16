"""
Structured output contracts shared by the agents.

These Pydantic models are handed to Gemini as response schemas, so the model
returns parseable JSON by construction. That removes the markdown-fence
stripping, the "did it include the required keys" checks and the retry-on-bad-
JSON loops that used to guard every generation call.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

Recommendation = Literal["BUY", "HOLD", "SELL"]
Conviction = Literal["HIGH", "MEDIUM", "LOW", "N/A"]


class Holding(BaseModel):
    """A single position read out of a portfolio statement or free text."""

    ticker: str = Field(description="Uppercase ticker, with .NS/.BO suffix for Indian listings")
    company_name: str = Field(default="", description="Company name as printed in the statement")
    allocation_percentage: Optional[float] = Field(
        default=None, description="Share of the portfolio, 0-100, if the statement shows it"
    )
    shares: Optional[float] = Field(
        default=None, description="Number of shares held, if the statement shows it"
    )


class PortfolioExtraction(BaseModel):
    """Everything the intake step can learn from a statement."""

    is_portfolio: bool = Field(
        description="False when the document or text is not a portfolio statement at all"
    )
    rejection_reason: str = Field(
        default="", description="User-facing explanation when is_portfolio is False"
    )
    detected_market: Literal["US", "INDIA", "MIXED", "UNKNOWN"] = Field(
        default="UNKNOWN", description="Market the holdings are listed on"
    )
    holdings: List[Holding] = Field(default_factory=list)
    holdings_missing_share_counts: List[str] = Field(
        default_factory=list,
        description="Tickers with no share count - these cannot receive SELL advice",
    )
    notes: str = Field(default="", description="Anything the analyst should know")


class TickerResolution(BaseModel):
    """Result of turning user-typed names into exchange-correct tickers."""

    resolved: List[str] = Field(
        default_factory=list, description="Tickers that belong to the requested market"
    )
    rejected: List[str] = Field(
        default_factory=list, description="Inputs that belong to a different market or are unknown"
    )
    explanation: str = Field(
        default="", description="Short user-facing note about anything rejected"
    )


class AllocationLine(BaseModel):
    """One row of the budget split."""

    ticker: str
    percentage: str = Field(description="e.g. '25%'")
    investment_amount: str = Field(description="Currency-prefixed, e.g. '$2500'")
    number_of_shares: str = Field(
        default="", description="Filled in deterministically after the fact - leave empty"
    )


class StockRecommendation(BaseModel):
    """A per-stock verdict with its reasoning."""

    ticker: str
    recommendation: Recommendation
    conviction_level: Conviction = "N/A"
    investment_amount: str = Field(
        description="Currency-prefixed. Non-zero for BUY, zero for HOLD and SELL"
    )
    number_of_shares: str = Field(
        default="", description="Filled in deterministically after the fact - leave empty"
    )
    shares_to_sell: str = Field(
        default="", description="SELL only: 'ALL (N shares)' or 'PARTIAL: N shares'"
    )
    key_metrics: str = Field(
        default="", description="Current P/E, target upside, analyst rating, revenue growth"
    )
    reasoning: str = Field(description="Two or three sentences justifying the call")


class PortfolioRecommendation(BaseModel):
    """The complete allocation report emailed to the user."""

    allocation_breakdown: List[AllocationLine] = Field(default_factory=list)
    individual_stock_recommendations: List[StockRecommendation] = Field(default_factory=list)
    risk_warnings: List[str] = Field(default_factory=list)
    strategy_alignment: str = Field(
        default="", description="How this report follows the user's stated strategy"
    )
    cash_reserve_recommendation: str = Field(
        default="", description="Set when no stock qualified for a BUY"
    )


# ----------------------------------------------------------------------
# Document analysis
#
# One agent reads every kind of document the product accepts. What differs
# per type is the schema its text is extracted against, so the schemas live
# together here and the registry in document_analyser_agent/doc_types.py
# pairs each one with its instruction.
# ----------------------------------------------------------------------

DocumentType = Literal[
    "portfolio_statement",
    "contract_note",
    "annual_report",
    "unknown",
]


class DocumentClassification(BaseModel):
    """Which of the supported document types a piece of text is."""

    document_type: DocumentType = Field(
        description="The supported type this document matches, or 'unknown'"
    )
    confidence: Literal["HIGH", "MEDIUM", "LOW"] = "MEDIUM"
    reasoning: str = Field(
        default="", description="One sentence on what in the text decided it"
    )


class Trade(BaseModel):
    """A single executed trade on a contract note."""

    ticker: str = Field(description="Uppercase ticker, with .NS/.BO for Indian listings")
    side: Literal["BUY", "SELL"]
    quantity: Optional[float] = Field(default=None, description="Shares traded")
    price: Optional[float] = Field(default=None, description="Price per share")
    trade_date: str = Field(default="", description="As printed, ISO format where possible")


class ContractNote(BaseModel):
    """A broker's confirmation of trades executed on one day."""

    is_contract_note: bool = Field(
        description="False when the document is not a contract note at all"
    )
    rejection_reason: str = Field(default="", description="User-facing reason when false")
    broker_name: str = Field(default="")
    detected_market: Literal["US", "INDIA", "MIXED", "UNKNOWN"] = "UNKNOWN"
    trades: List[Trade] = Field(default_factory=list)
    total_charges: Optional[float] = Field(
        default=None, description="Brokerage, taxes and fees combined, if shown"
    )
    notes: str = Field(default="")


class AnnualReportSummary(BaseModel):
    """The figures worth carrying forward from an annual or quarterly report."""

    is_annual_report: bool = Field(
        description="False when the document is not a company financial report"
    )
    rejection_reason: str = Field(default="", description="User-facing reason when false")
    company_name: str = Field(default="")
    ticker: str = Field(default="", description="Ticker if the report names one")
    fiscal_period: str = Field(default="", description="e.g. 'FY2025' or 'Q3 2025'")
    revenue: str = Field(default="", description="As reported, with its unit")
    net_income: str = Field(default="", description="As reported, with its unit")
    earnings_per_share: str = Field(default="")
    key_highlights: List[str] = Field(
        default_factory=list, description="Findings that would move an investment view"
    )
    stated_risks: List[str] = Field(default_factory=list)
    notes: str = Field(default="")


class ReportNarrative(BaseModel):
    """The human-readable framing wrapped around a finished allocation.

    The numbers are already settled by the time this is written - this is the
    covering note that tells the investor what the report says and why, in
    their own terms rather than as a table.
    """

    subject_line: str = Field(
        description="Email subject line, specific to this report - never a generic label"
    )
    headline: str = Field(
        description="One sentence stating what the report recommends overall"
    )
    summary: str = Field(
        description=(
            "Two or three short paragraphs: what was analysed, what the allocation "
            "does, and how it follows the investor's stated strategy"
        )
    )
    what_changed: List[str] = Field(
        default_factory=list,
        description="The decisions that matter most, one line each, most significant first",
    )
    caveats: List[str] = Field(
        default_factory=list,
        description="What the investor should know before acting - stale data, positions that could not be priced, missing share counts",
    )
