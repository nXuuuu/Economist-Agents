from crewai import Task
from textwrap import dedent

class MacroTasks:

    def gather_macro_data_task(self, agent):
        return Task(
            description=dedent("""\
                Gather macroeconomic and fundamental data:
                1. Fetch the latest US indicators (CPI, rates, unemployment) from the FRED API.
                2. Fetch the upcoming economic calendar releases and consensus forecasts.
                3. Fetch the latest global geopolitical briefs from Foreign Affairs.

                Compile all findings into a structured Macro Data Brief.
                """),
            expected_output=(
                "A structured Macro Data Brief with FRED indicator values and dates, "
                "upcoming economic calendar events with forecast/actual/prior columns, "
                "and top geopolitical developments."
            ),
            agent=agent,
        )

    def gather_asset_data_task(self, agent, target_assets):
        return Task(
            description=dedent(f"""\
                Monitor specific assets: {target_assets}.
                1. Fetch the live exchange prices for Gold (GC=F) and the US Dollar Index (DX-Y.NYB).
                2. Fetch the latest news and narratives directly associated with these two tickers.

                Compile into a clean Asset Pricing & News Brief.
                """),
            expected_output=(
                "A structured Asset Pricing & News Brief with exact current prices "
                "and recent news headlines for Gold and DXY."
            ),
            agent=agent,
        )

    def gather_positioning_flows_task(self, agent):
        return Task(
            description=dedent("""\
                Trace institutional positioning and asset flows:
                1. Fetch the official CFTC Commitments of Traders (COT) data for Gold.
                   Report the exact Non-Commercial net long/short figures and the week-over-week direction.
                2. Note the GLD ETF AUM figure as a proxy for institutional gold demand.
                3. Synthesise into a clear positioning bias signal (Bullish / Bearish / Neutral).

                Compile all findings into a Positioning & Flows Brief.
                """),
            expected_output=(
                "A Positioning & Flows Brief with CFTC net position numbers, "
                "GLD ETF AUM, and an overall positioning bias signal."
            ),
            agent=agent,
        )

    def analyze_macro_regime_task(self, agent):
        return Task(
            description=dedent("""\
                Using the Macro Data Brief, Asset Brief, and Flows Brief:
                Synthesise the economic indicators, geopolitical events, and asset pricing.
                Identify and explain the current global macro regime
                (e.g. stagflation, expansion, contraction, deflation).
                Explain what central bank rate cycles and geopolitical dynamics imply for gold and the dollar.
                """),
            expected_output=(
                "A macro regime analysis explaining the current liquidity environment "
                "and monetary policy direction with implications for Gold and DXY."
            ),
            agent=agent,
        )

    def synthesize_and_forecast_task(self, agent):
        return Task(
            description=dedent("""\
                Review all previous outputs:
                - Macro Scout's data brief (FRED indicators, calendar, geopolitics)
                - Asset Analyst's price & news brief
                - Flows Analyst's COT positioning brief
                - Macro Economist's regime analysis

                Perform these analyses:
                0. Write a brief "Analyst Executive Summary" at the very top in simple layman's terms.
                1. Detail the interplay between Gold and DXY given the current regime and pricing.
                2. Explicitly cite the FRED data: exact Unemployment Rate, CPI, and Fed Funds Rate values and dates.
                3. Analyse the COT positioning using the ACTUAL NET NUMBERS — explain if the market is crowded or set to turn.
                4. Forecast upcoming calendar events: predict beat/meet/miss for each, with the EXACT DATE and TIME in Cambodia Time (UTC+7).
                5. Do NOT include trading entry/exit levels or stop-losses.

                **OUTPUT FORMAT — two sections separated by exactly `---KHMER_SECTION---`:**

                # Analyst Executive Summary
                [Simple overview for non-technical readers...]

                # Detailed Macro Analysis
                [Full English report...]
                ---KHMER_SECTION---
                [Khmer translation...]
                """),
            expected_output=(
                "A dual-language report: English section (Executive Summary + full analysis) "
                "followed by Khmer translation, separated by ---KHMER_SECTION---."
            ),
            agent=agent,
        )
