"""
Report rendering and delivery.

Turning the structured recommendation into an email and posting it to the
delivery webhook is presentation and I/O, not reasoning, so it stays as plain
Python that the agent calls once it decides the report is ready.
"""

import base64
import json
import os
from datetime import datetime
from typing import Optional

import requests

from logger import get_logger

logger = get_logger(__name__)


def render_report_html(text: str) -> str:
    """
    Converts portfolio analysis JSON to HTML email-friendly format.
    Parses JSON format and applies proper HTML styling with color coding.

    Args:
        text: The portfolio analysis in JSON format

    Returns:
        HTML formatted string suitable for email body
    """
    try:
        # Parse JSON input
        data = json.loads(text)

        html_parts = []

        # Start HTML with basic styling
        html_parts.append('''<html>
<head>
<style>
body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 900px; margin: 0 auto; padding: 20px; background-color: #f5f5f5; }
h1 { color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; font-size: 24px; margin-top: 25px; }
h2 { color: #34495e; margin-top: 30px; font-size: 20px; }
h3 { color: #7f8c8d; margin-top: 20px; font-size: 16px; font-weight: bold; }
.allocation { background-color: #ecf0f1; padding: 15px; border-radius: 5px; margin: 15px 0; }
.stock-card { background-color: #ffffff; border-left: 6px solid #3498db; padding: 15px 20px; margin: 15px 0; border-radius: 5px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
.stock-card p { margin: 8px 0; line-height: 1.5; }
.buy { border-left-color: #27ae60; background-color: #f0fcf4; }
.hold { border-left-color: #f39c12; background-color: #fef9f0; }
.sell { border-left-color: #e74c3c; background-color: #fef5f5; }
.ticker { font-weight: bold; font-size: 18px; color: #2c3e50; }
.recommendation { font-weight: bold; padding: 5px 12px; border-radius: 4px; display: inline-block; font-size: 14px; letter-spacing: 0.5px; }
.rec-buy { background-color: #27ae60; color: white; }
.rec-hold { background-color: #f39c12; color: white; }
.rec-sell { background-color: #e74c3c; color: white; }
ul { margin: 10px 0; }
li { margin: 8px 0; }
.warning { background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; margin: 15px 0; }
.summary { background-color: #ffffff; border-left: 6px solid #2c3e50; padding: 18px 22px; margin: 0 0 24px 0; border-radius: 5px; }
.summary .headline { font-size: 17px; font-weight: bold; color: #2c3e50; margin: 0 0 12px 0; }
.summary p { margin: 10px 0; }
.changes { margin: 14px 0 0 0; padding-left: 20px; }
.changes li { margin: 6px 0; }
strong { color: #2c3e50; }
</style>
</head>
<body>''')

        # Add Market Info header if available
        market_preference = data.get('market_preference', 'US')
        currency_symbol = data.get('currency_symbol', '$')
        market_name = 'India (NSE/BSE)' if market_preference == 'INDIA' else 'US (NYSE/NASDAQ)'
        currency_name = 'Indian Rupees (INR)' if market_preference == 'INDIA' else 'US Dollars (USD)'
        html_parts.append(f'<p style="color: #7f8c8d; font-size: 14px; margin-bottom: 20px;"><strong>Market:</strong> {market_name} | <strong>Currency:</strong> {currency_name}</p>')

        # Covering note, when the report generator wrote one. It goes above the
        # numbers because that is where a reader starts.
        narrative = data.get('narrative') or {}
        if narrative:
            html_parts.append('<div class="summary">')
            if narrative.get('headline'):
                html_parts.append(f'<p class="headline">{narrative["headline"]}</p>')
            for paragraph in (narrative.get('summary') or '').split('\n'):
                if paragraph.strip():
                    html_parts.append(f'<p>{paragraph.strip()}</p>')
            if narrative.get('what_changed'):
                html_parts.append('<ul class="changes">')
                for line in narrative['what_changed']:
                    html_parts.append(f'<li>{line}</li>')
                html_parts.append('</ul>')
            html_parts.append('</div>')

            if narrative.get('caveats'):
                html_parts.append('<div class="warning">')
                html_parts.append('<strong>Before you act on this</strong>')
                html_parts.append('<ul>')
                for caveat in narrative['caveats']:
                    html_parts.append(f'<li>{caveat}</li>')
                html_parts.append('</ul>')
                html_parts.append('</div>')

        # Add Allocation Breakdown section
        if 'allocation_breakdown' in data and data['allocation_breakdown']:
            html_parts.append('<h1>ALLOCATION BREAKDOWN</h1>')
            html_parts.append('<ul class="allocation">')

            for allocation in data['allocation_breakdown']:
                ticker = allocation.get('ticker', 'N/A')
                percentage = allocation.get('percentage', 'N/A')
                investment_amount = allocation.get('investment_amount', 'N/A')
                html_parts.append(f'<li><strong>{ticker}:</strong> {percentage} - {investment_amount}</li>')

            html_parts.append('</ul>')

        # Add Individual Stock Recommendations section
        if 'individual_stock_recommendations' in data and data['individual_stock_recommendations']:
            html_parts.append('<h1>INDIVIDUAL STOCK RECOMMENDATIONS</h1>')

            for stock in data['individual_stock_recommendations']:
                ticker = stock.get('ticker', 'N/A')
                recommendation = stock.get('recommendation', 'HOLD').upper()
                investment_amount = stock.get('investment_amount', '$0')
                key_metrics = stock.get('key_metrics', 'N/A')
                reasoning = stock.get('reasoning', 'No reasoning provided')

                # Determine card styling based on recommendation
                rec_type = 'hold'
                rec_class = 'rec-hold'
                if recommendation == 'BUY':
                    rec_type = 'buy'
                    rec_class = 'rec-buy'
                elif recommendation == 'SELL':
                    rec_type = 'sell'
                    rec_class = 'rec-sell'

                html_parts.append(f'<div class="stock-card {rec_type}">')
                html_parts.append(f'<span class="ticker">{ticker}</span> - <span class="recommendation {rec_class}">{recommendation}</span>')

                if recommendation == 'BUY':
                    html_parts.append(f'<p><strong>Investment Amount: {investment_amount}</strong></p>')
                elif recommendation == 'SELL':
                    shares_to_sell = stock.get('shares_to_sell', 'Not specified')
                    html_parts.append(f'<p><strong>⚠️ Action Required: Sell {shares_to_sell}</strong></p>')

                html_parts.append(f'<p><strong>Key Metrics:</strong> {key_metrics}</p>')
                html_parts.append(f'<p><strong>Reasoning:</strong> {reasoning}</p>')
                html_parts.append('</div>')

        # Add Risk Warnings section
        if 'risk_warnings' in data and data['risk_warnings']:
            html_parts.append('<h1>RISK WARNINGS</h1>')
            html_parts.append('<ul>')

            for warning in data['risk_warnings']:
                html_parts.append(f'<li>{warning}</li>')

            html_parts.append('</ul>')

        # Close HTML
        html_parts.append('</body></html>')

        return ''.join(html_parts)

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse JSON in convert_portfolio_analysis_to_html: {e}")
        # Fallback to simple HTML with error message
        return f'''<html>
<head>
<style>
body {{ font-family: Arial, sans-serif; padding: 20px; }}
.error {{ color: #e74c3c; background-color: #fef5f5; padding: 15px; border-left: 4px solid #e74c3c; }}
</style>
</head>
<body>
<div class="error">
<h2>Error Processing Portfolio Analysis</h2>
<p>Failed to parse the portfolio analysis data. Please check the format.</p>
<p>Error: {str(e)}</p>
</div>
<pre>{text}</pre>
</body>
</html>'''
    except Exception as e:
        logger.error(f"Unexpected error in convert_portfolio_analysis_to_html: {e}")
        return f'''<html>
<head>
<style>
body {{ font-family: Arial, sans-serif; padding: 20px; }}
.error {{ color: #e74c3c; background-color: #fef5f5; padding: 15px; border-left: 4px solid #e74c3c; }}
</style>
</head>
<body>
<div class="error">
<h2>Unexpected Error</h2>
<p>An unexpected error occurred while processing the analysis.</p>
<p>Error: {str(e)}</p>
</div>
</body>
</html>'''


def send_report_email(analysis_response: str, email_to: str, webhook_url: Optional[str] = None, username: Optional[str] = None, password: Optional[str] = None, subject: Optional[str] = None) -> str:
    """
    Securely sends analysis response data to the Activepieces webhook endpoint.
    
    Args:
        analysis_response: The analysis data to send
        email_to: Email address to send the analysis to
        webhook_url: Webhook URL (defaults to Activepieces endpoint)
        username: Basic auth username (defaults to environment variable)
        password: Basic auth password (defaults to environment variable)
    
    Returns:
        Success/error message with details
    """
    try:
        logger.info("Preparing to send analysis response to webhook endpoint")
        # Use environment variables for sensitive data if not provided
        webhook_url = webhook_url or "https://cloud.activepieces.com/api/v1/webhooks/a3jeiaYrX1ZqVdSAye25A"
        username = username or os.getenv("ACTIVEPIECES_USERNAME")
        password = password or os.getenv("ACTIVEPIECES_PASSWORD")
        
        # Validate required parameters
        if not username or not password:
            logger.error("Missing Activepieces authentication credentials")
            return "Error: Missing authentication credentials. Please set ACTIVEPIECES_USERNAME and ACTIVEPIECES_PASSWORD environment variables."
        
        if not analysis_response or not analysis_response.strip():
            logger.error("Empty analysis response provided")
            return "Error: Analysis response cannot be empty."
        
        # Get current date for email body
        current_date = datetime.now().strftime("%B %d, %Y")
        
        # Add date to the beginning of HTML content
        response_with_date = analysis_response.replace(
            'ALLOCATION BREAKDOWN',
            f'ALLOCATION BREAKDOWN - {current_date}'
        )
        
        # Prepare the request data - include both plain text and HTML versions
        payload = {
            "analysis_response": response_with_date,  # Add HTML version for email with date
            "email_to": email_to
        }
        
        # Create basic auth header - exactly like your working curl
        credentials = f"{username}:{password}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/json"
            # Removed User-Agent to match your curl exactly
        }
        
        logger.info(f"Sending analysis data to webhook: {webhook_url}")
        logger.info(f"Payload: {payload}")
        html_content = render_report_html(response_with_date)
        html_payload = {
            "analysis_response": html_content,
            "email_to": email_to
        }
        if subject:
            html_payload["subject"] = subject
        logger.info(f"html_payload: {html_payload}")
        logger.info(f"Headers: {json.dumps({k: v for k, v in headers.items() if k != 'Authorization'}, indent=2)}")
        logger.info(f"Auth: Basic {encoded_credentials[:10]}...")
        
        # Make the POST request - exactly like your curl
        response = requests.post(
            webhook_url,
            json=html_payload,
            headers=headers,
            timeout=30
        )
        
        # Log the full response for debugging
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response headers: {dict(response.headers)}")
        logger.info(f"Response text: {response.text[:500]}")
        
        # Check response status
        if response.status_code == 200:
            logger.info("Successfully sent analysis data to webhook")
            return f"Success: Analysis data sent to webhook. Response: {response.status_code} - {response.text[:100]}..."
        elif response.status_code == 401:
            logger.error("Authentication failed - check username/password")
            return f"Error: Authentication failed. Please verify your Activepieces credentials. Response: {response.text[:200]}"
        elif response.status_code == 404:
            logger.error("Webhook endpoint not found")
            return f"Error: Webhook endpoint not found. Please verify the URL. Response: {response.text[:200]}"
        elif response.status_code >= 500:
            logger.error(f"Server error from webhook: {response.status_code}")
            return f"Error: Server error from webhook ({response.status_code}). Response: {response.text[:200]}"
        else:
            logger.warning(f"Unexpected response from webhook: {response.status_code}")
            return f"Warning: Unexpected response from webhook ({response.status_code}): {response.text[:200]}"
            
    except requests.exceptions.Timeout:
        logger.error("Request timeout - webhook endpoint took too long to respond")
        return "Error: Request timeout. The webhook endpoint took too long to respond."
    except requests.exceptions.SSLError:
        logger.error("SSL certificate verification failed")
        return "Error: SSL certificate verification failed. Please check the webhook endpoint."
    except requests.exceptions.ConnectionError:
        logger.error("Connection error - unable to reach webhook endpoint")
        return "Error: Connection error. Unable to reach the webhook endpoint."
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {str(e)}")
        return f"Error: Request failed - {str(e)}"
    except Exception as e:
        logger.error(f"Unexpected error sending to webhook: {str(e)}")
        return f"Error: Unexpected error occurred - {str(e)}"

