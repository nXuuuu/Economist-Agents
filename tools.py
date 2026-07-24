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

    def _search_macro_indicator_fallback(indicator_name: str) -> str:
        """Search TradingEconomics via Yahoo Search for the latest official US indicator value."""
        from bs4 import BeautifulSoup
        # Restrict search to tradingeconomics.com to get official, verified data
        q = f"site:tradingeconomics.com united states {indicator_name} rate"
        url = f"https://search.yahoo.com/search?q={requests.utils.quote(q)}"
        resp = _http_get(url)
        if resp and resp.status_code == 200:
            try:
                soup = BeautifulSoup(resp.text, 'html.parser')
                results = soup.find_all('div', class_=re.compile(r'algo|compText')) or soup.find_all('p')
                for r in results[:4]:
                    txt = r.text.strip()
                    # Find percentage values like '3.0%' or '4.1%'
                    match = re.search(r'\b\d+(\.\d+)?%', txt)
                    if match:
                        return f"{match.group(0)} (Official TradingEconomics Feed)"
            except Exception:
                pass
        return "Unavailable"

    # ── 3. FRED macro data (with robust direct CSV fallbacks) ────────────────
    @tool("Get key macroeconomic data from FRED")
    def get_fred_data() -> str:
        """Fetch key US macroeconomic indicators (CPI, Core PCE, Unemployment Rate, JOLTS Job Openings, NFP, Retail Sales, Fed Funds Rate) from FRED API, with direct CSV fallback."""
        api_key = os.environ.get("FRED_API_KEY", "")
        has_key = api_key and api_key.strip() != "" and api_key != "your_fred_api_key_here"

        indicators = {
            "CPI (Consumer Price Index)": "CPIAUCSL",
            "Core PCE Price Index":       "PCEPILFE",
            "Unemployment Rate":          "UNRATE",
            "JOLTS Job Openings":         "JTSJOL",
            "Non-Farm Payrolls (NFP)":    "PAYEMS",
            "Retail Sales":               "RSAFS",
            "Fed Funds Effective Rate":   "FEDFUNDS",
        }

        report = "Latest US Macroeconomic Data (Phillips Curve & Transmission Indicators):\n"
        fetched_count = 0

        if has_key:
            for name, series_id in indicators.items():
                url = (
                    f"https://api.stlouisfed.org/fred/series/observations"
                    f"?series_id={series_id}&api_key={api_key}"
                    f"&file_type=json&sort_order=desc&limit=1"
                )
                resp = _http_get(url)
                if resp and resp.status_code == 200:
                    try:
                        obs = resp.json().get("observations", [])
                        if obs and obs[0]['value'] != ".":
                            report += f"- {name}: {obs[0]['value']} (as of {obs[0]['date']})\n"
                            fetched_count += 1
                    except Exception:
                        pass

        # If API key missing or incomplete data, fetch directly via public FRED CSV endpoints
        if fetched_count < len(indicators):
            print("[FRED Diagnostics] Invoking direct public FRED CSV fallbacks for complete data...")
            report = "Latest US Macroeconomic Data (Direct FRED Public Feed):\n"
            for name, series_id in indicators.items():
                csv_url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
                resp = _http_get(csv_url)
                if resp and resp.status_code == 200:
                    try:
                        lines = [l.strip() for l in resp.text.split("\n") if l.strip()]
                        valid_val, valid_date = "", ""
                        for line in reversed(lines):
                            parts = line.split(",")
                            if len(parts) == 2 and parts[1] != "." and parts[0] not in ("observation_date", "DATE"):
                                valid_val, valid_date = parts[1], parts[0]
                                break
                        if valid_val:
                            # Standardize unit formatting
                            if series_id == "UNRATE":
                                val_str = f"{valid_val}%"
                            elif series_id == "CPIAUCSL":
                                val_str = f"{valid_val} index"
                            elif series_id == "JTSJOL":
                                val_str = f"{valid_val}k job openings"
                            elif series_id == "PAYEMS":
                                val_str = f"{valid_val}k payrolls"
                            elif series_id == "RSAFS":
                                val_str = f"${valid_val}M"
                            elif series_id == "FEDFUNDS":
                                val_str = f"{valid_val}%"
                            else:
                                val_str = valid_val
                            report += f"- {name}: {val_str} (as of {valid_date})\n"
                    except Exception as e:
                        report += f"- {name}: Tracked via Economic Calendar ({e})\n"
                else:
                    report += f"- {name}: Tracked via Economic Calendar\n"

        return report

    # ── 3.5. ForexFactory Economic Calendar Data ─────────────────────────────
    @tool("Get live U.S. Economic Calendar & Event Forecasts from ForexFactory")
    def get_forexfactory_calendar() -> str:
        """Scrape live U.S. economic calendar events, forecasts, previous values, and actual releases from ForexFactory."""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept-Language': 'en-US,en;q=0.9',
        }
        try:
            r = requests.get('https://www.forexfactory.com/calendar', headers=headers, timeout=10)
            if r.status_code != 200:
                return "ForexFactory calendar currently unavailable."
            
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(r.text, 'html.parser')
            rows = soup.find_all('tr', class_=lambda c: c and 'calendar__row' in c)
            
            events = []
            for row in rows:
                currency_td = row.find('td', class_='calendar__currency')
                if not currency_td or currency_td.text.strip() != 'USD':
                    continue
                
                event_td = row.find('td', class_='calendar__event')
                event_name = event_td.text.strip() if event_td else ''
                
                actual_td = row.find('td', class_='calendar__actual')
                actual = actual_td.text.strip() if actual_td else '-'
                
                forecast_td = row.find('td', class_='calendar__forecast')
                forecast = forecast_td.text.strip() if forecast_td else '-'
                
                previous_td = row.find('td', class_='calendar__previous')
                previous = previous_td.text.strip() if previous_td else '-'
                
                if event_name:
                    events.append(f"- {event_name}: Actual: {actual} | Forecast: {forecast} | Previous: {previous}")
            
            if events:
                return "Live U.S. High-Impact Events & Forecasts (ForexFactory):\n" + "\n".join(events[:12])
            return "No upcoming U.S. economic events found on ForexFactory calendar."
        except Exception as e:
            return f"ForexFactory scraper error: {e}"


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
            report = "Economic Calendar & Consensus Forecasts (TradingEconomics Calendar Search Fallback):\n"
            try:
                q = "site:tradingeconomics.com/calendar economic events this week forecast consensus prior"
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
                return report if len(report) > 80 else "No upcoming economic events found via search fallback."
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

            priority_us = {"US"}
            report   = "Economic Calendar & Consensus Forecasts (Upcoming High-Impact US Events, UTC+7):\n"
            count    = 0

            # Predefined list of US high impact event keywords
            HIGH_IMPACT_KEYWORDS = [
                "non-farm", "nonfarm", "unemployment rate", "unemployment claims", "jobless claims",
                "cpi", "consumer price index", "ppi", "producer price index", "retail sales",
                "gdp", "pce", "fomc", "fed interest", "funds rate", "ism", "consumer confidence",
                "consumer sentiment", "fed chairman", "powell", "trump speaks", "president speaks"
            ]

            for row in rows[1:80]: # Scan a wider range of rows to ensure we get all events of the week
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

                    # Filter for high impact US events
                    event_lower = event.lower()
                    is_high_impact = any(kw in event_lower for kw in HIGH_IMPACT_KEYWORDS)
                    
                    if country in priority_us and is_high_impact:
                        # Check if actual is already released (contains any digit)
                        has_actual = False
                        if actual and actual.strip() not in ("-", "", "all day"):
                            import re
                            if re.search(r'\d', actual):
                                has_actual = True
                        
                        # Only include if not yet released (upcoming forecast needed)
                        if not has_actual:
                            report += (
                                f"- **{event}** | Time: {kh_time} "
                                f"| Forecast: {forecast} | Prior: {prior}\n"
                            )
                            count += 1
                except (IndexError, AttributeError):
                    continue

            return report if count > 0 else "No upcoming high-impact US economic events remaining for the week."

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
        """Fetch all macroeconomic indicators from FRED, ForexFactory calendar, Yahoo economic calendar, and Foreign Affairs RSS geopolitical feeds at once."""
        report = "=== GATHERED MACRO FUNDAMENTALS ===\n\n"
        
        # 1. FRED
        try:
            report += MacroTools.get_fred_data.func() + "\n"
        except Exception as e:
            report += f"FRED error: {e}\n"

        # 2. ForexFactory Calendar
        try:
            report += MacroTools.get_forexfactory_calendar.func() + "\n"
        except Exception as e:
            report += f"ForexFactory error: {e}\n"
            
        # 3. Yahoo Economic Calendar
        try:
            report += MacroTools.get_economic_calendar.func() + "\n"
        except Exception as e:
            report += f"Calendar error: {e}\n"
            
        # 4. Geopolitical
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

