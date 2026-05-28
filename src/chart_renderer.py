"""Generate TradingView chart screenshots using Playwright."""
import logging
import os
import tempfile
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

# Map yfinance exchange codes to TradingView prefixes
EXCHANGE_MAP = {
    "NMS": "NASDAQ",  # Nasdaq Global Select
    "NGM": "NASDAQ",  # Nasdaq Global Market
    "NCM": "NASDAQ",  # Nasdaq Capital Market
    "NYQ": "NYSE",    # New York Stock Exchange
    "ASE": "AMEX",    # American Stock Exchange
    "BATS": "BATS",
}

HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>TradingView Chart - {symbol}</title>
  <style>
    html, body {{
      margin: 0;
      padding: 0;
      width: 1200px;
      height: 800px;
      overflow: hidden;
      background-color: #131722;
    }}
    #tv_chart_container {{
      width: 100%;
      height: 100%;
    }}
  </style>
</head>
<body>
  <div id="tv_chart_container"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
    new TradingView.widget({{
      "width": 1200,
      "height": 800,
      "symbol": "{tv_symbol}",
      "interval": "D",
      "timezone": "America/New_York",
      "theme": "dark",
      "style": "1",
      "locale": "zh_CN",
      "enable_publishing": false,
      "hide_side_toolbar": false,
      "allow_symbol_change": false,
      "container_id": "tv_chart_container",
      "studies": [
        {{ "id": "MAExp@tv-basicstudies", "inputs": {{ "length": 20 }} }},
        {{ "id": "MAExp@tv-basicstudies", "inputs": {{ "length": 50 }} }},
        {{ "id": "MAExp@tv-basicstudies", "inputs": {{ "length": 200 }} }},
        {{ "id": "RSI@tv-basicstudies", "inputs": {{ "length": 14 }} }},
        {{ "id": "MACD@tv-basicstudies" }}
      ]
    }});
  </script>
</body>
</html>
"""

def get_tv_symbol(symbol: str, exchange: str = "") -> str:
    """Format symbol with correct TradingView exchange prefix."""
    prefix = EXCHANGE_MAP.get(exchange.upper(), "")
    if prefix:
        return f"{prefix}:{symbol}"
    
    # Defaults / fallback logic
    if symbol in ["NVDA", "MRVL", "CRDO", "ALAB", "APLD"]:
        return f"NASDAQ:{symbol}"
    elif symbol in ["VRT"]:
        return f"NYSE:{symbol}"
    
    return symbol

def capture_screenshot(symbol: str, exchange: str, output_path: str) -> bool:
    """
    Renders TradingView advanced chart widget to a temp HTML file,
    opens it with Playwright, waits for it to render, and saves a screenshot.
    """
    tv_symbol = get_tv_symbol(symbol, exchange)
    logger.info(f"Rendering chart for {tv_symbol}...")
    
    # Generate HTML content
    html_content = HTML_TEMPLATE.format(symbol=symbol, tv_symbol=tv_symbol)
    
    # Create temporary file
    temp_dir = Path(tempfile.gettempdir())
    temp_html_path = temp_dir / f"tv_chart_{symbol}.html"
    temp_html_path.write_text(html_content, encoding="utf-8")
    
    success = False
    try:
        with sync_playwright() as p:
            # Launch chromium headless
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1200, "height": 800})
            
            # Go to file
            page.goto(temp_html_path.as_uri())
            
            # Wait for the widget iframe to be present
            page.wait_for_selector("iframe", timeout=10000)
            
            # Wait a few seconds for the canvas inside the iframe to load and render the data
            page.wait_for_timeout(4500)
            
            # Take screenshot of the page
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            page.screenshot(path=output_path)
            
            logger.info(f"Screenshot successfully saved to {output_path}")
            browser.close()
            success = True
    except Exception as e:
        logger.error(f"Failed to capture screenshot for {symbol}: {e}")
    finally:
        # Clean up temp file
        if temp_html_path.exists():
            try:
                temp_html_path.unlink()
            except Exception:
                pass
                
    return success
