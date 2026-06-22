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
    Validates that necessary third-party API tokens are present before starting the pipeline.
    Prevents runtime failures mid-execution.
    """
    required_keys: Set[str] = {"GROQ_API_KEY"}
    missing_keys = [key for key in required_keys if not os.getenv(key)]
    
    if missing_keys:
        raise ValueError(
            f"❌ CRITICAL CONFIGURATION FAILURE: Missing required environment keys: {missing_keys}. "
            "Please check your .env file."
        )

# Execute credential verification on module import
verify_credentials()

# Configuration Settings
GROQ_MODEL: str = "llama-3.3-70b-versatile"  # Free-tier Groq API model optimized for B2B/compliance reasoning
TEMPERATURE: float = 0.1                    # Low temperature for deterministic extraction and compliance checks
