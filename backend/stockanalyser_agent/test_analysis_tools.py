#!/usr/bin/env python3
"""
Tests for the stock analyser's tools.

These cover the parts the agent is deliberately not allowed to improvise: the
money arithmetic, the capture of market data out of MCP responses, and the
recording of the brief. The agent's routing between tools is not asserted here
- that is the model's job, and pinning it down would defeat the point.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("GOOGLE_API_KEY", "test-key")

import agent as analyser


class FakeToolContext:
    """Stands in for ADK's ToolContext, which is just a state carrier here."""

    def __init__(self, state=None):
        self.state = state or {}


def test_parse_money():
    cases = {
        "$2,500": 2500.0,
        "$2500": 2500.0,
        "₹1,00,000": 100000.0,
        "Rs 1500.50": 1500.5,
        "$0": 0.0,
        "": 0.0,
        None: 0.0,
    }
    for raw, expected in cases.items():
        actual = analyser._parse_money(raw)
        assert actual == expected, f"{raw!r} parsed as {actual}, expected {expected}"


def test_record_analysis_context_flags_a_broken_brief():
    ctx = FakeToolContext()
    result = analyser.record_analysis_context(
        user_id="u1",
        session_id="s1",
        email="not-an-email",
        market="india",
        investment_amount=0,
        strategy="Long term",
        portfolio_context="",
        tool_context=ctx,
    )
    assert result["status"] == "incomplete_brief"
    assert len(result["problems"]) == 2
    # The market is still normalised so the rest of the run stays coherent.
    assert ctx.state["market"] == "INDIA"
    assert ctx.state["currency_symbol"] == "₹"


def test_record_stock_list_deduplicates_across_both_lists():
    ctx = FakeToolContext()
    result = analyser.record_stock_list(
        existing_stocks=["aapl", " googl "],
        new_stocks=["AAPL", "NVDA"],
        tool_context=ctx,
    )
    assert result["tickers_to_research"] == ["AAPL", "GOOGL", "NVDA"]


def test_capture_market_data_extracts_the_price_and_shrinks_the_payload():
    class FakeTool:
        name = "get_stock_info"

    payload = {
        "stock_type": "EQUITY",
        "core_valuation_metrics": {"currentPrice": 250.5, "trailingPE": 31.2},
        "padding": "x" * 5000,
    }
    ctx = FakeToolContext()
    result = analyser.capture_market_data(
        FakeTool(), {"symbol": "aapl"}, ctx, {"result": json.dumps(payload)}
    )

    assert ctx.state["prices"]["AAPL"] == 250.5
    assert "AAPL" in ctx.state["research"]
    # The analyst sees a digest, not the whole document.
    assert len(result["digest"]) < result["bytes_recorded"]


def test_capture_market_data_reads_etf_prices_from_their_own_field():
    class FakeTool:
        name = "get_stock_info"

    payload = {"stock_type": "ETF", "trading_valuation": {"regularMarketPrice": 512.75}}
    ctx = FakeToolContext()
    analyser.capture_market_data(FakeTool(), {"symbol": "VOO"}, ctx, json.dumps(payload))
    assert ctx.state["prices"]["VOO"] == 512.75


def test_deliver_report_prices_from_live_data_only():
    ctx = FakeToolContext(
        {
            "currency_symbol": "$",
            "market": "US",
            "session_id": "",
            "user_id": "",
            "email": "",
            "investment_amount": 10000.0,
            "portfolio_context": "",
            "prices": {"AAPL": 250.0, "TSLA": 400.0},
            "allocation_report": {
                "individual_stock_recommendations": [
                    {"ticker": "AAPL", "recommendation": "BUY", "investment_amount": "$2,500"},
                    {"ticker": "TSLA", "recommendation": "SELL", "investment_amount": "$0"},
                    {"ticker": "MSFT", "recommendation": "BUY", "investment_amount": "$1,000"},
                    {"ticker": "GOOGL", "recommendation": "HOLD", "investment_amount": "$0"},
                ],
                "allocation_breakdown": [
                    {"ticker": "AAPL", "percentage": "25%", "investment_amount": "$2,500"}
                ],
            },
        }
    )

    result = analyser.deliver_report(ctx)
    assert result["status"] == "ok"

    lines = {
        line["ticker"]: line
        for line in ctx.state["allocation_report"]["individual_stock_recommendations"]
    }
    assert lines["AAPL"]["number_of_shares"] == "10.0000 shares"
    assert lines["AAPL"]["entry_price"] == "$250.00"
    # A SELL is priced but not sized here - the model sizes it from share counts.
    assert "number_of_shares" not in lines["TSLA"]
    # A stock with no live price is reported, never guessed at.
    assert result["could_not_price"] == ["MSFT"]
    assert "number_of_shares" not in lines["MSFT"]
    # HOLD is left alone entirely.
    assert "entry_price" not in lines["GOOGL"]


def test_deliver_report_refuses_without_an_allocation():
    result = analyser.deliver_report(FakeToolContext({}))
    assert result["status"] == "error"


def main():
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_")]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"PASS  {test.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL  {test.__name__}: {exc}")
        except Exception as exc:
            failures += 1
            print(f"ERROR {test.__name__}: {type(exc).__name__}: {exc}")

    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
