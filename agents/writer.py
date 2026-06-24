# agents/writer.py
"""
Agent 4: Blog Writer.
Takes structured keyword clusters, conducts competitor research via Google (Serper) and Firecrawl,
and writes comprehensive, deep-dive SEO blog posts (1500+ words).
"""

import os
import json
import re
import requests
import time
from typing import List, Dict, Any
from config import GROQ_MODEL, TEMPERATURE

def load_clusters(filepath: str) -> List[Dict[str, Any]]:
    """Loads the clustered keywords from the JSON output of Agent 3."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict) and "clusters" in data:
                return data["clusters"]
            raise ValueError("Clusters file must contain a dictionary with a 'clusters' list.")
    except Exception as e:
        print(f"⚠️ Error loading clusters from {filepath}: {e}")
        return []

def get_competitor_context(topic: str) -> Dict[str, Any]:
    """
    Searches Google for the topic, extracts top ranking URLs, and scrapes
    the top competitor's content to extract structure, length, and themes.
    """
    serper_key = os.getenv("SERPER_API_KEY")
    firecrawl_key = os.getenv("FIRECRAWL_API_KEY")
    
    context = {
        "competitor_urls": [],
        "competitor_content_sample": "",
        "suggested_outlines": []
    }
    
    if not serper_key:
        print("⚠️ SERPER_API_KEY is not set. Skipping competitor search.")
        return context
        
    try:
        # 1. Search Google via Serper
        search_url = "https://google.serper.dev/search"
        headers = {
            "X-API-KEY": serper_key,
            "Content-Type": "application/json"
        }
        payload = {"q": topic}
        res = requests.post(search_url, json=payload, headers=headers, timeout=15)
        res.raise_for_status()
        search_data = res.json()
        
        organic_results = search_data.get("organic", [])
        if not organic_results:
            return context
            
        # Extract top 3 competitor URLs and snippets
        top_urls = [item["link"] for item in organic_results[:3] if "link" in item]
        context["competitor_urls"] = top_urls
        
        # Build suggested outlines from the titles/snippets of top ranking pages
        outlines = []
        for item in organic_results[:5]:
            outlines.append(f"- Title: {item.get('title')}\n  Snippet: {item.get('snippet')}")
        context["suggested_outlines"] = outlines
        
        # 2. Try scraping the top ranking URL using Firecrawl
        if top_urls and firecrawl_key:
            target_url = top_urls[0]
            print(f"🕷️ Scraping top competitor: {target_url} using Firecrawl...")
            scrape_url = "https://api.firecrawl.dev/v1/scrape"
            scrape_headers = {
                "Authorization": f"Bearer {firecrawl_key}",
                "Content-Type": "application/json"
            }
            scrape_payload = {
                "url": target_url,
                "formats": ["markdown"],
                "onlyMainContent": True
            }
            # Give it a 20s timeout to avoid hanging the pipeline
            scrape_res = requests.post(scrape_url, json=scrape_payload, headers=scrape_headers, timeout=20)
            if scrape_res.status_code == 200:
                scrape_data = scrape_res.json()
                if scrape_data.get("success") and "data" in scrape_data:
                    markdown_content = scrape_data["data"].get("markdown", "")
                    # Limit sample to first 3000 characters to prevent model context blowing up
                    context["competitor_content_sample"] = markdown_content[:3000]
                    print(f"✅ Successfully scraped {len(markdown_content)} chars.")
                else:
                    print(f"⚠️ Firecrawl scrape request succeeded but returned unsuccessful: {scrape_data}")
            else:
                print(f"⚠️ Firecrawl scrape request failed: {scrape_res.status_code}")
                
    except Exception as e:
        print(f"⚠️ Error getting competitor context: {e}")
        
    return context

def call_llm(system_prompt: str, user_prompt: str, temperature: float, response_format: str = None) -> str:
    """Helper function to call the Groq API."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set in the environment variables.")
        
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": temperature
    }
    if response_format == "json":
        payload["response_format"] = {"type": "json_object"}
        
    response = requests.post(url, json=payload, headers=headers, timeout=90)
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]

def generate_blog_post(cluster: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generates a structured, highly detailed, and SEO-friendly blog post
    using a two-step outline generation and section-by-section writing process.
    Returns a dictionary with meta_title, meta_description, url_slug, and markdown_body.
    """
    hub_topic = cluster.get("hub_topic", "General Compliance & Invoicing")
    keywords = cluster.get("keywords", [])
    product_fit = cluster.get("product_fit_rationale", "Aligns with our active billing features.")
    
    # Perform competitor research
    print(f"🔍 Researching competitors for topic: '{hub_topic}'...")
    competitor_info = get_competitor_context(hub_topic)
    
    suggested_outlines_str = "\n".join(competitor_info["suggested_outlines"])
    competitor_sample_str = competitor_info["competitor_content_sample"]
    
    # Step 1: Generate Outline
    print("📝 Step 1: Generating detailed blog outline...")
    outline_system = (
        "You are InvoHydra's Senior B2B Content Writer & SEO Director.\n"
        "Your task is to design a detailed, comprehensive, and logically ordered outline for a B2B blog post.\n"
        "The outline should contain 5 to 7 distinct sections (including introduction and conclusion/FAQ).\n"
        "For each section, provide a section title and detailed guidelines of what should be covered.\n"
        "Return your response ONLY as a JSON object with a single key 'sections' containing a list of section objects. "
        "Each section object must have two fields: 'title' and 'guidelines'.\n\n"
        "Example structure:\n"
        "{\n"
        "  \"sections\": [\n"
        "    {\"title\": \"1. Introduction to GSTIN Validation\", \"guidelines\": \"Explain what GSTIN is, why validation is critical for B2B transactions, and outline customer pain points.\"},\n"
        "    {\"title\": \"2. Common Compliance Challenges\", \"guidelines\": \"Detail common mistakes businesses make when handling manual validation and the risk of penalties.\"}\n"
        "  ]\n"
        "}"
    )
    
    outline_user = (
        f"Target Hub Topic: {hub_topic}\n"
        f"Keywords to Integrate: {', '.join(keywords)}\n"
        f"Product Fit Rationale: {product_fit}\n\n"
        f"--- COMPETITOR OUTLINE RESEARCH ---\n{suggested_outlines_str}\n\n"
        f"--- TOP COMPETITOR CONTENT SAMPLE ---\n{competitor_sample_str}\n\n"
        "Please generate a detailed outline that covers this topic extensively, outperforming the competitors."
    )
    
    try:
        outline_raw = call_llm(outline_system, outline_user, temperature=0.4, response_format="json")
        outline_data = json.loads(outline_raw)
        sections = outline_data.get("sections", [])
    except Exception as e:
        print(f"⚠️ Failed to generate outline via JSON. Falling back to simple default outline. Error: {e}")
        sections = [
            {"title": f"1. Introduction to {hub_topic}", "guidelines": f"Introduce the concept of {hub_topic} and its importance."},
            {"title": f"2. Understanding the Challenges in {hub_topic}", "guidelines": f"Explain the key compliance and operational hurdles."},
            {"title": f"3. How to Solve {hub_topic} Efficiency", "guidelines": "Provide actionable steps and solutions."},
            {"title": f"4. Incorporating InvoHydra for {hub_topic}", "guidelines": f"Explain how InvoHydra helps solve these challenges using: {product_fit}."},
            {"title": f"5. Conclusion and Key Takeaways", "guidelines": "Summarize findings and next steps."}
        ]

    # Step 2: Write section by section
    print(f"✍️ Step 2: Writing {len(sections)} sections individually...")
    written_sections = []
    
    for idx, sec in enumerate(sections, 1):
        title = sec.get("title", f"Section {idx}")
        guidelines = sec.get("guidelines", "")
        print(f"   ↳ Writing section [{idx}/{len(sections)}]: {title}")
        
        section_system = (
            "You are InvoHydra's Senior B2B Content Writer, SEO Director & Copywriter.\n"
            "Your task is to write a highly detailed, comprehensive, and engaging section of a B2B blog post.\n\n"
            "WRITING GUIDELINES:\n"
            "1. Write in a clear, authoritative, and helpful tone suitable for B2B MSMEs and SaaS founders.\n"
            "2. Aim to write approximately 300 to 450 words just for this section to cover it in depth. Avoid wrapping up quickly.\n"
            "3. Incorporate the target keywords naturally if relevant.\n"
            "4. Highlight product alignment: explain how InvoHydra helps solve these challenges based on the product fit rationale where appropriate. "
            "Do NOT claim or mention features we do not support (such as automated e-invoicing or e-way bills) if they violate our product truth map. Focus only on active, supported features.\n"
            "5. Do NOT include any introductory header filler (like 'Here is the section content') or closing remarks. Start writing the content of the section directly.\n"
            "6. Use clear formatting, bullet points, or bold text within the section to make it highly readable.\n"
            "7. Hyperlink Placement (CRITICAL): When mentioning InvoHydra features or pages, you must naturally hyperlink appropriate terms to their corresponding InvoHydra web pages. Do not over-link; limit hyperlinks to 1-2 per section and ensure they are contextually natural.\n"
            "   Use the following exact URLs:\n"
            "   - [InvoHydra](https://www.invohydra.com/) (Home/Platform)\n"
            "   - [Pricing](https://www.invohydra.com/pricing) (or Plan pricing)\n"
            "   - [Contact Us](https://www.invohydra.com/contact) (or scheduling/reaching support)\n"
            "   - [Smart Invoicing](https://www.invohydra.com/products/smart-invoicing)\n"
            "   - [Smart GST Billing](https://www.invohydra.com/products/smart-gst-billing)\n"
            "   - [Smart Proforma Invoice](https://www.invohydra.com/products/smart-proforma-invoice)\n"
            "   - [POS Billing](https://www.invohydra.com/products/pos-billing)\n"
            "   - [Smart E-Invoicing](https://www.invohydra.com/products/smart-e-inavoicing) (use exact URL `https://www.invohydra.com/products/smart-e-inavoicing`)\n"
            "   - [Smart E-Way Billing](https://www.invohydra.com/products/smart-e-way-billing) (use exact URL `https://www.invohydra.com/products/smart-e-way-billing`)\n"
            "   - [Smart Accounting](https://www.invohydra.com/products/smart-accounting)\n"
            "   - [Smart Inventory](https://www.invohydra.com/products/smart-inventory)\n"
            "   - [Multicurrency Billing](https://www.invohydra.com/products/multicurrency) (or multi-currency invoicing)\n"
            "   - [Book a Demo](https://www.invohydra.com/Book) (or Book Demo)\n"
            "   Format them as standard markdown links, e.g. `[Smart GST Billing](https://www.invohydra.com/products/smart-gst-billing)`."
        )
        
        section_user = (
            f"Target Hub Topic: {hub_topic}\n"
            f"Keywords to Keep in Mind: {', '.join(keywords)}\n"
            f"Product Fit Rationale: {product_fit}\n\n"
            f"--- FULL ARTICLE OUTLINE ---\n" + "\n".join([f"- {s.get('title')}" for s in sections]) + "\n\n"
            f"--- CURRENT SECTION TO WRITE ---\n"
            f"Title: {title}\n"
            f"Guidelines / Focus: {guidelines}\n\n"
            f"Please write this section (approx 300-450 words) starting directly with the appropriate heading (e.g. '## {title}' or '### {title}'):"
        )
        
        try:
            # Using higher temperature (0.6) for creative/natural B2B writing
            section_content = call_llm(section_system, section_user, temperature=0.6)
            written_sections.append(section_content.strip())
            # Throttle requests to respect Groq rate limits
            time.sleep(4)
        except Exception as e:
            print(f"⚠️ Failed to write section '{title}': {e}")
            written_sections.append(f"## {title}\n\n*Content generation failed for this section due to an API error.*")
            time.sleep(2)

    # Stitch them together
    markdown_body = f"# {hub_topic}\n\n" + "\n\n".join(written_sections)
    
    # Throttle before metadata call
    time.sleep(3)
    
    # Step 3: Generate SEO Metadata
    print("🏷️ Step 3: Generating SEO Metadata...")
    metadata_system = (
        "You are an expert B2B Copywriter & SEO Specialist.\n"
        "Your task is to generate high-performing SEO metadata for the provided blog post.\n"
        "You must return ONLY a JSON object with exactly three keys:\n"
        "- 'meta_title': A compelling, click-worthy SEO title under 60 characters.\n"
        "- 'meta_description': A high-performing SEO meta description between 120 and 160 characters.\n"
        "- 'url_slug': A clean, lowercase URL slug (using hyphens, no spaces, letters/numbers only).\n\n"
        "Example format:\n"
        "{\n"
        "  \"meta_title\": \"Automating GST Compliance for SaaS Platforms\",\n"
        "  \"meta_description\": \"Learn how to integrate real-time GSTIN validation and automate tax calculations on your SaaS platform using InvoHydra webhooks.\",\n"
        "  \"url_slug\": \"automating-gst-compliance-saas\"\n"
        "}"
    )
    
    metadata_user = (
        f"Target Hub Topic: {hub_topic}\n\n"
        f"--- GENERATED BLOG POST CONTENT ---\n{markdown_body[:4000]}...\n\n"
        "Please generate the meta_title, meta_description, and url_slug for this article."
    )
    
    try:
        metadata_raw = call_llm(metadata_system, metadata_user, temperature=0.3, response_format="json")
        metadata = json.loads(metadata_raw)
    except Exception as e:
        print(f"⚠️ Failed to generate SEO metadata: {e}")
        # Fallback
        metadata = {
            "meta_title": hub_topic[:60],
            "meta_description": f"Learn more about {hub_topic} and how to optimize it for your B2B MSME or SaaS company.",
            "url_slug": re.sub(r'[^a-z0-9-]', '', hub_topic.lower().replace(" ", "-"))
        }
        
    return {
        "target_keyword": hub_topic,
        "meta_title": metadata.get("meta_title", hub_topic),
        "meta_description": metadata.get("meta_description", ""),
        "url_slug": metadata.get("url_slug", ""),
        "markdown_body": markdown_body
    }

def generate_all_blogs(clusters_path: str, output_dir: str, limit: int = None) -> None:
    """Iterates through all clusters and generates individual JSON blog post files."""
    import time
    clusters = load_clusters(clusters_path)
    if not clusters:
        print("⚠️ No clusters found to generate blogs for.")
        return
        
    os.makedirs(output_dir, exist_ok=True)
    print(f"✍️ Starting competitor-informed blog generation (Total clusters: {len(clusters)})...")
    if limit:
        print(f"🎯 Limiting generation to {limit} new blog posts per run.")
    
    generated_count = 0
    for i, cluster in enumerate(clusters, 1):
        if limit and generated_count >= limit:
            print(f"🛑 Reached the limit of {limit} blogs. Stopping generation for this run.")
            break

        topic = cluster.get("hub_topic", f"Topic_{i}")
        # Sanitize filename
        filename = re.sub(r'[^a-zA-Z0-9_-]', '_', topic.lower().replace(" ", "_")) + ".json"
        filepath = os.path.join(output_dir, filename)
        
        if os.path.exists(filepath):
            print(f"⏩ Skipping '{topic}': Blog post already exists at {filepath}")
            continue
            
        print(f"📝 Generating blog for: '{topic}'...")
        blog_data = generate_blog_post(cluster)
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(blog_data, f, indent=2, ensure_ascii=False)
        print(f"💾 Saved blog post to: {filepath}")
        generated_count += 1
        
        if limit and generated_count < limit:
            # Adding a 10s delay between blogs to help with Groq free tier rate limits
            print("⏳ Waiting 10 seconds before generating the next blog to respect API rate limits...")
            time.sleep(10)
        
    print(f"🎉 Generated {generated_count} new blog posts successfully.")
