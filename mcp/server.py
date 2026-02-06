import os
import json  # This is a built-in module, no need to add to requirements.txt
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
import yfinance as yf
import pandas_ta as ta
from datetime import datetime
import logging
from typing import Annotated
from pydantic import Field
from utils import df_to_dict_str_keys

# Set up logger
logger = logging.getLogger("finhub-mcp")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

# Load environment variables from .env
load_dotenv()

# Initialize FastMCP server
mcp = FastMCP("stock-market")

@mcp.tool()
def get_stock_symbol_lookup(query: str) -> str:
    """
    Stock Symbol Lookup - searches for best-matching symbols based on your query.

    Args:
        query: You can input anything from symbol or security's name e.g. apple

    Returns:
        str: The best matching stock ticker symbol
    """
    try:
        search = yf.Search(query, max_results=1)

        if not search.quotes or len(search.quotes) == 0:
            return f"No symbols found matching '{query}'."

        # Return the best matching symbol (first result)
        return search.quotes[0]['symbol']

    except Exception as e:
        return f"Error looking up symbol: {str(e)}"

@mcp.tool()
def get_stock_news(symbol: Annotated[str, Field(description="The stock symbol")]) -> str:
    """Fetches recent news articles related to a specific stock symbol with title, summary, and publication date."""
    logger.info(f"Fetching news for symbol: {symbol}")
    ticker = yf.Ticker(symbol)
    news = ticker.get_news()
    
    if not news:
        logger.info(f"No news found for {symbol}")
        return f"No news articles found for {symbol}."
    
    # Extract only title, summary, and pubDate from each news item
    simplified_news = []
    for item in news:
        if isinstance(item, dict) and "content" in item:
            content = item["content"]
            simplified_item = {
                "title": content.get("title", "No title"),
                "summary": content.get("summary", "No summary"),
                "pubDate": content.get("pubDate", "No date")
            }
            simplified_news.append(simplified_item)
    
    logger.info(f"Retrieved {len(simplified_news)} news articles for {symbol}: {simplified_news}")
    return json.dumps(simplified_news, indent=2, ensure_ascii=False)

@mcp.tool()
def get_price_history(symbol: str, period: str = "1wk", interval: str = "1d") -> str:
    """Fetch historical price data for a given stock symbol over a specified period and interval, and calculate RSI and MACD."""
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval, rounding=True)
    if df.empty:
        logger.info(f"No price history data available for {symbol}")
        return "No data available."
    # Calculate RSI
    df["RSI"] = ta.rsi(df["Close"])
    # Calculate MACD
    macd = ta.macd(df["Close"])
    if macd is not None:
        df = df.join(macd)
    else:
        logger.warning(f"MACD could not be calculated for {symbol} (possibly not enough data)")
    # Calculate Bollinger Bands
    bb = ta.bbands(df["Close"])
    if bb is not None:
        df = df.join(bb)
    else:
        logger.warning(f"Bollinger Bands could not be calculated for {symbol} (possibly not enough data)")
    # Calculate Support and Resistance
    df["Support"] = df["Close"].rolling(window=20, min_periods=1).min()
    df["Resistance"] = df["Close"].rolling(window=20, min_periods=1).max()
    response = df.to_markdown()
    logger.info(f"Retrieved price history for {symbol} with period={period}, interval={interval}")
    return response

@mcp.tool()
def search(
    query: Annotated[str, Field(description="The search query (ticker symbol or company name)")],
    search_type: Annotated[str, Field(description="Type of search results to retrieve ('all', 'quotes', or 'news')")],
) -> str:
    """Fetches and organizes search results from Yahoo Finance, including stock quotes and news articles."""
    s = yf.Search(query)
    result = None
    match search_type.lower():
        case "all":
            result = s.all
        case "quotes":
            result = s.quotes
        case "news":
            result = s.news
        case _:
            return "Invalid output_type. Use 'all', 'quotes', or 'news'."
    
    logger.info(f"Search results for {query} ({search_type}): {result}")
    return json.dumps(result, ensure_ascii=False)

@mcp.tool()
def get_stock_info(symbol: str) -> str:
    """Fetches basic stock information for a given stock symbol."""
    ticker = yf.Ticker(symbol)
    info = ticker.info

    # If info is empty, try to lookup the correct symbol
    if not info:
        logger.warning(f"No info found for {symbol}, attempting symbol lookup")
        correct_symbol = get_stock_symbol_lookup(symbol)
        if correct_symbol and not correct_symbol.startswith("No symbols") and not correct_symbol.startswith("Error") and not correct_symbol.startswith("Unable"):
            logger.info(f"Found correct symbol: {correct_symbol}")
            ticker = yf.Ticker(correct_symbol)
            info = ticker.info
            symbol = correct_symbol
        else:
            return f"Unable to find valid information for '{symbol}'. Symbol lookup returned: {correct_symbol}"

    is_etf = info.get("quoteType") == "ETF"

    # Only fetch financial statements for non-ETF securities
    balance_sheet = None
    cash_flow = None
    quarterly_income_stmt = None
    analyst_price_targets = None
    financials = None

    if not is_etf:
        try:
            balance_sheet = df_to_dict_str_keys(ticker.balance_sheet) if hasattr(ticker, "balance_sheet") and ticker.balance_sheet is not None else None
        except Exception as e:
            logger.warning(f"Could not fetch balance sheet for {symbol}: {e}")

        try:
            cash_flow = df_to_dict_str_keys(ticker.cashflow) if hasattr(ticker, "cashflow") and ticker.cashflow is not None else None
        except Exception as e:
            logger.warning(f"Could not fetch cash flow for {symbol}: {e}")

        try:
            quarterly_income_stmt = df_to_dict_str_keys(ticker.quarterly_income_stmt) if hasattr(ticker, "quarterly_income_stmt") and ticker.quarterly_income_stmt is not None else None
        except Exception as e:
            logger.warning(f"Could not fetch quarterly income statement for {symbol}: {e}")

        try:
            analyst_price_targets = ticker.analyst_price_targets if hasattr(ticker, "analyst_price_targets") and ticker.analyst_price_targets is not None else None
        except Exception as e:
            logger.warning(f"Could not fetch analyst price targets for {symbol}: {e}")

        try:
            financials = df_to_dict_str_keys(ticker.financials) if hasattr(ticker, "financials") and ticker.financials is not None else None
        except Exception as e:
            logger.warning(f"Could not fetch financials for {symbol}: {e}")

    stock_news = get_stock_news(symbol=symbol)

    if is_etf:
        # ETF-specific formatting
        # Primary ETF Analysis Keys
        etf_analysis = {k: info.get(k) for k in [
            'totalAssets', 'netAssets', 'netExpenseRatio', 'ytdReturn',
            'threeYearAverageReturn', 'fiveYearAverageReturn', 'trailingThreeMonthReturns',
            'beta3Year', 'dividendYield', 'trailingAnnualDividendYield', 'trailingAnnualDividendRate'
        ]}

        # Trading & Valuation Keys
        etf_trading = {k: info.get(k) for k in [
            'regularMarketPrice', 'navPrice', 'volume', 'regularMarketVolume',
            'averageVolume', 'averageVolume10days', 'averageDailyVolume10Day',
            'averageDailyVolume3Month', 'bid', 'ask', 'bidSize', 'askSize'
        ]}

        # Price Movement Keys
        etf_price_movement = {k: info.get(k) for k in [
            'fiftyTwoWeekLow', 'fiftyTwoWeekHigh', 'fiftyTwoWeekRange',
            'fiftyTwoWeekChangePercent', 'fiftyDayAverage', 'twoHundredDayAverage',
            'regularMarketChange', 'regularMarketChangePercent'
        ]}

        # Fund Information Keys
        etf_fund_info = {k: info.get(k) for k in [
            'category', 'fundFamily', 'longBusinessSummary', 'fundInceptionDate',
            'shortName', 'longName', 'symbol'
        ]}

        response = json.dumps({
            "stock_type": "ETF",
            "etf_analysis": etf_analysis,
            "trading_valuation": etf_trading,
            "price_movement": etf_price_movement,
            "fund_information": etf_fund_info,
            "stock_news": stock_news
        }, ensure_ascii=False)

    else:
        # Equity-specific formatting (existing logic)
        # Core Valuation Metrics
        core_valuation = {k: info.get(k) for k in [
            'currentPrice', 'targetMeanPrice', 'targetHighPrice', 'targetLowPrice',
            'marketCap', 'enterpriseValue', 'trailingPE', 'forwardPE', 'priceToBook',
            'priceToSalesTrailing12Months', 'trailingPegRatio'
        ]}

        # Financial Performance
        financial_performance = {k: info.get(k) for k in [
            'totalRevenue', 'netIncomeToCommon', 'grossProfits', 'grossMargins',
            'operatingMargins', 'ebitdaMargins', 'profitMargins', 'earningsGrowth',
            'revenueGrowth', 'returnOnAssets', 'returnOnEquity', 'trailingEps',
            'forwardEps', 'epsCurrentYear'
        ]}

        # Financial Health
        financial_health = {k: info.get(k) for k in [
            'totalCash', 'totalCashPerShare', 'totalDebt', 'debtToEquity',
            'currentRatio', 'quickRatio', 'freeCashflow', 'operatingCashflow'
        ]}

        # Market Data & Trading
        market_data = {k: info.get(k) for k in [
            'volume', 'averageVolume', 'beta', 'fiftyTwoWeekLow', 'fiftyTwoWeekHigh',
            '52WeekChange', 'fiftyDayAverage', 'twoHundredDayAverage',
            'recommendationMean', 'recommendationKey', 'numberOfAnalystOpinions'
        ]}

        # Dividend Information
        dividend_info = {k: info.get(k) for k in [
            'dividendRate', 'dividendYield', 'payoutRatio', 'trailingAnnualDividendRate',
            'exDividendDate'
        ]}

        # Balance Sheet Essentials
        balance_sheet_keys = {}
        if balance_sheet:
            for key in ['Total Assets', 'Stockholders Equity', 'Working Capital',
                       'Cash And Cash Equivalents', 'Total Debt', 'Net PPE']:
                balance_sheet_keys[key] = balance_sheet.get(key)

        # Income Statement Key Items
        income_stmt_keys = {}
        if financials:
            for key in ['Total Revenue', 'Gross Profit', 'Operating Income',
                       'Net Income', 'Cost Of Revenue', 'Research And Development']:
                income_stmt_keys[key] = financials.get(key)

        # Cash Flow Highlights
        cash_flow_keys = {}
        if cash_flow:
            for key in ['Operating Cash Flow', 'Free Cash Flow', 'Capital Expenditure',
                       'Cash Dividends Paid']:
                cash_flow_keys[key] = cash_flow.get(key)

        response = json.dumps({
            "stock_type": "EQUITY",
            "core_valuation_metrics": core_valuation,
            "financial_performance": financial_performance,
            "financial_health": financial_health,
            "market_data_trading": market_data,
            "dividend_information": dividend_info,
            "balance_sheet_essentials": balance_sheet_keys,
            "income_statement_key_items": income_stmt_keys,
            "cash_flow_highlights": cash_flow_keys,
            "analyst_price_targets": analyst_price_targets,
            "stock_news": stock_news
        }, ensure_ascii=False)

    logger.info(f"Retrieved stock info for {symbol}: {response}")
    return response

@mcp.tool()
def get_stock_recommendations(symbol: Annotated[str, Field(description="The stock symbol")]) -> str:
    """Fetches analyst recommendations for a specific stock symbol as a markdown table, or a message if unavailable."""
    ticker = yf.Ticker(symbol)
    recs = ticker.recommendations
    if recs is None or recs.empty:
        logger.info(f"No recommendations found for {symbol}")
        return f"No analyst recommendations available for {symbol}."
    # Optionally limit to the most recent 20 recommendations for brevity
    recs = recs.tail(20)
    logger.info(f"Retrieved recommendations for {symbol}: {recs}")
    return recs.to_markdown()

@mcp.tool()
def get_US_market_news() -> str:
    """Fetches recent market news articles with title, content, and source details."""
    market = yf.Market(market="US")
    return market.summary

# @mcp.tool()
# def get_basic_financials(symbol: str) -> str:
    """
    Get basic financial information for a company.

    Args:
        symbol: The stock symbol to look up (e.g., AAPL for Apple Inc.)

    Returns:
        str: Basic financial metrics in JSON format including P/E ratio, market cap, etc.
    """
    try:
        # Get basic financials from Finnhub
        data = finnhub_client.company_basic_financials(symbol.upper(), 'all')
        
        if not data or "metric" not in data:
            return f"Unable to get financial information for symbol '{symbol}'."
        
        metrics = data["metric"]
        
        # Select the most important metrics
        important_metrics = {
            "symbol": symbol.upper(),
            "company_name": data.get("series", {}).get("name", "Unknown"),
            "market_capitalization": metrics.get("marketCapitalization", None),
            "pe_ratio": metrics.get("peBasicExclExtraTTM", None),
            "pb_ratio": metrics.get("pbQuarterlyTTM", None),
            "dividend_yield": metrics.get("dividendYieldIndicatedAnnual", None),
            "52_week_high": metrics.get("52WeekHigh", None),
            "52_week_low": metrics.get("52WeekLow", None),
            "52_week_change": metrics.get("52WeekPriceReturnDaily", None),
            "beta": metrics.get("beta", None),
            "eps_ttm": metrics.get("epsBasicExclExtraItemsTTM", None),
            "revenue_per_share_ttm": metrics.get("revenuePerShareTTM", None),
            "revenue_growth_ttm": metrics.get("revenueGrowthTTM3Y", None),
            "debt_to_equity": metrics.get("totalDebtEquityQuarterly", None),
            "roa": metrics.get("roaTTM", None),
            "roe": metrics.get("roeTTM", None)
        }
        
        # Return formatted JSON string
        return json.dumps(important_metrics, indent=2)
        
    except Exception as e:
        return f"Error getting financial information: {str(e)}"


# @mcp.tool()
# def get_market_news(category: str = "general", min_id: int = 0) -> str:
    """
    Get the latest market news.

    Args:
        category: News category. Available values: general, forex, crypto, merger.
        min_id: Use this to get only news after this ID.

    Returns:
        str: Latest market news in JSON format with headlines, summaries, and URLs.
    """
    try:
        # Validate category
        valid_categories = ["general", "forex", "crypto", "merger"]
        if category.lower() not in valid_categories:
            return f"Invalid category. Please use one of: {', '.join(valid_categories)}"
        
        # Get market news from Finnhub
        data = finnhub_client.general_news(category.lower(), min_id=min_id)
        
        if not data or len(data) == 0:
            return f"No news available for category '{category}'."
        
        # Format the response
        formatted_data = {
            "category": category.lower(),
            "news_count": len(data),
            "articles": []
        }
        
        # Limit to 10 most recent articles to avoid overwhelming responses
        for item in data[:10]:
            formatted_data["articles"].append({
                "id": item.get("id", 0),
                "headline": item.get("headline", "No headline"),
                "summary": item.get("summary", "No summary available"),
                "source": item.get("source", "Unknown source"),
                "datetime": item.get("datetime", 0),
                "url": item.get("url", ""),
                "related_symbols": item.get("related", [])
            })
        
        # Return formatted JSON string
        return json.dumps(formatted_data, indent=2)
        
    except Exception as e:
        return f"Error getting market news: {str(e)}"


# @mcp.tool()
# def get_company_news(symbol: str, from_date: str, to_date: str) -> str:
    """
    Get news for a specific company over a date range.

    Args:
        symbol: The stock symbol (e.g., AAPL for Apple Inc.)
        from_date: Start date in YYYY-MM-DD format
        to_date: End date in YYYY-MM-DD format

    Returns:
        str: Company-specific news in JSON format with headlines, summaries, and URLs.
    """
    try:
        # Validate date format (YYYY-MM-DD)
        try:
            # Simple validation of date format
            if not (len(from_date) == 10 and len(to_date) == 10):
                return "Date format must be YYYY-MM-DD"

                # Ensure the format has dashes in the right places
            if from_date[4] != '-' or from_date[7] != '-' or to_date[4] != '-' or to_date[7] != '-':
                return "Date format must be YYYY-MM-DD (with dashes)"

        except Exception:
            return "Invalid date format. Please use YYYY-MM-DD format."

            # Get company news from Finnhub - keep the dashes in the dates
        data = finnhub_client.company_news(symbol.upper(), _from=from_date, to=to_date)

        if not data or len(data) == 0:
            return f"No news available for {symbol} between {from_date} and {to_date}."

            # Format the response
        formatted_data = {
            "symbol": symbol.upper(),
            "from_date": from_date,
            "to_date": to_date,
            "news_count": len(data),
            "articles": []
        }

        # Limit to 10 most recent articles to avoid overwhelming responses
        for item in data[:10]:
            formatted_data["articles"].append({
                "headline": item.get("headline", "No headline"),
                "summary": item.get("summary", "No summary available"),
                "source": item.get("source", "Unknown source"),
                "datetime": item.get("datetime", 0),
                "url": item.get("url", ""),
                "related_symbols": item.get("related", [])
            })

            # Return formatted JSON string
        return json.dumps(formatted_data, indent=2)

    except Exception as e:
        return f"Error getting company news: {str(e)}"

# @mcp.prompt("stock_analysis")
# def stock_analysis_prompt():
    """
    Analyze a stock by looking up its basic information, current price, and stock metrics.

    Example usage:
    I want to analyze Apple stock. First, look up the symbol for Apple.
    Then get the current price and basic financial information.
    Finally, summarize whether this looks like a good investment based on different aspects like P/E ratio,
    dividend yield, and recent price movements.
    """
    return """                                                                                                                                             
    I need to analyze a stock for potential investment. Please help me with the following:                                                                     
    
    1. Look up the symbol for {company_name}                                                                                                                   
    2. Get the current price for the best matching symbol                                                                                                      
    3. Retrieve the basic financial information
    4. Get the latest market news
    5. Get the company news for the stock
    6. Based on the P/E ratio, dividend yield, and recent price movements, provide a brief assessment of whether this might be a good investment opportunity   
    
    Please format your analysis in a clear, structured way with sections for each piece of information.                                                        
    """

@mcp.prompt("stock_analysis")
def stock_analysis_prompt():
    """
    Analyze a stock by looking up its stock price, its stock news, its stock price history, and its stock recommendations.

    Example usage:
    I want to analyze Apple stock. First, look up the symbol for Apple.
    Then get the stock info, if `stock_type` is `ETF`, it will only contain `info`, otherwise it will contain `info` along with `balance_sheet`, `cash_flow`, `quarterly_income_stmt`, `financials`, and `analyst_price_targets`.
    """
    return """                                                                                                                                             
    I need to analyze a stock for potential investment. Please help me with the following:                                                                     
    
    1. Look up the symbol for {company_name}
    2. Get the stock info. If `stock_type` is `ETF`, it will only contain `info`, otherwise it will contain `info` along with `balance_sheet`, `cash_flow`, `quarterly_income_stmt`, `financials`, and `analyst_price_targets`.
    3. Based on the stock info, stock price history, stock news, RSI, MACD, Bollinger Bands and stock recommendations, provide a brief assessment of whether this might be a good investment opportunity   
    
    Please format your analysis in a clear, structured way with sections for each piece of information.                                                        
    """

@mcp.prompt("market_overview")
def market_overview_prompt():
    """
    Get a comprehensive market overview including general market news and data for major indices.
    """
    return """
    """

# @mcp.prompt("market_overview")
# def market_overview_prompt():
#     """
#     Get a comprehensive market overview including general market news and data for major indices.

#     Example usage:
#     Give me a market overview with the latest general news and current prices for major indices like
#     AAPL, MSFT, GOOGL, AMZN, and SPY.
#     """
#     return """                                                                                                                                             
#     Please provide a comprehensive market overview with:                                                                                                       
    
#     1. The latest general market news (use the get_market_news tool with category="general")                                                                   
#     2. Current prices for these major stocks and indices:                                                                                                      
#        - Apple (AAPL)                                                                                                                                          
#        - Microsoft (MSFT)                                                                                                                                      
#        - S&P 500 ETF (SPY)                                                                                                                                     
#        - {additional_symbol_1}                                                                                                                                 
#        - {additional_symbol_2}                                                                                                                                 
    
#     3. Summarize the overall market sentiment based on the news and price movements                                                                            
#     """

# @mcp.prompt("company_news_analysis")
# def company_news_analysis_prompt():
    """
    Analyze recent news for a specific company and its potential impact on stock price.

    Example usage:
    Analyze recent news for NVDA from 2023-01-01 to 2023-01-31 and tell me how it might
    affect the stock price.
    """
    return """                                                                                                                                             
    Please analyze recent news for {symbol} from {start_date} to {end_date} and assess its potential impact on the stock price:                                
    
    1. Retrieve company-specific news for the specified period                                                                                                 
    2. Get the current stock price for context                                                                                                                 
    3. Summarize the key news items, focusing on:                                                                                                              
       - Product announcements                                                                                                                                 
       - Financial results                                                                                                                                     
       - Management changes                                                                                                                                    
       - Regulatory issues                                                                                                                                     
       - Competitive developments                                                                                                                              
    4. Provide an assessment of whether these news items are likely to have a positive, negative, or neutral impact on the stock price                         
    """

if __name__ == "__main__":
    # Initialize and run the server                                                                                                                        
    mcp.run(transport='stdio')        
