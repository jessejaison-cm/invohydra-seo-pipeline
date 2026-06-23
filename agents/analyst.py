# agents/analyst.py
"""
Agent 2: The Difficulty Analyst.

Analyzes SEO competition for each keyword discovered by Agent 1.
Discards keywords where giant authority domains dominate the top 10
Google results — because a new/growing site can't realistically outrank them.

Only "winnable" keywords pass through to Agent 3 (Clusterer).

Pipeline:
  Keywords from Agent 1
      ↓
  For each keyword → Serper API (fetch top 10 organic results)
      ↓
  Extract domains from top 10 results
      ↓
  Score against authority domain blacklist
      ↓
  PASS  → keyword is winnable (few/no giants in top 10)
  MAYBE → borderline (some giants present, human review recommended)
  FAIL  → keyword is too competitive (giants dominate top 10)
      ↓
  Output: surviving keywords + full difficulty report JSON
"""

import sys
import os

# Makes the project root importable when run directly.
# e.g.  python agents/analyst.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_project_root, ".env"))


import json
import time
import requests
from typing import List, Dict, Any, Tuple
from urllib.parse import urlparse


# ──────────────────────────────────────────────────────────────────────────────
# AUTHORITY DOMAIN BLACKLIST
# These are high-DA domains that consistently rank top 3 for most keywords.
# If too many of these appear in a keyword's top 10, we can't realistically
# compete — especially as a newer/growing SaaS product.
# ──────────────────────────────────────────────────────────────────────────────

# Tier 1 — Absolute giants. One of these in top 3 = very hard to beat.
TIER_1_DOMAINS = {
    # Global mega-authority
    "forbes.com", "hubspot.com", "investopedia.com", "nerdwallet.com",
    "businessinsider.com", "techcrunch.com", "zdnet.com",
    # Indian GST/tax authority sites
    "gst.gov.in", "incometax.gov.in", "cbic.gov.in",
    # Big Indian finance/compliance media
    "cleartax.in", "taxmanagementindia.com", "taxguru.in", "caclubindia.com",
    # Dominant Indian billing software competitors with massive content teams
    "tallysolutions.com", "zoho.com", "quickbooks.intuit.com",
}

# Tier 2 — Strong competitors. Several in top 10 = difficult but not impossible.
TIER_2_DOMAINS = {
    # Indian business/finance media
    "economictimes.indiatimes.com", "livemint.com", "moneycontrol.com",
    "financialexpress.com", "business-standard.com", "thehindu.com",
    # Indian GST/accounting blogs with huge content libraries
    "bankbazaar.com", "paisabazaar.com", "indiafilings.com",
    "vakilsearch.com", "legalraasta.com", "bajajfinserv.in",
    # SaaS review/comparison sites
    "g2.com", "capterra.com", "getapp.com", "softwaresuggest.com",
    "techjockey.com", "trustradius.com",
    # Indian billing software competitors
    "vyapar.in", "profitbooks.net", "marg erp.in",
}

# Scoring weights
TIER_1_WEIGHT = 3   # Each Tier 1 domain in top 10 adds 3 difficulty points
TIER_2_WEIGHT = 1   # Each Tier 2 domain in top 10 adds 1 difficulty point

# Thresholds (out of a max possible score)
PASS_THRESHOLD  = 3   # Score ≤ 3  → PASS  (winnable)
MAYBE_THRESHOLD = 7   # Score ≤ 7  → MAYBE (borderline)
                       # Score > 7  → FAIL  (too competitive)


# ──────────────────────────────────────────────────────────────────────────────
# STEP 1: FETCH SERP FOR A SINGLE KEYWORD
# ──────────────────────────────────────────────────────────────────────────────

def fetch_serp(keyword: str) -> List[Dict[str, Any]]:
    """
    Fetches the top 10 organic Google results for a keyword via Serper API.

    Returns a list of organic result dicts, each containing at minimum:
      - 'link': the result URL
      - 'title': the page title
      - 'position': rank (1-10)

    Returns empty list on failure (pipeline continues without crashing).
    """
    serper_key = os.getenv("SERPER_API_KEY")
    if not serper_key:
        raise ValueError("SERPER_API_KEY is not set in your .env file.")

    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": serper_key,
        "Content-Type": "application/json"
    }
    payload = {
        "q": keyword,
        "gl": "in",    # India — same geo as Agent 1 for consistency
        "hl": "en",
        "num": 10
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json().get("organic", [])
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "unknown"
        print(f"      ⚠️  Serper HTTP error {status} for '{keyword}': {e}")
        return []
    except requests.exceptions.Timeout:
        print(f"      ⚠️  Serper timeout for '{keyword}'. Skipping.")
        return []
    except Exception as e:
        print(f"      ⚠️  Unexpected error for '{keyword}': {e}")
        return []


# ──────────────────────────────────────────────────────────────────────────────
# STEP 2: EXTRACT AND SCORE DOMAINS
# ──────────────────────────────────────────────────────────────────────────────

def extract_domain(url: str) -> str:
    """
    Extracts the base domain from a URL, stripping www. prefix.

    Examples:
      "https://www.forbes.com/article/..."  → "forbes.com"
      "https://cleartax.in/s/gst-billing"  → "cleartax.in"
    """
    try:
        parsed = urlparse(url)
        domain = parsed.netloc.lower()
        # Strip www. and any other subdomain prefix
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def score_keyword(organic_results: List[Dict[str, Any]]) -> Tuple[int, List[str], List[str]]:
    """
    Scores the difficulty of a keyword based on the authority of domains
    appearing in its top 10 organic results.

    Returns:
        score       — integer difficulty score (higher = harder)
        tier1_hits  — list of Tier 1 domains found in top 10
        tier2_hits  — list of Tier 2 domains found in top 10
    """
    score = 0
    tier1_hits = []
    tier2_hits = []

    for result in organic_results:
        domain = extract_domain(result.get("link", ""))
        if not domain:
            continue

        if domain in TIER_1_DOMAINS:
            score += TIER_1_WEIGHT
            tier1_hits.append(domain)
        elif domain in TIER_2_DOMAINS:
            score += TIER_2_WEIGHT
            tier2_hits.append(domain)

    return score, tier1_hits, tier2_hits


def get_verdict(score: int) -> str:
    """
    Converts a numeric difficulty score into a human-readable verdict.

      PASS  → Low competition. InvoHydra can realistically rank for this.
      MAYBE → Moderate competition. Winnable with strong content.
      FAIL  → High competition. Giants dominate. Skip this keyword.
    """
    if score <= PASS_THRESHOLD:
        return "PASS"
    elif score <= MAYBE_THRESHOLD:
        return "MAYBE"
    else:
        return "FAIL"


# ──────────────────────────────────────────────────────────────────────────────
# STEP 3: ANALYSE ALL KEYWORDS
# ──────────────────────────────────────────────────────────────────────────────

def analyse_keywords(keywords: List[str], delay: float = 1.5) -> Dict[str, Any]:
    """
    Runs difficulty analysis on every keyword.

    For each keyword:
      1. Fetches top 10 Google results via Serper
      2. Extracts domains and scores against authority blacklist
      3. Assigns PASS / MAYBE / FAIL verdict

    Args:
        keywords: List of keyword strings from Agent 1
        delay:    Seconds to wait between Serper API calls (avoids rate limiting)

    Returns a structured dict:
    {
        "surviving_keywords": [...],   ← PASS + MAYBE keywords (go to Agent 3)
        "passed": [...],               ← PASS only
        "maybe": [...],                ← MAYBE only (borderline)
        "failed": [...],               ← FAIL (discarded)
        "full_report": [...]           ← detailed per-keyword analysis
    }
    """
    print(f"\n   Analysing {len(keywords)} keywords — this calls Serper once per keyword.")
    print(f"   Delay between calls: {delay}s  |  Est. time: ~{int(len(keywords) * delay)}s\n")

    full_report  = []
    passed       = []
    maybe        = []
    failed       = []

    for i, keyword in enumerate(keywords, 1):
        print(f"   [{i:02}/{len(keywords):02}] 🔍  \"{keyword}\"")

        # Fetch SERP
        organic_results = fetch_serp(keyword)

        if not organic_results:
            # If Serper failed, give benefit of the doubt — treat as PASS
            print(f"          ↳ No results returned. Defaulting to PASS.")
            verdict = "PASS"
            score   = 0
            tier1_hits = []
            tier2_hits = []
            top_domains = []
        else:
            score, tier1_hits, tier2_hits = score_keyword(organic_results)
            verdict = get_verdict(score)
            top_domains = [
                extract_domain(r.get("link", ""))
                for r in organic_results[:5]
                if r.get("link")
            ]

        # Visual verdict indicator
        indicator = {"PASS": "✅", "MAYBE": "⚠️ ", "FAIL": "❌"}[verdict]
        print(f"          ↳ {indicator} {verdict}  |  Score: {score}  "
              f"|  Tier1: {tier1_hits or 'none'}  "
              f"|  Tier2: {tier2_hits or 'none'}")

        # Build per-keyword report entry
        report_entry = {
            "keyword":    keyword,
            "verdict":    verdict,
            "score":      score,
            "tier1_hits": tier1_hits,
            "tier2_hits": tier2_hits,
            "top_5_domains": top_domains,
            "reason": _build_reason(verdict, score, tier1_hits, tier2_hits)
        }
        full_report.append(report_entry)

        # Sort into buckets
        if verdict == "PASS":
            passed.append(keyword)
        elif verdict == "MAYBE":
            maybe.append(keyword)
        else:
            failed.append(keyword)

        # Polite delay between API calls
        if i < len(keywords):
            time.sleep(delay)

    # PASS + MAYBE both proceed to Agent 3
    surviving_keywords = passed + maybe

    return {
        "surviving_keywords": surviving_keywords,
        "passed":             passed,
        "maybe":              maybe,
        "failed":             failed,
        "full_report":        full_report
    }


def _build_reason(verdict: str, score: int, tier1_hits: List[str], tier2_hits: List[str]) -> str:
    """Generates a human-readable explanation for the verdict."""
    if verdict == "PASS":
        if score == 0:
            return "No major authority domains in top 10. High opportunity for InvoHydra."
        return f"Low authority presence (score={score}). Winnable with quality content."
    elif verdict == "MAYBE":
        parts = []
        if tier1_hits:
            parts.append(f"Tier 1 domains present: {', '.join(tier1_hits)}")
        if tier2_hits:
            parts.append(f"Tier 2 domains present: {', '.join(tier2_hits)}")
        return f"Moderate competition (score={score}). {' | '.join(parts)}. Winnable with strong content."
    else:
        parts = []
        if tier1_hits:
            parts.append(f"Tier 1 giants: {', '.join(tier1_hits)}")
        if tier2_hits:
            parts.append(f"Tier 2 strong: {', '.join(tier2_hits)}")
        return f"Too competitive (score={score}). {' | '.join(parts)}. Unlikely to rank page 1."


# ──────────────────────────────────────────────────────────────────────────────
# MAIN ORCHESTRATOR
# ──────────────────────────────────────────────────────────────────────────────

def filter_by_difficulty(
    keywords: List[str],
    report_output_path: str = None,
    keywords_output_path: str = None,
    delay: float = 1.5
) -> List[str]:
    """
    Agent 2 main function.

    Takes keywords from Agent 1, analyses each one's SEO difficulty,
    and returns only the winnable ones for Agent 3.

    Args:
        keywords:             List of keywords from Agent 1
        report_output_path:   Path to save the full difficulty report JSON
        keywords_output_path: Path to save just the surviving keyword list
        delay:                Seconds between Serper calls (default 1.5s)

    Returns:
        List of surviving keyword strings (PASS + MAYBE verdicts only).
    """
    print(f"\n{'─'*60}")
    print(f"📊   AGENT 2 — DIFFICULTY ANALYST")
    print(f"{'─'*60}")
    print(f"📥  Input: {len(keywords)} keywords from Agent 1")
    print(f"\n   Scoring system:")
    print(f"   • Tier 1 domain in top 10 → +{TIER_1_WEIGHT} points each")
    print(f"   • Tier 2 domain in top 10 → +{TIER_2_WEIGHT} point each")
    print(f"   • Score ≤ {PASS_THRESHOLD}  → ✅ PASS  (proceed to Agent 3)")
    print(f"   • Score ≤ {MAYBE_THRESHOLD}  → ⚠️  MAYBE (proceed with caution)")
    print(f"   • Score > {MAYBE_THRESHOLD}  → ❌ FAIL  (discard)")

    if not keywords:
        print("⚠️  No keywords to analyse. Exiting Agent 2.")
        return []

    # ── Run analysis ───────────────────────────────────────────────────────
    results = analyse_keywords(keywords, delay=delay)

    # ── Print summary ──────────────────────────────────────────────────────
    total    = len(keywords)
    n_passed = len(results["passed"])
    n_maybe  = len(results["maybe"])
    n_failed = len(results["failed"])
    n_surviving = len(results["surviving_keywords"])

    print(f"\n{'─'*60}")
    print(f"📊  DIFFICULTY ANALYSIS SUMMARY")
    print(f"{'─'*60}")
    print(f"   Total analysed:  {total}")
    print(f"   ✅ PASS:         {n_passed}  (low competition)")
    print(f"   ⚠️  MAYBE:        {n_maybe}  (moderate — review recommended)")
    print(f"   ❌ FAIL:         {n_failed}  (discarded — too competitive)")
    print(f"   ─────────────────────────────")
    print(f"   🎯 Surviving:    {n_surviving}  keywords proceed to Agent 3")

    if results["failed"]:
        print(f"\n   Discarded keywords:")
        for kw in results["failed"]:
            entry = next(r for r in results["full_report"] if r["keyword"] == kw)
            print(f"      ✗ \"{kw}\"")
            print(f"        → {entry['reason']}")

    if results["maybe"]:
        print(f"\n   ⚠️  Borderline keywords (proceeding but review recommended):")
        for kw in results["maybe"]:
            entry = next(r for r in results["full_report"] if r["keyword"] == kw)
            print(f"      ? \"{kw}\"")
            print(f"        → {entry['reason']}")

    # ── Save full report ───────────────────────────────────────────────────
    if report_output_path:
        os.makedirs(
            os.path.dirname(report_output_path) if os.path.dirname(report_output_path) else ".",
            exist_ok=True
        )
        report_data = {
            "summary": {
                "total_analysed":   total,
                "passed":           n_passed,
                "maybe":            n_maybe,
                "failed":           n_failed,
                "surviving":        n_surviving,
            },
            "scoring_config": {
                "tier1_weight":     TIER_1_WEIGHT,
                "tier2_weight":     TIER_2_WEIGHT,
                "pass_threshold":   PASS_THRESHOLD,
                "maybe_threshold":  MAYBE_THRESHOLD,
            },
            "surviving_keywords":   results["surviving_keywords"],
            "passed":               results["passed"],
            "maybe":                results["maybe"],
            "failed":               results["failed"],
            "full_report":          results["full_report"],
        }
        with open(report_output_path, "w", encoding="utf-8") as f:
            json.dump(report_data, f, indent=2, ensure_ascii=False)
        print(f"\n💾  Full difficulty report saved to: {report_output_path}")

    # ── Save surviving keywords list ───────────────────────────────────────
    if keywords_output_path and results["surviving_keywords"]:
        os.makedirs(
            os.path.dirname(keywords_output_path) if os.path.dirname(keywords_output_path) else ".",
            exist_ok=True
        )
        with open(keywords_output_path, "w", encoding="utf-8") as f:
            json.dump(results["surviving_keywords"], f, indent=2, ensure_ascii=False)
        print(f"💾  Surviving keywords saved to:      {keywords_output_path}")

    return results["surviving_keywords"]


# ──────────────────────────────────────────────────────────────────────────────
# STANDALONE TEST MODE
# Run directly to test Agent 2 in isolation:
#   python agents/analyst.py
#   python agents/analyst.py data/discovered_keywords.json
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Load keywords from file argument or default discovered_keywords.json
    input_path = sys.argv[1] if len(sys.argv) > 1 else "data/discovered_keywords.json"

    if not os.path.exists(input_path):
        print(f"❌  Input file not found: {input_path}")
        print(f"    Run Agent 1 first:  python agents/discoverer.py")
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        keywords = json.load(f)

    print(f"📂  Loaded {len(keywords)} keywords from: {input_path}")

    surviving = filter_by_difficulty(
        keywords=keywords,
        report_output_path="data/difficulty_report.json",
        keywords_output_path="data/filtered_keywords.json",
        delay=1.5
    )

    print(f"\n🎉  Agent 2 standalone run complete.")
    print(f"    {len(surviving)} keywords passed difficulty filter.")
    print(f"    Ready for Agent 3:  python agents/planner.py")
