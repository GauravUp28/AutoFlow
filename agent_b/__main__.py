
import sys
import argparse
import re
from rich import print
from agent_b.web_automation import run_task_on_webapp
from agent_b.url_inference import get_url_for_task

import os
from pathlib import Path
from slugify import slugify
from dotenv import load_dotenv

def main():
    load_dotenv()
    # API key / provider sanity check and auto-selection
    gem_key = os.getenv("GEMINI_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    if not gem_key and not openai_key:
        print("[red]No API keys found. Set GEMINI_API_KEY or OPENAI_API_KEY in .env before running.[/red]")
        sys.exit(1)
    if not os.getenv("PLANNER_PROVIDER"):
        if openai_key:
            os.environ["PLANNER_PROVIDER"] = "openai"
        elif gem_key:
            os.environ["PLANNER_PROVIDER"] = "gemini"
    print(f"[cyan]Planner provider: {os.getenv('PLANNER_PROVIDER')}\n[/cyan]")
    print("\n[bold cyan]╔═══════════════════════════════════════════════════════╗[/bold cyan]")
    print("[bold cyan]║   Softlight Agent B - Fully Automated Workflow        ║[/bold cyan]")
    print("[bold cyan]║      AI-Powered Browser Automation System             ║[/bold cyan]")
    print("[bold cyan]╚═══════════════════════════════════════════════════════╝[/bold cyan]\n")
    
    # CLI args and env fallbacks
    parser = argparse.ArgumentParser(description="Softlight Agent B")
    parser.add_argument("--task", dest="task", help="Task to execute", default=None)
    parser.add_argument("--url", dest="url", help="Optional starting URL (skips inference)", default=None)
    parser.add_argument("--headless", dest="headless", help="Run headless", action="store_true")
    parser.add_argument("--no-auth", dest="no_auth", help="Skip authentication (for read-only tasks)", action="store_true")
    parser.add_argument("--email", dest="cred_email", help="Login email/username (non-interactive)", default=None)
    parser.add_argument("--password", dest="cred_password", help="Login password (non-interactive; consider omitting to be prompted)", default=None)
    args = parser.parse_args()

    task = args.task or os.getenv("TASK")
    if not task:
        task = input("Enter the task (e.g., 'Search for playwright in npm'): ").strip()
    
    if not task:
        print("[yellow]No task provided, exiting.[/yellow]")
        return
    
    # Smart URL inference based on task (skip if --url provided)
    print(f"\n[cyan]Analyzing task: '{task}'...[/cyan]")
    if args.url:
        url = args.url
        print(f"[green]Using provided URL: {url}[/green]")
    else:
        inferred_url = get_url_for_task(task)
        url = inferred_url

    # Unified brand extraction utility
    from agent_b.brand_utils import extract_brands
    brands = extract_brands(task)
    if url:
        print(f"[green]Using inferred URL: {url}[/green]")
    
    # Prepare output directory for screenshots
    if url:
        # Prefer hostname for stable slug
        try:
            from urllib.parse import urlparse
            host = urlparse(url).hostname or url
            app_slug = slugify(host)
        except Exception:
            app_slug = slugify(url)
    else:
        app_slug = slugify(brands[0]) if brands else "manual_navigation"
    
    task_slug = slugify(task)[:80]
    out_dir = Path("dataset") / app_slug / task_slug
    os.makedirs(out_dir, exist_ok=True)
    
    print(f"[bold green]═══════════════════════════════════════[/bold green]")
    print(f"[bold green]Task:[/bold green] {task}")
    print(f"[bold green]URL:[/bold green] {url if url else '[auto-detect]'}")
    print(f"[bold green]Output:[/bold green] {out_dir}")
    print(f"[bold green]Output (abs):[/bold green] {out_dir.absolute()}")
    print(f"[bold green]═══════════════════════════════════════[/bold green]\n")
    
    print("[cyan]Starting automated workflow...[/cyan]")
    run_task_on_webapp(
        task,
        url if url else None,
        out_dir,
        headless=True if args.headless else None,
        skip_auth=args.no_auth,
        cred_email=args.cred_email,
        cred_password=args.cred_password
    )
    
    print(f"\n[bold cyan]✓ All done! Check your screenshots in:[/bold cyan]")
    print(f"[bold cyan]  {out_dir.absolute()}[/bold cyan]\n")

if __name__ == "__main__":
    main()
