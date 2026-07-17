"""
One-time migration: Upload all local .md reports to Supabase.
Run this once from your local machine:  py -3.13 migrate_reports.py
"""
import os
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
REPORTS_DIR  = "reports"

if not SUPABASE_URL or not SUPABASE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_KEY must be set in your .env file.")
    exit(1)

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

files = sorted(
    [f for f in os.listdir(REPORTS_DIR) if f.endswith(".md")],
    key=lambda x: int(x.split("_")[-1].split(".")[0]) if "_" in x else 0
)

if not files:
    print("No .md files found in reports/ folder.")
    exit(0)

print(f"Found {len(files)} reports to migrate...\n")

for filename in files:
    path = os.path.join(REPORTS_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    try:
        res = supabase.table("reports").upsert(
            {"filename": filename, "content": content},
            on_conflict="filename"
        ).execute()
        print(f"  Migrated: {filename}")
    except Exception as e:
        print(f"  Failed:   {filename} -- {e}")

print("\nMigration complete!")
