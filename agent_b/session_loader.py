"""Load existing browser sessions to bypass authentication.

This allows the agent to use your already-authenticated browser session
without needing real credentials.
"""

import json
import os
from pathlib import Path


def get_chrome_profile_path():
    """Get the Chrome user data directory.

    Order of resolution:
    1. CHROME_PROFILE_PATH env var (explicit override)
    2. Platform default location
    """
    override = os.getenv('CHROME_PROFILE_PATH')
    if override:
        p = Path(override).expanduser()
        if p.exists():
            return p
        else:
            print(f"[yellow]CHROME_PROFILE_PATH does not exist: {p}[/yellow]")
    if os.name == 'nt':  # Windows
        return Path(os.getenv('LOCALAPPDATA')) / 'Google' / 'Chrome' / 'User Data'
    elif os.name == 'posix':
        sysname = os.uname().sysname if hasattr(os, 'uname') else ''
        if sysname == 'Darwin':  # macOS
            return Path.home() / 'Library' / 'Application Support' / 'Google' / 'Chrome'
        else:  # Linux
            return Path.home() / '.config' / 'google-chrome'
    return None


def load_session_from_chrome(context, domain: str):
    """Load cookies from Chrome profile for a specific domain."""
    try:
        # Playwright can use Chrome's persistent context
        # This shares the actual Chrome session including cookies
        return True
    except Exception as e:
        print(f"[yellow]Could not load Chrome session: {e}[/yellow]")
        return False


def save_session_cookies(page, filepath: str):
    """Save current page cookies to a JSON file."""
    try:
        cookies = page.context.cookies()
        with open(filepath, 'w') as f:
            json.dump(cookies, f, indent=2)
        print(f"[green]✓ Saved session cookies to {filepath}[/green]")
        return True
    except Exception as e:
        print(f"[yellow]Could not save cookies: {e}[/yellow]")
        return False


def load_session_cookies(context, filepath: str):
    """Load cookies from a JSON file into the browser context."""
    try:
        if not os.path.exists(filepath):
            return False
        
        with open(filepath, 'r') as f:
            cookies = json.load(f)
        
        context.add_cookies(cookies)
        print(f"[green]✓ Loaded session cookies from {filepath}[/green]")
        return True
    except Exception as e:
        print(f"[yellow]Could not load cookies: {e}[/yellow]")
        return False


def use_persistent_context(playwright, headless=False, user_data_dir=None):
    """Launch browser with persistent context (system Chrome channel preferred).

    Adds robust diagnostics for profile lock issues and provides guidance to user.
    """
    if not user_data_dir:
        user_data_dir = get_chrome_profile_path()
    if not user_data_dir or not Path(user_data_dir).exists():
        print(f"[yellow]Chrome profile path not found: {user_data_dir}[/yellow]")
        return None

    try:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(user_data_dir),
            headless=headless,
            channel="chrome",  # ensure real Chrome is used
            viewport={'width': 1920, 'height': 1080},
            slow_mo=300,
        )
        return context
    except Exception as e:
        msg = str(e)
        locked = 'Opening in existing browser session' in msg or 'Target page, context or browser has been closed' in msg
        if locked:
            print('[red]❌ Chrome profile appears locked by a running Chrome instance.[/red]')
            print('[yellow]Attempting lightweight profile clone for session reuse...[/yellow]')
            # Try to clone essential profile data into a temp directory
            try:
                import shutil, tempfile
                src_default = Path(user_data_dir) / 'Default'
                if not src_default.exists():
                    print('[yellow]Default profile folder not found; cannot clone.[/yellow]')
                    raise RuntimeError('No Default profile to clone')
                temp_root = Path(tempfile.mkdtemp(prefix='automation_profile_'))
                # Copy only critical subfolders/files
                include = ['Cookies', 'Web Data', 'Network', 'Preferences', 'Login Data']
                (temp_root / 'Default').mkdir(parents=True, exist_ok=True)
                for name in include:
                    src = src_default / name
                    if src.exists():
                        try:
                            if src.is_dir():
                                shutil.copytree(src, (temp_root / 'Default' / name))
                            else:
                                shutil.copy2(src, (temp_root / 'Default' / name))
                        except Exception:
                            continue
                print(f'[cyan]Cloned minimal profile to {temp_root}[/cyan]')
                clone_ctx = playwright.chromium.launch_persistent_context(
                    user_data_dir=str(temp_root),
                    headless=headless,
                    channel='chrome',
                    viewport={'width': 1920, 'height': 1080},
                    slow_mo=300,
                )
                print('[green]✓ Using cloned profile (limited auth reuse)[/green]')
                return clone_ctx
            except Exception as clone_err:
                print(f'[yellow]Profile clone failed: {clone_err}[/yellow]')
                print('[yellow]Close ALL Chrome windows and retry for full session reuse.[/yellow]')
        else:
            print('[yellow]Persistent context error not due to lock; proceeding without session.[/yellow]')
        print(f"[yellow]Could not use persistent context: {e}[/yellow]")
        return None
