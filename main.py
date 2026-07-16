from crewai import Crew, Process
from agents import MacroAgents
from tasks import MacroTasks
from dotenv import load_dotenv
import sys
import os
from fpdf import FPDF
from supabase import create_client, Client

def upload_to_supabase(filename, content):
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        print("\nSupabase credentials not configured. Skipping DB storage.")
        return
    try:
        supabase: Client = create_client(url, key)
        supabase.table('reports').insert({
            "filename": filename,
            "content": content
        }).execute()
        print(f"\nSuccessfully stored report in Supabase table 'reports'")
    except Exception as e:
        print(f"\nError uploading report to Supabase: {e}")

def generate_markdown_report(result_text):
    print("\nGenerating Markdown Report...")
    
    # Split the report into English and Khmer
    parts = result_text.split("---KHMER_SECTION---")
    english_content = parts[0].strip() if len(parts) > 0 else result_text
    khmer_content = parts[1].strip() if len(parts) > 1 else ""
    
    # Create the reports folder if it doesn't exist
    reports_dir = "reports"
    os.makedirs(reports_dir, exist_ok=True)
    
    # Find the next available incremental file name (e.g., reports/macro_report_1.md, macro_report_2.md)
    i = 1
    while True:
        md_path = os.path.join(reports_dir, f"macro_report_{i}.md")
        if not os.path.exists(md_path):
            break
        i += 1
        
    # Construct complete report text (both English and Khmer segments, if present)
    complete_report = "# Global Macro Analysis Report (Gold & DXY)\n\n"
    complete_report += "## English Version\n\n"
    complete_report += english_content
    if khmer_content:
        complete_report += "\n\n---\n\n"
        complete_report += "## ភាសាខ្មែរ (Khmer Version)\n\n"
        complete_report += khmer_content

    try:
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(complete_report)
        print(f"\nSuccessfully generated Markdown report: {md_path}")
    except Exception as e:
        print(f"\nError saving Markdown: {e}")

    # Also upload to Supabase if configured!
    upload_to_supabase(f"macro_report_{i}.md", complete_report)


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    load_dotenv()
    
    print("Welcome to the 5-Agent Macro Research Desk")
    print("------------------------------------------")
    
    # Target assets: Gold (GC=F) and US Dollar Index (DX-Y.NYB)
    target_assets = ["GC=F", "DX-Y.NYB"]
    print(f"Target Assets: {target_assets}")
    
    # Initialize agents and tasks
    agents = MacroAgents()
    tasks = MacroTasks()
    
    # Create the 5 agents
    macro_analyst = agents.macro_analyst_agent()
    asset_analyst = agents.asset_analyst_agent()
    flows_analyst = agents.flows_analyst_agent()
    macro_economist = agents.macro_economist_agent()
    lead_economist = agents.lead_asset_economist_agent()
    
    # Create the 5 tasks
    task1 = tasks.gather_macro_data_task(macro_analyst)
    task2 = tasks.gather_asset_data_task(asset_analyst, target_assets)
    task3 = tasks.gather_positioning_flows_task(flows_analyst)
    task4 = tasks.analyze_macro_regime_task(macro_economist)
    task5 = tasks.synthesize_and_forecast_task(lead_economist)
    
    # Assemble the crew sequentially
    macro_crew = Crew(
        agents=[
            macro_analyst, 
            asset_analyst, 
            flows_analyst, 
            macro_economist, 
            lead_economist
        ],
        tasks=[task1, task2, task3, task4, task5],
        process=Process.sequential,
        verbose=True
    )
    
    print("\nStarting the 5-Agent Macro Research Process...\n")
    
    # Kickoff the crew
    result = macro_crew.kickoff()
    
    print("\n==============================================")
    print("FINAL MACRO RESEARCH REPORT")
    print("==============================================\n")
    print(result)
    
    # Generate the dual-language Markdown report
    generate_markdown_report(str(result))

if __name__ == "__main__":
    main()
