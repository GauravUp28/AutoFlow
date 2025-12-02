"""
Automatic URL inference without hardcoding specific websites.
Uses web search (DuckDuckGo HTML) and heuristic ranking to pick the best URL
for the user's task. Tries multiple smart query variants to avoid manual input.
"""

from urllib.parse import quote_plus, urlparse
import requests
from bs4 import BeautifulSoup
import re
import os
from typing import List, Tuple, Optional
from autoflow.brand_utils import extract_brands
import os


def _search_duckduckgo(query: str, max_results: int = 10):
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    r = requests.get(url, headers=headers, timeout=20)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    results = []
    for a in soup.select("a.result__a"):
        href = a.get("href")
        title = a.get_text(" ").strip()
        if href and href.startswith("http"):
            results.append({"url": href, "title": title})
        if len(results) >= max_results:
            break
    return results


def _score_result(res: dict, task: str) -> float:
    u = res.get("url", "")
    title = (res.get("title", "") or "").lower()
    parsed = urlparse(u)
    host = parsed.hostname or ""

    # Base score by position is handled by caller; here we apply bonuses/penalties.
    score = 0.0

    # Prefer HTTPS and known app-y paths
    if parsed.scheme == "https":
        score += 0.5
    if any(x in u for x in ["/app", "/login", "/signin", "/signup", "/dashboard", "/downloads", "/download"]):
        score += 0.6

    # Extract brand from task
    tl = task.lower()
    task_brands = extract_brands(task)
    
    # Strong boost if brand appears in hostname
    if task_brands:
        for brand in task_brands:
            if brand.lower() in host:
                score += 2.0
                break
    
    # Penalize docs/support/blog pages only if the task isn't explicitly a how-to/guide
    if not any(k in tl for k in ["how to", "how do i", "guide", "tutorial", "docs", "help", "documentation", "manual"]):
        if any(x in host or x in u for x in ["docs.", "support.", "help.", "developer.", "blog."]):
            score -= 0.4

    # Boost if task tokens appear in title or domain
    task_tokens = [t for t in re.split(r"[^a-z0-9]+", tl) if t and len(t) > 2]
    for tok in set(task_tokens):
        if tok and (tok in title or tok in host):
            score += 0.15

    # Prefer shorter, cleaner paths (likely home/app pages)
    path_len = len((parsed.path or "/").strip("/").split("/"))
    if path_len <= 2:
        score += 0.2

    return score


def _extract_brand_candidates(task: str) -> List[str]:
    # Delegated to unified extractor for consistency across components
    return extract_brands(task)


def _extract_topic_keywords(task: str, brands: List[str]) -> List[str]:
    tl = (task or "").lower()
    toks = [t for t in re.split(r"[^a-z0-9]+", tl) if t]
    stop = set(brands) | set([
        'how','do','i','to','in','the','a','an','and','or','of','for','with','on','my','new','create','make','build','setup','set',
        'sign','signup','sign-up','signin','login','log','log-in','account','project','app','apps'
    ])
    return [t for t in toks if t not in stop and len(t) > 2][:4]


def _query_variants(task: str) -> List[str]:
    brands = _extract_brand_candidates(task)
    variants = [task]
    topics = _extract_topic_keywords(task, brands)

    # Action-specific variants
    t = (task or "").lower()
    action = None
    if any(k in t for k in ["sign up", "signup", "register", "create account"]):
        action = "signup"
    elif any(k in t for k in ["login", "log in", "sign in"]):
        action = "login"
    elif any(k in t for k in ["download", "install"]):
        action = "download"

    for b in brands:
        variants.append(f"official {b}")
        variants.append(b)
        if action:
            variants.append(f"{b} {action}")
        if topics:
            q1 = f"{b} {' '.join(topics)}"
            q2 = f"how to {' '.join(topics)} in {b}"
            variants.extend([q1, q2])

    # Deduplicate while preserving order
    seen = set()
    uniq = []
    for q in variants:
        ql = q.strip().lower()
        if ql and ql not in seen:
            seen.add(ql)
            uniq.append(q)
    return uniq


def infer_url_via_search(task: str) -> Tuple[Optional[str], str]:
    """Search the web with multiple query variants and pick the best candidate URL."""
    try:
        all_scored = []
        queries = _query_variants(task)
        for qi, q in enumerate(queries):
            try:
                results = _search_duckduckgo(q, max_results=8)
            except Exception:
                results = []
            for i, r in enumerate(results):
                s = _score_result(r, task)
                # Position bias (per-query) and slight query-order bias
                s += max(0.0, 0.35 - i * 0.05)
                s += max(0.0, 0.20 - qi * 0.05)
                all_scored.append((s, r))

        if not all_scored:
            return None, "none"

        # Sort and pick top
        all_scored.sort(key=lambda x: x[0], reverse=True)

        # Optional debug of top candidates
        if os.getenv("DEBUG_URL_INFERENCE"):
            print("[cyan]Top URL candidates:[/cyan]")
            for s, r in all_scored[:5]:
                print(f"  - {r['url']}  [score={s:.2f}]  title='{r.get('title','')[:80]}'")

        best = all_scored[0][1]
        return best.get("url"), "high" if all_scored[0][0] > 0.65 else "medium"
    except Exception:
        return None, "none"


def _infer_url_with_ai(task: str) -> Optional[str]:
    """Use LLM to infer the official website URL from the task description."""
    # Don't extract brands - let AI interpret the full task context
    
    # Enhanced prompt that gives AI full context to reason intelligently
    prompt = f"""Analyze this user task and return the PRIMARY website HOMEPAGE they need to start from:

Task: "{task}"

Instructions:
- Identify the MAIN service/platform where the task will be performed
- Return the HOMEPAGE URL, NOT deep links to specific pages/packages
- For search tasks like "search X in Y", return Y's homepage (user will search from there)
- For download tasks like "download X", return X's official homepage
- For creation tasks like "create Y in X", return X's homepage (user will navigate to create from there)
- Ignore OS/platform context (macOS, Windows, Linux)
- Return ONLY the homepage URL starting with https://
- If unclear, return 'UNKNOWN'

Examples:
- "search playwright in npm" → https://www.npmjs.com (homepage, NOT /package/playwright)
- "how to download python in macos" → https://python.org (Python homepage)
- "create repository in github" → https://github.com (GitHub homepage)
- "add todo in todomvc" → https://todomvc.com (TodoMVC homepage)

URL:"""
    
    # Try providers in order
    provider = (os.getenv("PLANNER_PROVIDER") or "").lower()
    
    # Try OpenAI
    openai_key = os.getenv("OPENAI_API_KEY")
    if (provider in ["", "openai"]) and openai_key:
        try:
            import openai
            client = openai.OpenAI(api_key=openai_key)
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=100,
            )
            url = resp.choices[0].message.content.strip()
            if url and url.startswith("http") and "UNKNOWN" not in url.upper():
                return url
        except Exception:
            pass
    
    # Try Anthropic
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if (provider in ["", "anthropic"]) and anthropic_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            model = os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
            resp = client.messages.create(
                model=model,
                max_tokens=100,
                temperature=0.0,
                messages=[{"role": "user", "content": prompt}],
            )
            url = "".join(getattr(p, "text", "") for p in resp.content).strip()
            if url and url.startswith("http") and "UNKNOWN" not in url.upper():
                return url
        except Exception:
            pass
    
    # Try Gemini
    gemini_key = os.getenv("GEMINI_API_KEY")
    if (provider in ["", "google", "gemini"]) and gemini_key:
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model_name = os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            url = getattr(response, "text", "").strip()
            if url and url.startswith("http") and "UNKNOWN" not in url.upper():
                return url
        except Exception:
            pass
    
    return None


def get_direct_url(task: str) -> Optional[str]:
    """Extract explicit brand from task and return URL if env override exists.
    No hardcoded domains - fully dynamic via search or user-provided env vars.
    """
    brands = extract_brands(task)
    if not brands:
        return None
    
    brand_lower = brands[0].lower()
    
    # Check for env override (BASE_URL_<BRAND>)
    env_key = f"BASE_URL_{brand_lower.upper()}"
    override = os.getenv(env_key)
    if override:
        return override if override.startswith('http') else f"https://{override}"
    
    # No hardcoded fallback - rely on search
    return None


def get_url_for_task(task: str):
    """Get a best-effort URL for a task without hardcoding specific sites."""
    # First, try env override (if user set BASE_URL_<BRAND>)
    direct = get_direct_url(task)
    if direct:
        print(f"[green]✓ Using env override URL: {direct}[/green]")
        return direct
    
    # Second, try AI-powered URL inference
    ai_url = _infer_url_with_ai(task)
    if ai_url:
        print(f"[green]✓ AI inferred URL: {ai_url}[/green]")
        return ai_url
    
    # Fallback to web search inference
    url, conf = infer_url_via_search(task)
    if url:
        print(f"[green]✓ Inferred URL via web search: {url} (confidence: {conf})[/green]")
        return url

    # If all failed, browser-side search fallback (handled by runner)
    print("[yellow]⚠ URL inference unavailable; runner will use browser-side search fallback.[/yellow]")
    return None
