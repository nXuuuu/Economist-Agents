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
            expected_output="A structured Macro Data Brief containing inflation/labor metrics, upcoming calendars, and geopolitical news.",
            agent=agent
        )

    def gather_asset_data_task(self, agent, target_assets):
        return Task(
            description=dedent(f"""\
                Monitor specific assets: {target_assets}.
                You must:
                1. Fetch the live exchange prices for Gold (GC=F) and the US Dollar Index (DX-Y.NYB).
                2. Fetch the latest news and narratives directly associated with these two tickers.
                
                Compile into a clean Asset Pricing & News Brief.
                """),
            expected_output="A structured Asset Pricing & News Brief detailing prices and news narratives for Gold and DXY.",
            agent=agent
        )

    def gather_positioning_flows_task(self, agent):
        return Task(
            description=dedent("""\
                Trace institutional positioning and asset flows:
                1. Search for Commitments of Traders (COT) weekly positioning reports for Gold and DXY.
                2. Find net positioning details for Commercials vs. Non-Commercials (speculators).
                3. Search for recent institutional flows (ETF inflows, central bank reserve purchases, exchange liquidations).
                
                Compile all positioning findings into a positioning brief.
                """),
            expected_output="A positioning brief outlining COT net positions and fund flows.",
            agent=agent
        )
        
    def analyze_macro_regime_task(self, agent):
        return Task(
            description=dedent("""\
                Analyze the Macro Data Brief.
                Synthesize the fundamental economic rates, labor data, and geopolitical events.
                Explain the current global economic regime (e.g. stagflation, growth, recession, deflation).
                Explain what central bank rate cycles and geopolitical tensions mean for global liquidity directions.
                """),
            expected_output="A macro regime analysis explaining global liquidity trends and monetary policy dynamics.",
            agent=agent
        )
        
    def synthesize_and_forecast_task(self, agent):
        return Task(
            description=dedent("""\
                Review all previous inputs:
                - The Macro Economist's regime analysis.
                - The Asset Analyst's price action details.
                - The Flows Analyst's COT positioning and money flows report.
                
                You must perform these core analyses:
                0. Create a brief "Analyst Executive Summary" at the very top of the English report using simple, clear, and easy wording in layman's terms so that non-technical users can instantly understand the key outlook.
                1. Detail the interplay between Gold and DXY based on the current regime and pricing.
                2. Explicitly present and analyze the latest US macroeconomic data from FRED: the Unemployment Rate, CPI, and the Effective Fed Funds Rate (you must list the exact values and dates).
                3. Analyze the COT positioning to explain if the market is over-extended (crowded) or ready to turn.
                4. **Forecast upcoming news data:** Predict if the upcoming events on the economic calendar will beat, meet, or miss consensus expectations based on recent trend patterns and asset behavior. For each prediction, you MUST include the SPECIFIC DATE and TIME of the release in Cambodia Time (UTC+7, as retrieved by your tools).
                5. **Do not include any trading entry/exit levels or stop-losses.** Focus purely on deep, high-level analysis and data forecasts.
                
                **OUTPUT FORMAT:**
                You must output the final report in two distinct parts, separated by the exact delimiter `---KHMER_SECTION---` as shown below:
                
                # Analyst Executive Summary
                [A simple, easy-to-read overview of the macro outlook in layman's terms...]
                
                # Detailed Macro Analysis
                [English Report Contents...]
                ---KHMER_SECTION---
                [Khmer Translation of the Report Contents...]
                """),
            expected_output="A dual-language report containing a detailed English section starting with a simple Analyst Executive Summary, followed by a Khmer translation, separated by the delimiter ---KHMER_SECTION---.",
            agent=agent
        )
