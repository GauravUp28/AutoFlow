from playwright.sync_api import sync_playwright
from agent_b.ui_state_capturer import capture_screenshot
from agent_b.state_tracker import detect_ui_change
from agent_b.llm_interpreter import get_steps_and_selectors, get_dynamic_steps
from agent_b.auth_support import get_site_credentials, is_login_like, attempt_login, get_login_urls, task_requires_authentication
from agent_b.url_inference import get_url_for_task
import json
import time
import os
import re
from urllib.parse import quote_plus
from urllib.parse import urlparse
from agent_b.brand_utils import extract_brands
from agent_b.constants import AUTH_KEYWORDS
import json

# Metadata generation removed for clean output


def _extract_brands_local(task: str):
    # Backwards compatibility wrapper; now uses unified utility
    return extract_brands(task)


def _first_visible(page, selector: str, max_scan: int = 12):
    try:
        loc = page.locator(selector)
        cnt = loc.count()
        for i in range(min(cnt, max_scan)):
            cand = loc.nth(i)
            try:
                cand.scroll_into_view_if_needed(timeout=2000)
            except Exception:
                pass
            try:
                if cand.is_visible():
                    return cand
            except Exception:
                continue
    except Exception:
        pass
    return None


def _robust_click(page, selector: str) -> bool:
    # Strip visual markers from selector (used in planning context)
    selector = selector.replace("🔹 ", "").strip()
    
    # Try visible candidate first
    cand = _first_visible(page, selector)
    if cand:
        try:
            cand.click(timeout=8000)
            return True
        except Exception:
            try:
                cand.click(force=True, timeout=4000)
                return True
            except Exception:
                pass
    # Fallbacks: treat selector as text label when plausible
    label = None
    try:
        m = re.search(r"has-text\('\s*(.*?)\s*'\)", selector)
        if m:
            label = m.group(1)
    except Exception:
        label = None
    if not label and (not any(ch in selector for ch in ['[', ']', '#', '.', ':', '/', '(', ')'])) and len(selector) <= 80:
        label = selector
    if label:
        label_lower = label.lower()
        # Special handling for search buttons
        if label_lower in ['search', 'submit', 'go']:
            # Try form submit button first
            try:
                page.locator("button[type='submit'], input[type='submit']").first.click(timeout=4000)
                return True
            except Exception:
                pass
            # Try search icon/button
            try:
                page.locator("button:has-text('Search'), [aria-label*='search' i], [type='search']").first.click(timeout=4000)
                return True
            except Exception:
                pass
        # Special handling for package/result links (npm, pypi, etc.)
        # Try aria-label match for package names
        try:
            page.locator(f"a[aria-label*='{label}' i]").first.click(timeout=4000)
            return True
        except Exception:
            pass
        # Try exact text match
        try:
            page.get_by_text(label, exact=False).first.click(timeout=6000)
            return True
        except Exception:
            pass
        # Try role-based match
        for role in ["button", "link"]:
            try:
                page.get_by_role(role, name=re.compile(re.escape(label), re.I)).first.click(timeout=4000)
                return True
            except Exception:
                pass
        # Try partial href match for links (e.g., "playwright" in href)
        if len(label.split()) <= 2:
            try:
                page.locator(f"a[href*='{label.lower()}']").first.click(timeout=4000)
                return True
            except Exception:
                pass
    # Last resort: force click first match
    try:
        page.click(selector, force=True, timeout=4000)
        return True
    except Exception:
        return False


def _robust_fill(page, selector: str, value: str) -> bool:
    cand = _first_visible(page, selector)
    if cand:
        try:
            try:
                cand.click(timeout=3000)
            except Exception:
                pass
            try:
                cand.focus()
            except Exception:
                pass
            cand.fill(value, timeout=8000)
            return True
        except Exception:
            try:
                cand.type(value, timeout=8000)
                return True
            except Exception:
                pass

    # Extract ID or name from selector (AI may provide "Username #login name=login (text)")
    try:
        id_match = re.search(r"#([a-zA-Z0-9_-]+)", selector)
    except Exception:
        id_match = None
    try:
        name_attr_match = re.search(r"name=([a-zA-Z0-9_\[\]-]+)", selector)
    except Exception:
        name_attr_match = None

    if id_match:
        try:
            page.locator(f"#{id_match.group(1)}").fill(value, timeout=6000)
            return True
        except Exception:
            pass

    if name_attr_match:
        try:
            page.locator(f"[name='{name_attr_match.group(1)}']").fill(value, timeout=6000)
            return True
        except Exception:
            pass

    # Fallback by label/placeholder from selector hints
    label = None
    try:
        ph_match = re.search(r"placeholder\*?=\'?([^\']+)\'?", selector)
        if ph_match:
            label = ph_match.group(1)
    except Exception:
        label = None
    if not label:
        try:
            name_old = re.search(r"name=['\"]([^'\"]+)['\"]", selector)
            if name_old:
                label = name_old.group(1)
        except Exception:
            label = label
    if label:
        try:
            page.get_by_label(re.compile(re.escape(label), re.I)).fill(value, timeout=6000)
            return True
        except Exception:
            pass
        try:
            page.get_by_placeholder(re.compile(re.escape(label), re.I)).fill(value, timeout=6000)
            return True
        except Exception:
            pass
    # Last resort: first visible textbox
    try:
        tb = _first_visible(page, "input, textarea")
        if tb:
            tb.fill(value, timeout=6000)
            return True
    except Exception:
        pass
    return False


def run_task_on_webapp(task, url=None, out_dir=None, headless=None, skip_auth=False, cred_email=None, cred_password=None):
    """
    Fully automated workflow execution with screenshot capture at each step.
    No manual intervention required.
    
    Args:
        skip_auth: If True, skip all authentication attempts (useful for read-only tasks)
    """
    with sync_playwright() as p:
        # Simple browser launch - no session complexity
        if headless is None:
            hv = os.getenv("HEADLESS", "0").lower()
            headless = hv in ("1", "true", "yes")
        slow_mo = 0 if headless else 300
        browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        page.set_viewport_size({"width": 1920, "height": 1080})
        page.set_default_timeout(15000)  # 15s timeout - fail fast
        
        # If the task contains an explicit URL, use it as the starting point
        explicit_url = None
        try:
            # Match full URLs
            m = re.search(r"https?://[^\s)]+", task)
            if m:
                explicit_url = m.group(0)
            # Match domain references like "from python.org" or "in github.com"
            if not explicit_url:
                dm = re.search(r"(?:from|in|at|on)\s+([a-z0-9.-]+\.(com|org|io|app|net|co|ai|so))", task, re.I)
                if dm:
                    explicit_url = f"https://{dm.group(1)}"
        except Exception:
            explicit_url = None

        # If URL already provided (explicit or via parameter), use it directly
        url_found = False
        if url or explicit_url:
            target_url = url or explicit_url
            try:
                page.goto(target_url, wait_until="domcontentloaded", timeout=15000)
                page.wait_for_load_state("load", timeout=5000)
                url = target_url
                url_found = True
                print(f"[green]✓ Using provided URL: {url}[/green]")
            except Exception as e:
                print(f"[yellow]⚠ Could not open provided URL ({e}), falling back to inference[/yellow]")
                url_found = False
        
        # Extract brand candidates (generic, optional) used only for optional search fallback logs
        brands = _extract_brands_local(task)

        # If we still don't have a URL, use generic search-based inference (no brand hardcoding)
        if not url_found:
            inferred = get_url_for_task(task)
            if inferred:
                try:
                    page.goto(inferred, wait_until="domcontentloaded", timeout=20000)
                    page.wait_for_load_state("load", timeout=8000)
                    url = inferred
                    url_found = True
                    print(f"[green]✓ Inferred and opened URL: {url}[/green]")
                except Exception as e:
                    print(f"[yellow]⚠ Inferred URL failed to load: {e}[/yellow]")
                    url_found = False

        # Final fallback – open search engine directly and allow later steps to navigate
        if not url_found:
            try:
                search_query = brands[0] if brands else task.split(' ')[0]
                search_url = f"https://duckduckgo.com/?q={quote_plus(search_query)}"
                print(f"[cyan]Fallback: opening search for '{search_query}'[/cyan]")
                page.goto(search_url, wait_until="domcontentloaded", timeout=20000)
                page.wait_for_load_state("load", timeout=8000)
                url = page.url
            except Exception as e:
                print(f"[red]❌ Fallback search failed: {e}[/red]")
                page.goto("about:blank")
                url = None

        # Log outcome succinctly
        print(f"\n[cyan]{'='*50}[/cyan]")
        if url_found and url:
            print(f"[green]✓ URL Selection Complete: {url}[/green]")
        else:
            print(f"[yellow]⚠ Started from search context (dynamic navigation required)[/yellow]")
        print(f"[cyan]{'='*50}[/cyan]\n")

        # Intended app base (scheme + host) for later SSO return logic
        intended_app_base = None
        try:
            if url:
                parsed_host = re.match(r"https?://[^/]+", url)
                intended_app_base = parsed_host.group(0) if parsed_host else None
        except Exception:
            intended_app_base = None
        
        # Wait a bit for page to settle
        time.sleep(2)
        
        # CRITICAL: Verify page is not blank before proceeding
        current_page_url = page.url
        if current_page_url in ["about:blank", "", "chrome://newtab/"] or not current_page_url:
            print(f"[red]❌ Page is blank or not loaded![/red]")
            print(f"[yellow]Current URL: {current_page_url}[/yellow]")
            if url:
                print(f"[cyan]Attempting to navigate to selected URL: {url}[/cyan]")
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_load_state("load", timeout=10000)
                    print(f"[green]✓ Page loaded: {page.url}[/green]")
                except Exception as e:
                    print(f"[red]❌ Could not load page: {e}[/red]")
                    raise Exception(f"Failed to load target website. Page remained blank at '{current_page_url}'")
            else:
                raise Exception("No URL selected and page is blank - cannot proceed with workflow")

        # Dismiss common overlays/cookie banners to unblock interactions
        def _dismiss_overlays(page):
            overlay_selectors = [
                "button:has-text('Accept')",
                "button:has-text('Agree')",
                "button:has-text('I Agree')",
                "button:has-text('Allow all')",
                "button:has-text('Got it')",
                "button:has-text('Okay')",
                "button:has-text('OK')",
                "[role='dialog'] button:has-text('Accept')",
            ]
            for sel in overlay_selectors:
                try:
                    loc = page.locator(sel)
                    if loc.count() > 0 and loc.first.is_visible():
                        loc.first.click(timeout=2000)
                        time.sleep(0.5)
                except Exception:
                    continue
        try:
            _dismiss_overlays(page)
        except Exception:
            pass
        
        print(f"\n[cyan]========================================")
        print(f"[cyan] Agent B: Fully Automated Workflow")
        print(f"[cyan]========================================")
        print(f"[green] Task: {task}")
        print(f"[green] Starting URL: {page.url or url or 'Manual'}")
        print(f"[green] Screenshots: {out_dir}\n")
        
        # Capture initial state
        step_num = 0
        filename = os.path.join(out_dir, f"step_{step_num:02d}_initial.png")
        capture_screenshot(page, filename)
        print(f"[green] ✓ Step {step_num}: Initial state captured[/green]")
        
        # Check if we're on a login/signup page first
        print(f"\n[cyan]Analyzing page state...[/cyan]")
        print(f"[cyan]Current URL: {page.url}[/cyan]")
        time.sleep(1)  # Let page settle
        def safe_page_content(p):
            try:
                if p.is_closed():
                    return ""
                return p.content()
            except Exception as e:
                print(f"[yellow]Page content unavailable: {e}[/yellow]")
                return ""
        # Ensure page is alive; recreate if closed
        if page.is_closed():
            try:
                page = context.new_page()
                print("[yellow]Recreated closed page context[/yellow]")
            except Exception:
                pass
        html = safe_page_content(page)
        current_url = page.url
        
        # Parse HTML for analysis
        soup = None
        try:
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            pass
        
        # Detect CAPTCHA/anti-bot walls early and stop to avoid wasted steps
        try:
            html_low = (html or "").lower()
            captcha_signals = [
                "captcha", "hcaptcha", "recaptcha", "i'm not a robot",
                "type the text you hear or see", "verify you are human"
            ]
            if any(sig in html_low for sig in captcha_signals):
                print("[yellow]⚠ CAPTCHA or anti-bot challenge detected. Automation will pause.[/yellow]")
                print("[yellow]  Tip: Use Chrome session with an already logged-in profile or a cookies file.[/yellow]")
                # Capture and exit gracefully
                filename = os.path.join(out_dir, f"step_{step_num+1:02d}_captcha_detected.png")
                capture_screenshot(page, filename)
                time.sleep(1)
                try:
                    if out_dir:
                        report_path = os.path.join(out_dir, 'steps_log.md')
                        with open(report_path, 'a', encoding='utf-8') as f:
                            f.write("\n> CAPTCHA detected - workflow halted to avoid unnecessary interactions.\n")
                except Exception:
                    pass
                # Leave browser open briefly for inspection then teardown
                time.sleep(2)
                try:
                    if 'context' in locals() and context:
                        context.close()
                except Exception:
                    pass
                try:
                    if 'browser' in locals() and browser:
                        browser.close()
                except Exception:
                    pass
                return
        except Exception:
            pass
        
        # Let AI determine if this task requires authentication by analyzing the page state
        # No hardcoded keyword matching - AI interprets intent from context
        task_needs_auth = False
        task_is_read_only = False
        
        # Detect if we're on a login/marketing page
        is_demo_site = 'todomvc' in current_url.lower() or 'example' in current_url.lower() or 'demo' in current_url.lower()
        
        # Use AI to determine if authentication is actually needed for this task
        needs_auth = False
        if not is_demo_site and not skip_auth:
            # Check if task requires authentication (regardless of whether we're on a login form)
            needs_auth = task_requires_authentication(task, html, current_url)
            
            if needs_auth:
                print("[yellow]⚠ Task requires authentication to complete.[/yellow]")
                print(f"[yellow]Attempting to authenticate...[/yellow]")
        
        on_auth_wall = needs_auth
        
        # Generate automation plan
        print(f"[cyan]Generating automation plan from live page...[/cyan]")
        steps = get_steps_and_selectors(task, current_url, html)
        
        # If AI returned only generic actions, proceed; no heuristic regeneration in AI-only mode
        if steps and all(s.get('action') in ['wait', 'scroll'] for s in steps):
            print('[yellow]AI plan minimal; proceeding without heuristic fallback[/yellow]')
        
        # If we still have a bad plan (no meaningful interactions), try to provide guidance
        if steps:
            meaningful_actions = [s for s in steps if s.get('action') in ['click', 'fill', 'navigate']]
            if len(meaningful_actions) < 2:
                print("[yellow]Limited interactions detected. This may indicate:[/yellow]")
                print("[yellow]  - The site requires authentication[/yellow]")
                print("[yellow]  - The workflow requires manual steps[/yellow]")
                print("[yellow]  - The page structure is complex (SPA/dynamic content)[/yellow]")

        # Persist steps plan
        if out_dir:
            plan_path = os.path.join(out_dir, 'steps_plan.json')
            try:
                with open(plan_path, 'w', encoding='utf-8') as f:
                    json.dump(steps, f, indent=2)
                print(f"[green]✓ Saved plan to {plan_path}[/green]")
            except Exception as e:
                print(f"[yellow]⚠ Could not save plan: {e}[/yellow]")

        # Auto-login if on login page (unless --no-auth flag)
        if skip_auth:
            print('[cyan]Authentication skipped by --no-auth flag[/cyan]')
        elif on_auth_wall:
            print('[cyan]Login page detected - attempting authentication...[/cyan]')
            
            # Get credentials
            creds = get_site_credentials(
                url,
                task=task,
                interactive=True,
                override_email=cred_email,
                override_password=cred_password
            )
            if not creds:
                print('[yellow]No credentials provided - will attempt workflow without authentication[/yellow]')
            
            tried_login = False
            
            if creds:
                # Try direct login on current page
                try:
                    if attempt_login(page, creds):
                        tried_login = True
                        time.sleep(2)
                        capture_screenshot(page, os.path.join(out_dir or '.', 'step_00_auth_success.png'))
                        print('[green]✓ Logged in successfully[/green]')
                except Exception as e:
                    print(f'[yellow]Login attempt failed: {e}[/yellow]')
                
                # If direct login failed, try known login URLs
                if not tried_login:
                    for login_url in get_login_urls(url):
                        try:
                            print(f"[cyan]Trying login URL: {login_url}[/cyan]")
                            page.goto(login_url, wait_until="domcontentloaded", timeout=40000)
                            time.sleep(1)
                            if attempt_login(page, creds):
                                tried_login = True
                                capture_screenshot(page, os.path.join(out_dir or '.', 'step_00_auth_success.png'))
                                print('[green]✓ Authentication succeeded[/green]')
                                break
                            else:
                                print('[yellow]  Login verification failed[/yellow]')
                        except Exception as e:
                            print(f'[yellow]  Login URL error: {e}[/yellow]')
                            continue
            
            # Check authentication result
            if not tried_login and creds:
                print('[red]✗ Authentication failed - could not log in[/red]')
                print('[yellow]Proceeding with limited access - workflow may fail...[/yellow]')
            
            # Refresh page analysis after login attempt
            if tried_login:
                time.sleep(2)
                html = page.content()
                current_url = page.url
                
                # Handle SSO redirect back to app
                try:
                    from agent_b.auth_support import detect_sso_provider
                    sso = detect_sso_provider(page)
                    if sso and intended_app_base:
                        print(f"[cyan]Returning from {sso} to app: {intended_app_base}[/cyan]")
                        page.goto(intended_app_base, wait_until="domcontentloaded", timeout=20000)
                        time.sleep(2)
                        html = page.content()
                        current_url = page.url
                except Exception as e:
                    print(f"[yellow]SSO redirect handling: {e}[/yellow]")
                
                # Regenerate plan with authenticated context - pure AI, no hardcoded paths
                print('[cyan]Regenerating plan for authenticated session...[/cyan]')
                steps = get_steps_and_selectors(task, current_url, html)
                if out_dir:
                    plan_path = os.path.join(out_dir, 'steps_plan.json')
                    try:
                        with open(plan_path, 'w', encoding='utf-8') as f:
                            json.dump(steps, f, indent=2)
                        print(f"[green]✓ Updated plan: {plan_path}[/green]")
                    except Exception:
                        pass
        
        elif is_login_like(page):
            # On login page but skip_auth is False and on_auth_wall is False
            # This shouldn't happen normally, but handle gracefully
            print('[yellow]Login page detected but not attempting authentication[/yellow]')
        
        
        
        if not steps:
            print("[red]✗ No automation steps generated. Check your API keys or task description.[/red]")
            browser.close()
            return
        
        print(f"[green]✓ Generated {len(steps)} automation steps[/green]\n")
        
        # Execute each step automatically
        exec_log = []  # collect step results for a human-readable report
        previous_dom = None
        try:
            previous_dom = page.content()
        except Exception:
            previous_dom = None
        # Track last successfully loaded URL for page recreation
        try:
            last_url = page.url
        except Exception:
            last_url = None
        # Screenshot capture strategy
        capture_mode = (os.getenv('CAPTURE_MODE', 'smart') or 'smart').lower()
        smart_capture = capture_mode != 'all'

        def ensure_page():
            """Ensure we have an open page. Recreate if closed and try to restore last URL."""
            nonlocal page, context, last_url
            recreate_needed = False
            try:
                recreate_needed = page.is_closed()
            except Exception:
                recreate_needed = True
            if recreate_needed:
                print("[yellow]⚠ Page appears closed; creating a new page[/yellow]")
                try:
                    page = context.new_page()
                    if last_url:
                        try:
                            page.goto(last_url, wait_until="domcontentloaded", timeout=15000)
                            page.wait_for_load_state("load", timeout=8000)
                            print(f"[green]✓ Restored last URL: {last_url}[/green]")
                        except Exception as e:
                            print(f"[yellow]Could not restore last URL ({e})[/yellow]")
                except Exception as e:
                    print(f"[red]✗ Failed to recreate page: {e}[/red]")

        # Maintain dynamic loop to allow AI-driven step injection
        executed_history = []  # for dynamic replanning (subset fields)
        idx = 0
        while idx < len(steps):
            step = steps[idx]
            step_num = idx + 1
            action = step.get('action', '').lower()
            description = step.get('description', 'Unknown action')
            selector = step.get('selector', '')
            value = step.get('value', '')
            
            print(f"[cyan]━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━[/cyan]")
            print(f"[cyan]Step {step_num}: {description}[/cyan]")
            print(f"[yellow]  Action: {action}[/yellow]")
            
            try:
                # Ensure page is open before executing action
                ensure_page()
                # Set up change tracking
                url_before = None
                try:
                    url_before = page.url
                except Exception:
                    url_before = None
                took_extra_capture = False
                ui_change_detected = False
                url_changed = False
                if action == 'navigate':
                    nav_url = step.get('url', url)
                    print(f"[yellow]  Navigating to: {nav_url}[/yellow]")
                    try:
                        page.goto(nav_url, wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_load_state("load", timeout=10000)
                        try:
                            last_url = page.url
                        except Exception:
                            pass
                    except Exception:
                        print(f"[yellow]  ⚠ Navigation slow, continuing anyway[/yellow]")
                    time.sleep(1)
                    ui_change_detected = True  # navigation implies change
                
                elif action == 'click':
                    print(f"[yellow]  Clicking: {selector}[/yellow]")
                    # Pre-click counts for success detection
                    try:
                        pre_form_cnt = page.locator("form").count()
                    except Exception:
                        pre_form_cnt = 0
                    try:
                        pre_modal_cnt = page.locator("dialog, [role='dialog'], .modal").count()
                    except Exception:
                        pre_modal_cnt = 0
                    clicked = _robust_click(page, selector)
                    if not clicked:
                        print(f"[yellow]  ⚠ Click failed - element may not be visible[/yellow]")
                    else:
                        # CRITICAL: Wait for DOM changes or navigation after click
                        print(f"[dim]  Waiting for UI state change...[/dim]")
                        time.sleep(1.5)  # Allow time for navigation or DOM updates
                        
                        # Check for navigation (URL change)
                        try:
                            if page.url != url_before:
                                print(f"[green]  ✓ Navigation detected: {url_before} → {page.url}[/green]")
                                ui_change_detected = True
                        except Exception:
                            pass
                        
                        # Check for modal/dialog/dropdown appearance
                        try:
                            # Wait for any new elements to appear (dialog, modal, dropdown, form)
                            page.wait_for_selector("dialog, [role='dialog'], [role='menu'], .modal, form", timeout=2000, state="visible")
                            print(f"[green]  ✓ Detected new UI element (modal/form/dropdown)[/green]")
                            ui_change_detected = True
                        except Exception:
                            # No modal/dropdown detected, continue
                            pass
                        # If clicking likely opened search, wait for searchbox to appear
                        try:
                            if re.search(r"search|find|filter", selector, re.I):
                                page.wait_for_selector("input[type='search'], [role='searchbox'], input[placeholder*='search' i]", timeout=2000, state="visible")
                        except Exception:
                            pass
                        time.sleep(1.5)  # Extra time for animations/transitions
                        # Modal/form state detection via DOM diff heuristic
                        try:
                            current_dom = page.content()
                            if previous_dom and current_dom:
                                # Detect emergence of interactive layer or validation messages
                                emergence_signals = ["<dialog", "role=\"dialog\"", "class=\"modal", "<form", "aria-modal=\"true\""]
                                validation_signals = ["aria-invalid=\"true\""]
                                newly_present = [sig for sig in emergence_signals if sig in current_dom and sig not in previous_dom]
                                validation_new = [sig for sig in validation_signals if sig in current_dom and sig not in previous_dom]
                                # Only trigger on actual modals/forms, not search result validation states
                                current_url_lower = page.url.lower()
                                is_search_results = 'search' in current_url_lower or 'query' in current_url_lower or '?q=' in current_url_lower
                                if (newly_present or validation_new) and not is_search_results:
                                    layer_msg_parts = []
                                    if newly_present:
                                        layer_msg_parts.append(f"layers: {', '.join(newly_present)}")
                                    if validation_new:
                                        layer_msg_parts.append(f"validation: {', '.join(validation_new)}")
                                    print(f"[green]  ✓ UI change detected ({' ; '.join(layer_msg_parts)})[/green]")
                                    print("[dim]    (Extra capture for transitional state) [/dim]")
                                    extra_name = os.path.join(out_dir, f"step_{step_num:02d}_layer.png")
                                    if capture_screenshot(page, extra_name):
                                        took_extra_capture = True
                                        ui_change_detected = True
                                        # Dynamic replan trigger on new layer
                                        dyn_steps = get_dynamic_steps(task, page.url, current_dom, executed_history)
                                        if dyn_steps:
                                            print(f"[cyan]AI added {len(dyn_steps)} dynamic step(s) after layer detection[/cyan]")
                                            # Insert right after current step
                                            steps[idx+1:idx+1] = dyn_steps
                            previous_dom = current_dom
                        except Exception:
                            previous_dom = current_dom if 'current_dom' in locals() else previous_dom
                        # Success detection: if a submit/create/save click removed a form/modal
                        try:
                            post_form_cnt = page.locator("form").count()
                        except Exception:
                            post_form_cnt = pre_form_cnt
                        try:
                            post_modal_cnt = page.locator("dialog, [role='dialog'], .modal").count()
                        except Exception:
                            post_modal_cnt = pre_modal_cnt
                        submit_like = any(token in selector.lower() for token in ["submit", "create", "save", "done", "continue", "next"]) or re.search(r"type=['\"]submit['\"]", selector, re.I)
                        if submit_like and (post_form_cnt < pre_form_cnt or post_modal_cnt < pre_modal_cnt):
                            success_name = os.path.join(out_dir, f"step_{step_num:02d}_success.png")
                            if capture_screenshot(page, success_name):
                                print(f"[green]  ✓ Success state captured (form/modal dismissed)")
                                took_extra_capture = True
                                ui_change_detected = True
                                # Trigger dynamic steps for possible follow-up actions
                                dyn_steps = get_dynamic_steps(task, page.url, page.content(), executed_history)
                                if dyn_steps:
                                    print(f"[cyan]AI added {len(dyn_steps)} dynamic step(s) after success state[/cyan]")
                                    steps[idx+1:idx+1] = dyn_steps
                    try:
                        last_url = page.url
                    except Exception:
                        pass
                
                elif action == 'fill':
                    print(f"[yellow]  Filling: {selector} with '{value}'[/yellow]")
                    v = value
                    sel_l = selector.lower()
                    if not v:
                        if 'email' in sel_l:
                            # Use previously obtained credentials if available, else prompt
                            try:
                                if 'creds' in locals() and creds and creds.get('email'):
                                    v = creds['email']
                                else:
                                    v = input('Enter login email: ').strip()
                            except Exception:
                                v = ''
                        elif 'password' in sel_l:
                            try:
                                import getpass
                                if 'creds' in locals() and creds and creds.get('password'):
                                    v = creds['password']
                                else:
                                    v = getpass.getpass('Enter login password: ').strip()
                            except Exception:
                                v = ''
                        else:
                            # Neutral placeholders for non-auth fields (avoid storing secrets)
                            if 'firstname' in sel_l or 'first' in sel_l:
                                v = 'Test'
                            elif 'lastname' in sel_l or 'last' in sel_l:
                                v = 'User'
                            elif 'username' in sel_l or 'user' in sel_l:
                                v = f"user{int(time.time())}"
                            elif 'name' in sel_l:
                                v = 'Sample Name'
                            elif 'title' in sel_l:
                                v = 'Sample Title'
                            elif 'description' in sel_l or 'desc' in sel_l:
                                v = 'Sample description'
                            else:
                                v = 'Sample'
                    else:
                        pass
                    ok = _robust_fill(page, selector, v)
                    if not ok:
                        print('[yellow]  ⚠ Fill failed - element not interactable[/yellow]')
                    time.sleep(1)
                    try:
                        last_url = page.url
                    except Exception:
                        pass
                
                elif action == 'press':
                    print(f"[yellow]  Action: press[/yellow]")
                    key = step.get('key', 'Enter')
                    print(f"[yellow]  Pressing key: {key}[/yellow]")
                    try:
                        page.keyboard.press(key)
                        time.sleep(0.5)  # Brief delay for key press effect
                    except Exception as e:
                        print(f"[yellow]  ⚠ Key press failed - {e}[/yellow]")
                
                elif action == 'wait':
                    print(f"[yellow]  Waiting for: {selector}[/yellow]")
                    waited = False
                    # Extract delay hint from description if present (e.g., "wait 3 seconds")
                    wait_delay = 0.5
                    try:
                        delay_match = re.search(r'(\d+)\s*(?:second|sec)', description.lower())
                        if delay_match:
                            wait_delay = max(0.5, int(delay_match.group(1)))
                    except Exception:
                        pass
                    try:
                        # Support multiple comma-separated tokens and text= selectors
                        parts = [s.strip() for s in selector.split(',') if s.strip()]
                        if not parts:
                            parts = [selector]
                        for part in parts:
                            if part.lower().startswith('text='):
                                txt = part[5:]
                                try:
                                    page.get_by_text(txt, exact=False).first.wait_for(state='visible', timeout=8000)
                                    waited = True
                                    break
                                except Exception:
                                    continue
                            else:
                                try:
                                    page.wait_for_selector(part, timeout=8000)
                                    waited = True
                                    break
                                except Exception:
                                    continue
                    except Exception:
                        pass
                    if not waited:
                        # Final fallback to body
                        try:
                            page.wait_for_selector('body', timeout=5000)
                            waited = True
                        except Exception:
                            pass
                    # Extra wait for success states to render (especially after submit actions in prior step)
                    if idx > 0:
                        prev_step = steps[idx - 1]
                        prev_was_submit = prev_step.get('action') == 'click' and any(kw in prev_step.get('selector', '').lower() for kw in ['submit', 'create', 'save', 'download', 'continue', 'confirm'])
                        if prev_was_submit:
                            wait_delay = max(wait_delay, 3.0)  # Ensure at least 3 seconds for success state
                            print(f"[dim]  Extended wait after submit action ({wait_delay}s)[/dim]")
                    time.sleep(wait_delay)
                    try:
                        last_url = page.url
                    except Exception:
                        pass
                
                elif action == 'scroll':
                    print(f"[yellow]  Scrolling page[/yellow]")
                    page.evaluate("window.scrollBy(0, 500)")
                    time.sleep(1)
                    try:
                        last_url = page.url
                    except Exception:
                        pass
                
                else:
                    print(f"[yellow]  Unknown action: {action}[/yellow]")
                    time.sleep(0.5)
                    try:
                        last_url = page.url
                    except Exception:
                        pass
                
                # Compute URL change
                try:
                    url_after = page.url
                    url_changed = (url_before is not None and url_after != url_before)
                except Exception:
                    url_changed = False

                # Decide whether to capture default screenshot
                should_capture = True
                if smart_capture:
                    # Always capture fill/press/navigate actions (show user input and key results)
                    # For click/wait/scroll, only capture if UI changed or URL changed
                    # CRITICAL: Always capture clicks on submit/create/save/download buttons (final actions)
                    is_final_action = action == 'click' and any(kw in selector.lower() for kw in ['submit', 'create', 'save', 'download', 'continue', 'confirm', 'finish', 'done'])
                    # Always capture last 2 steps of plan to ensure final state is saved
                    is_near_end = idx >= len(steps) - 2
                    should_capture = (action in ['fill', 'press', 'navigate'] or ui_change_detected or url_changed or is_final_action or is_near_end) and not took_extra_capture

                if should_capture:
                    filename = os.path.join(out_dir, f"step_{step_num:02d}_{action}.png")
                    shot_ok = capture_screenshot(page, filename)
                    if shot_ok:
                        print(f"[green]  ✓ Screenshot saved: {filename}[/green]")
                    else:
                        print(f"[yellow]  ⚠ Screenshot failed (page may be closed): {filename}[/yellow]")
                    record = {
                        "step": step_num,
                        "description": description,
                        "action": action,
                        "selector": selector,
                        "status": "ok" if shot_ok else "warning: screenshot_failed",
                        "screenshot": os.path.basename(filename),
                        "url": page.url,
                    }
                    exec_log.append(record)
                    executed_history.append(record)
                else:
                    record = {
                        "step": step_num,
                        "description": description,
                        "action": action,
                        "selector": selector,
                        "status": "ok (screenshot skipped: no significant change)",
                        "screenshot": "skipped",
                        "url": page.url,
                    }
                    exec_log.append(record)
                    executed_history.append(record)
                
            except Exception as e:
                print(f"[red]  ✗ Error: {str(e)}[/red]")
                # Still capture screenshot on error
                filename = os.path.join(out_dir, f"step_{step_num:02d}_error.png")
                err_ok = capture_screenshot(page, filename)
                if err_ok:
                    print(f"[yellow]  ⚠ Error screenshot saved: {filename}[/yellow]")
                else:
                    print(f"[red]  ✗ Failed to capture error screenshot: {filename}[/red]")
                # Continue with next step
                err_record = {
                    "step": step_num,
                    "description": description,
                    "action": action,
                    "selector": selector,
                    "status": f"error: {str(e)}" + ("; screenshot_failed" if not err_ok else ""),
                    "screenshot": os.path.basename(filename),
                    "url": page.url if not page.is_closed() else None,
                }
                exec_log.append(err_record)
                executed_history.append(err_record)
                continue
            idx += 1  # advance after possible dynamic insertion

        # Capture final state
        step_num += 1
        filename = os.path.join(out_dir, f"step_{step_num:02d}_final.png")
        final_ok = capture_screenshot(page, filename)
        if final_ok:
            print(f"\n[green]✓ Final state captured: {filename}[/green]")
        else:
            print(f"\n[yellow]⚠ Final screenshot failed: {filename}[/yellow]")
        
        print(f"\n[cyan]========================================[/cyan]")
        print(f"[green]✓ Workflow completed![/green]")
        print(f"[green]✓ Total steps: {step_num}[/green]")
        print(f"[green]✓ Screenshots saved to: {out_dir}[/green]")
        print(f"[cyan]========================================[/cyan]\n")
        
        # Write a human-readable step-by-step report
        try:
            if out_dir:
                report_path = os.path.join(out_dir, 'steps_log.md')
                with open(report_path, 'w', encoding='utf-8') as f:
                    f.write(f"# Step-by-step execution log\n\n")
                    f.write(f"Task: {task}\n\n")
                    for rec in exec_log:
                        f.write(f"- Step {rec['step']}: {rec['description']}\n")
                        f.write(f"  - Action: {rec['action']}\n")
                        if rec.get('selector'):
                            f.write(f"  - Selector: `{rec['selector']}`\n")
                        f.write(f"  - Status: {rec['status']}\n")
                        f.write(f"  - Screenshot: {rec['screenshot']}\n\n")
                print(f"[green]✓ Wrote step-by-step report: {report_path}[/green]")
                # Run summary JSON
                summary = {
                    "task": task,
                    "total_steps": step_num,
                    "captures": len([r for r in exec_log if r['screenshot'] not in ('skipped')]),
                    "layers": len([1 for r in os.listdir(out_dir) if '_layer.png' in r]),
                    "success_states": len([1 for r in os.listdir(out_dir) if '_success.png' in r]),
                    "final_capture": final_ok,
                    "provider": os.getenv('PLANNER_PROVIDER'),
                    "model": os.getenv('PLANNER_MODEL') or os.getenv('OPENAI_MODEL') or os.getenv('ANTHROPIC_MODEL') or os.getenv('GEMINI_MODEL'),
                }
                try:
                    with open(os.path.join(out_dir, 'run_summary.json'), 'w', encoding='utf-8') as sf:
                        json.dump(summary, sf, indent=2)
                    print(f"[green]✓ Wrote run summary: {os.path.join(out_dir, 'run_summary.json')}[/green]")
                except Exception as se:
                    print(f"[yellow]⚠ Could not write run summary: {se}[/yellow]")
        except Exception as e:
            print(f"[yellow]⚠ Could not write report: {e}[/yellow]")

        # Keep browser open for 3 seconds to show final state
        time.sleep(3)
        # Graceful teardown: handle persistent context (no browser var) and normal mode
        try:
            if 'context' in locals() and context:
                context.close()
        except Exception:
            pass
        try:
            if 'browser' in locals() and browser:
                browser.close()
        except Exception:
            pass
