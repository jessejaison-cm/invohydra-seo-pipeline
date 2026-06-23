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
SEED_TOPICS = [
    "best GST billing software for Indian MSMEs",
    "how to automate invoicing for SaaS companies India",
    "recurring billing and subscription management India",
    "smart GST invoice generation and verification India",
    "POS billing software for retail shops in India",
    "proforma invoice vs tax invoice rules GST",
    "multicurrency invoicing software for exports India",
]
