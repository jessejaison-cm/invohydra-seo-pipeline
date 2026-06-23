# agents/discoverer.py
"""
Agent 1: The Keyword Discoverer.

Automatically finds new, relevant long-tail keywords based on a broad seed topic.

Pipeline:
  Seed Topic
      ↓
  Serper API — Primary search (transactional query)
      ↓
  If PAA=0 and Related=0 → Secondary search (informational variant)
      ↓
  Extract PAA questions + Related Searches + Organic titles
      ↓
  Groq LLM filtering (remove junk, competitor brands, clean formatting)
      ↓
  Clean list of 10-20 long-tail keywords
"""

import sys
import os

# Makes the project root importable when this file is run directly.
# e.g.  python agents/discoverer.py
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import requests
from typing import List, Dict, Any
from config import GROQ_MODEL, TEMPERATURE


# ──────────────────────────────────────────────────────────────────────────────
# HELPER: INFORMATIONAL QUERY VARIANT
# ──────────────────────────────────────────────────────────────────────────────

def _to_informational_query(seed_topic: str) -> str:
    """
    Converts a transactional seed topic into an informational query
    that reliably triggers 'People Also Ask' and 'Related Searches' in Google.

    Why: PAA boxes appear for informational queries ("how to", "what is").
    Commercial topics like "GST billing software India" rarely produce PAA.

    Examples:
      "GST billing software for Indian MSMEs"
        → "how to choose GST billing software for Indian MSMEs"
      "invoice automation for SaaS companies India"
        → "how to choose invoice automation for SaaS companies India"
    """
    topic_lower = seed_topic.lower()
    # Already informational — don't wrap it again
    if any(topic_lower.startswith(w) for w in ["how", "what", "why", "when", "which", "best", "top"]):
        return seed_topic

    return f"how to choose {seed_topic}"


# ──────────────────────────────────────────────────────────────────────────────
# HELPER: GOOGLE AUTOCOMPLETE
# ──────────────────────────────────────────────────────────────────────────────

def get_google_autocomplete(query: str) -> List[str]:
    """
    Fetches autocomplete suggestions from Google for the given query.
    This provides excellent long-tail keywords that real users are typing.
    """
    url = f"http://suggestqueries.google.com/complete/search?client=chrome&q={query}"
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        if len(data) > 1 and isinstance(data[1], list):
            return data[1]
    except Exception as e:
        print(f"⚠️  Google Autocomplete failed: {e}")
    return []


# ──────────────────────────────────────────────────────────────────────────────
# STEP 1: SEARCH GOOGLE VIA SERPER API
# ──────────────────────────────────────────────────────────────────────────────

def search_seed_topic(seed_topic: str) -> Dict[str, Any]:
    """
    Calls the Serper API (Google Search wrapper) for the given seed topic.
    Uses India geo-targeting (gl=in) for accurate GST/billing-related results.

    Returns the full Serper JSON response which includes:
      - organic:          top 10 ranked pages
      - peopleAlsoAsk:   PAA questions (gold for long-tail keywords)
      - relatedSearches: related query suggestions
    """
    serper_key = os.getenv("SERPER_API_KEY")
    if not serper_key:
        raise ValueError(
            "SERPER_API_KEY is not set. "
            "Sign up at https://serper.dev (2,500 free searches) and add it to your .env file."
        )

    url = "https://google.serper.dev/search"
    headers = {
        "X-API-KEY": serper_key,
        "Content-Type": "application/json"
    }
    payload = {
        "q": seed_topic,
        "gl": "in",   # India geo-location — critical for GST/billing keyword accuracy
        "hl": "en",   # English results
        "num": 10     # Top 10 organic results
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "unknown"
        print(f"⚠️  Serper API HTTP error {status}: {e}")
        raise
    except requests.exceptions.Timeout:
        print("⚠️  Serper API timed out after 15s.")
        raise
    except requests.exceptions.ConnectionError:
        print("⚠️  Could not connect to Serper API. Check your internet connection.")
        raise


# ──────────────────────────────────────────────────────────────────────────────
# STEP 2: EXTRACT KEYWORD CANDIDATES FROM SERPER RESPONSE
# ──────────────────────────────────────────────────────────────────────────────

def extract_keyword_candidates(serper_data: Dict[str, Any]) -> List[str]:
    """
    Extracts raw keyword candidates from a Serper API response.

    Priority order (per architecture spec):
      1. 'People Also Ask' questions  ← best long-tail signals
      2. 'Related Searches'           ← strong search intent signals
      3. Organic result titles        ← supplementary signals

    Returns a deduplicated list of raw candidates.
    """
    candidates = []

    # ── 1. People Also Ask (PAA) ─────────────────────────────────────────────
    paa_items = serper_data.get("peopleAlsoAsk", [])
    paa_questions = [
        item.get("question", "").strip()
        for item in paa_items
        if item.get("question", "").strip()
    ]
    print(f"   ├── 'People Also Ask' questions found: {len(paa_questions)}")
    candidates.extend(paa_questions)

    # ── 2. Related Searches ───────────────────────────────────────────────────
    related_items = serper_data.get("relatedSearches", [])
    related_queries = [
        item.get("query", "").strip()
        for item in related_items
        if item.get("query", "").strip()
    ]
    print(f"   ├── 'Related Searches' found:           {len(related_queries)}")
    candidates.extend(related_queries)

    # ── 3. Organic result titles (supplementary) ─────────────────────────────
    organic_items = serper_data.get("organic", [])
    organic_titles = [
        item.get("title", "").strip()
        for item in organic_items[:5]
        if item.get("title", "").strip() and len(item.get("title", "")) < 100
    ]
    print(f"   └── Organic title signals:               {len(organic_titles)}")
    candidates.extend(organic_titles)

    # ── Deduplicate while preserving order ───────────────────────────────────
    seen = set()
    unique = []
    for c in candidates:
        normalized = c.lower().strip()
        if normalized not in seen and len(normalized) > 3:
            seen.add(normalized)
            unique.append(c)

    return unique


# ──────────────────────────────────────────────────────────────────────────────
# STEP 3: FILTER AND CLEAN WITH GROQ LLM
# ──────────────────────────────────────────────────────────────────────────────

def filter_keywords_with_llm(candidates: List[str], seed_topic: str) -> List[str]:
    """
    Sends raw keyword candidates to Groq LLM for intelligent filtering.

    The LLM:
      - Removes competitor brand names (Zoho, Tally, QuickBooks, etc.)
      - Removes irrelevant or overly generic phrases
      - Rewrites messy titles into clean, search-friendly keyword format
      - Outputs 10-20 high-quality long-tail keywords

    Falls back to returning the top 15 raw candidates (lowercased) if the API fails.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set in environment variables.")

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    system_prompt = (
        "You are an expert B2B SEO Keyword Analyst for InvoHydra — a GST billing, invoicing, "
        "and compliance SaaS platform built for Indian MSMEs and SaaS founders.\n\n"
        "You will receive raw keyword candidates extracted from Google Search results. "
        "Your job is to filter, clean, and select the best long-tail keywords.\n\n"
        "STRICT FILTERING RULES:\n"
        "1. ✅ KEEP: Long-tail keywords about GST billing, invoicing, tax compliance, "
        "recurring billing, or SaaS billing tools in India.\n"
        "2. ✅ KEEP: Real user questions or transactional search intents "
        "(e.g., 'how to file gstr-1', 'best invoice software for msme').\n"
        "3. ✅ REWRITE: Convert messy titles or full sentences into clean, "
        "search-friendly keyword format (lowercase, concise, 3-9 words).\n"
        "4. ❌ REMOVE: Any competitor brand names — Zoho, Tally, QuickBooks, Vyapar, "
        "ClearTax, FreshBooks, Khatabook, Marg, Busy, Biz Analyst, or similar.\n"
        "5. ❌ REMOVE: Irrelevant topics, news headlines, or content not about "
        "billing/invoicing/GST compliance.\n"
        "6. ❌ REMOVE: Single-word or two-word generic phrases (e.g., 'software', 'billing').\n"
        "7. ❌ REMOVE: Keywords longer than 10 words.\n\n"
        "OUTPUT RULES:\n"
        "- Return between 10 and 20 keywords.\n"
        "- All keywords must be lowercase.\n"
        "- Return ONLY a valid JSON object with a single key 'keywords' (list of strings).\n"
        "- No explanations, no preamble, no markdown wrapping — pure JSON only.\n\n"
        "Example: {\"keywords\": ["
        "\"gst invoice software for msme\", "
        "\"automated gst billing india\", "
        "\"recurring invoice api saas india\""
        "]}"
    )

    candidates_formatted = "\n".join(f"- {c}" for c in candidates)
    user_content = (
        f"Seed Topic: {seed_topic}\n\n"
        f"Raw Keyword Candidates ({len(candidates)} total):\n"
        f"{candidates_formatted}\n\n"
        f"Please filter and return 10-20 high-quality long-tail keywords as a JSON object."
    )

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "temperature": TEMPERATURE,
        "response_format": {"type": "json_object"}
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        raw_content = response.json()["choices"][0]["message"]["content"]
        parsed = json.loads(raw_content)
        keywords = parsed.get("keywords", [])

        if not keywords:
            print("⚠️  LLM returned empty keyword list. Using raw candidates as fallback.")
            return _fallback_clean(candidates)

        return keywords

    except requests.exceptions.HTTPError as e:
        print(f"⚠️  Groq API HTTP error: {e}. Using raw candidates as fallback.")
        return _fallback_clean(candidates)
    except json.JSONDecodeError as e:
        print(f"⚠️  Could not parse Groq JSON response: {e}. Using fallback.")
        return _fallback_clean(candidates)
    except Exception as e:
        print(f"⚠️  Unexpected LLM error: {e}. Using fallback.")
        return _fallback_clean(candidates)


def _fallback_clean(candidates: List[str]) -> List[str]:
    """
    Fallback: returns top 15 raw candidates, lowercased and stripped.
    Used when the LLM call fails so the pipeline still progresses.
    """
    return [c.lower().strip() for c in candidates[:15] if len(c.strip()) > 5]


# ──────────────────────────────────────────────────────────────────────────────
# MAIN ORCHESTRATOR
# ──────────────────────────────────────────────────────────────────────────────

def discover_keywords(seed_topic: str, output_path: str = None) -> List[str]:
    """
    Agent 1 main function.

    Takes a broad seed topic, searches Google via Serper (with an automatic
    informational-variant fallback search if PAA is empty), filters candidates
    with Groq LLM, and returns a clean list of 10-20 long-tail keywords.

    Args:
        seed_topic:  A broad search topic, e.g. "GST billing software for Indian MSMEs"
        output_path: Optional file path to save keywords as JSON

    Returns:
        List of 10-20 clean, long-tail keyword strings.
    """
    print(f"\n{'─'*60}")
    print(f"🕵️   AGENT 1 — KEYWORD DISCOVERER")
    print(f"{'─'*60}")
    print(f"📌  Seed Topic: \"{seed_topic}\"")

    # ── Step 1: Primary search (transactional query) ───────────────────────
    print(f"\n[1/3] 🔍  Primary search via Serper API...")
    try:
        serper_data = search_seed_topic(seed_topic)
    except Exception as e:
        print(f"❌  Primary search failed — cannot proceed for this seed topic.\n    Error: {e}")
        return []

    candidates = extract_keyword_candidates(serper_data)

    # ── Step 1b: Secondary search if PAA and Related Searches were empty ───
    # PAA boxes only trigger for informational queries ("how to", "what is").
    # Commercial/transactional seed topics often return PAA=0 and Related=0.
    # In that case, we run a second search with an informational variant to
    # unlock those high-value keyword signals before passing to the LLM.
    paa_count     = len(serper_data.get("peopleAlsoAsk", []))
    related_count = len(serper_data.get("relatedSearches", []))

    if paa_count == 0 and related_count == 0:
        informational_query = _to_informational_query(seed_topic)
        print(f"\n   ⚠️  PAA=0 and Related Searches=0 on primary search.")
        print(f"   🔄  Running informational variant: \"{informational_query}\"")

        try:
            serper_data_2 = search_seed_topic(informational_query)
            candidates_2  = extract_keyword_candidates(serper_data_2)

            paa_2     = len(serper_data_2.get("peopleAlsoAsk", []))
            related_2 = len(serper_data_2.get("relatedSearches", []))
            print(f"\n   ✅  Secondary search: PAA={paa_2}, Related={related_2}, "
                  f"New candidates={len(candidates_2)}")

            # Merge both searches, deduplicate, preserve order
            seen = set(c.lower().strip() for c in candidates)
            for c in candidates_2:
                if c.lower().strip() not in seen:
                    candidates.append(c)
                    seen.add(c.lower().strip())

        except Exception as e:
            print(f"   ⚠️  Secondary search failed: {e}. Continuing with primary results only.")

    # ── Step 1c: Google Autocomplete (Bonus candidates) ────────────────────
    print(f"\n   🔍  Fetching Google Autocomplete suggestions...")
    autocomplete_candidates = get_google_autocomplete(seed_topic)
    if autocomplete_candidates:
        print(f"   ✅  Autocomplete found {len(autocomplete_candidates)} suggestions.")
        seen = set(c.lower().strip() for c in candidates)
        for c in autocomplete_candidates:
            if c.lower().strip() not in seen:
                candidates.append(c)
                seen.add(c.lower().strip())

    # ── Step 2: Summary ────────────────────────────────────────────────────
    print(f"\n[2/3] 📊  Total unique candidates across all searches: {len(candidates)}")

    if not candidates:
        print(
            "⚠️  No candidates found. "
            "Try a different or broader seed topic."
        )
        return []

    # ── Step 3: LLM filtering ──────────────────────────────────────────────
    print(f"\n[3/3] 🧠  Filtering with Groq LLM (removing junk + competitor brands)...")
    keywords = filter_keywords_with_llm(candidates, seed_topic)

    # ── Print results ──────────────────────────────────────────────────────
    print(f"\n✅  Discovery complete — {len(keywords)} quality keywords found:")
    for i, kw in enumerate(keywords, 1):
        print(f"    {i:2}. {kw}")

    # ── Save output if path provided ───────────────────────────────────────
    if output_path and keywords:
        os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(keywords, f, indent=2, ensure_ascii=False)
        print(f"\n💾  Keywords saved to: {output_path}")

    return keywords


# ──────────────────────────────────────────────────────────────────────────────
# STANDALONE TEST MODE
# Run this file directly to test Agent 1 in isolation:
#   python agents/discoverer.py
#   python agents/discoverer.py "best GST billing software for Indian MSMEs"
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    seed = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "best GST billing software for Indian MSMEs"

    result = discover_keywords(
        seed_topic=seed,
        output_path="data/discovered_keywords.json"
    )

    print(f"\n🎉  Agent 1 standalone run complete.")
    print(f"    {len(result)} keywords ready for Agent 3 (Clusterer).")