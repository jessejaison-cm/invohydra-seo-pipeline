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
import requests

def fetch_unsplash_image(blog_title: str, target_keyword: str) -> bytes:
    """Fetches a professional Unsplash image themed around offices, money, buildings, or workspace."""
    api_key = os.getenv("UNSPLASH_API_KEY")
    if not api_key:
        print("⚠️ UNSPLASH_API_KEY is missing. Cannot fetch from Unsplash.")
        return b""
        
    themes = ["office", "workspace", "money", "business building", "corporate finance", "accounting", "skyscraper"]
    selected_theme = random.choice(themes)
    
    # Try search query combining target keyword and selected theme
    search_query = f"{target_keyword} {selected_theme}"
    
    url = "https://api.unsplash.com/search/photos"
    headers = {
        "Accept-Version": "v1"
    }
    params = {
        "query": search_query,
        "client_id": api_key,
        "orientation": "landscape",
        "per_page": 15
    }
    
    try:
        print(f"🔍 Searching Unsplash for '{search_query}'...")
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        results = data.get("results", [])
        if not results:
            # Fallback: search just the theme itself
            print(f"⚠️ No results for '{search_query}'. Trying fallback: '{selected_theme}'...")
            params["query"] = selected_theme
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            
        if not results:
            # Ultimate fallback to generic 'office'
            print("⚠️ No results for theme either. Falling back to 'office'...")
            params["query"] = "office"
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
            data = response.json()
            results = data.get("results", [])
            
        if results:
            img_info = random.choice(results)
            img_url = img_info.get("urls", {}).get("regular")
            if img_url:
                print(f"📥 Downloading image from Unsplash: {img_url}")
                img_response = requests.get(img_url, timeout=30)
                img_response.raise_for_status()
                return img_response.content
    except Exception as e:
        print(f"⚠️ Unsplash image download failed: {e}")
        
    return b""





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
    print("  🎨  PHASE 4.5 — AGENT 7: THE ILLUSTRATOR (UNSPLASH)")
    print("═"*60)

    # Setup gemini solely for charts (if enabled)
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
        slug = blog_data.get("url_slug", filename.replace(".json", "").replace("_", "-"))
        image_filename = f"{slug}.jpg"
        image_path = os.path.join(BLOGS_DIR, image_filename)
        local_image_url = f"/blog-images/{image_filename}"
        
        # Check if the title mentions the phase or if this is the Illustrator phase
        # Let's change the console output to show it's fetching from Unsplash
        if not os.path.exists(image_path):
            print(f"📸 [{idx}/{len(blog_files)}] Fetching unique Unsplash header image for: '{title}'...")
            img_bytes = fetch_unsplash_image(title, target_keyword)
            if img_bytes:
                with open(image_path, "wb") as img_f:
                    img_f.write(img_bytes)
                
                # Clean up any existing image tags from body text (header image is handled by front-end metadata)
                import re
                body = re.sub(r'!\[.*?\]\(.*?\)\s*', '', body).strip()
                
                blog_data["image"] = local_image_url
                changed = True
                print(f"   ✅ Successfully fetched and saved Unsplash image to {image_filename}!")
        else:
            print(f"⏩ [{idx}/{len(blog_files)}] Unsplash image '{image_filename}' already exists. Skipping generation.")
            # Ensure the image field is correctly mapped to this local URL in the JSON
            if blog_data.get("image") != local_image_url:
                blog_data["image"] = local_image_url
                changed = True

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
