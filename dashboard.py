import streamlit as st
import os
import json
import subprocess
import time
import re
import requests
import zipfile
import io
from dotenv import load_dotenv

# Load configuration at start
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

WEBSITE_REPO = "InvoHydra/InvoHydra-Landing-Page"
GITHUB_TOKEN = "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"
PIPELINE_REPO = "jessejaison-cm/invohydra-seo-pipeline"
SAFE_BRANCH_NAME = "blog-automation"

if "pipeline_proc" not in st.session_state:
    st.session_state["pipeline_proc"] = None
if "audit_proc" not in st.session_state:
    st.session_state["audit_proc"] = None
if "show_logs_for_run" not in st.session_state:
    st.session_state["show_logs_for_run"] = None
if "show_logs_num" not in st.session_state:
    st.session_state["show_logs_num"] = None

def get_workflow_run_logs(repo, run_id, token=None):
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/logs"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "InvoHydra-SEO-Dashboard"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            zip_bytes = io.BytesIO(res.content)
            with zipfile.ZipFile(zip_bytes) as z:
                log_contents = []
                for filename in sorted(z.namelist()):
                    if filename.endswith(".txt") and not filename.startswith("suite_"):
                        with z.open(filename) as f:
                            content = f.read().decode("utf-8", errors="ignore")
                            # Remove ANSI coloring escape codes from terminal logs
                            clean_content = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', content)
                            # Shorten file path/name for readability
                            step_title = filename.split("/")[-1] if "/" in filename else filename
                            log_contents.append(f"=== Step Log: {step_title} ===\n{clean_content}\n")
                return "\n".join(log_contents)
        elif res.status_code == 404:
            return "No logs generated yet. The workflow might be queued or initiating."
    except Exception as e:
        return f"Failed to retrieve workflow logs: {e}"
    return "Logs could not be fetched (possibly expired or rate limited)."

# Helper functions for GitHub REST API Integration
def load_json_from_github(repo, path, branch="main", token=None):
    # Bypass GitHub API and CDN caching by appending a unique timestamp query parameter
    url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}&t={int(time.time())}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "InvoHydra-SEO-Dashboard"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            if isinstance(data, dict) and "content" in data:
                import base64
                # GitHub returns base64 string with line breaks. b64decode parses it correctly.
                content_bytes = base64.b64decode(data["content"])
                content_str = content_bytes.decode("utf-8", errors="ignore")
                return json.loads(content_str)
    except Exception as e:
        pass
    return {}

def get_blogs_from_github(repo, path="src/app/blog/posts", branch="blog-automation", token=None):
    url = f"https://api.github.com/repos/{repo}/contents/{path}?ref={branch}&t={int(time.time())}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "InvoHydra-SEO-Dashboard"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    blogs = []
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            files_list = res.json()
            if isinstance(files_list, list):
                for f in files_list:
                    if f.get("name", "").endswith(".json") and f.get("type") == "file":
                        download_url = f.get("download_url")
                        if download_url:
                            # Bypass raw CDN cache using a timestamp query parameter
                            cache_bust_url = f"{download_url}?t={int(time.time())}"
                            blog_res = requests.get(cache_bust_url, headers=headers, timeout=10)
                            if blog_res.status_code == 200:
                                try:
                                    blogs.append((f.get("name"), blog_res.json()))
                                except:
                                    pass
    except Exception as e:
        pass
    return blogs


def trigger_workflow_dispatch(repo, workflow_id, ref="main", inputs=None, token=None):
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_id}/dispatches"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/json",
        "User-Agent": "InvoHydra-SEO-Dashboard"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    payload = {"ref": ref}
    if inputs:
        payload["inputs"] = inputs
    try:
        res = requests.post(url, headers=headers, json=payload, timeout=15)
        return res.status_code == 204
    except:
        return False

def get_workflow_runs(repo, workflow_id, token=None, limit=5):
    url = f"https://api.github.com/repos/{repo}/actions/workflows/{workflow_id}/runs?per_page={limit}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "InvoHydra-SEO-Dashboard"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            return res.json().get("workflow_runs", [])
    except:
        pass
    return []

def get_run_jobs(repo, run_id, token=None):
    url = f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/jobs"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "InvoHydra-SEO-Dashboard"
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            return res.json().get("jobs", [])
    except:
        pass
    return []

# Configuration
st.set_page_config(page_title="InvoHydra Enterprise SEO", layout="wide")

# CSS Styling for SaaS Reporting & Steppers
st.markdown("""
<style>
    /* Global styles */
    .report-title {
        font-family: 'Inter', -apple-system, sans-serif;
        font-weight: 800;
        color: #1e293b;
        margin-bottom: 2px;
    }
    .report-subtitle {
        color: #64748b;
        font-size: 1.05rem;
        margin-bottom: 20px;
    }
    
    /* Card layout */
    .agent-grid {
        display: flex;
        flex-direction: column;
        gap: 12px;
        margin-top: 15px;
        margin-bottom: 20px;
    }
    
    .agent-card {
        border-radius: 10px;
        padding: 16px 20px;
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        display: flex;
        align-items: center;
        justify-content: space-between;
        transition: all 0.2s ease-in-out;
    }
    
    /* Dark mode adjustments via Streamlit custom components theme compatibility */
    @media (prefers-color-scheme: dark) {
        .agent-card {
            background: #1e293b;
            border-color: #334155;
        }
        .agent-title {
            color: #f1f5f9 !important;
        }
        .agent-desc {
            color: #cbd5e1 !important;
        }
    }
    
    .agent-info {
        display: flex;
        flex-direction: column;
        gap: 4px;
        flex-grow: 1;
        margin-right: 20px;
    }
    
    .agent-header-row {
        display: flex;
        align-items: center;
        gap: 12px;
    }
    
    .agent-title {
        font-weight: 700;
        font-size: 1.05rem;
        color: #0f172a;
        margin: 0;
    }
    
    .agent-desc {
        font-size: 0.9rem;
        color: #475569;
        margin: 0;
    }
    
    /* Status Badge styling */
    .status-badge {
        padding: 4px 12px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        display: inline-flex;
        align-items: center;
        gap: 6px;
    }
    
    .status-pending {
        background-color: #f1f5f9;
        color: #64748b;
        border: 1px solid #cbd5e1;
    }
    
    .status-running {
        background-color: #dbeafe;
        color: #2563eb;
        border: 1px solid #bfdbfe;
        animation: pulse-border 1.5s infinite alternate;
    }
    
    .status-completed {
        background-color: #dcfce7;
        color: #16a34a;
        border: 1px solid #bbf7d0;
    }
    
    .status-failed {
        background-color: #fee2e2;
        color: #dc2626;
        border: 1px solid #fecaca;
    }
    
    @keyframes pulse-border {
        0% {
            box-shadow: 0 0 0 0px rgba(37, 99, 235, 0.4);
        }
        100% {
            box-shadow: 0 0 0 6px rgba(37, 99, 235, 0);
        }
    }
</style>
""", unsafe_allow_html=True)

DATA_DIR = "data"
BLOGS_DIR = os.path.join(DATA_DIR, "blogs")
DIFFICULTY_REPORT = os.path.join(DATA_DIR, "difficulty_report.json")
AUDIT_REPORT = os.path.join(DATA_DIR, "audit_report.json")
STATE_FILE = os.path.join(DATA_DIR, "pipeline_state.json")

# Helper to read JSON
def load_json(path):
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

# Log parsing utility for Pipeline Run
def parse_pipeline_logs(log_path):
    state = {
        "active_phase": 0,
        "phases": {
            1: {"status": "pending", "details": "Awaiting keyword exploration..."},
            2: {"status": "pending", "details": "Awaiting difficulty & volume checks..."},
            3: {"status": "pending", "details": "Awaiting product capability mapping..."},
            4: {"status": "pending", "details": "Awaiting SEO article generation..."},
            5: {"status": "pending", "details": "Awaiting header image downloads & layout formatting..."},
            6: {"status": "pending", "details": "Awaiting repository commit & pull request submission..."}
        }
    }
    if not os.path.exists(log_path):
        return state

    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except:
        return state

    # Parse Agent 1
    if "PHASE 1 — AGENT 1" in content:
        state["phases"][1]["status"] = "running"
        state["active_phase"] = 1
        seeds = re.findall(r"Seed topics configured: (\d+)", content)
        kw_saved = re.findall(r"Combined total across \d+ seed topics: (\d+) unique keywords", content)
        if kw_saved:
            state["phases"][1]["status"] = "completed"
            state["phases"][1]["details"] = f"✅ Success: Discovered {kw_saved[-1]} unique search opportunities."
        elif seeds:
            state["phases"][1]["details"] = f"🔍 Active: Mining search terms from Serper API (Topics config: {seeds[-1]})...."
        else:
            state["phases"][1]["details"] = "🔍 Starting Keyword Discovery..."

    # Parse Agent 2
    if "PHASE 2 — AGENT 2" in content:
        state["phases"][1]["status"] = "completed"
        state["phases"][2]["status"] = "running"
        state["active_phase"] = 2
        passed = re.findall(r"Passed:\s*(\d+)", content)
        failed = re.findall(r"Failed \(Too Hard\):\s*(\d+)", content)
        winnable = re.findall(r"Passing (\d+) winnable keywords", content)
        if winnable:
            state["phases"][2]["status"] = "completed"
            state["phases"][2]["details"] = f"✅ Success: Passed {winnable[-1]} low-competition terms. (Filtered: Failed {failed[-1] if failed else 0})."
        elif passed or failed:
            state["phases"][2]["details"] = f"⚡ Active: Filtering search volume & difficulty (Passed: {passed[-1] if passed else 0}, Failed: {failed[-1] if failed else 0})...."
        else:
            state["phases"][2]["details"] = "⚡ Active: Fetching SERP metrics & assessing winnability..."

    # Parse Agent 3
    if "PHASE 3 — AGENT 3" in content:
        state["phases"][2]["status"] = "completed"
        state["phases"][3]["status"] = "running"
        state["active_phase"] = 3
        clusters = re.findall(r"Clustered into (\d+) topic clusters", content)
        rejected = re.findall(r"Rejected (\d+) keywords", content)
        if clusters:
            state["phases"][3]["status"] = "completed"
            state["phases"][3]["details"] = f"✅ Success: Grouped into {clusters[-1]} editorial clusters. (Rejected {rejected[-1] if rejected else 0} due to lack of product fit)."
        else:
            state["phases"][3]["details"] = "🧠 Active: Matching terms with InvoHydra product capabilities..."

    # Parse Agent 4
    if "PHASE 4 — AGENT 4" in content:
        state["phases"][3]["status"] = "completed"
        state["phases"][4]["status"] = "running"
        state["active_phase"] = 4
        writing_for = re.findall(r"Generating blog for:\s*'([^']+)'", content)
        saved_blog = re.findall(r"Saved blog post to:\s*([^\n]+)", content)
        total_clusters = re.findall(r"Total clusters:\s*(\d+)", content)
        limit = re.findall(r"Limiting generation to (\d+) new blog posts", content)
        
        tot_target = limit[-1] if limit else (total_clusters[-1] if total_clusters else "?")
        done_count = len(saved_blog)
        
        if "ILLUSTRATION COMPLETE" in content or "Found" in content and "blogs to illustrate" in content:
            state["phases"][4]["status"] = "completed"
            state["phases"][4]["details"] = f"✅ Success: Authored {done_count} premium articles."
        elif writing_for:
            state["phases"][4]["details"] = f"✍️ Active: Writing article {done_count + 1} of {tot_target}: '{writing_for[-1]}'"
        else:
            state["phases"][4]["details"] = "✍️ Active: Preparing blog structures and outline schemas..."

    # Parse Agent 4.5
    if "blogs to illustrate" in content or "Fetching unique Unsplash header image" in content or "📸" in content:
        state["phases"][4]["status"] = "completed"
        state["phases"][5]["status"] = "running"
        state["active_phase"] = 5
        illustrated = re.findall(r"Successfully fetched and saved Unsplash image", content)
        to_illustrate = re.findall(r"Found (\d+) blogs to illustrate", content)
        tot_illustrate = to_illustrate[-1] if to_illustrate else "?"
        
        if "ILLUSTRATION COMPLETE" in content or "PHASE 5 — AUTO-PUBLISHER" in content:
            state["phases"][5]["status"] = "completed"
            state["phases"][5]["details"] = f"✅ Success: Gathered header illustrations for all {tot_illustrate} articles."
        else:
            state["phases"][5]["details"] = f"📸 Active: Querying Unsplash for matching media (Completed: {len(illustrated)} of {tot_illustrate})..."

    # Parse Agent 5
    if "PHASE 5 — AUTO-PUBLISHER" in content:
        state["phases"][5]["status"] = "completed"
        state["phases"][6]["status"] = "running"
        state["active_phase"] = 6
        if "PIPELINE RUN COMPLETE" in content:
            state["phases"][6]["status"] = "completed"
            state["phases"][6]["details"] = "✅ Success: Content synced, branch pushed, and Pull Request generated."
        else:
            state["phases"][6]["details"] = "🚀 Active: Cloning website repository and pushing changes..."

    return state

# Log parsing utility for Auditor Run
def parse_audit_logs(log_path):
    state = {
        "status": "pending",
        "details": "Awaiting rank audit trigger..."
    }
    if not os.path.exists(log_path):
        return state

    try:
        with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except:
        return state

    if "🕵️  AGENT 6: PERFORMANCE AUDITOR" in content:
        state["status"] = "running"
        found_blogs = re.findall(r"Found (\d+) published blogs", content)
        checking_lines = re.findall(r"Checking rank for keyword:", content)
        checked_count = len(checking_lines)
        tot_blogs = found_blogs[-1] if found_blogs else "?"
        
        if "Auditing completed" in content or "Saved audit report" in content:
            state["status"] = "completed"
            state["details"] = f"✅ Success: Audited all {tot_blogs} blogs against target SERPs."
        else:
            state["details"] = f"🕵️ Active: Checking live Google positions... (Audited: {checked_count} of {tot_blogs})"
    return state

# Log parsing utility for Feature Updater Run
def parse_updater_logs(content):
    state = {
        "status": "pending",
        "details": "Awaiting Feature Updater trigger...",
        "changes": [],
        "new_topics": []
    }
    if not content:
        return state

    if "Starting Feature Truth Auto-Updater" in content:
        state["status"] = "running"
        state["details"] = "Starting Feature Updater agent..."

    # Check scraping
    scraping_urls = re.findall(r"🔍 Scraping: ([^\n\r]+)", content)
    if scraping_urls:
        state["details"] = f"🔍 Scraping website pages (Last: {scraping_urls[-1]})..."

    if "Analyzing features with Groq LLM" in content:
        state["details"] = "🧠 Analyzing features with Groq LLM..."

    if "Successfully updated" in content or "No changes detected in features" in content:
        state["details"] = "✅ Features analyzed and updated."

    # Parse changes
    if "Changes detected:" in content:
        changes_part = content.split("Changes detected:")[-1]
        for line in changes_part.splitlines():
            line = line.strip()
            if line.startswith("- "):
                state["changes"].append(line[2:])
            elif line and not line.startswith("-") and "Checking for new seed topics" in line:
                break

    if "Checking for new seed topics" in content:
        state["details"] = "🧠 Checking for new seed topics to generate..."

    # Parse generated topics
    if "Generated" in content and "NEW seed topics:" in content:
        topics_part = content.split("NEW seed topics:")[-1]
        for line in topics_part.splitlines():
            line = line.strip()
            if line.startswith("- "):
                state["new_topics"].append(line[2:])
            elif line and "Successfully appended" in line:
                break

    if "Successfully appended new topics" in content:
        state["status"] = "completed"
        state["details"] = f"✅ Success: Generated and appended {len(state['new_topics'])} new seed topics."
    elif "No new seed topics needed" in content:
        state["status"] = "completed"
        state["details"] = "✅ Success: Feature map updated. No new seed topics needed."
    elif "Groq API request failed" in content or "Failed to load" in content:
        state["status"] = "failed"
        state["details"] = "❌ Failed: Error encountered during execution."

    return state

# Helper to render status badge HTML
def render_status(status):
    if status == "running":
        return '<span class="status-badge status-running">● Running</span>'
    elif status == "completed" or status == "success":
        return '<span class="status-badge status-completed">✓ Done</span>'
    elif status == "failed" or status == "failure" or status == "cancelled":
        return '<span class="status-badge status-failed">✗ Failed</span>'
    else:
        return '<span class="status-badge status-pending">○ Pending</span>'

# Helper to render GHA status badges
def render_gha_status(status, conclusion):
    if status == "in_progress":
        return '<span class="status-badge status-running">● Running</span>'
    elif status == "queued":
        return '<span class="status-badge status-pending">○ Queued</span>'
    elif status == "completed":
        if conclusion == "success":
            return '<span class="status-badge status-completed">✓ Success</span>'
        elif conclusion == "failure":
            return '<span class="status-badge status-failed">✗ Failed</span>'
        else:
            return f'<span class="status-badge status-failed">✗ {conclusion.capitalize()}</span>'
    return f'<span class="status-badge status-pending">○ {status.capitalize()}</span>'

# ─── SIDEBAR: GLOBAL CONTROLS ──────────────────────────────────────────
with st.sidebar:
    st.title("InvoHydra SEO")
    st.markdown("Enterprise SEO Pipeline Control")
    st.divider()
    
    is_cloud = True
    
    with st.expander("⚙️ Pipeline Options", expanded=False):
        topic_override = st.text_input("Topic Override (Optional)", placeholder="e.g., Enterprise SEO")
        blog_limit = st.number_input("Blog Generation Limit", min_value=1, max_value=20, value=2)

    if st.button("Execute AI Pipeline", type="primary", width="stretch"):
        inputs = {"limit": str(blog_limit)}
        if topic_override.strip():
            inputs["topic"] = topic_override.strip()
        
        st.info("Triggering remote GitHub actions workflow...")
        success = trigger_workflow_dispatch(PIPELINE_REPO, "seo-pipeline.yml", "main", inputs, GITHUB_TOKEN)
        if success:
            st.success("🎉 SEO Pipeline triggered successfully!")
            time.sleep(2)
            st.rerun()
        else:
            st.error("Failed to trigger pipeline workflow on GitHub Actions.")
            
    if st.button("Run SEO Rank Audit", width="stretch"):
        st.info("Triggering remote GitHub Actions auditor...")
        success = trigger_workflow_dispatch(PIPELINE_REPO, "seo-auditor.yml", "main", None, GITHUB_TOKEN)
        if success:
            st.success("🎉 Auditor triggered successfully!")
            time.sleep(2)
            st.rerun()
        else:
            st.error("Failed to trigger auditor workflow on GitHub Actions.")

    if st.button("Run Feature Updater", width="stretch"):
        st.info("Triggering remote Feature Updater...")
        success = trigger_workflow_dispatch(PIPELINE_REPO, "feature-updater.yml", "main", None, GITHUB_TOKEN)
        if success:
            st.success("🎉 Feature Updater triggered successfully!")
            time.sleep(2)
            st.rerun()
        else:
            st.error("Failed to trigger Feature Updater workflow on GitHub Actions.")
        
    st.divider()
    st.caption("System Status: Online")
    st.caption("Version: 2.1.0 (Enterprise)")

# ─── HEADER & GLOBAL METRICS ───────────────────────────────────────────
st.title("Search Engine Operations")
st.markdown("Centralized monitoring and control system for automated content generation and ranking analytics.")
st.divider()

# Load Data based on Dashboard Mode
if is_cloud:
    # 1. Fetch JSON reports from Pipeline Repository main branch
    st.sidebar.info("🌐 Fetching report data from GitHub...")
    diff_report = load_json_from_github(PIPELINE_REPO, "data/difficulty_report.json", "main", GITHUB_TOKEN)
    audit = load_json_from_github(PIPELINE_REPO, "data/audit_report.json", "main", GITHUB_TOKEN)
    state = load_json_from_github(PIPELINE_REPO, "data/pipeline_state.json", "main", GITHUB_TOKEN)
    
    # 2. Fetch published blogs from website repo blog-automation branch
    remote_blogs = get_blogs_from_github(WEBSITE_REPO, "src/app/blog/posts", "blog-automation", GITHUB_TOKEN)
    total_blogs = len(remote_blogs)
else:
    # Local Mode: load from local files
    state = load_json(STATE_FILE)
    diff_report = load_json(DIFFICULTY_REPORT)
    audit = load_json(AUDIT_REPORT)
    total_blogs = len([f for f in os.listdir(BLOGS_DIR) if f.endswith('.json')]) if os.path.exists(BLOGS_DIR) else 0

# Calculate Metrics
passed_kw = len(diff_report.get('surviving_keywords', []))
failed_kw = len(diff_report.get('failed', []))
top_10_ranks = len(audit.get("top_10", [])) if "top_10" in audit else audit.get("metrics", {}).get("top_10", 0)

# Top Metrics Row
col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Blogs Published", total_blogs)
col2.metric("Top 10 Rankings", top_10_ranks)
col3.metric("Approved Keywords", passed_kw)
col4.metric("Current Campaign Topic", state.get('current_topic', state.get('current_topic_index', 'Idle')))

st.write("") # Spacing

# Check active states (only relevant in Local Mode)
pipeline_active = not is_cloud and st.session_state["pipeline_proc"] is not None and st.session_state["pipeline_proc"].poll() is None
audit_active = not is_cloud and st.session_state["audit_proc"] is not None and st.session_state["audit_proc"].poll() is None

# ─── TABS ────────────────────────────────────────────────────────────
tab_system, tab_intelligence, tab_library, tab_analytics = st.tabs([
    "System Overview", 
    "Keyword Intelligence", 
    "Content Management", 
    "Ranking Analytics"
])

# ─── TAB 1: SYSTEM OVERVIEW ──────────────────────────────────────────
with tab_system:
    col_info_a, col_info_b = st.columns([2, 1])
    
    with col_info_a:
        if is_cloud:
            st.subheader("🌐 GitHub Actions Workflow Runs")
            st.markdown("Monitor remote automation tasks executing on GitHub runners.")
            
            # Fetch runs
            pipeline_runs = get_workflow_runs(PIPELINE_REPO, "seo-pipeline.yml", GITHUB_TOKEN, limit=3)
            audit_runs = get_workflow_runs(PIPELINE_REPO, "seo-auditor.yml", GITHUB_TOKEN, limit=3)
            updater_runs = get_workflow_runs(PIPELINE_REPO, "feature-updater.yml", GITHUB_TOKEN, limit=3)

            # Live Feature Updater Tracker (Always show latest run's parsed status/results)
            if updater_runs:
                latest_run = updater_runs[0]
                latest_status = latest_run.get("status")
                latest_conclusion = latest_run.get("conclusion")
                latest_id = latest_run.get("id")
                latest_num = latest_run.get("run_number")
                
                is_running = latest_status in ["in_progress", "queued"]
                
                with st.container(border=True):
                    st.markdown(f"#### ⚙️ Feature Updater Live Status Tracker (Run #{latest_num})")
                    
                    # Always load logs for active runs, and cache them for completed runs to avoid rate limits
                    run_logs = ""
                    if is_running:
                        run_logs = get_workflow_run_logs(PIPELINE_REPO, latest_id, GITHUB_TOKEN)
                    else:
                        cache_key = f"summary_logs_{latest_id}"
                        if cache_key not in st.session_state:
                            run_logs = get_workflow_run_logs(PIPELINE_REPO, latest_id, GITHUB_TOKEN)
                            st.session_state[cache_key] = run_logs
                        else:
                            run_logs = st.session_state[cache_key]
                    
                    parsed = parse_updater_logs(run_logs)
                    
                    col_stat, col_det = st.columns([1, 4])
                    with col_stat:
                        stat_val = "running" if is_running else ("completed" if latest_conclusion == "success" else ("failed" if latest_conclusion == "failure" else "pending"))
                        st.markdown(render_status(stat_val), unsafe_allow_html=True)
                    with col_det:
                        if is_running and not run_logs:
                            st.write("Initializing run... fetching logs.")
                        else:
                            st.write(parsed["details"])
                    
                    if parsed["changes"]:
                        st.markdown("**Detected Feature Changes:**")
                        for change in parsed["changes"]:
                            st.write(f"- {change}")
                            
                    if parsed["new_topics"]:
                        st.markdown("**Generated Seed Topics:**")
                        for topic in parsed["new_topics"]:
                            st.write(f"- `{topic}`")
                            
                    if is_running:
                        st.caption("🔄 *Auto-refreshing to stream live agent updates...*")
                    else:
                        st.caption("✅ *Run finished.*")
                st.write("") # Spacing
            
            st.markdown("### 🤖 Pipeline Runs (`seo-pipeline.yml`)")
            if pipeline_runs:
                for run in pipeline_runs:
                    run_num = run.get("run_number")
                    status = run.get("status")
                    conclusion = run.get("conclusion")
                    run_id = run.get("id")
                    created_at = run.get("created_at", "").replace("T", " ").replace("Z", "")
                    title = run.get("display_title", "Manual / Scheduled Run")
                    
                    with st.container(border=True):
                        col_run_info, col_run_action = st.columns([5, 1])
                        with col_run_info:
                            st.markdown(f"**Run #{run_num}: {title}**")
                            st.caption(f"Started: {created_at} UTC")
                            st.markdown(render_gha_status(status, conclusion), unsafe_allow_html=True)
                        with col_run_action:
                            if st.button("View Logs", key=f"logs_btn_{run_id}"):
                                st.session_state["show_logs_for_run"] = run_id
                                st.session_state["show_logs_num"] = run_num
                                st.rerun()
            else:
                st.info("No workflow runs found. Trigger the pipeline first.")
                
            st.markdown("### 🕵️ Auditor Runs (`seo-auditor.yml`)")
            if audit_runs:
                for run in audit_runs:
                    run_num = run.get("run_number")
                    status = run.get("status")
                    conclusion = run.get("conclusion")
                    run_id = run.get("id")
                    created_at = run.get("created_at", "").replace("T", " ").replace("Z", "")
                    
                    with st.container(border=True):
                        col_run_info, col_run_action = st.columns([5, 1])
                        with col_run_info:
                            st.markdown(f"**Audit Run #{run_num}**")
                            st.caption(f"Started: {created_at} UTC")
                            st.markdown(render_gha_status(status, conclusion), unsafe_allow_html=True)
                        with col_run_action:
                            if st.button("View Logs", key=f"logs_btn_{run_id}"):
                                st.session_state["show_logs_for_run"] = run_id
                                st.session_state["show_logs_num"] = run_num
                                st.rerun()
            else:
                st.info("No audit runs found.")
                
            st.markdown("### ⚙️ Feature Updater Runs (`feature-updater.yml`)")
            if updater_runs:
                for run in updater_runs:
                    run_num = run.get("run_number")
                    status = run.get("status")
                    conclusion = run.get("conclusion")
                    run_id = run.get("id")
                    created_at = run.get("created_at", "").replace("T", " ").replace("Z", "")
                    
                    with st.container(border=True):
                        col_run_info, col_run_action = st.columns([5, 1])
                        with col_run_info:
                            st.markdown(f"**Feature Updater Run #{run_num}**")
                            st.caption(f"Started: {created_at} UTC")
                            st.markdown(render_gha_status(status, conclusion), unsafe_allow_html=True)
                        with col_run_action:
                            if st.button("View Logs", key=f"logs_btn_{run_id}"):
                                st.session_state["show_logs_for_run"] = run_id
                                st.session_state["show_logs_num"] = run_num
                                st.rerun()
            else:
                st.info("No Feature Updater runs found.")
                
            # Log Viewer Section
            if st.session_state["show_logs_for_run"]:
                st.write("")
                st.divider()
                selected_run_id = st.session_state["show_logs_for_run"]
                selected_run_num = st.session_state["show_logs_num"]
                st.subheader(f"🖥️ Execution Logs (Run #{selected_run_num})")
                
                col_log_actions_1, col_log_actions_2 = st.columns([5, 1])
                with col_log_actions_2:
                    if st.button("Close Logs", key="close_logs_btn"):
                        st.session_state["show_logs_for_run"] = None
                        st.session_state["show_logs_num"] = None
                        st.rerun()
                        
                with st.spinner("Downloading and parsing logs from GitHub Actions..."):
                    logs_content = get_workflow_run_logs(PIPELINE_REPO, selected_run_id, GITHUB_TOKEN)
                st.code(logs_content, language="text")
        else:
            st.subheader("⚡ Live Agent Workspace")
            st.markdown("Monitor local automated agent interactions during campaign execution.")
            
            # Render the Stepper Pipeline
            log_path = "data/pipeline_run.log"
            pipeline_status = parse_pipeline_logs(log_path)
            
            st.markdown('<div class="agent-grid">', unsafe_allow_html=True)
            
            # Agent 1
            a1_status = pipeline_status["phases"][1]["status"]
            a1_details = pipeline_status["phases"][1]["details"]
            st.markdown(f"""
            <div class="agent-card">
                <div class="agent-info">
                    <div class="agent-header-row">
                        <p class="agent-title">Agent 1: Keyword Discoverer</p>
                    </div>
                    <p class="agent-desc">{a1_details}</p>
                </div>
                {render_status(a1_status)}
            </div>
            """, unsafe_allow_html=True)
            
            # Agent 2
            a2_status = pipeline_status["phases"][2]["status"]
            a2_details = pipeline_status["phases"][2]["details"]
            st.markdown(f"""
            <div class="agent-card">
                <div class="agent-info">
                    <div class="agent-header-row">
                        <p class="agent-title">Agent 2: Difficulty Analyst</p>
                    </div>
                    <p class="agent-desc">{a2_details}</p>
                </div>
                {render_status(a2_status)}
            </div>
            """, unsafe_allow_html=True)
            
            # Agent 3
            a3_status = pipeline_status["phases"][3]["status"]
            a3_details = pipeline_status["phases"][3]["details"]
            st.markdown(f"""
            <div class="agent-card">
                <div class="agent-info">
                    <div class="agent-header-row">
                        <p class="agent-title">Agent 3: Semantic Clusterer</p>
                    </div>
                    <p class="agent-desc">{a3_details}</p>
                </div>
                {render_status(a3_status)}
            </div>
            """, unsafe_allow_html=True)
            
            # Agent 4
            a4_status = pipeline_status["phases"][4]["status"]
            a4_details = pipeline_status["phases"][4]["details"]
            st.markdown(f"""
            <div class="agent-card">
                <div class="agent-info">
                    <div class="agent-header-row">
                        <p class="agent-title">Agent 4: Blog Writer</p>
                    </div>
                    <p class="agent-desc">{a4_details}</p>
                </div>
                {render_status(a4_status)}
            </div>
            """, unsafe_allow_html=True)
            
            # Agent 4.5
            a5_status = pipeline_status["phases"][5]["status"]
            a5_details = pipeline_status["phases"][5]["details"]
            st.markdown(f"""
            <div class="agent-card">
                <div class="agent-info">
                    <div class="agent-header-row">
                        <p class="agent-title">Agent 4.5: Media Illustrator</p>
                    </div>
                    <p class="agent-desc">{a5_details}</p>
                </div>
                {render_status(a5_status)}
            </div>
            """, unsafe_allow_html=True)
            
            # Agent 5
            a6_status = pipeline_status["phases"][6]["status"]
            a6_details = pipeline_status["phases"][6]["details"]
            st.markdown(f"""
            <div class="agent-card">
                <div class="agent-info">
                    <div class="agent-header-row">
                        <p class="agent-title">Agent 5: Auto-Publisher</p>
                    </div>
                    <p class="agent-desc">{a6_details}</p>
                </div>
                {render_status(a6_status)}
            </div>
            """, unsafe_allow_html=True)
            
            # Agent 6 (Performance Auditor)
            audit_log_path = "data/audit_run.log"
            audit_status = parse_audit_logs(audit_log_path)
            if audit_active or audit_status["status"] != "pending":
                st.markdown(f"""
                <div class="agent-card">
                    <div class="agent-info">
                        <div class="agent-header-row">
                            <p class="agent-title">Agent 6: Performance Auditor</p>
                        </div>
                        <p class="agent-desc">{audit_status["details"]}</p>
                    </div>
                    {render_status(audit_status["status"])}
                </div>
                """, unsafe_allow_html=True)
                
            st.markdown('</div>', unsafe_allow_html=True)
        
    with col_info_b:
        st.subheader("📋 Pipeline Context")
        with st.container(border=True):
            st.markdown("**Campaign Active / Selected Index:**")
            if is_cloud:
                idx = state.get("current_topic_index", "N/A")
                st.write(f"Index {idx} of 16 (Seed topic rotates dynamically)")
            else:
                st.write(state.get('current_topic', 'None (Idle)'))
            st.markdown("**Last Action Date:**")
            st.write(state.get('last_run_date', state.get('last_topic_change_date', 'None')))
            st.markdown("**Domain Host:**")
            st.write(WEBSITE_REPO.split("/")[-1] if "/" in WEBSITE_REPO else WEBSITE_REPO)
            st.markdown("**Health Status:**")
            if is_cloud:
                # Find if any active GHA run is executing
                pipeline_running = pipeline_runs and pipeline_runs[0].get("status") in ["in_progress", "queued"]
                audit_running = audit_runs and audit_runs[0].get("status") in ["in_progress", "queued"]
                updater_running = updater_runs and updater_runs[0].get("status") in ["in_progress", "queued"]
                if pipeline_running:
                    st.info("⚡ Pipeline Running on GitHub")
                elif audit_running:
                    st.info("🕵️ Auditor Running on GitHub")
                elif updater_running:
                    st.info("⚙️ Feature Updater Running on GitHub")
                else:
                    st.success("🟢 Ready (All Workflows Idle)")
            else:
                if pipeline_active:
                    st.info("⚡ Execution In Progress")
                elif audit_active:
                    st.info("🕵️ Rank Auditing In Progress")
                else:
                    st.success("🟢 Ready / Idle")
 
    # Auto-refresh loop for live cloud streaming
    if is_cloud:
        pipeline_running = pipeline_runs and pipeline_runs[0].get("status") in ["in_progress", "queued"]
        audit_running = audit_runs and audit_runs[0].get("status") in ["in_progress", "queued"]
        updater_running = updater_runs and updater_runs[0].get("status") in ["in_progress", "queued"]
        
        if pipeline_running or audit_running or updater_running:
            st.info("🔄 Active run detected on GitHub. Dashboard is auto-refreshing in 6 seconds to stream live logs and update metrics...")
            time.sleep(6)
            st.rerun()

# ─── TAB 2: KEYWORD INTELLIGENCE ─────────────────────────────────────
with tab_intelligence:
    st.subheader("Keyword Difficulty & Viability Analysis")
    st.markdown("Automated SERP analysis filtering high-competition queries.")
    
    if diff_report:
        col_pass, col_fail = st.columns(2)
        
        with col_pass:
            st.markdown(f"**Approved Targets ({passed_kw})**")
            surviving = diff_report.get('surviving_keywords', [])
            if surviving:
                st.dataframe([{"Approved Keyword": kw} for kw in surviving], width="stretch", hide_index=True)
                
        with col_fail:
            st.markdown(f"**Rejected Targets ({failed_kw})**")
            failed_kws = diff_report.get('failed', [])
            if failed_kws:
                full_report = diff_report.get('full_report', [])
                failed_data = []
                for kw in failed_kws:
                     reason = "Too competitive"
                     for item in full_report:
                         if item.get("keyword") == kw:
                             reason = item.get("reason", reason)
                             break
                     failed_data.append({"Keyword": kw, "Rejection Reason": reason})
                st.dataframe(failed_data, width="stretch", hide_index=True)
                
        st.divider()
        st.markdown("**Detailed Winnability Report**")
        full_report = diff_report.get('full_report', [])
        if full_report:
            report_data = []
            for item in full_report:
                report_data.append({
                    "Keyword": item.get("keyword"),
                    "Verdict": item.get("verdict"),
                    "Score": item.get("score"),
                    "Reason": item.get("reason")
                })
            st.dataframe(report_data, width="stretch", hide_index=True)
            
        CLUSTERS_FILE = os.path.join(DATA_DIR, "clustered_keywords.json") if not is_cloud else None
        clusters_data = None
        if is_cloud:
            clusters_data = load_json_from_github(PIPELINE_REPO, "data/clustered_keywords.json", "main", GITHUB_TOKEN)
        elif CLUSTERS_FILE and os.path.exists(CLUSTERS_FILE):
            clusters_data = load_json(CLUSTERS_FILE)
            
        if clusters_data and "clusters" in clusters_data:
            st.divider()
            st.markdown("**Semantic Clusters & Capability Alignment**")
            cluster_rows = []
            for cluster in clusters_data["clusters"]:
                cluster_rows.append({
                    "Hub Topic": cluster.get("hub_topic"),
                    "Demand": cluster.get("demand"),
                    "Intent": cluster.get("intent"),
                    "Product Fit Rationale": cluster.get("product_fit_rationale"),
                    "Keywords": ", ".join(cluster.get("keywords", []))
                })
            st.dataframe(cluster_rows, width="stretch", hide_index=True)
    else:
        st.warning("No keyword intelligence data available. Execute the pipeline to populate this section.")

# ─── TAB 3: CONTENT MANAGEMENT ──────────────────────────────────────────
with tab_library:
    st.subheader("Content Management System")
    st.markdown("Review and manage AI-generated editorial content before final deployment.")
    
    if is_cloud:
        st.markdown(f"📂 *Showing blogs published on the `{SAFE_BRANCH_NAME}` branch of `{WEBSITE_REPO}`*")
        if remote_blogs:
            for file, blog_data in remote_blogs:
                title = blog_data.get("meta_title", "Untitled Document")
                with st.expander(f"📄 {title}"):
                    col_meta, col_content = st.columns([1, 2])
                    with col_meta:
                        st.markdown("**Target Keyword**")
                        st.write(f"`{blog_data.get('target_keyword', 'N/A')}`")
                        st.markdown("**Meta Description**")
                        st.write(blog_data.get('meta_description', 'N/A'))
                        st.markdown("**Repository Filename**")
                        st.code(file)
                    with col_content:
                        st.markdown("**Markdown Body Preview**")
                        st.markdown(blog_data.get("markdown_body", "No content available."))
        else:
            st.warning("Content library is currently empty or remote repository blogs folder could not be read.")
    else:
        st.markdown("📂 *Showing blogs generated locally in this workspace*")
        if os.path.exists(BLOGS_DIR) and total_blogs > 0:
            blog_files = [f for f in os.listdir(BLOGS_DIR) if f.endswith('.json')]
            for file in blog_files:
                blog_data = load_json(os.path.join(BLOGS_DIR, file))
                title = blog_data.get("meta_title", "Untitled Document")
                with st.expander(f"{title}"):
                    col_meta, col_content = st.columns([1, 2])
                    with col_meta:
                        st.markdown("**Target Keyword**")
                        st.write(f"`{blog_data.get('target_keyword', 'N/A')}`")
                        st.markdown("**Meta Description**")
                        st.write(blog_data.get('meta_description', 'N/A'))
                        st.markdown("**File System Reference**")
                        st.code(file)
                    with col_content:
                        st.markdown("**Markdown Body Preview**")
                        st.markdown(blog_data.get("markdown_body", "No content available."))
        else:
            st.warning("Content library is currently empty.")

# ─── TAB 4: RANKING ANALYTICS ──────────────────────────────────────────────
with tab_analytics:
    st.subheader("Search Engine Performance")
    st.markdown("Continuous monitoring of target keywords against the primary domain.")
    
    if audit:
        # Resolve metrics dynamically based on three categories
        n_top10 = len(audit.get("top_10", []))
        n_page2 = len(audit.get("page_2_refresh", []))
        n_unranked = len(audit.get("not_found_or_deep", []))
        
        with st.container(border=True):
            m1, m2, m3 = st.columns(3)
            m1.metric("Pages in Top 10", n_top10)
            m2.metric("Pages on Page 2 (Needs Refresh)", n_page2)
            m3.metric("Pages Unranked / Deep", n_unranked)
            
        st.write("")
        st.markdown("**Detailed Position Tracking**")
        
        all_results = []
        for item in audit.get("top_10", []):
            all_results.append({
                "Target Keyword": item.get("keyword"),
                "SERP Position": item.get("rank"),
                "Blog File": item.get("filename"),
                "Resolved URL": item.get("url")
            })
        for item in audit.get("page_2_refresh", []):
            all_results.append({
                "Target Keyword": item.get("keyword"),
                "SERP Position": item.get("rank"),
                "Blog File": item.get("filename"),
                "Resolved URL": item.get("url")
            })
        for item in audit.get("not_found_or_deep", []):
            all_results.append({
                "Target Keyword": item.get("keyword"),
                "SERP Position": "Not Found / Deep" if item.get("rank") == -1 else item.get("rank"),
                "Blog File": item.get("filename"),
                "Resolved URL": item.get("url") or "N/A"
            })
            
        if all_results:
            st.dataframe(all_results, width="stretch", hide_index=True)
        else:
            st.info("No rankings recorded in the report.")
    else:
        st.warning("Analytics data unavailable. Execute an SEO Rank Audit from the sidebar.")


