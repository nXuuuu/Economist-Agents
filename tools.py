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
def _http_get(url, headers=None, timeout=12, max_attempts=3):
    """GET with exponential-backoff retry. Returns Response or None."""
    _headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    if headers:
        _headers.update(headers)
    last_exc = None
    for attempt in range(max_attempts):
        try:
            resp = requests.get(url, headers=_headers, timeout=timeout)
            resp.raise_for_status()
            return resp
        except Exception as exc:
            last_exc = exc
            if attempt < max_attempts - 1:
                time.sleep(2 ** attempt)   # 1 s → 2 s → 4 s
    return None   # caller must handle None


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
                summary += f"- {item.get('title', '')} (Publisher: {item.get('publisher', '')})\n"
            return summary
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

    # ── 3. FRED macro data (with retry) ──────────────────────────────────────
    @tool("Get key macroeconomic data from FRED")
    def get_fred_data() -> str:
        """Fetch key US macroeconomic indicators (CPI Inflation, Fed Funds Rate, and Unemployment Rate) from the Federal Reserve Economic Data (FRED) API."""
        api_key = os.environ.get("FRED_API_KEY", "")
        if not api_key or api_key.strip() == "" or api_key == "your_fred_api_key_here":
            return "FRED API Key is missing. Add FRED_API_KEY to your environment variables."

        indicators = {
            "CPI (Consumer Price Index)": "CPIAUCSL",
            "Fed Funds Effective Rate":   "FEDFUNDS",
            "Unemployment Rate":          "UNRATE",
        }

        report = "Latest US Macroeconomic Data (FRED):\n"
        for name, series_id in indicators.items():
            url = (
                f"https://api.stlouisfed.org/fred/series/observations"
                f"?series_id={series_id}&api_key={api_key}"
                f"&file_type=json&sort_order=desc&limit=1"
            )
            resp = _http_get(url, timeout=10)
            if resp is None:
                report += f"- {name}: Unavailable after 3 attempts.\n"
                continue
            try:
                obs = resp.json().get("observations", [])
                if obs:
                    report += f"- {name}: {obs[0]['value']} (as of {obs[0]['date']})\n"
                else:
                    report += f"- {name}: No observations found.\n"
            except Exception as e:
                report += f"- {name}: Parse error — {e}\n"
        return report

    # ── 4. Geopolitical news (with retry) ────────────────────────────────────
    @tool("Get recent global geopolitical news")
    def get_geopolitical_news() -> str:
        """Fetch the latest geopolitical developments and reports from the Foreign Affairs RSS feed."""
        url = "https://www.foreignaffairs.com/rss.xml"
        resp = _http_get(url, timeout=12)
        if resp is None:
            return "Failed to fetch geopolitical news after 3 attempts."
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
        resp = _http_get(url, timeout=15)
        if resp is None:
            return "Economic calendar unavailable after 3 attempts."

        try:
            soup = BeautifulSoup(resp.text, 'html.parser')
            table = soup.find('table')
            if not table:
                # try alternate selectors
                table = soup.find(attrs={"data-test": re.compile(r"calendar|economic", re.I)})
            if not table:
                return "Economic calendar table not found on page (Yahoo Finance may have changed layout)."

            rows = table.find_all('tr')
            if len(rows) <= 1:
                return "Economic calendar table is empty."

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
                needed = max(col.values()) + 1
                if len(cells) < needed:
                    continue
                try:
                    event    = cells[col['event']].text.strip()
                    country  = cells[col['country']].text.strip()
                    time_raw = cells[col['time']].text.strip()
                    actual   = cells[col.get('actual',   4)].text.strip()
                    forecast = cells[col.get('forecast', 5)].text.strip()
                    prior    = cells[col.get('prior',    6)].text.strip()
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

        resp = _http_get(cftc_url, timeout=15)
        cftc_ok = False

        if resp is not None:
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
                    title = item.get('title', '')
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
