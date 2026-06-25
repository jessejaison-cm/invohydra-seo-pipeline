# agents/illustrator.py
"""
Agent 7 (Phase 4.5): The Media Illustrator

Reads the generated blogs from Agent 4.
1. Uses the Unsplash API to fetch a professional, real-world header image.
2. Uses the Gemini API to generate an interactive Mermaid.js flowchart.
It injects both directly into the Markdown body of the blog.
"""

import os
import sys
import json
import time
import requests

# Make the project root importable when run directly.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from google import genai

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(_project_root, ".env"))

BLOGS_DIR = os.path.join(_project_root, "data", "blogs")

client = None

def setup_gemini():
    global client
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("⚠️ GEMINI_API_KEY is missing. Gemini charts will be skipped.")
        return False
    client = genai.Client(api_key=api_key)
    return True

import random

def fetch_unsplash_image(query: str) -> tuple:
    """Uses the Unsplash API to fetch a relevant header image URL randomly from top results."""
    api_key = os.getenv("UNSPLASH_API_KEY")
    if not api_key:
        print("⚠️ UNSPLASH_API_KEY is missing. Header images will be skipped.")
        return "", ""
        
    # To prevent Unsplash from always returning pictures of "cash" or "money" for billing topics,
    # we append modern, abstract B2B SaaS aesthetic keywords to the search query.
    saas_modifiers = ["modern office", "laptop workspace", "startup desk", "technology", "business meeting", "digital dashboard", "professional workspace"]
    abstract_query = f"{random.choice(saas_modifiers)}"
    
    # We use the abstract query to get a high-quality SaaS corporate image
    url = f"https://api.unsplash.com/search/photos?query={abstract_query}&per_page=15&orientation=landscape"
    headers = {
        "Authorization": f"Client-ID {api_key}"
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()
        if data.get("results"):
            # Pick a random image from the top 10 results so we don't get duplicates!
            photo = random.choice(data["results"])
            img_url = photo["urls"]["regular"]
            alt_text = photo.get("alt_description") or query.title()
            
            # Format as clean markdown with a professional caption instead of attribution
            markdown = f"![{alt_text}]({img_url})\n> *{alt_text.capitalize()}*\n\n"
            return markdown, img_url
        return "", ""
    except Exception as e:
        print(f"   ⚠️ Unsplash API Error for query '{query}': {e}")
        return "", ""


def generate_mermaid_chart(blog_title: str, blog_content: str) -> str:
    """Uses Gemini 2.5 Flash to generate a Mermaid.js chart based on the blog text."""
    global client
    if not client:
        return ""
    try:
        prompt = (
            f"You are an expert technical illustrator for a B2B SaaS blog. "
            f"Read the following blog post titled '{blog_title}' and create ONE highly relevant, "
            f"professional Mermaid.js flowchart or architecture diagram that visualizes a key concept from the text.\n\n"
            f"Requirements:\n"
            f"1. Output ONLY the raw Mermaid code inside a markdown block (```mermaid ... ```).\n"
            f"2. Do not include any other text or explanations.\n"
            f"3. Make it detailed but clean.\n"
            f"4. Do NOT use C-style comments like '//' or '#' inside the Mermaid code. Comments in Mermaid must begin with '%%'. Better yet, do not include any comments.\n\n"
            f"Blog Content Preview:\n{blog_content[:3000]}"
        )
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
        )
        text = response.text.strip()
        
        # Clean up in case Gemini added extra markdown wrapping
        if text.startswith("```mermaid"):
            return text + "\n"
        elif text.startswith("```"):
            return text.replace("```", "```mermaid\n", 1) + "\n"
        else:
            return f"```mermaid\n{text}\n```\n"
    except Exception as e:
        print(f"   ⚠️ Gemini Mermaid Generation Failed: {e}")
        return ""

def illustrate_blogs():
    print("\n" + "═"*60)
    print("  🎨  PHASE 4.5 — AGENT 7: THE ILLUSTRATOR (UNSPLASH + GEMINI)")
    print("═"*60)

    gemini_ready = setup_gemini()

    if not os.path.exists(BLOGS_DIR):
        print(f"⚠️ No blogs found in {BLOGS_DIR}.")
        return

    blog_files = [f for f in os.listdir(BLOGS_DIR) if f.endswith('.json')]
    if not blog_files:
        print("⚠️ No JSON blog files found. Exiting.")
        return

    print(f"📄 Found {len(blog_files)} blogs to illustrate.")

    for idx, filename in enumerate(blog_files, 1):
        filepath = os.path.join(BLOGS_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            blog_data = json.load(f)

        title = blog_data.get("meta_title", "Untitled")
        target_keyword = blog_data.get("target_keyword", title.split()[0])
        body = blog_data.get("markdown_body", "")

        changed = False

        # 1. Unsplash Header Image
        if "![Header Image]" not in body and "unsplash.com" not in body:
            print(f"📸 [{idx}/{len(blog_files)}] Fetching Unsplash header image for: '{target_keyword}'...")
            unsplash_markdown, img_url = fetch_unsplash_image(target_keyword)
            if unsplash_markdown:
                # Inject at the very beginning
                body = unsplash_markdown + body
                blog_data["image"] = img_url
                changed = True
                print(f"   ✅ Successfully added Unsplash image: {img_url}")
        else:
            print(f"⏩ [{idx}/{len(blog_files)}] Already has header image. Skipping Unsplash.")
            # If the 'image' field is missing from blog_data, extract the existing Unsplash URL from body
            if "image" not in blog_data or not blog_data["image"]:
                import re
                match = re.search(r'!\[.*?\]\((https?://[^\s)]+unsplash\.com[^\s)]*)\)', body)
                if match:
                    blog_data["image"] = match.group(1)
                    changed = True
                    print(f"   🔍 Extracted existing Unsplash image URL: {blog_data['image']}")

        # 2. Gemini Mermaid Chart (DISABLED for now until frontend supports it)
        # If the Next.js frontend doesn't have remark-mermaid installed, it renders as a code block.
        # We will skip generating it so it doesn't look like broken code to the users.
        pass

        # Save if changes were made
        if changed:
            blog_data["markdown_body"] = body
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(blog_data, f, indent=2, ensure_ascii=False)
            print(f"💾 Updated {filename} with new illustrations.")

        # Sleep to respect rate limits
        time.sleep(2)

    print("\n" + "═"*60)
    print("  ✅  ILLUSTRATION COMPLETE")
    print("═"*60)

if __name__ == "__main__":
    illustrate_blogs()
