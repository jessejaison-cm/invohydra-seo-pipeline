# main.py
"""
Main execution script for the InvoHydra SEO Pipeline.

Current agent flow:
  Agent 1 (Keyword Discoverer)
      ↓
  Agent 2 (Difficulty Analyst)
      ↓
  Agent 3 (Semantic Clusterer)
      ↓
  Agent 4 (Blog Writer)
      ↓
  Agent 4.5 (Illustrator)  ← NEW
      ↓
  Agent 5 (Auto-Publisher)
"""

import os
import json
import argparse
from datetime import date
from agents.discoverer import discover_keywords
from agents.analyst import analyse_keywords
from agents.planner import load_keywords, load_feature_truth, cluster_keywords
from agents.writer import generate_all_blogs
from agents.illustrator import illustrate_blogs
from agents.publisher import publish_blogs
from config import SEED_TOPICS

# ──────────────────────────────────────────────────────────────────────────────
# PIPELINE CONFIGURATION
# Edit these paths to match your project layout.
# ──────────────────────────────────────────────────────────────────────────────
MANUAL_KEYWORDS_PATH    = "data/manual_keywords.json"
DISCOVERED_KEYWORDS_PATH = "data/discovered_keywords.json"
FEATURES_PATH           = "data/feature_truth.json"
CLUSTERS_OUTPUT_PATH    = "data/clustered_keywords.json"
BLOGS_DIR               = "data/blogs"
STATE_FILE_PATH         = "data/pipeline_state.json"

# Set to True to skip Agent 1 and use manual_keywords.json instead
USE_MANUAL_KEYWORDS = False
# ──────────────────────────────────────────────────────────────────────────────


def get_rotating_topic(topics_pool: list) -> str:
    """
    Implements stateful rotation of topics.
    Tracks the active topic index in a local state JSON file.
    Advances to the next topic on every successful run.
    """
    if not topics_pool:
        raise ValueError("SEED_TOPICS list in config.py is empty.")

    os.makedirs("data", exist_ok=True)
    today = date.today()
    
    # Default initial state
    state = {
        "current_topic_index": 0,
        "last_topic_change_date": today.isoformat()
    }
    
    if os.path.exists(STATE_FILE_PATH):
        try:
            with open(STATE_FILE_PATH, "r", encoding="utf-8") as f:
                loaded_state = json.load(f)
                if isinstance(loaded_state, dict):
                    state["current_topic_index"] = int(loaded_state.get("current_topic_index", 0))
                    state["last_topic_change_date"] = str(loaded_state.get("last_topic_change_date", today.isoformat()))
        except Exception as e:
            print(f"⚠️  Could not read state file: {e}. Resetting state.")

    # Bounds check index in case the pool size was reduced
    old_idx = state["current_topic_index"]
    if old_idx >= len(topics_pool):
        old_idx = 0

    # Advance the index to the next topic for the next run
    new_idx = (old_idx + 1) % len(topics_pool)
    state["current_topic_index"] = new_idx
    state["last_topic_change_date"] = today.isoformat()
    
    try:
        with open(STATE_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
        print(f"🔄  Topic rotation: Advanced topic index from {old_idx} to {new_idx}.")
    except Exception as e:
        print(f"⚠️  Could not write state file: {e}")

    selected_topic = topics_pool[old_idx]
    print(f"💡  Active topic selected: \"{selected_topic}\" (Index {old_idx} of {len(topics_pool)})")
    return selected_topic


def run_agent_1(topics_to_run: list) -> list:
    """
    Runs Agent 1 across all configured SEED_TOPICS.
    Deduplicates keywords across topics and saves to DISCOVERED_KEYWORDS_PATH.
    Returns the combined keyword list.
    """
    print("\n" + "═"*60)
    print("  PHASE 1 — AGENT 1: KEYWORD DISCOVERER")
    print("═"*60)
    print(f"  Seed topics configured: {len(topics_to_run)}")
    for i, topic in enumerate(topics_to_run, 1):
        print(f"  {i}. {topic}")

    all_discovered = []

    for seed in topics_to_run:
        discovered = discover_keywords(seed_topic=seed)
        all_discovered.extend(discovered)

    # Deduplicate across all seed topics while preserving order
    seen = set()
    unique_keywords = []
    for kw in all_discovered:
        normalized = kw.lower().strip()
        if normalized not in seen:
            seen.add(normalized)
            unique_keywords.append(kw)

    print(f"\n📊  Combined total across {len(topics_to_run)} seed topics: {len(unique_keywords)} unique keywords")

    if unique_keywords:
        os.makedirs("data", exist_ok=True)
        with open(DISCOVERED_KEYWORDS_PATH, "w", encoding="utf-8") as f:
            json.dump(unique_keywords, f, indent=2, ensure_ascii=False)
        print(f"💾  All discovered keywords saved to: {DISCOVERED_KEYWORDS_PATH}")

    return unique_keywords


def run_agent_2(keywords: list) -> list:
    """
    Runs Agent 2: Analyzes keywords and filters out difficult ones.
    Saves analysis report to data/difficulty_report.json.
    Returns the surviving (winnable) keywords.
    """
    print("\n" + "═"*60)
    print("  PHASE 2 — AGENT 2: DIFFICULTY ANALYST")
    print("═"*60)
    
    if not keywords:
        print("⚠️  No keywords passed to Agent 2. Skipping analysis.")
        return []

    report = analyse_keywords(keywords)
    surviving = report.get("surviving_keywords", [])
    report_path = "data/difficulty_report.json"
    
    os.makedirs("data", exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        
    print(f"\n📊  Analyst Results:")
    print(f"  ├── Passed: {len(report.get('passed', []))}")
    print(f"  ├── Maybe (Borderline): {len(report.get('maybe', []))}")
    print(f"  └── Failed (Too Hard): {len(report.get('failed', []))}")
    print(f"💾  Full difficulty report saved to: {report_path}")
    print(f"✅  Passing {len(surviving)} winnable keywords to Phase 3.")
    
    return surviving


def run_agent_3(keywords: list) -> dict:
    """
    Runs Agent 3: clusters keywords against the feature truth map.
    Saves output to CLUSTERS_OUTPUT_PATH.
    """
    print("\n" + "═"*60)
    print("  PHASE 3 — AGENT 3: SEMANTIC INTENT CLUSTERER")
    print("═"*60)

    print(f"📦  Loading feature capabilities map from: {FEATURES_PATH}")
    features = load_feature_truth(FEATURES_PATH)

    print(f"🧠  Clustering {len(keywords)} keywords against feature truth map...")
    results = cluster_keywords(keywords, features)

    os.makedirs("data", exist_ok=True)
    with open(CLUSTERS_OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    cluster_count  = len(results.get("clusters", []))
    rejected_count = len(results.get("rejected_keywords", []))
    print(f"✅  Clustered into {cluster_count} topic clusters.")
    print(f"🚫  Rejected {rejected_count} keywords (capability violations).")
    print(f"💾  Saved to: {CLUSTERS_OUTPUT_PATH}")

    return results


def run_agent_4(limit: int = None) -> None:
    """Runs Agent 4: generates one blog post per cluster."""
    print("\n" + "═"*60)
    print("  PHASE 4 — AGENT 4: BLOG WRITER")
    print("═"*60)
    generate_all_blogs(CLUSTERS_OUTPUT_PATH, BLOGS_DIR, limit=limit)


def run_agent_4_5() -> None:
    """Runs Agent 4.5: Illustrates the generated blogs."""
    illustrate_blogs()


def run_agent_5() -> None:
    """Runs Agent 5: safely pushes generated blogs to the Landing Page repo."""
    # We call publish_blogs from publisher.py
    publish_blogs()


def main():
    parser = argparse.ArgumentParser(description="InvoHydra SEO Pipeline")
    parser.add_argument("--topic", type=str, help="Manually override the seed topic to generate keywords/blogs for.")
    parser.add_argument("--limit", type=int, default=2, help="Limit the number of blogs generated in this run (default: 2).")
    parser.add_argument("--force", action="store_true", help="Bypass daily and weekly frequency limits.")
    args = parser.parse_args()

    print("\n🚀  Starting InvoHydra SEO Pipeline...")
    
    # Load and check scheduling/frequency constraints
    today_str = date.today().isoformat()
    state = {}
    if os.path.exists(STATE_FILE_PATH):
        try:
            with open(STATE_FILE_PATH, "r", encoding="utf-8") as f:
                state = json.load(f)
        except Exception:
            state = {}
            
    generation_runs = state.get("generation_runs", [])
    
    # Clean up dates older than 7 days
    from datetime import timedelta
    seven_days_ago = date.today() - timedelta(days=7)
    valid_runs = []
    for run_date_str in generation_runs:
        try:
            run_date = date.fromisoformat(run_date_str)
            if run_date >= seven_days_ago:
                valid_runs.append(run_date_str)
        except ValueError:
            pass
            
    # Check frequency rules (unless --force is specified)
    if not args.force:
        if today_str in valid_runs:
            print(f"\n🛑 Pipeline run BLOCKED: Generation has already run today ({today_str}).")
            print("   ↳ Max 1 generation run (2 blogs) per day.")
            print("   ↳ Use --force to bypass this check.")
            return
            
        if len(valid_runs) >= 2:
            print(f"\n🛑 Pipeline run BLOCKED: Generation has already run twice in the last 7 days (Runs: {', '.join(valid_runs)}).")
            print("   ↳ Max 2 runs (4 blogs) per week.")
            print("   ↳ Use --force to bypass this check.")
            return
    else:
        print("⚠️  Bypassing scheduling/frequency checks (--force active).")

    if args.topic:
        print(f"🎯  Manual Override: Using provided seed topic: \"{args.topic}\"")
        topics_to_run = [args.topic]
    else:
        rotating_topic = get_rotating_topic(SEED_TOPICS)
        topics_to_run = [rotating_topic]

    # ── Phase 1: Keyword Discovery (Agent 1) ──────────────────────────────
    if USE_MANUAL_KEYWORDS:
        print(f"\n📦  USE_MANUAL_KEYWORDS=True — Loading from: {MANUAL_KEYWORDS_PATH}")
        keywords = load_keywords(MANUAL_KEYWORDS_PATH)
        print(f"✅  Loaded {len(keywords)} manual keywords.")
    else:
        keywords = run_agent_1(topics_to_run)

        if not keywords:
            # Graceful fallback if all Serper searches failed
            print(
                f"\n⚠️  Agent 1 returned no keywords. "
                f"Falling back to manual keywords at: {MANUAL_KEYWORDS_PATH}"
            )
            keywords = load_keywords(MANUAL_KEYWORDS_PATH)
            print(f"✅  Fallback loaded {len(keywords)} keywords.")

    # ── Phase 2: Difficulty Analyst (Agent 2) ─────────────────────────────
    winnable_keywords = run_agent_2(keywords)

    if not winnable_keywords:
        print("\n🛑  Pipeline stopped: No winnable keywords passed Agent 2.")
        return

    # ── Phase 3: Semantic Clustering (Agent 3) ────────────────────────────
    run_agent_3(winnable_keywords)

    # ── Phase 4: Blog Generation (Agent 4) ───────────────────────────────
    # Clean the blogs directory so we only publish what is generated in this specific run
    if os.path.exists(BLOGS_DIR):
        import shutil
        print(f"🧹 Cleaning blogs output directory: {BLOGS_DIR}")
        for filename in os.listdir(BLOGS_DIR):
            file_path = os.path.join(BLOGS_DIR, filename)
            try:
                if os.path.isfile(file_path) or os.path.islink(file_path):
                    os.unlink(file_path)
                elif os.path.isdir(file_path):
                    shutil.rmtree(file_path)
            except Exception as e:
                print(f"⚠️ Failed to delete {file_path}. Reason: {e}")
    else:
        os.makedirs(BLOGS_DIR, exist_ok=True)

    run_agent_4(limit=args.limit)


    # ── Phase 4.5: Illustrator (Agent 7) ─────────────────────────────────
    run_agent_4_5()

    # ── Phase 5: Auto-Publisher (Agent 5) ────────────────────────────────
    run_agent_5()

    # Record this successful generation run
    valid_runs.append(today_str)
    state["generation_runs"] = valid_runs
    state["last_run_date"] = today_str
    state["current_topic"] = topics_to_run[0]
    
    try:
        with open(STATE_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"⚠️ Could not update state file with run date: {e}")

    # ── Summary ───────────────────────────────────────────────────────────
    print("\n" + "═"*60)
    print("  🎉  PIPELINE RUN COMPLETE")
    print("═"*60)
    print(f"  ├── Discovered keywords → {DISCOVERED_KEYWORDS_PATH}")
    print(f"  ├── Clustered keywords  → {CLUSTERS_OUTPUT_PATH}")
    print(f"  └── Blog posts          → {BLOGS_DIR}/")
    print("═"*60)
    print("\nNext steps:")
    print("  • Review blogs:     python serve_blogs.py")
    print("  • Inject links:     python inject_hyperlinks.py")
    print("  • View discovered:  data/discovered_keywords.json\n")


if __name__ == "__main__":
    main()
