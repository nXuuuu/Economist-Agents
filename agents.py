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
            goal='Gather macroeconomic indicators (PMI, JOLTS, NFP, Retail Sales, CPI/PCE, Fed Funds Rate), economic calendars, and global geopolitical reports.',
            backstory='You are a junior analyst focused on systemic macroeconomic data. You pull all FRED indicator series, BLS stats, Yahoo economic calendars, and Geopolitical briefs using your unified macro tool.',
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
            goal='Analyze Phillips Curve dynamics (labor slack vs inflation), rate cycles, and the 6-step indicator transmission sequence to define the overarching market regime.',
            backstory=(
                'You are a senior macro economist trained in Phillips Curve theory (pi = pi_e - beta*(u - u_n) + v) and macroeconomic transmission chains. '
                'You evaluate how early business activity (PMI) and labor demand (JOLTS) lead payrolls (NFP) and consumer demand (Retail Sales), '
                'and how labor market tightness impacts inflation (CPI/PCE) and Federal Reserve interest rate policy.'
            ),
            llm=GEMINI_MODEL,
            verbose=True,
            allow_delegation=False
        )
        
    def lead_asset_economist_agent(self):
        return Agent(
            role='Lead Asset Economist & Synthesizer',
            goal='Merge Phillips Curve regime analysis with positioning flows and price actions to detail the Gold-Dollar relationship and forecast upcoming economic data directions.',
            backstory=(
                'You are the Lead Synthesizer. You connect fundamental transmission chains (PMI -> JOLTS -> NFP -> Retail Sales -> CPI/PCE -> Interest Rates) '
                'with institutional positioning flows. You detail how these macro forces drive Gold (GC=F) and DXY (DX-Y.NYB), forecast upcoming calendar events, '
                'and build the final bilingual executive report in English and Khmer.'
            ),
            llm=GEMINI_MODEL,
            verbose=True,
            allow_delegation=False
        )
