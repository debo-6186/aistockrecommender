import yfinance as yf
import pandas_ta as ta
from typing import Annotated
from pydantic import Field
import logging
import json
import webbrowser
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# Set up logger
logger = logging.getLogger("finhub-mcp")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

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

def get_bollinger_bands(symbol: str, period: str = "3mo", interval: str = "1d") -> str:
    """Fetch historical price data for a given stock symbol over a specified period and interval, and calculate Bollinger Bands."""
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval, rounding=True)
    if df.empty:
        return "No data available."
    bb = ta.bbands(df["Close"])
    if bb is not None:
        df = df.join(bb)
    else:
        print("Bollinger Bands could not be calculated (possibly not enough data).")
    return df.to_markdown()

def get_support_resistance(symbol: str, period: str = "3mo", interval: str = "1d", window: int = 20) -> str:
    """Fetch historical price data for a given stock symbol and calculate rolling support and resistance levels."""
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval, rounding=True)
    if df.empty:
        return "No data available."
    df["Support"] = df["Close"].rolling(window=window, min_periods=1).min()
    df["Resistance"] = df["Close"].rolling(window=window, min_periods=1).max()
    return df.to_markdown()

def get_ticker_recommendations(symbol: Annotated[str, Field(description="The stock symbol")]) -> str:
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

def df_to_dict_str_keys(df):
    if df is None:
        return None
    # Convert DataFrame to dict, then ensure all keys are strings
    d = df.to_dict()
    if isinstance(d, dict):
        return {str(k): {str(kk): vv for kk, vv in v.items()} for k, v in d.items()}
    return d

def get_stock_info(symbol: str) -> str:
    """Fetches basic stock information for a given stock symbol."""
    ticker = yf.Ticker(symbol)
    info = ticker.info
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

def get_market_news() -> str:
    """Fetches recent market news articles with title, content, and source details."""
    market = yf.Market(market="US")
    return market.summary

def google_search(query: str) -> list:
    """Return the top 10 Google search result links for the given query as a list of URLs."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
    }
    url = f"https://www.google.com/search?q={query.replace(' ', '+')}"
    response = requests.get(url, headers=headers)
    soup = BeautifulSoup(response.text, "html.parser")
    links = []
    for g in soup.find_all('a'):
        href = g.get('href')
        if href and href.startswith('/url?q='):
            link = href.split('/url?q=')[1].split('&')[0]
            if not link.startswith('http'):  # skip non-http links
                continue
            links.append(link)
            if len(links) == 10:
                break
    return links

def brave_search(query: str, api_key: str, count: int = 10) -> list:
       url = "https://api.search.brave.com/res/v1/web/search"
       headers = {"Accept": "application/json", "X-Subscription-Token": api_key}
       params = {"q": query, "count": count}
       response = requests.get(url, headers=headers, params=params)
       if response.status_code == 200:
           data = response.json()
           return [item["url"] for item in data.get("web", {}).get("results", [])]
       else:
           print("Error:", response.status_code, response.text)
           return []
       
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

def get_stock_price_yfinance(symbol: str) -> str:
    """
    Retrieve stock data including company info, financials, trading metrics and governance data.
    """
    logger.info(f"Fetching stock price and info for symbol: {symbol}")
    ticker = yf.Ticker(symbol)

    # Convert timestamps to human-readable format
    info = ticker.info
    for key, value in info.items():
        if not isinstance(key, str):
            continue

        if key.lower().endswith(("date", "start", "end", "timestamp", "time", "quarter")):
            retries = 0
            while retries < 3:
                try:
                    info[key] = datetime.fromtimestamp(value).strftime("%Y-%m-%d %H:%M:%S")
                    break
                except TypeError as e:
                    logger.warning(f"TypeError converting {key}: {value} (attempt {retries+1}/3): {e}")
                    retries += 1
                    if retries == 3:
                        logger.error(f"Failed to convert {key}: {value} after 3 attempts, skipping.")
                        break
                except Exception as e:
                    logger.error(f"Unable to convert {key}: {value} to datetime, got error: {e}")
                    break

    logger.info(f"Retrieved info for {symbol}: {info}")
    return json.dumps(info, ensure_ascii=False)
       
def main():
    symbol = "MSFT"
    # print(f"Getting price history for {symbol}...")
    # history = get_price_history(symbol)
    # print(history)
    # print(f"Getting recommendations for {symbol}...")
    # recommendations = get_ticker_recommendations(symbol)
    # print(recommendations)
    # stock_info = get_price_history(symbol)
    # logger.info(f"Retrieved stock info for {symbol}: {stock_info}")
    # market_news = get_market_news()
    # logger.info(f"Retrieved market news: {market_news}")
    # api_key = "BSAqoIno8QGsxFve46gkcOVTcPgm4Ch"
    # links = brave_search("list top 10 stocks in technology sector in US stock market", api_key)
    # logger.info(f"Retrieved Brave search links: {links}")
    stock_info = get_stock_info(symbol)
    logger.info(f"Retrieved stock info for {symbol}: {stock_info}")
    # stock_info = get_stock_price_yfinance(symbol)
    # logger.info(f"Retrieved stock info for {symbol}: {stock_info}")

if __name__ == "__main__":
    main()
