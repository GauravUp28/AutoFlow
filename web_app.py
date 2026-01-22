import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

import streamlit as st
import os
import time
import json
from pathlib import Path
from slugify import slugify
from datetime import datetime

# Import your existing backend logic
try:
    from autoflow.web_automation import run_task_on_webapp
    from autoflow.url_inference import get_url_for_task
    from autoflow.brand_utils import extract_brands
except ImportError:
    from autoflow.web_automation import run_task_on_webapp
    from autoflow.url_inference import get_url_for_task
    from autoflow.brand_utils import extract_brands

# --- Page Config ---
st.set_page_config(
    page_title="AutoFlow - AI Web Automation",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Custom CSS for Dark Theme ---
st.markdown("""
<style>
    /* Main container */
    .main .block-container {
        padding-top: 2rem;
        padding-bottom: 2rem;
        max-width: 1200px;
    }

    /* Header styling */
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem 2.5rem;
        border-radius: 16px;
        margin-bottom: 2rem;
        color: white;
        box-shadow: 0 4px 20px rgba(102, 126, 234, 0.3);
    }
    .main-header h1 {
        margin: 0;
        font-size: 2.5rem;
        font-weight: 700;
        color: white !important;
    }
    .main-header p {
        margin: 0.5rem 0 0 0;
        opacity: 0.9;
        font-size: 1.1rem;
        color: rgba(255,255,255,0.9) !important;
    }

    /* Metric cards */
    .metric-card {
        background: linear-gradient(135deg, rgba(102, 126, 234, 0.15) 0%, rgba(118, 75, 162, 0.15) 100%);
        padding: 1.25rem;
        border-radius: 12px;
        border-left: 4px solid #667eea;
        margin-bottom: 1rem;
        backdrop-filter: blur(10px);
    }
    .metric-card.success {
        border-left-color: #10b981;
        background: linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(16, 185, 129, 0.05) 100%);
    }
    .metric-card.warning {
        border-left-color: #f59e0b;
        background: linear-gradient(135deg, rgba(245, 158, 11, 0.15) 0%, rgba(245, 158, 11, 0.05) 100%);
    }
    .metric-card.error {
        border-left-color: #ef4444;
        background: linear-gradient(135deg, rgba(239, 68, 68, 0.15) 0%, rgba(239, 68, 68, 0.05) 100%);
    }
    .metric-card h3 {
        margin: 0;
        font-size: 0.75rem;
        color: #a1a1aa !important;
        text-transform: uppercase;
        letter-spacing: 0.1em;
        font-weight: 600;
    }
    .metric-card .value {
        font-size: 2rem;
        font-weight: 700;
        color: #fafafa !important;
        margin: 0.25rem 0 0 0;
    }

    /* Screenshot gallery */
    .screenshot-card {
        background: rgba(255, 255, 255, 0.03);
        border-radius: 12px;
        padding: 0.75rem;
        margin-bottom: 1rem;
        border: 1px solid rgba(255, 255, 255, 0.08);
        transition: all 0.2s ease;
    }
    .screenshot-card:hover {
        background: rgba(255, 255, 255, 0.06);
        border-color: rgba(102, 126, 234, 0.3);
        transform: translateY(-2px);
    }
    .step-badge {
        display: inline-block;
        padding: 0.35rem 0.85rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
        margin-bottom: 0.75rem;
        color: white !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    .step-badge.default { background: linear-gradient(135deg, #667eea, #764ba2); }
    .step-badge.action-click { background: linear-gradient(135deg, #3b82f6, #2563eb); }
    .step-badge.action-fill { background: linear-gradient(135deg, #10b981, #059669); }
    .step-badge.action-navigate { background: linear-gradient(135deg, #8b5cf6, #7c3aed); }
    .step-badge.action-press { background: linear-gradient(135deg, #f59e0b, #d97706); }
    .step-badge.action-wait { background: linear-gradient(135deg, #6b7280, #4b5563); }
    .step-badge.action-scroll { background: linear-gradient(135deg, #ec4899, #db2777); }
    .step-badge.success { background: linear-gradient(135deg, #10b981, #059669); }
    .step-badge.error { background: linear-gradient(135deg, #ef4444, #dc2626); }
    .step-badge.layer { background: linear-gradient(135deg, #8b5cf6, #7c3aed); }
    .step-badge.initial { background: linear-gradient(135deg, #06b6d4, #0891b2); }

    /* Timeline */
    .timeline-container {
        position: relative;
        padding-left: 28px;
        margin-top: 1rem;
    }
    .timeline-container::before {
        content: '';
        position: absolute;
        left: 8px;
        top: 0;
        bottom: 0;
        width: 2px;
        background: linear-gradient(180deg, #667eea 0%, #764ba2 100%);
        border-radius: 2px;
    }
    .timeline-item {
        position: relative;
        padding: 0.75rem 0 1.25rem 0;
    }
    .timeline-item strong {
        color: #e4e4e7 !important;
        font-size: 0.9rem;
    }
    .timeline-item::before {
        content: '';
        position: absolute;
        left: -24px;
        top: 0.85rem;
        width: 10px;
        height: 10px;
        border-radius: 50%;
        background: #667eea;
        border: 2px solid #1a1a2e;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.3);
    }
    .timeline-item.success::before {
        background: #10b981;
        box-shadow: 0 0 0 3px rgba(16, 185, 129, 0.3);
    }
    .timeline-item.error::before {
        background: #ef4444;
        box-shadow: 0 0 0 3px rgba(239, 68, 68, 0.3);
    }

    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #16162a 100%);
    }
    section[data-testid="stSidebar"] .stMarkdown h2 {
        color: #e4e4e7 !important;
        font-size: 1rem;
        font-weight: 600;
        border-bottom: 2px solid #667eea;
        padding-bottom: 0.5rem;
        margin-bottom: 1rem;
    }
    section[data-testid="stSidebar"] .stMarkdown h3 {
        color: #a1a1aa !important;
        font-size: 0.85rem;
        font-weight: 600;
        margin-top: 1.25rem;
        margin-bottom: 0.5rem;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }

    /* Button styling */
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        border: none !important;
        padding: 0.65rem 1.5rem;
        font-weight: 600;
        border-radius: 10px;
        transition: all 0.2s ease;
        box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
    }
    .stButton > button[kind="primary"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(102, 126, 234, 0.4);
    }

    /* Input styling */
    .stTextInput > div > div > input {
        border-radius: 10px !important;
        border: 2px solid rgba(255, 255, 255, 0.1) !important;
        background: rgba(255, 255, 255, 0.05) !important;
        padding: 0.75rem 1rem !important;
        font-size: 1rem;
        transition: all 0.2s ease;
    }
    .stTextInput > div > div > input:focus {
        border-color: #667eea !important;
        box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.2) !important;
    }

    /* Hide "Press Enter to apply" instruction */
    div[data-testid="InputInstructions"],
    .stTextInput div[data-testid="InputInstructions"],
    [data-testid="InputInstructions"] {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        height: 0 !important;
        overflow: hidden !important;
    }

    /* Results section */
    .results-header {
        background: linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(16, 185, 129, 0.05) 100%);
        padding: 1.25rem 1.5rem;
        border-radius: 12px;
        border-left: 4px solid #10b981;
        margin-bottom: 1.5rem;
    }
    .results-header h3 {
        color: #34d399 !important;
        margin: 0 !important;
        font-size: 1.1rem;
    }
    .results-header p {
        color: #6ee7b7 !important;
        margin: 0.5rem 0 0 0 !important;
        font-size: 0.9rem;
    }

    /* Section title styling */
    .section-title {
        color: #e4e4e7 !important;
        font-size: 1.1rem;
        font-weight: 600;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }

    /* Tabs styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 0.5rem;
        background: transparent;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px;
        padding: 0.5rem 1rem;
        background: rgba(255, 255, 255, 0.05);
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
    }

    /* Expander styling */
    .streamlit-expanderHeader {
        background: rgba(255, 255, 255, 0.03) !important;
        border-radius: 8px !important;
    }

    /* Footer */
    .footer-text {
        text-align: center;
        color: #71717a;
        font-size: 0.85rem;
        padding: 1rem 0;
    }

    /* Hide default Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}

    /* Divider */
    hr {
        border-color: rgba(255, 255, 255, 0.1) !important;
        margin: 1.5rem 0;
    }
</style>
""", unsafe_allow_html=True)

# --- Header ---
st.markdown("""
<div class="main-header">
    <h1>🚀 AutoFlow</h1>
    <p>AI-powered web automation - describe your task and watch it happen</p>
</div>
""", unsafe_allow_html=True)

# --- Sidebar Controls ---
with st.sidebar:
    st.markdown("## ⚙️ Configuration")

    st.markdown("### 🖥️ Browser")
    headless = st.toggle("Headless Mode", value=False, help="Run browser in background")

    st.markdown("### 🔐 Auth")
    no_auth = st.toggle("Skip Authentication", value=False, help="Don't attempt automatic login")

    use_cookies = st.toggle("Use Saved Session", value=False, help="Load saved cookies")
    cookies_path = None
    if use_cookies:
        cookies_path = st.text_input(
            "Cookie File Path",
            value="cookies/github.json",
            help="Path to your saved cookie file"
        )
        if cookies_path and not os.path.exists(cookies_path):
            st.error(f"⚠️ Not found: `{cookies_path}`")
        elif cookies_path and os.path.exists(cookies_path):
            st.success("✓ Cookie file found")

    st.markdown("### 🔑 Credentials")
    st.caption("Used if cookies disabled")
    cred_email = st.text_input(
        "Email",
        placeholder="user@example.com",
        disabled=use_cookies,
    )
    cred_password = st.text_input(
        "Password",
        type="password",
        disabled=use_cookies,
    )

    st.divider()

    st.markdown("### 📊 Stats")
    if 'total_runs' not in st.session_state:
        st.session_state.total_runs = 0
    if 'successful_runs' not in st.session_state:
        st.session_state.successful_runs = 0

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Runs", st.session_state.total_runs)
    with col2:
        st.metric("Success", st.session_state.successful_runs)

    st.divider()
    st.caption("AutoFlow v1.0")

# --- Main Interface ---
st.markdown('<p class="section-title">📝 Enter Your Task</p>', unsafe_allow_html=True)

col1, col2 = st.columns([5, 1])
with col1:
    task_input = st.text_input(
        "Task",
        placeholder="e.g., Search for playwright in npm and open the first result",
        label_visibility="collapsed"
    )
with col2:
    run_btn = st.button("🚀 Run", type="primary", use_container_width=True)

with st.expander("💡 Example Tasks"):
    st.markdown("""
    - Search for playwright in npm
    - Find React documentation
    - Look up Python requests library on PyPI
    - Find GitHub repository for TensorFlow
    """)

# --- Helper Functions ---
def get_action_color(action_type):
    colors = {
        'click': 'action-click',
        'fill': 'action-fill',
        'navigate': 'action-navigate',
        'press': 'action-press',
        'wait': 'action-wait',
        'scroll': 'action-scroll',
        'success': 'success',
        'error': 'error',
        'layer': 'layer',
        'initial': 'initial'
    }
    return colors.get(action_type.lower(), 'default')

def parse_screenshot_name(filename):
    stem = filename.stem
    parts = stem.split('_')

    step_num = "?"
    action = "capture"
    is_special = False
    special_type = None

    if len(parts) >= 2 and parts[0] == 'step':
        step_num = parts[1]
        if len(parts) >= 3:
            action = parts[2]

    if 'success' in stem.lower():
        is_special = True
        special_type = 'success'
    elif 'error' in stem.lower() or 'fail' in stem.lower():
        is_special = True
        special_type = 'error'
    elif 'layer' in stem.lower() or 'modal' in stem.lower():
        is_special = True
        special_type = 'layer'
    elif 'initial' in stem.lower():
        is_special = True
        special_type = 'initial'

    return {
        'step': step_num,
        'action': action,
        'is_special': is_special,
        'special_type': special_type,
        'display_name': stem.replace('_', ' ').title()
    }

def render_metric_card(title, value, card_type="default"):
    st.markdown(f"""
    <div class="metric-card {card_type}">
        <h3>{title}</h3>
        <div class="value">{value}</div>
    </div>
    """, unsafe_allow_html=True)

def load_run_summary(out_dir):
    summary_file = out_dir / "run_summary.json"
    if summary_file.exists():
        try:
            with open(summary_file, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return None

# --- Execution Logic ---
if run_btn and task_input:
    st.session_state.total_runs += 1

    start_time = time.time()

    st.divider()

    status_col, metrics_col = st.columns([2, 1])

    with status_col:
        with st.status("🚀 Initializing AutoFlow...", expanded=True) as status:
            try:
                st.write("🔍 **Step 1:** Analyzing task...")
                url = get_url_for_task(task_input)

                if url:
                    st.success(f"✓ Target: `{url}`")
                else:
                    st.warning("⚠️ No URL found - manual navigation")

                st.write("📁 **Step 2:** Preparing environment...")
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
                out_dir = Path("dataset") / app_slug / task_slug
                os.makedirs(out_dir, exist_ok=True)
                st.success(f"✓ Output: `{out_dir}`")

                st.write("🤖 **Step 3:** Running automation...")
                st.info("Check terminal for detailed logs")

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

                st.session_state.successful_runs += 1
                status.update(label="✅ Complete!", state="complete", expanded=False)

            except Exception as e:
                status.update(label="❌ Failed", state="error")
                st.error(f"**Error:** {str(e)}")
                st.stop()

    with metrics_col:
        st.markdown("#### 📊 Stats")
        total_time = time.time() - start_time
        render_metric_card("Duration", f"{total_time:.1f}s", "success")

        summary = load_run_summary(out_dir)
        if summary:
            render_metric_card("Screenshots", summary.get('total_captures', 'N/A'))
            render_metric_card("Steps", summary.get('total_steps', 'N/A'))

    # --- Results Display ---
    st.divider()

    st.markdown("""
    <div class="results-header">
        <h3>✅ Execution Complete</h3>
        <p>View captured screenshots and logs below</p>
    </div>
    """, unsafe_allow_html=True)

    tab_gallery, tab_timeline, tab_log, tab_details = st.tabs([
        "📸 Gallery",
        "📅 Timeline",
        "📄 Log",
        "🔧 Details"
    ])

    screenshots = sorted(list(out_dir.glob("*.png")))

    with tab_gallery:
        if screenshots:
            st.caption(f"{len(screenshots)} screenshots captured")

            view_col, filter_col = st.columns([3, 1])
            with view_col:
                view_mode = st.radio(
                    "View",
                    ["2 Columns", "3 Columns", "Full Width"],
                    horizontal=True,
                    label_visibility="collapsed"
                )
            with filter_col:
                show_special_only = st.checkbox("Key frames only")

            screenshot_data = [{'path': s, **parse_screenshot_name(s)} for s in screenshots]

            if show_special_only:
                screenshot_data = [s for s in screenshot_data if s['is_special']]

            num_cols = 3 if "3" in view_mode else (1 if "Full" in view_mode else 2)

            cols = st.columns(num_cols)
            for i, data in enumerate(screenshot_data):
                with cols[i % num_cols]:
                    badge_class = data['special_type'] if data['special_type'] else get_action_color(data['action'])
                    badge_text = data['special_type'].upper() if data['special_type'] else f"Step {data['step']}: {data['action'].upper()}"

                    st.markdown(f"""
                    <div class="screenshot-card">
                        <span class="step-badge {badge_class}">{badge_text}</span>
                    </div>
                    """, unsafe_allow_html=True)
                    st.image(str(data['path']), use_container_width=True)
        else:
            st.info("No screenshots captured")

    with tab_timeline:
        if screenshots:
            st.markdown('<div class="timeline-container">', unsafe_allow_html=True)

            for data in [{'path': s, **parse_screenshot_name(s)} for s in screenshots]:
                status_class = data['special_type'] if data['special_type'] in ['success', 'error'] else ""

                st.markdown(f"""
                <div class="timeline-item {status_class}">
                    <strong>{data['display_name']}</strong>
                </div>
                """, unsafe_allow_html=True)

                with st.expander("View Screenshot"):
                    st.image(str(data['path']), use_container_width=True)

            st.markdown('</div>', unsafe_allow_html=True)
        else:
            st.info("No timeline data")

    with tab_log:
        log_file = out_dir / "steps_log.md"
        if log_file.exists():
            st.markdown(log_file.read_text(encoding="utf-8"))
        else:
            st.info("No log available")

    with tab_details:
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Configuration:**")
            st.json({
                "task": task_input,
                "url": url,
                "headless": headless,
                "skip_auth": no_auth,
                "use_cookies": use_cookies,
                "output": str(out_dir)
            })

        with col2:
            st.markdown("**Summary:**")
            summary = load_run_summary(out_dir)
            if summary:
                st.json(summary)
            else:
                st.info("No summary")

        plan_file = out_dir / "steps_plan.json"
        if plan_file.exists():
            st.markdown("**AI Plan:**")
            try:
                with open(plan_file, 'r') as f:
                    st.json(json.load(f))
            except Exception:
                st.warning("Could not load plan")

elif run_btn and not task_input:
    st.warning("⚠️ Please enter a task first")

# --- Footer ---
st.divider()
st.markdown('<p class="footer-text">AutoFlow • AI-Powered Web Automation</p>', unsafe_allow_html=True)
