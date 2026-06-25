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

def generate_image_with_gemini(prompt: str) -> bytes:
    """Generates an image using Gemini (Imagen 3) and returns the raw bytes."""
    global client
    if not client:
        print("⚠️ Gemini client not initialized. Image generation skipped.")
        return b""
    try:
        print(f"🎨 Calling Gemini Imagen 3 with prompt: '{prompt}'...")
        response = client.models.generate_images(
            model='imagen-3.0-generate-002',
            prompt=prompt,
            config=dict(
                number_of_images=1,
                output_mime_type="image/jpeg",
                aspect_ratio="16:9",
            )
        )
        if response.generated_images:
            return response.generated_images[0].image.image_bytes
        return b""
    except Exception as e:
        print(f"⚠️ Gemini Image Generation Failed: {e}")
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

        # 1. Gemini Imagen Header Image
        slug = blog_data.get("url_slug", filename.replace(".json", "").replace("_", "-"))
        image_filename = f"{slug}.jpg"
        image_path = os.path.join(BLOGS_DIR, image_filename)
        local_image_url = f"/blog-images/{image_filename}"

        if not os.path.exists(image_path):
            print(f"📸 [{idx}/{len(blog_files)}] Generating unique Gemini Imagen 3 header image for: '{title}'...")
            image_prompt = (
                f"A professional, clean, modern B2B SaaS illustration representing: '{title}'. "
                f"Vector style graphic, high-tech corporate dashboard aesthetic, suitable as a blog header image. "
                f"Color scheme matching a modern software startup (deep blues, clean dark background, tech accents). "
                f"Minimalistic, strictly NO text, letters, or signs in the image."
            )
            img_bytes = generate_image_with_gemini(image_prompt)
            if img_bytes:
                with open(image_path, "wb") as img_f:
                    img_f.write(img_bytes)
                
                # Check if there is an existing image in body and clean it up
                import re
                body = re.sub(r'!\[.*?\]\((https?://.*?unsplash\.com.*?|/blog-images/.*?)\)\n(>\s*\*.*?\*\n\n)?', '', body)
                # Prepend the new local image markdown
                body = f"![Header Image]({local_image_url})\n\n" + body
                
                blog_data["image"] = local_image_url
                changed = True
                print(f"   ✅ Successfully generated and saved Gemini image to {image_filename}!")
        else:
            print(f"⏩ [{idx}/{len(blog_files)}] Gemini image '{image_filename}' already exists. Skipping generation.")
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
