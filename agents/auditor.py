# agents/auditor.py
"""
Agent 6: The Performance Auditor.

Scans all generated blogs, searches Google (via Serper) for their target keywords,
and checks if the company's domain (invohydra.com) is ranking in the top 100.

Flags blogs that are stuck on Page 2 (Rank 11-20) for a "Content Refresh".
"""

import os
import sys
import json
import time
import requests
from typing import Dict, Any

# Make the project root importable when run directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_project_root, ".env"))

TARGET_DOMAIN = "invohydra.com"
BLOGS_DIR = os.path.join(_project_root, "data", "blogs")
REPORT_PATH = os.path.join(_project_root, "data", "audit_report.json")

def check_rank(keyword: str) -> Dict[str, Any]:
    """
    Fetches top 100 organic Google results for the keyword.
    Returns the rank (position) of TARGET_DOMAIN, and the specific URL ranking.
    """
    serper_key = os.getenv("SERPER_API_KEY")
    if not serper_key:
        print("⚠️ SERPER_API_KEY is not set. Cannot run Auditor.")
        return {"rank": -1, "url": None}

    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": serper_key,
        "Content-Type": "application/json"
    }
    payload = {
        "q": keyword,
        "gl": "in",
        "hl": "en",
        "num": 100  # Request top 100 to see deep rankings
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        response.raise_for_status()
        organic_results = response.json().get("organic", [])
        
        for result in organic_results:
            link = result.get("link", "")
            if TARGET_DOMAIN in link:
                return {
                    "rank": result.get("position", -1),
                    "url": link
                }
        return {"rank": -1, "url": None}
    except Exception as e:
        print(f"      ⚠️ Serper API error for '{keyword}': {e}")
        return {"rank": -1, "url": None}

def run_auditor():
    print("\n" + "═"*60)
    print("  🕵️  AGENT 6: PERFORMANCE AUDITOR")
    print("═"*60)
    
    if not os.path.exists(BLOGS_DIR):
        print(f"⚠️ No blogs found in {BLOGS_DIR}. Have you run the pipeline yet?")
        return

    blog_files = [f for f in os.listdir(BLOGS_DIR) if f.endswith('.json')]
    if not blog_files:
        print("⚠️ No JSON blog files found. Exiting.")
        return

    print(f"📄 Found {len(blog_files)} published blogs. Checking live Google rankings...")
    print(f"🎯 Target Domain: {TARGET_DOMAIN}\n")

    report = {
        "top_10": [],
        "page_2_refresh": [],
        "not_found_or_deep": []
    }

    for idx, filename in enumerate(blog_files, 1):
        filepath = os.path.join(BLOGS_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                blog_data = json.load(f)
            except Exception as e:
                print(f"⚠️ Error reading {filename}: {e}")
                continue
        
        # Try to use target_keyword (new format), fallback to meta_title (old format)
        keyword = blog_data.get("target_keyword", blog_data.get("meta_title", ""))
        if not keyword:
            continue

        print(f"🔍 [{idx}/{len(blog_files)}] Checking keyword: \"{keyword}\"")
        result = check_rank(keyword)
        rank = result["rank"]
        url = result["url"]

        entry = {
            "keyword": keyword,
            "filename": filename,
            "rank": rank,
            "url": url
        }

        if rank == -1:
            print("   ↳ ❌ Not found in Top 100.")
            report["not_found_or_deep"].append(entry)
        elif rank <= 10:
            print(f"   ↳ ✅ SUCCESS: Ranked #{rank} on Page 1! ({url})")
            report["top_10"].append(entry)
        elif 11 <= rank <= 20:
            print(f"   ↳ ⚠️ REFRESH NEEDED: Stuck at #{rank} on Page 2. ({url})")
            report["page_2_refresh"].append(entry)
        else:
            print(f"   ↳ 🐢 Deep ranking: #{rank}. Needs backlinks/time.")
            report["not_found_or_deep"].append(entry)
            
        # Rate limiting Serper
        time.sleep(1.5)

    # Save report
    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n" + "═"*60)
    print("  📊  AUDIT COMPLETE")
    print("═"*60)
    print(f"  🏆 Top 10 (Page 1): {len(report['top_10'])}")
    print(f"  🔄 Needs Refresh (Page 2): {len(report['page_2_refresh'])}")
    print(f"  👻 Not Found/Deep: {len(report['not_found_or_deep'])}")
    print(f"\n💾 Report saved to: {REPORT_PATH}")

if __name__ == "__main__":
    run_auditor()
