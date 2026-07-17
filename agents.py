from crewai import Agent
from tools import MacroTools
import os
from dotenv import load_dotenv

load_dotenv()

# We use the native CrewAI/LiteLLM string format for Gemini
# CrewAI will automatically find GEMINI_API_KEY in the environment variables
GEMINI_MODEL = "gemini/gemini-3.1-flash-lite"

class MacroAgents:
    
    def macro_analyst_agent(self):
        return Agent(
            role='Macro Data Analyst',
            goal='Gather macroeconomic indicators, economic calendars, and global geopolitical reports.',
            backstory='You are a junior analyst focused on systemic macroeconomic data. You pull all FRED stats, Yahoo economic calendars, and Geopolitical briefs using your unified macro tool.',
            tools=[
                MacroTools.gather_all_macro_fundamentals
            ],
            llm=GEMINI_MODEL,
            verbose=True,
            allow_delegation=False
        )

    def asset_analyst_agent(self):
        return Agent(
            role='Asset Data Analyst',
            goal='Monitor price actions and specific news narratives for Gold (GC=F) and the US Dollar Index (DX-Y.NYB).',
            backstory='You are an execution-desk analyst. You monitor exchange prices and headlines using your unified asset tool.',
            tools=[
                MacroTools.gather_asset_prices_and_headlines
            ],
            llm=GEMINI_MODEL,
            verbose=True,
            allow_delegation=False
        )

    def flows_analyst_agent(self):
        return Agent(
            role='Flows & Positioning Analyst',
            goal='Check the flow of money in the market, including Commitments of Traders (COT) and institutional liquidity moves.',
            backstory='You are a flows specialist. You track where the "smart money" is positioning by analyzing CFTC reports and tracing big fund movements or ETF inflows/outflows.',
            tools=[
                MacroTools.search_cot_and_flows
            ],
            llm=GEMINI_MODEL,
            verbose=True,
            allow_delegation=False
        )
        
    def macro_economist_agent(self):
        return Agent(
            role='Chief Macro Economist',
            goal='Analyze interest rate cycles, inflation pressures, and geopolitical tensions to define the overarching market regime.',
            backstory='You are a senior economist. You look at global monetary policies, credit cycles, and trade geopolitics to define if we are in stagflation, recession, growth, or recovery.',
            llm=GEMINI_MODEL,
            verbose=True,
            allow_delegation=False
        )
        
    def lead_asset_economist_agent(self):
        return Agent(
            role='Lead Asset Economist & Synthesizer',
            goal='Merge macro regimes with positioning flows and price actions to detail the Gold-Dollar relationship and forecast upcoming economic data directions.',
            backstory='You are the Lead Synthesizer. You read both the fundamental regime and the positioning flows. You detail how these forces play out on Gold and DXY, forecast the upcoming calendar events, and build the final report in English and Khmer.',
            llm=GEMINI_MODEL,
            verbose=True,
            allow_delegation=False
        )
