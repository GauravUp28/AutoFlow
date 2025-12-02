import os
import re
import json
import getpass

def _domain_from_url(url: str|None) -> str|None:
    if not url:
        return None
    m = re.search(r"https?://([^/]+)/?", url)
    return m.group(1) if m else None


def prompt_user_credentials(site: str, task: str) -> dict|None:
    """Interactively prompt user for login credentials when authentication is required."""
    print(f"\n[bold yellow]⚠ Authentication Required[/bold yellow]")
    print(f"[cyan]Site:[/cyan] {site}")
    print(f"[cyan]Task:[/cyan] {task}")
    print(f"[dim]This task requires login access. Please provide your credentials.[/dim]")
    print(f"[dim]Tip: Set {site.upper().replace('.', '_').replace('-', '_')}_EMAIL and _PASSWORD in .env to skip this prompt[/dim]\n")
    
    try:
        email = input("Email/Username: ").strip()
        if not email:
            print("[yellow]No email provided, skipping authentication[/yellow]")
            return None
        
        password = getpass.getpass("Password: ").strip()
        if not password:
            print("[yellow]No password provided, skipping authentication[/yellow]")
            return None
        
        print("[green]✓ Credentials received[/green]\n")
        return {"email": email, "password": password, "site": site}
    except (KeyboardInterrupt, EOFError):
        print("\n[yellow]Authentication cancelled by user[/yellow]")
        return None


def get_site_credentials(url: str|None, task: str = "", interactive: bool = True, force_prompt: bool = False, override_email: str|None = None, override_password: str|None = None):
    """Get credentials for any site.

    Order of resolution:
      1. Explicit overrides (CLI flags)
      2. Force prompt (if force_prompt True)
      3. Domain/brand environment variables
      4. Credentials JSON mapping
      5. Interactive prompt (if interactive True)
    """
    dom = _domain_from_url(url)
    if not dom:
        return None

    # 0) Explicit overrides
    if override_email and override_password:
        return {"email": override_email, "password": override_password, "site": dom}

    # 1) Forced prompt bypasses env/JSON
    if force_prompt and interactive:
        return prompt_user_credentials(dom, task)

    # 2) Per-domain env vars, e.g., GITHUB_COM_EMAIL / GITHUB_COM_PASSWORD
    dom_key = dom.upper().replace('.', '_').replace('-', '_')
    email = os.getenv(f"{dom_key}_EMAIL")
    password = os.getenv(f"{dom_key}_PASSWORD")
    if email and password:
        print(f"[green]✓ Using {dom_key} credentials from environment[/green]")
        return {"email": email, "password": password, "site": dom}

    # 3) Per-brand env vars (first label), e.g., GITHUB_EMAIL / GITHUB_PASSWORD
    brand = dom.split('.')[0].upper()
    email = os.getenv(f"{brand}_EMAIL", email)
    password = os.getenv(f"{brand}_PASSWORD", password)
    if email and password:
        print(f"[green]✓ Using {brand} credentials from environment[/green]")
        return {"email": email, "password": password, "site": dom}

    # 4) Credentials JSON mapping (path via CREDENTIALS_JSON)
    cred_json_path = os.getenv('CREDENTIALS_JSON')
    if cred_json_path and os.path.exists(cred_json_path):
        try:
            data = json.loads(open(cred_json_path, 'r', encoding='utf-8').read())
            # lookup by full domain then brand
            rec = data.get(dom) or data.get(dom.split('.')[0])
            if rec and rec.get('email') and rec.get('password'):
                print(f"[green]✓ Using credentials from {cred_json_path}[/green]")
                return {"email": rec['email'], "password": rec['password'], "site": dom}
        except Exception:
            pass

    # 5) Interactive prompt (if enabled)
    if interactive:
        return prompt_user_credentials(dom, task)

    # 6) Skip authentication if no credentials available and not interactive
    return None


def get_login_urls(url: str|None):
    """Return a list of likely login URLs for ANY site - purely pattern-based, no hardcoding."""
    dom = _domain_from_url(url) or ""
    base = f"https://{dom}" if dom else None
    if not base:
        return []
    
    # Generic login URL patterns that work across most sites
    urls = [
        f"{base}/login",
        f"{base}/signin",
        f"{base}/auth/login",
        f"{base}/users/sign_in",
        f"{base}/account/login",
        f"{base}/user/login",
        f"{base}/auth",
        f"{base}/session/new",
    ]
    
    # Deduplicate
    seen = set()
    uniq = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)
    return uniq


def is_login_like(page) -> bool:
    """Heuristically detect if we are on a dedicated login page (not just a page with optional login button)."""
    try:
        # Check if password field is visible and prominent
        password_fields = page.locator("input[type='password']")
        has_password = password_fields.count() > 0
        
        if not has_password:
            return False
            
        # If there's a password field, verify it's actually a login form (not just in header/footer)
        # Check if the password field is in the main content area
        try:
            password_visible = False
            for i in range(password_fields.count()):
                if password_fields.nth(i).is_visible():
                    password_visible = True
                    break
            
            if not password_visible:
                return False
                
            # Additional check: Look for email/username field near the password field
            # A real login page will have both username and password fields prominently displayed
            email_fields = page.locator("input[type='email'], input[type='text'][name*='user'], input[type='text'][name*='email'], input[type='text'][name*='login']")
            has_email = email_fields.count() > 0
            
            # Only return True if we have both username and password fields visible (actual login form)
            return has_password and has_email
        except Exception:
            # If visibility check fails, be conservative and return False
            return False
            
    except Exception:
        return False


def task_requires_authentication(task: str, page_html: str, page_url: str) -> bool:
    """Use AI to determine if the task actually requires authentication based on task intent and page state.
    
    Returns True only if:
    - Task involves creating, modifying, or managing user-specific content
    - Current page shows authentication is blocking task completion
    """
    try:
        import openai
        api_key = os.getenv('OPENAI_API_KEY')
        if not api_key:
            # Fallback to heuristic if no API key
            auth_verbs = ['create', 'add', 'delete', 'remove', 'edit', 'configure', 'manage', 'upload', 'post', 'publish']
            task_lower = task.lower()
            return any(verb in task_lower for verb in auth_verbs)
        
        # Analyze page content (keep it brief to avoid token overload)
        page_snippet = page_html[:3000] if len(page_html) > 3000 else page_html
        
        prompt = f"""You are analyzing whether a web automation task requires user authentication.

TASK: {task}
CURRENT URL: {page_url}
PAGE CONTENT (snippet): {page_snippet[:1500]}

Determine if this task REQUIRES authentication (login) to complete:
- Return "YES" if the task involves: creating/editing/deleting user content, managing account settings, accessing private data
- Return "NO" if the task is: searching, browsing, reading public content, downloading public files, viewing public pages

Consider:
1. Is the task action read-only (search, view, download public content)? → NO auth needed
2. Does the task require modifying data or accessing private resources? → YES auth needed
3. Is the current page blocking task completion with a login wall? → YES auth needed
4. Can the task be completed on the public area of the site? → NO auth needed

Respond with ONLY one word: YES or NO"""

        client = openai.OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=10
        )
        
        answer = response.choices[0].message.content.strip().upper()
        return "YES" in answer
        
    except Exception as e:
        print(f"[yellow]⚠ AI auth check failed ({e}), using heuristic fallback[/yellow]")
        # Fallback heuristic
        auth_verbs = ['create', 'add', 'delete', 'remove', 'edit', 'configure', 'manage', 'upload', 'post', 'publish']
        task_lower = task.lower()
        return any(verb in task_lower for verb in auth_verbs)


def detect_sso_provider(page) -> str|None:
    """Detect if we're on an SSO provider page (Google, Microsoft, etc.)."""
    try:
        url = page.url.lower()
        title = (page.title() or "").lower()
        # Google SSO
        if "accounts.google.com" in url or "google" in title:
            return "google"
        # Microsoft/Azure SSO
        if "login.microsoftonline.com" in url or "microsoft" in title:
            return "microsoft"
        # Okta
        if "okta.com" in url or "okta" in title:
            return "okta"
        return None
    except Exception:
        return None


def handle_google_sso(page, session_mode: bool = False) -> bool:
    """Handle Google SSO account selection.
    If session_mode=True, assumes Chrome profile has Google accounts and auto-selects first.
    Returns True if account selection attempted.
    """
    try:
        # Check if we're on Google account picker
        if "accounts.google.com" not in page.url.lower():
            return False
        
        print("[cyan]Detected Google SSO - checking for existing accounts...[/cyan]")
        
        # Look for account selection elements (Google shows saved accounts)
        account_selectors = [
            "[data-identifier]",  # Account divs
            "div[role='link'][data-email]",
            "div[data-profileidentifier]",
        ]
        
        for sel in account_selectors:
            loc = page.locator(sel)
            if loc.count() > 0:
                if session_mode:
                    print("[green]✓ Found existing Google account - selecting automatically[/green]")
                    loc.first.click(timeout=5000)
                    page.wait_for_load_state("networkidle", timeout=15000)
                    return True
                else:
                    print("[yellow]Google account picker detected. Enable session mode for auto-selection.[/yellow]")
                    return False
        
        # No saved accounts found
        if session_mode:
            print("[yellow]No saved Google accounts in profile. Please log in manually once.[/yellow]")
        return False
    except Exception as e:
        print(f"[dim]SSO handling: {str(e)[:50]}[/dim]")
        return False


def _dismiss_blocking_overlays(page) -> bool:
    """Intelligently detect and dismiss blocking overlays like cookie modals, popups, etc."""
    import time
    
    dismissed_count = 0
    max_attempts = 2  # Reduced to avoid infinite loops
    
    for attempt in range(max_attempts):
        try:
            time.sleep(0.3)
            
            dismiss_patterns = [
                # X/Close buttons (highest priority)
                ("button[aria-label='Close']", "Close modal"),
                ("button[aria-label='Close dialog']", "Close dialog"),
                ("button[aria-label*='close' i]", "Close aria-label"),
                ("button.close", "Close class"),
                ("button:has-text('×')", "X button"),
                # Accept buttons (lower priority)
                ("button:has-text('Accept all')", "Accept all"),
                ("button:has-text('Accept')", "Accept"),
                ("button:has-text('Got it')", "Got it"),
            ]
            
            found_overlay = False
            
            for selector, description in dismiss_patterns:
                try:
                    loc = page.locator(selector).first
                    if loc.is_visible(timeout=300):
                        print(f"[dim]  Dismissing overlay: {description}[/dim]")
                        loc.click(timeout=1500)
                        time.sleep(0.5)
                        dismissed_count += 1
                        found_overlay = True
                        break
                except Exception:
                    continue
            
            if not found_overlay and attempt == 0:
                try:
                    page.keyboard.press('Escape')
                    print(f"[dim]  Pressed Escape[/dim]")
                    time.sleep(0.3)
                except Exception:
                    pass
            
            if not found_overlay:
                break
            
        except Exception:
            break
    
    if dismissed_count > 0:
        print(f"[dim]Dismissed {dismissed_count} overlays total[/dim]")
    
    return dismissed_count > 0


def _navigate_to_login_if_needed(page) -> bool:
    """Check if we're on a marketing page and navigate to login page if needed."""
    import time
    
    try:
        # Check if we're already on a login page (has email/password fields)
        if is_login_like(page):
            return True
        
        # Check if there's a Sign in button to click
        signin_patterns = [
            "a:has-text('Sign in')",
            "a:has-text('Log in')",
            "button:has-text('Sign in')",
            "button:has-text('Log in')",
            "[href*='/login']",
            "[href*='/signin']",
        ]
        
        for pattern in signin_patterns:
            try:
                loc = page.locator(pattern).first
                if loc.is_visible(timeout=1000):
                    print(f"[dim]Navigating to login page via: {pattern}[/dim]")
                    loc.click(timeout=3000)
                    time.sleep(2)
                    return True
            except Exception:
                continue
        
        return False
    except Exception:
        return False


def attempt_login(page, creds: dict) -> bool:
    """Try login using AI-generated steps that adapt to any site's login flow, including multi-step logins."""
    import time
    from autoflow.llm_interpreter import get_login_steps
    
    max_login_attempts = 3  # Handle up to 3-step login flows (e.g., email → password → 2FA)
    
    try:
        # First, handle any blocking overlays (cookie modals, popups, etc.)
        print("[cyan]Checking for blocking overlays...[/cyan]")
        _dismiss_blocking_overlays(page)
        
        # Wait for page to stabilize after dismissing overlays
        time.sleep(1)
        
        # Navigate to login page if we're on marketing/homepage
        print("[cyan]Navigating to login page if needed...[/cyan]")
        _navigate_to_login_if_needed(page)
        
        # Wait for navigation to complete
        time.sleep(1)
        
        # Dismiss any overlays that appeared after navigation
        _dismiss_blocking_overlays(page)
        
        for attempt in range(max_login_attempts):
            # Get current page state
            html = page.content()
            current_url = page.url
            
            print(f"[dim]Login attempt {attempt + 1}/{max_login_attempts} - URL: {current_url}[/dim]")
            
            # Check if we're still on a login-related page
            if attempt > 0:
                # First, check if page is asking for verification code
                page_text = page.content().lower()
                if any(phrase in page_text for phrase in ['check your email', 'sent you a', 'verification code', 'enter code', 'code sent to']):
                    print(f"[cyan]Email verification required, continuing login flow...[/cyan]")
                    # Don't exit, continue to next iteration to handle verification
                else:
                    # Check if login succeeded (no longer on login page)
                    still_on_login = is_login_like(page)
                    if not still_on_login:
                        # Check for success indicators
                        success_indicators = [
                            "text=/sign out|log out|logout/i",
                            "[aria-label*='profile' i]",
                            "[aria-label*='account' i]",
                            "text=/welcome|dashboard|workspace/i"
                        ]
                        found_success = False
                        for ind in success_indicators:
                            try:
                                if page.locator(ind).count() > 0:
                                    found_success = True
                                    break
                            except Exception:
                                    continue
                    
                        # Consider login successful ONLY if authenticated indicators are present
                        if found_success:
                            print(f"[green]✓ Login completed after {attempt} steps[/green]")
                            return True
                        else:
                            print("[yellow]  Not clearly authenticated yet; continuing login flow[/yellow]")
            
            print(f"[cyan]Generating AI-powered login steps for {current_url}[/cyan]")
            
            # Generate login steps using AI for current page state
            steps = get_login_steps(current_url, html, creds["email"])
            
            if not steps:
                print("[yellow]Could not generate login steps[/yellow]")
                if attempt > 0:
                    # We made some progress, check if login succeeded
                    break
                return False
            
            print(f"[dim]Generated {len(steps)} login steps for page {attempt + 1}[/dim]")
            
            page_changed = False
            
            # Execute each login step
            for i, step in enumerate(steps):
                action = step.get("action", "").lower()
                description = step.get("description", "")
                selector = step.get("selector", "")
                value = step.get("value", "")
                
                print(f"[dim]  Step {i+1}: {description}[/dim]")
                
                url_before = page.url
                
                try:
                    if action == "fill":
                        # Replace EMAIL and PASSWORD placeholders with actual credentials
                        if value == "EMAIL":
                            value = creds["email"]
                        elif value == "PASSWORD":
                            value = creds["password"]
                        elif value == "VERIFICATION_CODE":
                            # Prompt user for verification code
                            print("\n[bold yellow]⚠ Email Verification Required[/bold yellow]")
                            print("[cyan]A verification code has been sent to your email.[/cyan]")
                            print("[dim]Please check your email and enter the code below.[/dim]\n")
                            try:
                                import getpass
                                code = input("Verification Code: ").strip()
                                if not code:
                                    print("[yellow]No code provided, skipping verification[/yellow]")
                                    continue
                                value = code
                            except (KeyboardInterrupt, EOFError):
                                print("\n[yellow]Verification cancelled[/yellow]")
                                return False
                        
                        # Try to find and fill the field
                        filled = False

                        # Direct attribute/CSS targeting from selector text (e.g., "#login_field", "name=login")
                        try:
                            sel_txt = (selector or "").strip()
                            # ID selector
                            m_id = re.search(r"#([a-zA-Z0-9_-]+)", sel_txt)
                            if not filled and m_id:
                                loc = page.locator(f"#{m_id.group(1)}").first
                                if loc.is_visible():
                                    loc.click(timeout=2000); loc.fill(value); filled = True
                            # name= selector
                            m_name = re.search(r"name=([a-zA-Z0-9_\[\]-]+)", sel_txt)
                            if not filled and m_name:
                                loc = page.locator(f"[name='{m_name.group(1)}']").first
                                if loc.is_visible():
                                    loc.click(timeout=2000); loc.fill(value); filled = True
                            # Raw CSS if selector looks like one
                            if not filled and any(ch in sel_txt for ch in ['#','[',']','=']):
                                loc = page.locator(sel_txt).first
                                if loc.is_visible():
                                    loc.click(timeout=2000); loc.fill(value); filled = True
                        except Exception:
                            pass
                        
                        # Try by placeholder
                        try:
                            loc = page.get_by_placeholder(selector, exact=False)
                            if loc.count() > 0:
                                loc.first.click(timeout=2000)
                                time.sleep(0.2)
                                loc.first.fill(value)
                                filled = True
                        except Exception:
                            pass
                        
                        # Try by label
                        if not filled:
                            try:
                                loc = page.get_by_label(selector, exact=False)
                                if loc.count() > 0:
                                    loc.first.click(timeout=2000)
                                    time.sleep(0.2)
                                    loc.first.fill(value)
                                    filled = True
                            except Exception:
                                pass
                        
                        # Fallback: try any visible email/password input
                        if not filled and value == creds["email"]:
                            try:
                                loc = page.locator("input[type='email'], input[name*='email'], input[name*='username']").first
                                if loc.is_visible():
                                    loc.click(timeout=2000)
                                    time.sleep(0.2)
                                    loc.fill(value)
                                    filled = True
                            except Exception:
                                pass
                        
                        if not filled and value == creds["password"]:
                            try:
                                loc = page.locator("input[type='password']").first
                                if loc.is_visible():
                                    loc.click(timeout=2000)
                                    time.sleep(0.2)
                                    loc.fill(value)
                                    filled = True
                            except Exception:
                                pass
                        
                        if filled:
                            print(f"[dim]    ✓ Filled: {selector}[/dim]")
                        else:
                            print(f"[yellow]    ⚠ Could not find field: {selector}[/yellow]")
                        
                        time.sleep(0.3)
                    
                    elif action == "click":
                        # Try to find and click the button
                        clicked = False

                        # Interpret common selector patterns first (e.g., name=commit)
                        try:
                            sel_txt = (selector or "").strip()
                            # name=VALUE → try button/input/name attribute
                            m_name = re.search(r"name=([a-zA-Z0-9_\[\]-]+)", sel_txt)
                            if m_name and not clicked:
                                name_val = m_name.group(1)
                                for css in [
                                    f"button[name='{name_val}']",
                                    f"input[name='{name_val}']",
                                    f"[name='{name_val}']",
                                ]:
                                    try:
                                        loc = page.locator(css).first
                                        if loc.is_visible():
                                            loc.click(timeout=5000)
                                            clicked = True
                                            break
                                    except Exception:
                                        continue

                            # id/hash selector present → direct CSS works
                            if not clicked and "#" in sel_txt:
                                try:
                                    loc = page.locator(sel_txt).first
                                    if loc.is_visible():
                                        loc.click(timeout=5000)
                                        clicked = True
                                except Exception:
                                    pass

                            # Raw CSS attribute selectors like [data-...] or [type=submit]
                            if not clicked and any(ch in sel_txt for ch in ['[',']','=']):
                                try:
                                    loc = page.locator(sel_txt).first
                                    if loc.is_visible():
                                        loc.click(timeout=5000)
                                        clicked = True
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        
                        # Try by role and name
                        try:
                            loc = page.get_by_role("button", name=re.compile(re.escape(selector), re.I))
                            if loc.count() > 0:
                                loc.first.click(timeout=5000)
                                clicked = True
                        except Exception:
                            pass
                        
                        # Try by text
                        if not clicked:
                            try:
                                loc = page.get_by_text(selector, exact=False)
                                if loc.count() > 0:
                                    loc.first.click(timeout=5000)
                                    clicked = True
                            except Exception:
                                pass
                        
                        # Try button selector with text
                        if not clicked:
                            try:
                                loc = page.locator(f"button:has-text('{selector}'), a:has-text('{selector}')").first
                                if loc.is_visible():
                                    loc.click(timeout=5000)
                                    clicked = True
                            except Exception:
                                pass

                        # Generic submit fallback on forms (useful after filling password)
                        if not clicked:
                            try:
                                loc = page.locator("button[type='submit'], input[type='submit']").first
                                if loc.is_visible():
                                    loc.click(timeout=5000)
                                    clicked = True
                            except Exception:
                                pass
                        
                        if clicked:
                            print(f"[dim]    ✓ Clicked: {selector}[/dim]")
                            time.sleep(2)  # Wait after click for page to respond/navigate
                            
                            # Check if URL changed (navigation to next login step)
                            if page.url != url_before:
                                page_changed = True
                                print(f"[dim]    → Page navigated to: {page.url}[/dim]")
                        else:
                            print(f"[yellow]    ⚠ Could not find button: {selector}[/yellow]")
                    
                    elif action == "press":
                        key = step.get("key", "Enter")
                        page.keyboard.press(key)
                        print(f"[dim]    ✓ Pressed: {key}[/dim]")
                        time.sleep(1)
                        if page.url != url_before:
                            page_changed = True
                    
                    elif action == "wait":
                        time.sleep(2)
                
                except Exception as e:
                    print(f"[yellow]    ⚠ Step failed: {e}[/yellow]")
                    continue
            
            # If page changed during steps, regenerate plan for new page
            if page_changed:
                print(f"[dim]Page changed during login, checking next step...[/dim]")
                time.sleep(1)  # Brief wait for new page to stabilize
                continue
            else:
                # No more navigation, check if login succeeded
                break
        
        # Final verification after all attempts
        time.sleep(2)
        
        # Verify login succeeded by checking for authentication indicators
        try:
            # Check if still on login page (login failed)
            still_on_login = is_login_like(page)
            if still_on_login:
                print("[yellow]  Login failed - still on login page[/yellow]")
                return False
            
            # Check for error messages
            error_indicators = [
                "text='Incorrect username or password'",
                "text='Invalid credentials'",
                "text='Authentication failed'",
                "text='Login failed'",
                "[role='alert']",
                ".error",
                ".alert-danger"
            ]
            for err_sel in error_indicators:
                try:
                    if page.locator(err_sel).count() > 0:
                        print("[yellow]  Login failed - error message detected[/yellow]")
                        return False
                except Exception:
                    continue
            
            # Check for success indicators (authenticated state)
            success_indicators = [
                "[aria-label*='menu' i]",
                "[aria-label*='profile' i]",
                "button:has-text('Sign out')",
                "a:has-text('Sign out')",
                "img[alt*='avatar' i]",
                "[data-testid*='user-menu']"
            ]
            for succ_sel in success_indicators:
                try:
                    if page.locator(succ_sel).count() > 0:
                        print("[green]  ✓ Login verified - authenticated indicators found[/green]")
                        return True
                except Exception:
                    continue
            
            # If no clear success indicators, do NOT assume success
            print("[yellow]  Login status uncertain - not authenticated yet[/yellow]")
            return False
        except Exception:
            pass
        
        return False
    except Exception as e:
        print(f"[yellow]  Login attempt error: {str(e)[:80]}[/yellow]")
        return False


def _attempt_sso_login(page, creds: dict) -> bool:
    """Handle SSO provider login (Google, Microsoft, etc.)."""
    import time
    try:
        time.sleep(2)
        url = page.url.lower()
        
        # Google SSO
        if "accounts.google.com" in url:
            print("[cyan]  On Google SSO page[/cyan]")
            # Try email field
            email_selectors = ["input[type='email']", "#identifierId", "input[name='identifier']"]
            for sel in email_selectors:
                try:
                    loc = page.locator(sel)
                    if loc.count() > 0 and loc.first.is_visible():
                        loc.first.click(timeout=2000)
                        time.sleep(0.3)
                        loc.first.fill(creds["email"])
                        print("[dim]  Filled Google email[/dim]")
                        # Click next
                        page.locator("button:has-text('Next'), #identifierNext").first.click(timeout=5000)
                        time.sleep(3)
                        break
                except Exception:
                    continue
            
            # Try password field
            pass_selectors = ["input[type='password']", "input[name='password']", "#password"]
            for sel in pass_selectors:
                try:
                    loc = page.locator(sel)
                    if loc.count() > 0 and loc.first.is_visible():
                        loc.first.click(timeout=2000)
                        time.sleep(0.3)
                        loc.first.fill(creds["password"])
                        print("[dim]  Filled Google password[/dim]")
                        # Click next
                        page.locator("button:has-text('Next'), #passwordNext").first.click(timeout=5000)
                        time.sleep(4)
                        break
                except Exception:
                    continue
            
            # Wait for redirect back to app
            time.sleep(3)
            
            # Verify SSO login succeeded
            if is_login_like(page):
                print("[yellow]  SSO login failed - still on login page[/yellow]")
                return False
            
            print("[green]  ✓ SSO login successful[/green]")
            return True
        
        # Microsoft SSO
        elif "login.microsoftonline.com" in url or "login.live.com" in url:
            print("[cyan]  On Microsoft SSO page[/cyan]")
            # Email
            try:
                email_loc = page.locator("input[type='email'], input[name='loginfmt']")
                if email_loc.count() > 0:
                    email_loc.first.fill(creds["email"])
                    page.locator("input[type='submit'], button:has-text('Next')").first.click(timeout=5000)
                    time.sleep(3)
            except Exception:
                pass
            
            # Password
            try:
                pass_loc = page.locator("input[type='password'], input[name='passwd']")
                if pass_loc.count() > 0:
                    pass_loc.first.fill(creds["password"])
                    page.locator("input[type='submit'], button:has-text('Sign in')").first.click(timeout=5000)
                    time.sleep(4)
            except Exception:
                pass
            
            # Verify Microsoft SSO login
            if is_login_like(page):
                print("[yellow]  SSO login failed - still on login page[/yellow]")
                return False
            
            print("[green]  ✓ SSO login successful[/green]")
            return True
        
        # Generic fallback
        print("[yellow]  Unknown SSO provider, trying generic login[/yellow]")
        return False
        
    except Exception as e:
        print(f"[yellow]  SSO login error: {str(e)[:80]}[/yellow]")
        return False
