"""Helper script to save cookies after manual login.

Usage:
1. Run this script: python save_cookies.py
2. A browser will open
3. Manually log in to the sites you need (Linear, Notion, GitHub, etc.)
4. Press Enter in the terminal when done
5. Cookies will be saved to cookies/{site}.json

Then use them with: python -m agent_b --cookies cookies/linear.json
"""

from playwright.sync_api import sync_playwright
import json
import os
from pathlib import Path

def save_cookies_interactive():
    print("\n" + "="*60)
    print("🍪 Cookie Saver - Save Login Sessions")
    print("="*60)
    print("\nThis will open a browser where you can log in to sites.")
    print("After logging in, cookies will be saved for future use.\n")
    
    sites = input("Which sites do you want to log into? (comma-separated, e.g., linear,notion,github): ").strip()
    if not sites:
        print("No sites specified. Exiting.")
        return
    
    site_list = [s.strip() for s in sites.split(",")]
    
    # Create cookies directory
    cookies_dir = Path("cookies")
    cookies_dir.mkdir(exist_ok=True)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=500)
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()
        
        for site in site_list:
            site_clean = site.lower().strip()
            
            # Map common names to URLs
            site_urls = {
                "linear": "https://linear.app",
                "notion": "https://www.notion.so",
                "github": "https://github.com",
                "gitlab": "https://gitlab.com",
                "asana": "https://app.asana.com",
                "jira": "https://www.atlassian.com",
                "trello": "https://trello.com",
                "slack": "https://slack.com",
            }
            
            url = site_urls.get(site_clean, f"https://{site_clean}.com")
            
            print(f"\n{'='*60}")
            print(f"Opening {site_clean}...")
            print(f"URL: {url}")
            print(f"{'='*60}\n")
            
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception as e:
                print(f"⚠ Could not load {url}: {e}")
                continue
            
            input(f"\n👉 Log in to {site_clean} in the browser, then press Enter here...")
            
            # Save cookies
            cookies = context.cookies()
            cookie_file = cookies_dir / f"{site_clean}.json"
            
            with open(cookie_file, 'w') as f:
                json.dump(cookies, f, indent=2)
            
            print(f"✅ Saved {len(cookies)} cookies to {cookie_file}")
        
        print("\n" + "="*60)
        print("✅ All done! Cookies saved.")
        print("="*60)
        print("\nUsage:")
        print("  python -m agent_b --cookies cookies/linear.json --task 'Create a project in Linear'")
        print("  python -m agent_b --cookies cookies/notion.json --task 'Filter database in Notion'")
        print("\n")
        
        browser.close()

if __name__ == "__main__":
    save_cookies_interactive()
