from crewai import Task
from textwrap import dedent

class MacroTasks:

    def gather_macro_data_task(self, agent, current_date):
        return Task(
            description=dedent(f"""\
                Today's date is: {current_date}. 
                Gather macroeconomic and fundamental data:
                1. Fetch the latest US indicators (CPI, Core PCE, Unemployment Rate, JOLTS Job Openings, NFP, Retail Sales, Fed Funds Rate) from the FRED API.
                2. Fetch the upcoming economic calendar releases (including PMI, JOLTS, NFP, CPI/PCE releases) and consensus forecasts.
                3. Fetch the latest global geopolitical briefs from Foreign Affairs.

                Compile all findings into a structured Macro Data Brief. Mark any missing or fallback values with their actual dates if retrieved.
                """),
            expected_output=(
                "A structured Macro Data Brief with key FRED transmission metrics (PMI, JOLTS, NFP, Retail Sales, CPI/PCE, Fed Rates), "
                "upcoming economic calendar events with forecast/actual/prior columns, "
                "and top geopolitical developments."
            ),
            agent=agent,
        )

    def gather_asset_data_task(self, agent, target_assets, current_date):
        return Task(
            description=dedent(f"""\
                Today's date is: {current_date}. 
                Monitor specific assets: {target_assets}.
                Call the 'Gather asset prices and headlines' tool with the exact input: 'GC=F, DX-Y.NYB'.
                Compile all findings into a clean Asset Pricing & News Brief.
                """),
            expected_output=(
                "A structured Asset Pricing & News Brief with exact current prices "
                "and recent news headlines for Gold and DXY."
            ),
            agent=agent,
        )

    def gather_positioning_flows_task(self, agent, current_date):
        return Task(
            description=dedent(f"""\
                Today's date is: {current_date}. 
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

    def analyze_macro_regime_task(self, agent, current_date):
        return Task(
            description=dedent(f"""\
                Today's date is: {current_date}. 
                Using the Macro Data Brief, Asset Brief, and Flows Brief:
                Synthesise the economic indicators, geopolitical events, and asset pricing.
                
                Mandatory Transmission Chain Analysis (Step-by-Step):
                1. Activity & Sentiment (PMI) -> Predicts growth momentum and hiring intent.
                2. Labor Demand (JOLTS) -> Predicts labor tightness and upcoming NFP payroll strength.
                3. Labor Market Slack & Payrolls (NFP & Unemployment Rate) -> Evaluate Phillips Curve dynamics (Is tight labor driving wage inflation or is unemployment loosening pressure?).
                4. Aggregate Demand (Retail Sales) -> Evaluate consumer spending capacity and demand-pull inflation.
                5. Inflation Pressures (CPI / PCE) -> Evaluate actual inflation momentum.
                6. Monetary Policy & Market Reaction -> Determine Federal Reserve rate cycle direction and its direct transmission to Gold (GC=F) and the US Dollar Index (DX-Y.NYB).

                Identify and explain the overarching global macro regime (e.g. classical expansion, stagflation, policy-driven contraction, or disinflationary recovery).
                """),
            expected_output=(
                "A macro regime analysis detailing the 6-step transmission chain, Phillips Curve labor-inflation dynamics, "
                "and monetary policy direction with implications for Gold and DXY."
            ),
            agent=agent,
        )

    def synthesize_and_forecast_task(self, agent, current_date):
        return Task(
            description=dedent(f"""\
                Today's date is: {current_date}. 
                Review all previous outputs:
                - Macro Scout's data brief (FRED indicators, calendar, geopolitics)
                - Asset Analyst's price & news brief
                - Flows Analyst's COT positioning brief
                - Macro Economist's regime & Phillips Curve transmission analysis

                Perform these analyses:
                0. Write a brief "Analyst Executive Summary" at the very top in simple layman's terms. Mention that it is based on data for {current_date} and highlight the Phillips Curve labor-inflation outlook.
                1. Detail the 6-step macro transmission chain (PMI -> JOLTS -> NFP -> Retail Sales -> CPI/PCE -> Interest Rates) and its direct impact on Gold (GC=F) and DXY (DX-Y.NYB).
                2. Explicitly cite the FRED data: Unemployment Rate, CPI, Core PCE, JOLTS, NFP, Retail Sales, and Fed Funds Rate with exact dates.
                3. Analyse the COT positioning using the ACTUAL NET NUMBERS — explain if the market is crowded or set to turn.
                4. Forecast upcoming calendar events: Predict beat/meet/miss ONLY for the unreleased high-impact US economic events provided in the Scout's data brief. Include the EXACT DATE and TIME in Cambodia Time (UTC+7). If the brief states there are no upcoming high-impact events remaining for the week, explicitly write: 'No remaining high-impact US events to forecast this week.'
                5. Do NOT include trading entry/exit levels or stop-losses.

                **OUTPUT FORMAT — two sections separated by exactly `---KHMER_SECTION---`:**

                # Analyst Executive Summary
                [Simple overview for non-technical readers including labor-inflation transmission...]

                # Detailed Macro Analysis
                [Full English report including 6-step transmission chain & Phillips Curve regime...]
                ---KHMER_SECTION---
                [Khmer translation...]
                """),
            expected_output=(
                "A dual-language report: English section (Executive Summary + full 6-step transmission analysis) "
                "followed by Khmer translation, separated by ---KHMER_SECTION---."
            ),
            agent=agent,
        )
