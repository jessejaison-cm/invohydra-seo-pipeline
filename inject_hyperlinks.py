# inject_hyperlinks.py
import os
import json
import re
import requests
from config import GROQ_MODEL, TEMPERATURE

BLOGS_DIR = os.path.join("data", "blogs")

URL_MAPPING_INFO = """
- [InvoHydra](https://www.invohydra.com/) (Home/Platform)
- [Pricing](https://www.invohydra.com/pricing) (or Plan pricing)
- [Contact Us](https://www.invohydra.com/contact) (or scheduling/reaching support)
- [Smart Invoicing](https://www.invohydra.com/products/smart-invoicing)
- [Smart GST Billing](https://www.invohydra.com/products/smart-gst-billing)
- [Smart Proforma Invoice](https://www.invohydra.com/products/smart-proforma-invoice)
- [POS Billing](https://www.invohydra.com/products/pos-billing)
- [Smart E-Invoicing](https://www.invohydra.com/products/smart-e-invoicing) (exact URL: `https://www.invohydra.com/products/smart-e-invoicing`)
- [Smart E-Way Billing](https://www.invohydra.com/products/smart-e-way-billing) (exact URL: `https://www.invohydra.com/products/smart-e-way-billing`)
- [Smart Accounting](https://www.invohydra.com/products/smart-accounting)
- [Smart Inventory](https://www.invohydra.com/products/smart-inventory)
- [Multicurrency Billing](https://www.invohydra.com/products/multicurrency)
- [Book a Demo](https://www.invohydra.com/Book)
"""

import time

def inject_links_via_llm(markdown_content: str) -> str:
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set.")
        
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    system_prompt = (
        "You are an expert SEO copywriter. Your task is to update the provided blog post (written in Markdown) "
        "by naturally inserting hyperlinks into the text. Do NOT change the structure, headers, or rewrite the core content. "
        "Just identify existing words/phrases/features and turn them into appropriate markdown hyperlinks.\n\n"
        "HYPERLINK PLACEMENT RULES:\n"
        "1. Do not over-link. Only link when the feature, product, pricing, booking, or contact is mentioned. "
        "Limit to at most 1-2 links per major section.\n"
        "2. Ensure you use the exact matching URLs from this list:\n"
        f"{URL_MAPPING_INFO}\n"
        "3. Output ONLY the updated markdown content. Do not include any chat filler, intro, or explanation."
    )

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": markdown_content}
        ],
        "temperature": 0.2
    }

    max_retries = 5
    backoff = 4
    for attempt in range(max_retries):
        try:
            response = requests.post(url, json=payload, headers=headers, timeout=60)
            if response.status_code == 429:
                # Try to get retry-after header
                retry_after = response.headers.get("retry-after")
                sleep_time = int(retry_after) if retry_after and retry_after.isdigit() else backoff
                print(f"Rate limited (429). Sleeping for {sleep_time}s before retry (attempt {attempt + 1}/{max_retries})...")
                time.sleep(sleep_time)
                backoff *= 2
                continue
            response.raise_for_status()
            return response.json()["choices"][0]["message"]["content"].strip()
        except requests.exceptions.HTTPError as e:
            if response.status_code == 429:
                print(f"Rate limited (429). Sleeping for {backoff}s before retry (attempt {attempt + 1}/{max_retries})...")
                time.sleep(backoff)
                backoff *= 2
                continue
            raise e
        except Exception as e:
            if attempt == max_retries - 1:
                raise e
            print(f"Error occurred: {e}. Retrying in {backoff}s...")
            time.sleep(backoff)
            backoff *= 2

    raise Exception("Failed to call Groq API after maximum retries due to rate limiting or connection errors.")

def main():
    if not os.path.exists(BLOGS_DIR):
        print(f"Directory {BLOGS_DIR} does not exist.")
        return

    files = os.listdir(BLOGS_DIR)
    print(f"Found {len(files)} files in {BLOGS_DIR} to process.")

    for filename in files:
        filepath = os.path.join(BLOGS_DIR, filename)
        if filename.endswith(".json"):
            print(f"Processing JSON blog: {filename}...")
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    blog_data = json.load(f)
                
                markdown_body = blog_data.get("markdown_body", "")
                if markdown_body:
                    updated_body = inject_links_via_llm(markdown_body)
                    # Clean up potential LLM block wraps if it wraps with ```markdown
                    if updated_body.startswith("```markdown"):
                        updated_body = re.sub(r"^```markdown\n", "", updated_body)
                        updated_body = re.sub(r"\n```$", "", updated_body)
                    elif updated_body.startswith("```"):
                        updated_body = re.sub(r"^```\n", "", updated_body)
                        updated_body = re.sub(r"\n```$", "", updated_body)

                    blog_data["markdown_body"] = updated_body
                    with open(filepath, "w", encoding="utf-8") as f:
                        json.dump(blog_data, f, indent=2, ensure_ascii=False)
                    print(f"[OK] Updated {filename}")
                else:
                    print(f"[WARNING] No markdown_body found in {filename}")
            except Exception as e:
                print(f"[ERROR] Failed to process {filename}: {e}")
            time.sleep(3)

        elif filename.endswith(".md"):
            print(f"Processing MD blog: {filename}...")
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()

                updated_content = inject_links_via_llm(content)
                if updated_content.startswith("```markdown"):
                    updated_content = re.sub(r"^```markdown\n", "", updated_content)
                    updated_content = re.sub(r"\n```$", "", updated_content)
                elif updated_content.startswith("```"):
                    updated_content = re.sub(r"^```\n", "", updated_content)
                    updated_content = re.sub(r"\n```$", "", updated_content)

                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(updated_content)
                print(f"[OK] Updated {filename}")
            except Exception as e:
                print(f"[ERROR] Failed to process {filename}: {e}")
            time.sleep(3)

if __name__ == "__main__":
    main()
