import yfinance as yf
from crewai.tools import tool
import requests
import os
import xml.etree.ElementTree as ET
import re

class MacroTools:
    
    @tool("Get recent news for an asset")
    def get_news(ticker: str) -> str:
        """Fetch the latest news headlines for a given stock/asset ticker from Yahoo Finance."""
        try:
            asset = yf.Ticker(ticker)
            news = asset.news
            if not news:
                return f"No news found for {ticker}."
            
            summary = ""
            for item in news[:5]:
                summary += f"- {item.get('title', '')} (Publisher: {item.get('publisher', '')})\n"
            return summary
        except Exception as e:
            return f"Error fetching news: {str(e)}"
            
    @tool("Get current price")
    def get_price(ticker: str) -> str:
        """Fetch the current market price for a given stock/asset ticker."""
        try:
            asset = yf.Ticker(ticker)
            data = asset.history(period="1d")
            if data.empty:
                return f"Could not retrieve price for {ticker}"
            price = data['Close'].iloc[-1]
            return f"The current price of {ticker} is ${price:.2f}"
        except Exception as e:
            return f"Error fetching price: {str(e)}"

    @tool("Get key macroeconomic data from FRED")
    def get_fred_data() -> str:
        """Fetch key US macroeconomic indicators (CPI Inflation, Fed Funds Rate, and Unemployment Rate) from the Federal Reserve Economic Data (FRED) API."""
        api_key = os.environ.get("FRED_API_KEY")
        if not api_key or api_key == "your_fred_api_key_here" or api_key.strip() == "":
            return "FRED API Key is missing. Please add FRED_API_KEY to your .env file to fetch macroeconomic data."
        
        indicators = {
            "CPI (Consumer Price Index)": "CPIAUCSL",
            "Fed Funds Effective Rate": "FEDFUNDS",
            "Unemployment Rate": "UNRATE"
        }
        
        report = "Latest US Macroeconomic Data (FRED):\n"
        try:
            for name, series_id in indicators.items():
                url = f"https://api.stlouisfed.org/fred/series/observations?series_id={series_id}&api_key={api_key}&file_type=json&sort_order=desc&limit=1"
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    obs = data.get("observations", [])
                    if obs:
                        val = obs[0].get("value")
                        date = obs[0].get("date")
                        report += f"- {name}: {val} (As of: {date})\n"
                    else:
                        report += f"- {name}: No observations found.\n"
                else:
                    report += f"- {name}: Failed to fetch (Status {response.status_code}).\n"
            return report
        except Exception as e:
            return f"Error fetching FRED data: {str(e)}"

    @tool("Get recent global geopolitical news")
    def get_geopolitical_news() -> str:
        """Fetch the latest geopolitical developments and reports from the Foreign Affairs RSS feed."""
        url = "https://www.foreignaffairs.com/rss.xml"
        headers = {"User-Agent": "Mozilla/5.0"}
        
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                return f"Failed to fetch geopolitical news: Status {response.status_code}"
                
            root = ET.fromstring(response.content)
            items = root.findall(".//item")
            if not items:
                return "No geopolitical news found."
                
            report = "Recent Geopolitical Developments (Foreign Affairs):\n"
            for item in items[:5]:
                title_elem = item.find("title")
                desc_elem = item.find("description")
                title = title_elem.text if title_elem is not None else "No Title"
                desc = desc_elem.text if desc_elem is not None else "No Description"
                
                # Strip HTML tags from description if any
                desc_clean = re.sub(r'<[^>]*>', '', desc).strip()
                # Limit description length
                if len(desc_clean) > 200:
                    desc_clean = desc_clean[:200] + "..."
                report += f"- **{title}**: {desc_clean}\n"
            return report
        except Exception as e:
            return f"Error fetching geopolitical news: {str(e)}"

    @tool("Get upcoming economic calendar and consensus forecasts")
    def get_economic_calendar() -> str:
        """Fetch the current and upcoming economic events calendar including actual values, market expectation (consensus forecasts), and prior values from Yahoo Finance, with times formatted in Cambodia Time (UTC+7)."""
        from bs4 import BeautifulSoup
        import datetime
        
        def convert_to_cambodia_time(time_str):
            if not time_str or time_str.lower() in ["all day", "-", ""]:
                return time_str
            time_str_clean = time_str.replace("UTC", "").replace("GMT", "").strip()
            for fmt in ("%I:%M %p", "%H:%M", "%I:%M%p", "%H:%M %p"):
                try:
                    dt = datetime.datetime.strptime(time_str_clean, fmt)
                    dt_cambo = dt + datetime.timedelta(hours=7)
                    return dt_cambo.strftime("%I:%M %p (+7)")
                except ValueError:
                    continue
            return f"{time_str} (UTC)"

        url = "https://finance.yahoo.com/calendar/economic"
        headers = {"User-Agent": "Mozilla/5.0"}
        try:
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                return f"Failed to fetch economic calendar: Status {response.status_code}"
                
            soup = BeautifulSoup(response.text, 'html.parser')
            table = soup.find('table')
            if not table:
                return "No economic calendar table found on page."
                
            rows = table.find_all('tr')
            if len(rows) <= 1:
                return "Economic calendar is empty."
                
            report = "Economic Calendar & Consensus Forecasts (Upcoming/Recent, Cambodia Time +7):\n"
            count = 0
            for row in rows[1:25]:  # Limit to 24 events
                cols = row.find_all(['td', 'th'])
                if len(cols) >= 7:
                    event = cols[0].text.strip()
                    country = cols[1].text.strip()
                    time_raw = cols[2].text.strip()
                    time = convert_to_cambodia_time(time_raw)
                    for_period = cols[3].text.strip()
                    actual = cols[4].text.strip()
                    expectation = cols[5].text.strip()
                    prior = cols[6].text.strip()
                    
                    if country in ["US", "GB", "EU", "JP", "CN", "DE"]:
                        report += f"- **{event}** ({country}) | Time: {time} | For: {for_period} | Actual: {actual} | Forecast (Consensus): {expectation} | Prior: {prior}\n"
                        count += 1
            if count == 0:
                for row in rows[1:16]:
                    cols = row.find_all(['td', 'th'])
                    if len(cols) >= 7:
                        event = cols[0].text.strip()
                        country = cols[1].text.strip()
                        time_raw = cols[2].text.strip()
                        time = convert_to_cambodia_time(time_raw)
                        for_period = cols[3].text.strip()
                        actual = cols[4].text.strip()
                        expectation = cols[5].text.strip()
                        prior = cols[6].text.strip()
                        report += f"- **{event}** ({country}) | Time: {time} | For: {for_period} | Actual: {actual} | Forecast (Consensus): {expectation} | Prior: {prior}\n"
            return report
        except Exception as e:
            return f"Error fetching economic calendar: {str(e)}"

    @tool("Search for Commitments of Traders COT and money flows")
    def search_cot_and_flows() -> str:
        """Search the web for the latest weekly Commitments of Traders (COT) report net positioning and institutional money flows for Gold (GC=F) and the US Dollar Index (DXY)."""
        from bs4 import BeautifulSoup
        
        queries = [
            "Commitments of Traders Gold DXY COT report weekly positioning",
            "gold ETF flows central bank gold buying reserves DXY liquidity"
        ]
        headers = {"User-Agent": "Mozilla/5.0"}
        report = "Market Positioning & Institutional Money Flows:\n"
        
        for q in queries:
            try:
                url = f"https://search.yahoo.com/search?q={requests.utils.quote(q)}"
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'html.parser')
                    results = soup.find_all('div', class_=re.compile(r'algo'))
                    report += f"\nSearch Results for '{q}':\n"
                    for r in results[:3]:
                        title_elem = r.find('h3')
                        desc_elem = r.find('div', class_='compText') or r.find('p')
                        title = title_elem.text.strip() if title_elem else "No Title"
                        desc = desc_elem.text.strip() if desc_elem else "No Description"
                        report += f"- **{title}**: {desc[:200]}...\n"
                else:
                    report += f"\nFailed search for '{q}': Status {response.status_code}\n"
            except Exception as e:
                report += f"\nError searching '{q}': {str(e)}\n"
        return report
