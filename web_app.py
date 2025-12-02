import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import streamlit as st
import os
import time
from pathlib import Path
from slugify import slugify

# Import your existing backend logic
try:
    from autoflow.web_automation import run_task_on_webapp
    from autoflow.url_inference import get_url_for_task
    from autoflow.brand_utils import extract_brands
except ImportError:
    # Fallback if you renamed the package to 'autoflow'
    from autoflow.web_automation import run_task_on_webapp
    from autoflow.url_inference import get_url_for_task
    from autoflow.brand_utils import extract_brands

# --- Page Config ---
st.set_page_config(
    page_title="AutoFlow Web Interface",
    page_icon="🤖",
    layout="wide"
)

# --- Header ---
st.title("🤖 AutoFlow Agent")
st.markdown("Enter a natural language task, and the AI agent will navigate the web to perform it.")

# --- Sidebar Controls ---
with st.sidebar:
    st.header("⚙️ Configuration")
    
    # Mode Settings
    headless = st.toggle("Headless Mode", value=True, help="Run browser in background (faster)")
    no_auth = st.toggle("Skip Authentication", value=False, help="Don't attempt to log in automatically")
    
    st.divider()

    # Cookie Session Support
    use_cookies = st.toggle("Use Saved Cookies", value=False, help="Load a saved session (bypasses 2FA)")
    cookies_path = None
    if use_cookies:
        # We use a text input because the file exists on the SERVER (your PC), not the browser client
        # Defaulting to a common example path
        cookies_path = st.text_input("Cookie File Path", value="cookies/github.json", help="Relative path to your cookie file")
        if not os.path.exists(cookies_path):
            st.error(f"File not found: {cookies_path}")
    
    st.divider()
    
    # Credentials
    st.subheader("🔐 Credentials (Optional)")
    st.caption("Only used if cookies are disabled")
    cred_email = st.text_input("Email / Username", placeholder="user@example.com", disabled=use_cookies)
    cred_password = st.text_input("Password", type="password", disabled=use_cookies)
    
    st.divider()
    st.caption("Powered by AutoFlow v1.0")

# --- Main Interface ---
col1, col2 = st.columns([3, 1])
with col1:
    task_input = st.text_input("Enter your task:", placeholder="e.g., Search for playwright in npm")
with col2:
    # Add some vertical spacing to align button
    st.write("") 
    st.write("")
    run_btn = st.button("🚀 Run Agent", type="primary", use_container_width=True)

# --- Execution Logic ---
if run_btn and task_input:
    status_area = st.empty()
    results_area = st.container()

    with status_area.status("🚀 Initializing Agent...", expanded=True) as status:
        try:
            # 1. Infer URL (Reusing logic from __main__.py)
            st.write("🔍 Inferring target URL...")
            url = get_url_for_task(task_input)
            st.write(f"✅ Target: {url}")

            # 2. Setup Output Directory
            brands = extract_brands(task_input)
            if url:
                try:
                    from urllib.parse import urlparse
                    host = urlparse(url).hostname or url
                    app_slug = slugify(host)
                except Exception:
                    app_slug = slugify(url)
            else:
                app_slug = slugify(brands[0]) if brands else "manual_navigation"
            
            task_slug = slugify(task_input)[:80]
            # Use a specialized web_runs folder to keep it separate, or keep standard dataset/
            out_dir = Path("dataset") / app_slug / task_slug
            os.makedirs(out_dir, exist_ok=True)
            
            st.write(f"📂 Output Directory: `{out_dir}`")

            # 3. Run Automation
            st.write("🏃‍♂️ Executing workflow (check terminal for live logs)...")
            
            # We wrap this to catch output or just rely on file generation
            run_task_on_webapp(
                task=task_input,
                url=url,
                out_dir=out_dir,
                headless=headless,
                skip_auth=no_auth,
                cred_email=cred_email if cred_email else None,
                cred_password=cred_password if cred_password else None,
                cookies_path=cookies_path if use_cookies else None
            )
            
            status.update(label="✅ Workflow Complete!", state="complete", expanded=False)

        except Exception as e:
            status.update(label="❌ Error Occurred", state="error")
            st.error(f"An error occurred: {str(e)}")
            st.stop()

    # --- Results Display ---
    with results_area:
        st.divider()
        st.subheader("📸 Execution Artifacts")
        
        # 1. Display Log
        log_file = out_dir / "steps_log.md"
        if log_file.exists():
            with st.expander("📄 View Execution Log", expanded=False):
                st.markdown(log_file.read_text(encoding="utf-8"))

        # 2. Display Screenshots Gallery
        st.write("#### Captured States")
        
        # Get all png files, sorted by step number
        screenshots = sorted(list(out_dir.glob("*.png")))
        
        if screenshots:
            # Create a gallery layout
            cols = st.columns(2)
            for i, img_path in enumerate(screenshots):
                with cols[i % 2]:
                    # Format filename nicely: "step_01_click.png" -> "Step 01: Click"
                    caption = img_path.stem.replace("_", " ").title()
                    st.image(str(img_path), caption=caption, use_container_width=True)
        else:
            st.warning("No screenshots captured.")

elif run_btn and not task_input:
    st.warning("Please enter a task first.")