# agents/publisher.py
"""
Agent 5: The Auto-Publisher (Local Test Mode)

Safely pushes generated SEO blogs into a separate local Landing Page repository.
To avoid breaking the main website codebase, it acts like a Junior Developer:
1. Navigates to the Landing Page repo.
2. Checks out a safe, isolated Git branch (`seo-bot-publish`).
3. Converts the AI JSON blogs into standard MDX files with Frontmatter.
4. Saves them to the landing page's blog folder.
5. Commits the changes to the safe branch.
"""

import os
import sys
import json
import subprocess
import shutil

# Make the project root importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCAL_BLOGS_DIR = os.path.join(_project_root, "data", "blogs")

# User-provided Landing Page Paths
LANDING_PAGE_REPO = r"C:\Repo\InvoHydra-Landing-Page"
LANDING_PAGE_BLOG_DIR = r"C:\Repo\InvoHydra-Landing-Page\src\app\blog"
SAFE_BRANCH_NAME = "seo-bot-publish"

def run_git_command(command: list, cwd: str) -> bool:
    """Runs a git command in the specified directory."""
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if result.returncode != 0:
            # If there's nothing to commit, git returns an error, which we can ignore
            if "nothing to commit" not in result.stdout.lower():
                print(f"⚠️ Git command failed: {' '.join(command)}")
                print(f"Error: {result.stderr.strip()}")
            return False
        return True
    except Exception as e:
        print(f"⚠️ Failed to run git command {' '.join(command)}: {e}")
        return False


def format_as_mdx(blog_data: dict) -> str:
    """
    Converts the raw JSON blog data into a standard MDX file with Frontmatter.
    This is the standard format for Next.js / Astro blogs.
    """
    title = blog_data.get("meta_title", "Untitled Blog").replace('"', "'")
    description = blog_data.get("meta_description", "").replace('"', "'")
    body = blog_data.get("markdown_body", "")

    # Create YAML Frontmatter
    mdx_content = f"""---
title: "{title}"
description: "{description}"
author: "InvoHydra AI"
---

{body}
"""
    return mdx_content


def publish_blogs() -> None:
    print("\n" + "="*60)
    print("  🚀  AGENT 5: AUTO-PUBLISHER (LOCAL MERGE)")
    print("="*60)

    # 1. Verification
    if not os.path.exists(LANDING_PAGE_REPO):
        print(f"🛑 Error: Cannot find landing page repo at {LANDING_PAGE_REPO}")
        return
        
    if not os.path.exists(LOCAL_BLOGS_DIR):
        print(f"⚠️ No blogs found in {LOCAL_BLOGS_DIR} to publish.")
        return

    blog_files = [f for f in os.listdir(LOCAL_BLOGS_DIR) if f.endswith('.json')]
    if not blog_files:
        print("⚠️ No JSON blog files found. Exiting.")
        return

    print(f"📦 Found {len(blog_files)} blogs ready for publishing.")
    print(f"🔗 Target Repo: {LANDING_PAGE_REPO}")

    # 2. Safely Checkout Branch
    print(f"\n🌿 Creating safe isolated branch: '{SAFE_BRANCH_NAME}'...")
    # Fetch latest (optional) and checkout branch (create if not exists)
    run_git_command(["git", "checkout", "-B", SAFE_BRANCH_NAME], LANDING_PAGE_REPO)

    # Ensure target directory exists
    os.makedirs(LANDING_PAGE_BLOG_DIR, exist_ok=True)

    # 3. Process and Copy Files
    published_count = 0
    for filename in blog_files:
        filepath = os.path.join(LOCAL_BLOGS_DIR, filename)
        with open(filepath, "r", encoding="utf-8") as f:
            try:
                blog_data = json.load(f)
            except Exception as e:
                print(f"   ⚠️ Error reading {filename}: {e}")
                continue

        slug = blog_data.get("url_slug", filename.replace(".json", ""))
        mdx_filename = f"{slug}.mdx"
        mdx_filepath = os.path.join(LANDING_PAGE_BLOG_DIR, mdx_filename)

        mdx_content = format_as_mdx(blog_data)

        # Write to landing page repo
        with open(mdx_filepath, "w", encoding="utf-8") as out_f:
            out_f.write(mdx_content)
            
        print(f"   ✅ Copied: {mdx_filename} -> {LANDING_PAGE_BLOG_DIR}")
        published_count += 1

    # 4. Git Commit
    if published_count > 0:
        print("\n💾 Committing changes to the safe branch...")
        run_git_command(["git", "add", "src/app/blog/"], LANDING_PAGE_REPO)
        success = run_git_command(
            ["git", "commit", "-m", f"Auto-publish {published_count} SEO blogs via AI Agent"],
            LANDING_PAGE_REPO
        )
        if success:
            print(f"🎉 Successfully committed {published_count} blogs to branch '{SAFE_BRANCH_NAME}'!")
        else:
            print("   ↳ (No new changes to commit, branch is already up to date).")
    
    print("\n" + "="*60)
    print("  ✅  PUBLISHING COMPLETE")
    print("="*60)
    print(f"Next steps:")
    print(f"1. Open your Landing Page project in VS Code.")
    print(f"2. Switch to branch '{SAFE_BRANCH_NAME}'.")
    print(f"3. Run your local server (npm run dev) to test how the blogs look!")
    print(f"4. If they look good, merge the branch to main.")

if __name__ == "__main__":
    publish_blogs()
