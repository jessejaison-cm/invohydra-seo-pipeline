# agents/planner.py
"""
Agent 3: Semantic Intent Clusterer.
Takes raw seed keywords, validates them against product capabilities,
and clusters them into structured SEO targets based on Demand, Product Fit, and Intent.
"""

import os
import json
import requests
from typing import List, Dict, Any
from config import GROQ_MODEL, TEMPERATURE

def load_keywords(filepath: str) -> List[str]:
    """Loads the seed keywords from a JSON file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            raise ValueError("Keywords file must contain a JSON list of strings.")
    except Exception as e:
        print(f"⚠️ Error loading keywords from {filepath}: {e}")
        return []

def load_feature_truth(filepath: str) -> Dict[str, bool]:
    """Loads the product feature capability constraints from a JSON file."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
            raise ValueError("Feature truth file must contain a JSON dictionary.")
    except Exception as e:
        print(f"⚠️ Error loading feature truth from {filepath}: {e}")
        return {}

def cluster_keywords(keywords: List[str], features: Dict[str, bool]) -> Dict[str, Any]:
    """
    Submits keywords and product capabilities to the Groq API in JSON mode.
    Enforces demand checking, commercial intent classification, and capability alignment.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set in the environment variables.")
        
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Format features truth map as a readable block for the LLM system prompt
    features_formatted = json.dumps(features, indent=2)

    system_prompt = (
        "You are InvoHydra's Principal SEO & Compliance Keyword Strategist.\n"
        "Your task is to analyze a list of raw keywords and organize them into high-performing semantic clusters.\n\n"
        "CRITICAL COMPLIANCE RULES:\n"
        f"Here is our strict product capability truth map:\n{features_formatted}\n\n"
        "1. You MUST check each keyword against the capability truth map. If a keyword implies or mentions a feature "
        "tagged false (e.g. e-invoicing or e-way bills), you must either completely reject it from the clusters, "
        "or rewrite/adapt it so it matches our active features (true) only. Do NOT claim features we do not support.\n"
        "2. For each cluster, evaluate:\n"
        "   - 'demand': Demand level (High, Medium, Low).\n"
        "   - 'intent': Search intent category (Transactional, Informational, Navigational).\n"
        "   - 'product_fit_rationale': Explicitly explain which active feature supports this cluster.\n\n"
        "Return your response EXCLUSIVELY as a valid JSON object with the following structure:\n"
        "{\n"
        "  \"clusters\": [\n"
        "    {\n"
        "      \"hub_topic\": \"Name of the compliance/billing topic cluster\",\n"
        "      \"demand\": \"High/Medium/Low\",\n"
        "      \"intent\": \"Transactional/Informational/Navigational\",\n"
        "      \"product_fit_rationale\": \"Why this cluster fits our supported features list\",\n"
        "      \"keywords\": [\"keyword 1\", \"keyword 2\"]\n"
        "    }\n"
        "  ],\n"
        "  \"rejected_keywords\": [\n"
        "    {\n"
        "      \"original\": \"original keyword\",\n"
        "      \"reason\": \"explanation of why it violates capability boundaries\"\n"
        "    }\n"
        "  ]\n"
        "}"
    )

    user_payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Input keywords to process: {json.dumps(keywords)}"}
        ],
        "temperature": TEMPERATURE,
        "response_format": {"type": "json_object"}
    }

    try:
        response = requests.post(url, json=user_payload, headers=headers, timeout=30)
        response.raise_for_status()
        result_content = response.json()["choices"][0]["message"]["content"]
        return json.loads(result_content)
    except Exception as e:
        print(f"⚠️ Groq API request failed: {e}")
        # Return structured fallback dictionary
        return {
            "clusters": [],
            "rejected_keywords": [{"original": kw, "reason": "API execution failure fallback"} for kw in keywords]
        }
