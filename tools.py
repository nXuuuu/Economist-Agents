import yfinance as yf
from crewai.tools import tool
import requests
import os
import xml.etree.ElementTree as ET
import re
import time

# ─────────────────────────────────────────────────────────────────────────────
#  Shared retry helper — wraps every HTTP call with 3 attempts + backoff
# ─────────────────────────────────────────────────────────────────────────────
def _http_get(url, headers=None, timeout=3.5, max_attempts=2):
    """GET with fast timeout and retry. Returns Response or None."""
    _headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    if headers:
        _headers.update(headers)
    for attempt in range(max_attempts):
        try:
            resp = requests.get(url, headers=_headers, timeout=timeout)
            # Do NOT retry on client errors (unauthorized, forbidden, bad request, not found)
            if resp.status_code < 500 and resp.status_code != 429:
                return resp
            resp.raise_for_status()
            return resp
        except Exception:
            if attempt < max_attempts - 1:
                time.sleep(1.0)   # Sleep exactly 1s before retrying
    return None


class MacroTools:

    # ── 1. Asset news ────────────────────────────────────────────────────────
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
                content = item.get('content', {})
                title = content.get('title', '')
                publisher = content.get('provider', {}).get('displayName', '')
                if title:
                    summary += f"- {title} (Publisher: {publisher})\n"
            return summary if summary else f"No news found for {ticker}."
        except Exception as e:
            return f"Error fetching news for {ticker}: {str(e)}"

    # ── 2. Asset price ────────────────────────────────────────────────────────
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
            return f"Error fetching price for {ticker}: {str(e)}"

    # ── 3. FRED macro data (with retry & search fallback) ────────────────────
    def _search_macro_indicator_fallback(indicator_name: str) -> str:
        """Search Yahoo for the latest US indicator value when FRED fails."""
        from bs4 import BeautifulSoup
        q = f"latest US {indicator_name} rate value"
        url = f"https://search.yahoo.com/search?q={requests.utils.quote(q)}"
        resp = _http_get(url)
        if resp and resp.status_code == 200:
            try:
                soup = BeautifulSoup(resp.text, 'html.parser')
                # Find plain text nodes
                results = soup.find_all('div', class_=re.compile(r'algo|compText')) or soup.find_all('p')
                for r in results[:4]:
                    txt = r.text.strip()
                    # Look for percentage values like '3.4%' or '5.25%'
                    match = re.search(r'\b\d+(\.\d+)?%', txt)
                    if match:
                        return f"{match.group(0)} (estimated from search results)"
            except Exception:
                pass
        return "Unavailable"

    @tool("Get key macroeconomic data from FRED")
    def get_fred_data() -> str:
        """Fetch key US macroeconomic indicators (CPI Inflation, Fed Funds Rate, and Unemployment Rate) from the Federal Reserve Economic Data (FRED) API."""
        api_key = os.environ.get("FRED_API_KEY", "")
        has_key = api_key and api_key.strip() != "" and api_key != "your_fred_api_key_here"

        indicators = {
            "CPI (Consumer Price Index)": ("CPIAUCSL", "inflation"),
            "Fed Funds Effective Rate":   ("FEDFUNDS", "fed funds interest"),
            "Unemployment Rate":          ("UNRATE", "unemployment"),
        }

        report = "Latest US Macroeconomic Data:\n"
        for name, (series_id, search_term) in indicators.items():
            success = False
            if has_key:
                url = (
                    f"https://api.stlouisfed.org/fred/series/observations"
                    f"?series_id={series_id}&api_key={api_key}"
                    f"&file_type=json&sort_order=desc&limit=1"
                )
                resp = _http_get(url)
                if resp and resp.status_code == 200:
                    try:
                        obs = resp.json().get("observations", [])
                        if obs:
                            report += f"- {name}: {obs[0]['value']} (as of {obs[0]['date']})\n"
                            success = True
                    except Exception:
                        pass

            if not success:
                # API failed or key missing — use web search fallback
                val = MacroTools._search_macro_indicator_fallback(search_term)
                report += f"- {name}: {val} (Web search fallback)\n"
                
        return report

    # ── 4. Geopolitical news (with retry) ────────────────────────────────────
    @tool("Get recent global geopolitical news")
    def get_geopolitical_news() -> str:
        """Fetch the latest geopolitical developments and reports from the Foreign Affairs RSS feed."""
        url = "https://www.foreignaffairs.com/rss.xml"
        resp = _http_get(url)
        if resp is None or resp.status_code != 200:
            return "Failed to fetch geopolitical news."
        try:
            root = ET.fromstring(resp.content)
            items = root.findall(".//item")
            if not items:
                return "No geopolitical news found."
            report = "Recent Geopolitical Developments (Foreign Affairs):\n"
            for item in items[:5]:
                title = (item.find("title").text or "No Title") if item.find("title") is not None else "No Title"
                desc  = (item.find("description").text or "") if item.find("description") is not None else ""
                desc_clean = re.sub(r'<[^>]*>', '', desc).strip()[:200]
                report += f"- **{title}**: {desc_clean}{'...' if len(desc_clean)==200 else ''}\n"
            return report
        except Exception as e:
            return f"Error parsing geopolitical news: {str(e)}"

    # ── 5. Economic calendar (robust multi-strategy scraping + retry) ─────────
    @tool("Get upcoming economic calendar and consensus forecasts")
    def get_economic_calendar() -> str:
        """Fetch upcoming economic events including actual values, consensus forecasts, and prior values from Yahoo Finance. Times are in Cambodia Time (UTC+7)."""
        from bs4 import BeautifulSoup
        import datetime

        def to_kh_time(t):
            if not t or t.lower() in ("all day", "-", ""):
                return t
            clean = t.replace("UTC", "").replace("GMT", "").strip()
            for fmt in ("%I:%M %p", "%H:%M", "%I:%M%p"):
                try:
                    dt = datetime.datetime.strptime(clean, fmt) + datetime.timedelta(hours=7)
                    return dt.strftime("%I:%M %p (+7)")
                except ValueError:
                    continue
            return f"{t} (UTC)"

        url = "https://finance.yahoo.com/calendar/economic"
        resp = _http_get(url)
        
        # If Yahoo is blocked/timeout, fall back to Search for upcoming economic events
        if resp is None or resp.status_code != 200:
            report = "Economic Calendar & Consensus Forecasts (Web Search Fallback):\n"
            try:
                q = "economic calendar upcoming events this week forecast consensus prior"
                search_url = f"https://search.yahoo.com/search?q={requests.utils.quote(q)}"
                s_resp = _http_get(search_url)
                if s_resp and s_resp.status_code == 200:
                    soup = BeautifulSoup(s_resp.text, 'html.parser')
                    results = soup.find_all('div', class_=re.compile(r'algo'))
                    for r in results[:4]:
                        title = r.find('h3').text.strip() if r.find('h3') else ""
                        desc = (r.find('div', class_='compText') or r.find('p')).text.strip() if (r.find('div', class_='compText') or r.find('p')) else ""
                        if title and desc:
                            report += f"- **{title}**: {desc[:200]}...\n"
                return report if len(report) > 60 else "No upcoming economic events found via search fallback."
            except Exception as se:
                return f"Economic calendar search fallback failed: {se}"

        try:
            soup = BeautifulSoup(resp.text, 'html.parser')
            table = soup.find('table')
            if not table:
                table = soup.find(attrs={"data-test": re.compile(r"calendar|economic", re.I)})
            if not table:
                # Table missing - try search fallback instead of raising error
                raise ValueError("Economic calendar table not found on Yahoo page.")

            rows = table.find_all('tr')
            if len(rows) <= 1:
                raise ValueError("Economic calendar table is empty.")

            # ── Auto-detect column positions from header row ──────────────
            header_cells = rows[0].find_all(['th', 'td'])
            col = {}
            for i, cell in enumerate(header_cells):
                txt = cell.text.strip().lower()
                if 'event' in txt:                              col['event']    = i
                elif 'country' in txt:                          col['country']  = i
                elif 'time' in txt:                             col['time']     = i
                elif 'actual' in txt:                           col['actual']   = i
                elif any(k in txt for k in ('market', 'expect', 'est', 'forecast', 'consensus')):
                    col['forecast'] = i
                elif any(k in txt for k in ('prior', 'prev')):  col['prior']    = i

            # Positional fallback when header detection fails
            if len(col) < 4:
                col = {'event': 0, 'country': 1, 'time': 2, 'actual': 4, 'forecast': 5, 'prior': 6}

            priority = {"US", "GB", "EU", "JP", "CN", "DE"}
            report   = "Economic Calendar & Consensus Forecasts (Cambodia Time UTC+7):\n"
            count    = 0

            for row in rows[1:35]:
                cells = row.find_all(['td', 'th'])
                needed = max(col.values()) + 1 if col else 7
                if len(cells) < needed:
                    continue
                try:
                    event    = cells[col.get('event', 0)].text.strip()
                    country  = cells[col.get('country', 1)].text.strip()
                    time_raw = cells[col.get('time', 2)].text.strip()
                    actual   = cells[col.get('actual', 4)].text.strip()
                    forecast = cells[col.get('forecast', 5)].text.strip()
                    prior    = cells[col.get('prior', 6)].text.strip()
                    kh_time  = to_kh_time(time_raw)

                    if country in priority or count < 8:
                        report += (
                            f"- **{event}** ({country}) | Time: {kh_time} "
                            f"| Actual: {actual} | Forecast: {forecast} | Prior: {prior}\n"
                        )
                        count += 1
                except (IndexError, AttributeError):
                    continue

            return report if count > 0 else "Calendar fetched but no matching events found."

        except Exception as e:
            # Fallback to search if any parsing exception occurs
            report = "Economic Calendar & Consensus Forecasts (Web Search Fallback after parse error):\n"
            try:
                q = "economic calendar upcoming events this week forecast consensus prior"
                search_url = f"https://search.yahoo.com/search?q={requests.utils.quote(q)}"
                s_resp = _http_get(search_url)
                if s_resp and s_resp.status_code == 200:
                    soup = BeautifulSoup(s_resp.text, 'html.parser')
                    results = soup.find_all('div', class_=re.compile(r'algo'))
                    for r in results[:4]:
                        title = r.find('h3').text.strip() if r.find('h3') else ""
                        desc = (r.find('div', class_='compText') or r.find('p')).text.strip() if (r.find('div', class_='compText') or r.find('p')) else ""
                        if title and desc:
                            report += f"- **{title}**: {desc[:200]}...\n"
                return report if len(report) > 60 else f"Economic calendar error: {e}"
            except Exception:
                return f"Error parsing economic calendar: {str(e)}"

    # ── 6. COT data — CFTC official API (real numbers) ───────────────────────
    @tool("Search for Commitments of Traders COT and money flows")
    def search_cot_and_flows() -> str:
        """Fetch the latest weekly Commitments of Traders (COT) report for Gold from the official CFTC Socrata API. Returns actual net long/short positions for Non-Commercial (speculator) and Commercial (hedger) traders."""
        report = "Market Positioning & Institutional Money Flows (CFTC Official Data):\n"

        # CFTC Socrata Open Data API — Legacy Futures-Only COT report
        cftc_url = (
            "https://data.cftc.gov/resource/6dca-aqww.json"
            "?$where=market_and_exchange_names+like+'%25GOLD%25'"
            "&$order=as_of_date_in_form_yyyy_mm_dd+DESC"
            "&$limit=2"
        )

        resp = _http_get(cftc_url)
        cftc_ok = False

        if resp is not None and resp.status_code == 200:
            try:
                rows = resp.json()
                if rows:
                    cftc_ok = True
                    for row in rows:
                        date    = row.get('as_of_date_in_form_yyyy_mm_dd', 'N/A')
                        nc_long  = int(float(row.get('noncommercial_positions_long_all',  0)))
                        nc_short = int(float(row.get('noncommercial_positions_short_all', 0)))
                        c_long   = int(float(row.get('commercial_positions_long_all',     0)))
                        c_short  = int(float(row.get('commercial_positions_short_all',    0)))
                        nc_net   = nc_long  - nc_short
                        c_net    = c_long   - c_short
                        bias     = "BULLISH" if nc_net > 0 else "BEARISH"

                        report += (
                            f"\nGOLD COT — Week of {date}:\n"
                            f"  Non-Commercial (Speculators): Long {nc_long:,} | Short {nc_short:,} | NET {nc_net:+,}\n"
                            f"  Commercial     (Hedgers):     Long {c_long:,}  | Short {c_short:,}  | NET {c_net:+,}\n"
                            f"  Signal: Speculator net position is {bias} ({abs(nc_net):,} contracts)\n"
                        )
            except Exception as e:
                report += f"CFTC data parse error: {e}\n"

        if not cftc_ok:
            report += "CFTC API unavailable — using news-based fallback.\n"
            try:
                gold = yf.Ticker("GC=F")
                for item in (gold.news or [])[:4]:
                    content = item.get('content', {})
                    title = content.get('title', '')
                    if any(kw in title.lower() for kw in ['cot', 'positioning', 'flows', 'central bank', 'etf']):
                        report += f"- {title}\n"
            except Exception:
                pass

        # ── Supplement: GLD ETF AUM as institutional demand proxy ───────────
        try:
            gld  = yf.Ticker("GLD")
            info = gld.info
            aum  = info.get("totalAssets")
            if aum:
                report += f"\nGLD ETF Total Assets (AUM): ${aum:,.0f} (institutional gold demand proxy)\n"
        except Exception:
            pass

        return report

    # ── 7. UNIFIED Macro Fundamentals Tool ──────────────────────────────────
    @tool("Gather all macro fundamentals")
    def gather_all_macro_fundamentals() -> str:
        """Fetch all macroeconomic indicators from FRED, the Yahoo economic calendar, and Foreign Affairs RSS geopolitical feeds at once."""
        report = "=== GATHERED MACRO FUNDAMENTALS ===\n\n"
        
        # 1. FRED
        try:
            report += MacroTools.get_fred_data.func() + "\n"
        except Exception as e:
            report += f"FRED error: {e}\n"
            
        # 2. Economic Calendar
        try:
            report += MacroTools.get_economic_calendar.func() + "\n"
        except Exception as e:
            report += f"Calendar error: {e}\n"
            
        # 3. Geopolitical
        try:
            report += MacroTools.get_geopolitical_news.func() + "\n"
        except Exception as e:
            report += f"Geopolitical news error: {e}\n"
            
        return report

    # ── 8. UNIFIED Asset pricing & headlines Tool ────────────────────────────
    @tool("Gather asset prices and headlines")
    def gather_asset_prices_and_headlines(target_assets: str) -> str:
        """Fetch market prices and news headlines for multiple target assets at once. Input is comma separated assets list, e.g. 'GC=F, DX-Y.NYB'."""
        assets = [a.strip() for a in target_assets.split(",") if a.strip()]
        report = "=== GATHERED ASSET PRICES & HEADLINES ===\n\n"
        
        for asset in assets:
            report += f"--- {asset} ---\n"
            try:
                report += MacroTools.get_price.func(asset) + "\n"
            except Exception as e:
                report += f"Price error: {e}\n"
            try:
                report += MacroTools.get_news.func(asset) + "\n"
            except Exception as e:
                report += f"News error: {e}\n"
                
        return report

