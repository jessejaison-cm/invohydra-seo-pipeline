# config.py
"""
Configuration module for the InvoHydra SEO Pipeline.
Handles validation of environment variables and loads system settings.
"""

import os
from typing import Set
from dotenv import load_dotenv

# Load environmental variables from secure local file
load_dotenv()

def verify_credentials() -> None:
    """
    Validates that necessary API tokens are present before starting the pipeline.
    - REQUIRED keys: hard-fail if missing.
    - OPTIONAL keys: warn but allow execution to continue.
    """
    # ── Hard required: pipeline cannot function without these ──────────────
    required_keys: Set[str] = {"GROQ_API_KEY"}
    missing_keys = [key for key in required_keys if not os.getenv(key)]

    if missing_keys:
        raise ValueError(
            f"❌ CRITICAL CONFIGURATION FAILURE: Missing required environment keys: {missing_keys}. "
            "Please check your .env file."
        )

    # ── Optional: warn but continue ─────────────────────────────────────────
    optional_warnings = {
        "SERPER_API_KEY": (
            "Agent 1 (Keyword Discoverer) and Agent 4's competitor research will be skipped."
        ),
        "FIRECRAWL_API_KEY": (
            "Agent 4 will skip competitor content scraping (outline generation still works)."
        ),
    }

    for key, consequence in optional_warnings.items():
        if not os.getenv(key):
            print(f"⚠️  Optional key '{key}' not found → {consequence}")


# Execute credential verification on module import
verify_credentials()

# ── Model Configuration ────────────────────────────────────────────────────
GROQ_MODEL: str = "llama-3.3-70b-versatile"  # Free-tier Groq model, strong for B2B/compliance reasoning
TEMPERATURE: float = 0.1                       # Low temp = deterministic extraction and compliance checks

# ── Pipeline Seed Topics (used by Agent 1) ────────────────────────────────
# Add, remove, or edit topics here to control what Agent 1 searches for.
# These should be slightly broad so Agent 1 can discover the long-tail variants!
SEED_TOPICS = [
    "best GST billing software for Indian MSMEs",
    "how to automate invoicing for SaaS companies India",
    "recurring billing and subscription management India",
    "how to generate e-way bills automatically from invoices",
    "bulk GSTIN validation and verification API",
    "how to reconcile GSTR-1 and GSTR-2B automatically",
    "multi-currency invoicing software with Indian GST compliance",
    "real time GST calculation API for Indian marketplaces"
]

import time
import requests
from typing import Dict, Any

def call_groq_with_retry(payload: Dict[str, Any], timeout: int = 90, max_retries: int = 5, initial_backoff: float = 4.0) -> Dict[str, Any]:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set in the environment variables.")
        
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    backoff = initial_backoff
    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=timeout)
            if response.status_code == 429:
                retry_after = response.headers.get("retry-after")
                try:
                    sleep_time = float(retry_after) if retry_after else backoff
                except ValueError:
                    sleep_time = backoff
                print(f"⚠️ Groq API Rate Limit (429). Sleeping for {sleep_time}s before retry (attempt {attempt + 1}/{max_retries})...", flush=True)
                time.sleep(sleep_time)
                backoff *= 2
                continue
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            status_code = getattr(e.response, 'status_code', None)
            if status_code == 429:
                retry_after = getattr(e.response, 'headers', {}).get("retry-after")
                try:
                    sleep_time = float(retry_after) if retry_after else backoff
                except ValueError:
                    sleep_time = backoff
                print(f"⚠️ Groq API Rate Limit (429 HTTPError). Sleeping for {sleep_time}s before retry (attempt {attempt + 1}/{max_retries})...", flush=True)
                time.sleep(sleep_time)
                backoff *= 2
                continue
            if attempt == max_retries - 1:
                raise e
            print(f"⚠️ Groq API HTTP error: {e}. Retrying in {backoff}s...", flush=True)
            time.sleep(backoff)
            backoff *= 2
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            print(f"⚠️ Unexpected error: {e}. Retrying in {backoff}s...", flush=True)
            time.sleep(backoff)
            backoff *= 2
            
    raise Exception("Failed to call Groq API after maximum retries due to rate limiting.")
