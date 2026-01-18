import os
from dotenv import load_dotenv
import json
import re
from typing import List, Dict, Any, Optional
from bs4 import BeautifulSoup

load_dotenv()

# Import vision utilities
try:
    from autoflow.vision_utils import (
        is_vision_enabled,
        prepare_screenshot_for_vision,
        build_openai_vision_message,
        build_anthropic_vision_message,
        build_gemini_vision_content,
        get_vision_model,
    )
    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False
    def is_vision_enabled(): return False

def _extract_page_context(html: str | None) -> dict:
    """Extracts lightweight, high-signal page context for the planner.
    Collects clickable labels and input hints from the current DOM snapshot.
    """
    if not html:
        return {"clickables": [], "inputs": []}
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return {"clickables": [], "inputs": []}

    def clean_text(t: str) -> str:
        t = (t or "").strip()
        t = re.sub(r"\s+", " ", t)
        return t[:80]

    # Clickable labels with richer context
    clickables: List[str] = []
    for el in soup.select("button, a, [role='button'], [role='link'], [type='submit'], summary"):
        txt = clean_text(el.get_text(" ", strip=True))
        aria = clean_text(el.get("aria-label", ""))
        title = clean_text(el.get("title", ""))
        href = el.get("href", "")
        data_target = clean_text(el.get("data-target", ""))
        
        # For links, include href context if text is generic
        if el.name == "a" and href and txt and len(txt.split()) <= 2:
            href_part = href.split("/")[-1] if "/" in href else href
            label = f"{txt} ({href_part[:30]})" if href_part else txt
        else:
            label = next((v for v in [txt, aria, title, data_target] if v), "")
        
        if not label:
            continue
        lower = label.lower()
        
        # Filter marketing/nav noise
        if any(k in lower for k in ["learn more", "pricing", "careers", "blog", "news", "footer", "header", "about us", "contact us"]):
            continue
        
        # Prioritize action buttons (new, create, add, etc.)
        is_action = any(k in lower for k in ["new", "create", "add", "+", "start", "begin"])
        
        # Keep concise actionable labels
        if len(label.split()) <= 10:
            # Add visual indicator for primary actions
            if is_action:
                label = f"🔹 {label}"
            clickables.append(label)
        if len(clickables) >= 50:
            break

    # Input hints with more context
    inputs: List[str] = []
    for el in soup.select("input, textarea"):
        ph = clean_text(el.get("placeholder", ""))
        aria = clean_text(el.get("aria-label", ""))
        name = clean_text(el.get("name", ""))
        elem_id = clean_text(el.get("id", ""))
        input_type = clean_text(el.get("type", ""))
        
        # Build comprehensive hint with ID and name
        parts = []
        if ph: parts.append(ph)
        if aria and aria != ph: parts.append(f"[{aria}]")
        if elem_id: parts.append(f"#{elem_id}")
        if name and name != elem_id: parts.append(f"name={name}")
        if input_type: parts.append(f"({input_type})")
        
        hint = " ".join(parts) if parts else f"[{input_type} field]" if input_type else ""
        if not hint:
            continue
        
        low = hint.lower()
        if any(k in low for k in ["newsletter", "subscribe", "marketing", "cookie", "consent", "footer", "header", "nav"]):
            continue
        
        inputs.append(hint)
        if len(inputs) >= 25:
            break

    return {"clickables": clickables, "inputs": inputs}


def _build_planner_prompt(task: str, url: str | None, html: str | None) -> str:
    ctx = _extract_page_context(html)
    clickables = ctx["clickables"]
    inputs = ctx["inputs"]

    guidance = {
        "task": task,
        "url": url or "unknown",
        "clickables": clickables,
        "inputs": inputs,
    }

    schema = (
        "Return ONLY a JSON array. Each item must be an object with: "
        "description (string), action (navigate|click|fill|wait|scroll), "
        "selector (string for click/fill; omit for navigate), "
        "url (string only when action=navigate), value (string only when action=fill)."
    )

    rules = (
        "Rules: "
        "1) CRITICAL: Decompose the task into ALL its required verbs. "
        "Example: 'search and open playwright' requires BOTH a search step AND an open/click step. "
        "Do NOT stop after only one action—fulfill the complete task. "
        "2) Distinguish task types: "
        "   - 'Search for X' or 'Find X' = use site's search box. "
        "   - 'Download X', 'How to X', 'Install X' = navigate site sections (e.g., click 'Downloads', 'Docs'). "
        "   - 'Add a todo' or similar on demo/example sites = first click into the actual app/example, THEN perform action. "
        "3) Use clickables/inputs from the provided context for precise selectors. "
        "4) NEVER use CSS class selectors (e.g., .package-snippet, .result-item). Use visible text or aria-label instead. "
        "5) For search result links, use the package/item NAME as the selector (e.g., 'requests', 'playwright'), not generic terms. "
        "6) If page shows workspace/project UI (not login), skip any Sign in/Log in steps. "
        "7) Capture transitional states: modals, forms, success banners by targeting their controls. "
        "8) Prefer specific text selectors over generic class/ID when clickables list provides clear labels. "
        "9) Do NOT invent elements; if uncertain, choose the most common control label from the context. "
        "10) For search tasks: first fill search box, then click search/submit, THEN wait 2s for results to load, THEN click the TOP RESULT using its visible text. "
        "11) To submit a form or add an item after filling input, use action=press with key='Enter' instead of wait. "
        "12) After pressing Enter on a search form or navigation action, ALWAYS add a wait step (2 seconds) before attempting to interact with new page content. "
        "13) CREATE FLOWS: If the task says 'create' or 'new' for a specific resource (e.g., repository, project, page, issue), prefer clickables that explicitly include the resource name ('New repository', 'Create project'). If only a generic 'New' button exists, click it FIRST, then select the resource from the menu (e.g., 'New repository'). After the form/page opens, add fill steps for the primary name/title field (use a short, valid value like 'my-new-repo' for repositories, 'Test Project' for projects, 'Test issue' for issues), then click the final submit ('Create', 'Create repository', 'Submit'). "
        "14) For name/title inputs, use the exact hints from 'inputs' (placeholders, labels, or id/name like '#repository_name', "
        "    'name=repository[name]'). Avoid unrelated fields unless necessary to enable submission. "
        "15) CRITICAL COMPLETION RULE: After ANY submit/create/save/download action (button clicks like 'Create repository', 'Submit', 'Save', 'Download', etc.), you MUST add a wait step with selector='body' and 3-4 second delay description to allow the page to navigate, show success message, or complete the operation. Then add a scroll step to ensure the final state is visible and captured. NEVER end a plan immediately after a submit action without verification. "
        "16) SUCCESS VERIFICATION: For creation tasks ('create repository', 'create project'), after the create button click and wait, look for success indicators in the next page context (e.g., 'Repository created', success banner, or the newly created item visible). If planning dynamically, add a final wait step to capture this. For download tasks ('download Python'), after clicking the download link/button, add a wait step (3-4 seconds) to allow download dialog/confirmation to appear, then scroll to ensure final state is captured. "
        "17) FINAL STATE MANDATE: The last step in your plan should ALWAYS be either a 'wait' action (with body selector and 3+ second description) or a 'scroll' action to ensure the completion state is fully loaded and will be screenshot. Do NOT end plans with a click or fill action—always follow with wait/scroll for verification."
    )

    prompt = (
        f"You are an expert UI automation planner.\n"
        f"Goal: Generate a COMPLETE, PRECISE step sequence to fulfill EVERY part of the user's task within the current app view.\n\n"
        f"CRITICAL CONTEXT: The user's browser is ALREADY on the target website: {url or 'unknown'}.\n"
        f"DO NOT treat this as a web search task. You are automating interactions WITHIN this specific website.\n\n"
        f"TASK TYPE IDENTIFICATION:\n"
        f"- If task is 'how to download X' or 'download X' and you see navigation links (Downloads, Get Started, etc.), click those links first.\n"
        f"- If task is 'search for X' and you see a search input field, use the search functionality.\n"
        f"- If on a landing/demo page with examples, click into a specific example before performing actions.\n"
        f"- NEVER use the site's search box for 'how to' or 'download' tasks - navigate the site structure instead.\n"
        f"- CREATE/NEW tasks: Look for buttons marked with 🔹 (primary actions like 'New', 'Create', '+'). Click these FIRST to open the creation form.\n\n"
        f"Task breakdown: Break '{task}' into distinct actions. If task contains multiple verbs (e.g., 'search and open'), generate steps for EACH verb.\n\n"
        f"Context (JSON):\n{json.dumps(guidance, ensure_ascii=False, indent=2)}\n\n"
        f"{schema}\n{rules}\n\n"
        f"SELECTOR PRECISION:\n"
        f"- Use the EXACT text from clickables list (e.g., if you see '🔹 New', use selector 'New')\n"
        f"- For inputs, use the exact placeholder/label from inputs list\n"
        f"- Match text exactly as shown in the context - this ensures reliable element finding\n\n"
        f"Return only the JSON array with ALL steps required for complete task fulfillment ON THE CURRENT SITE ({url or 'current page'})."
    )
    return prompt


def _build_vision_planner_prompt(task: str, url: str | None, html: str | None) -> str:
    """Build enhanced prompt that instructs model to use screenshot context."""
    ctx = _extract_page_context(html)
    clickables = ctx["clickables"]
    inputs = ctx["inputs"]

    guidance = {
        "task": task,
        "url": url or "unknown",
        "clickables": clickables,
        "inputs": inputs,
    }

    schema = (
        "Return ONLY a JSON array. Each item must be an object with: "
        "description (string), action (navigate|click|fill|wait|scroll|press), "
        "selector (string for click/fill; omit for navigate), "
        "url (string only when action=navigate), value (string only when action=fill), "
        "key (string only when action=press, e.g., 'Enter')."
    )

    rules = (
        "Rules: "
        "1) CRITICAL: Use the SCREENSHOT to visually identify UI elements. Cross-reference with DOM context. "
        "2) Decompose the task into ALL required actions. Don't stop after one step. "
        "3) For buttons/links: Use the visible TEXT you see in the screenshot as the selector. "
        "4) For inputs: Use placeholder text, label text, or aria-label visible in DOM context. "
        "5) NEVER use CSS class selectors. Use visible text, aria-label, or semantic identifiers. "
        "6) If you see a search box visually, generate: fill → press Enter → wait → click result. "
        "7) For create/new tasks: Click the visible 'New' or '+' button FIRST, then fill the form. "
        "8) After submit/create actions, ALWAYS add a wait step (3+ seconds) for page to update. "
        "9) Last step should be wait or scroll to capture final state."
    )

    prompt = (
        f"You are an expert UI automation planner with VISUAL understanding.\n\n"
        f"IMPORTANT: You have been provided a SCREENSHOT of the current page. "
        f"Use BOTH the visual information AND the DOM context to create accurate selectors.\n\n"
        f"VISUAL ANALYSIS INSTRUCTIONS:\n"
        f"1. Look at the screenshot to identify the exact layout and element positions\n"
        f"2. Identify buttons, links, input fields, and interactive elements visually\n"
        f"3. Note any modals, overlays, or popups visible in the screenshot\n"
        f"4. Cross-reference visual elements with the DOM context below\n\n"
        f"CURRENT PAGE: {url or 'unknown'}\n"
        f"TASK: {task}\n\n"
        f"DOM Context (for selector hints):\n{json.dumps(guidance, ensure_ascii=False, indent=2)}\n\n"
        f"{schema}\n{rules}\n\n"
        f"Return only the JSON array with ALL steps required."
    )
    return prompt


def _call_with_vision_openai(prompt: str, screenshot_b64: str, model_override: str = None) -> Optional[str]:
    """Make vision API call to OpenAI. Returns response text or None."""
    try:
        import openai
        client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        model = model_override or get_vision_model("openai") or "gpt-4o-mini"

        messages = [
            {"role": "system", "content": "You are a precise UI automation planner with visual understanding. Return only valid JSON arrays."}
        ] + build_openai_vision_message(prompt, screenshot_b64)

        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=0.0,
            max_tokens=1500,
        )
        return resp.choices[0].message.content
    except Exception as e:
        print(f"[yellow]OpenAI vision call failed: {e}[/yellow]")
        return None


def _call_with_vision_anthropic(prompt: str, screenshot_b64: str, model_override: str = None) -> Optional[str]:
    """Make vision API call to Anthropic. Returns response text or None."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        model = model_override or get_vision_model("anthropic") or "claude-3-5-sonnet-latest"

        messages = build_anthropic_vision_message(prompt, screenshot_b64)

        resp = client.messages.create(
            model=model,
            max_tokens=1500,
            temperature=0.0,
            system="You are a precise UI automation planner with visual understanding. Return only valid JSON arrays.",
            messages=messages,
        )
        return "".join(getattr(p, "text", "") for p in resp.content)
    except Exception as e:
        print(f"[yellow]Anthropic vision call failed: {e}[/yellow]")
        return None


def _call_with_vision_gemini(prompt: str, image_bytes: bytes, model_override: str = None) -> Optional[str]:
    """Make vision API call to Gemini. Returns response text or None."""
    try:
        import google.generativeai as genai
        genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
        model_name = model_override or get_vision_model("gemini") or "gemini-1.5-pro"
        model = genai.GenerativeModel(model_name)

        content = build_gemini_vision_content(prompt, image_bytes)
        resp = model.generate_content(content)
        return getattr(resp, "text", "")
    except Exception as e:
        print(f"[yellow]Gemini vision call failed: {e}[/yellow]")
        return None


def _extract_json_array(text: str) -> List[Dict[str, Any]]:
    """Best-effort extraction of a JSON array from model output."""
    if not text:
        return []
    # Strip code fences
    t = re.sub(r"```(?:json)?|```", "", text).strip()
    # If content is already an array
    if t.lstrip().startswith("["):
        try:
            return json.loads(t)
        except Exception:
            pass
    # Fallback: find first [ ... ] block
    m = re.search(r"\[.*\]", t, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return []
    return []


def _validate_steps(steps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for s in steps or []:
        if not isinstance(s, dict):
            continue
        action = (s.get("action") or "").lower()
        desc = s.get("description") or ""
        if action not in {"navigate", "click", "fill", "press", "wait", "scroll"}:
            continue
        if action == "navigate" and not s.get("url"):
            continue
        if action == "press" and not s.get("key"):
            continue
        if action in {"click", "fill"} and not s.get("selector"):
            continue
        # Sanitize types
        s["description"] = str(desc)
        if "selector" in s and s["selector"] is not None:
            s["selector"] = str(s["selector"])[:300]
        if "url" in s and s["url"] is not None:
            s["url"] = str(s["url"])[:500]
        if "value" in s and s["value"] is not None:
            s["value"] = str(s["value"])[:300]
        out.append(s)
    return out[:20]


def get_steps_and_selectors(task, url=None, html=None, screenshot: bytes = None):
    """
    Generate step-by-step automation plan using available AI services.

    Args:
        task: The task description
        url: Current page URL
        html: Current page HTML
        screenshot: Optional screenshot bytes for vision-enhanced planning

    Provider order (unless overridden): OpenAI -> Anthropic -> Gemini -> Fallback.
    When USE_VISION=1 and screenshot provided, uses vision-capable models first.
    """

    # Provider preferences
    provider = (os.getenv("PLANNER_PROVIDER") or "").lower()
    model_override = os.getenv("PLANNER_MODEL")

    # Prepare vision data if enabled and screenshot provided
    vision_data = None
    if VISION_AVAILABLE and is_vision_enabled() and screenshot:
        result = prepare_screenshot_for_vision(screenshot)
        if result:
            vision_data = {"b64": result[0], "bytes": result[1], "meta": result[2]}
            print(f"[dim]Vision mode: image prepared ({result[2].get('optimized_size', 'unknown')})[/dim]")

    # Build appropriate prompt
    if vision_data:
        prompt = _build_vision_planner_prompt(task, url, html)
    else:
        prompt = _build_planner_prompt(task, url, html)

    # Try OpenAI
    openai_key = os.getenv("OPENAI_API_KEY")
    if (provider in ["", "openai"]) and openai_key:
        # Try vision first if available
        if vision_data:
            content = _call_with_vision_openai(prompt, vision_data["b64"], model_override)
            if content:
                steps = _extract_json_array(content)
                steps = _validate_steps(steps)
                if steps:
                    print("[green]✓ Vision planning succeeded (OpenAI)[/green]")
                    return steps
                print("[yellow]Vision returned invalid response, falling back to text[/yellow]")

        # Text-only fallback
        try:
            import openai
            client = openai.OpenAI(api_key=openai_key)
            model_name = model_override or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            resp = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "You are a precise UI automation planner. You decompose tasks into complete, actionable step sequences, fulfilling ALL task verbs and requirements. You return only valid JSON arrays."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,
                max_tokens=1500,
            )
            content = resp.choices[0].message.content
            steps = _extract_json_array(content)
            steps = _validate_steps(steps)
            if steps:
                return steps
        except Exception:
            pass

    # Try Anthropic
    anthropic_key = os.getenv("ANTHROPIC_API_KEY")
    if (provider in ["", "anthropic"]) and anthropic_key:
        # Try vision first if available
        if vision_data:
            content = _call_with_vision_anthropic(prompt, vision_data["b64"], model_override)
            if content:
                steps = _extract_json_array(content)
                steps = _validate_steps(steps)
                if steps:
                    print("[green]✓ Vision planning succeeded (Anthropic)[/green]")
                    return steps
                print("[yellow]Vision returned invalid response, falling back to text[/yellow]")

        # Text-only fallback
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=anthropic_key)
            model_name = model_override or os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
            resp = client.messages.create(
                model=model_name,
                max_tokens=1500,
                temperature=0.0,
                system="You are a precise UI automation planner. You decompose tasks into complete, actionable step sequences, fulfilling ALL task verbs. Return only valid JSON arrays.",
                messages=[{"role": "user", "content": prompt}],
            )
            content = "".join(getattr(p, "text", "") for p in resp.content)
            steps = _extract_json_array(content)
            steps = _validate_steps(steps)
            if steps:
                return steps
        except Exception:
            pass

    # Try Google Gemini
    gemini_key = os.getenv("GEMINI_API_KEY")
    if (provider in ["", "google", "gemini"]) and gemini_key:
        # Try vision first if available
        if vision_data:
            content = _call_with_vision_gemini(prompt, vision_data["bytes"], model_override)
            if content:
                steps = _extract_json_array(content)
                steps = _validate_steps(steps)
                if steps:
                    print("[green]✓ Vision planning succeeded (Gemini)[/green]")
                    return steps
                print("[yellow]Vision returned invalid response, falling back to text[/yellow]")

        # Text-only fallback
        try:
            import google.generativeai as genai
            genai.configure(api_key=gemini_key)
            model_name = model_override or os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt)
            content = getattr(response, "text", "")
            steps = _extract_json_array(content)
            steps = _validate_steps(steps)
            if steps:
                return steps
        except Exception:
            pass

    # No heuristic fallback in AI-only mode; return minimal safe plan
    # Last resort: generic minimal plan
    return [
        {"description": "Wait for page body", "action": "wait", "selector": "body"},
        {"description": "Scroll page", "action": "scroll"},
    ]


def get_dynamic_steps(task: str, url: str | None, html: str | None, history: list[dict], screenshot: bytes = None):
    """Request follow-up steps from the LLM given newly appeared UI (modal/form/success) and prior execution history.

    Args:
        task: The original task description
        url: Current page URL
        html: Current page HTML
        history: List of previously executed steps
        screenshot: Optional screenshot bytes for vision-enhanced planning

    Returns a validated list of additional steps (may be empty).
    This does NOT fall back to heuristics.
    """
    provider = (os.getenv("PLANNER_PROVIDER") or "").lower()
    model_override = os.getenv("PLANNER_MODEL")

    # Prepare vision data if enabled and screenshot provided
    vision_data = None
    if VISION_AVAILABLE and is_vision_enabled() and screenshot:
        result = prepare_screenshot_for_vision(screenshot)
        if result:
            vision_data = {"b64": result[0], "bytes": result[1], "meta": result[2]}

    # Condense history for prompt (limit last 12)
    recent = history[-12:]
    hist_serializable = []
    for h in recent:
        hist_serializable.append({
            "step": h.get("step"),
            "action": h.get("action"),
            "description": h.get("description"),
            "status": h.get("status"),
            "url": h.get("url"),
        })

    # Minimal DOM slice (avoid huge prompt)
    dom_slice = ""
    if html:
        dom_slice = re.sub(r"\s+", " ", html)[:4000]  # cap length

    # Build prompt - enhanced for vision if available
    if vision_data:
        prompt = (
            "You are continuing an in-progress UI automation plan. "
            "You have been provided a SCREENSHOT of the current page state.\n\n"
            "VISUAL ANALYSIS: Look at the screenshot to identify:\n"
            "- Any newly appeared modals, dialogs, or popups\n"
            "- Form fields that need to be filled\n"
            "- Success/error banners or messages\n"
            "- Buttons to proceed or close the current layer\n\n"
            f"Task: {task}\nCurrent URL: {url or 'unknown'}\n"
            f"Recent Steps JSON: {json.dumps(hist_serializable, ensure_ascii=False)}\n\n"
            f"DOM Context: {dom_slice}\n\n"
            "Return ONLY a JSON array of objects with keys: description, action (navigate|click|fill|wait|scroll|press), "
            "selector (omit if navigate), url (only if navigate), value (only if fill), key (only if press). "
            "Use visible text from the screenshot for selectors. Limit to 5 steps."
        )
    else:
        prompt = (
            "You are continuing an in-progress UI automation plan. "
            "Given new UI state (possibly a modal/form/success layer) produce the NEXT focused steps only.\n\n"
            f"Task: {task}\nCurrent URL: {url or 'unknown'}\n"
            f"Recent Steps JSON: {json.dumps(hist_serializable, ensure_ascii=False)}\n\n"
            f"DOM Slice: {dom_slice}\n\n"
            "Return ONLY a JSON array of objects with keys: description, action (navigate|click|fill|wait|scroll), selector (omit if navigate), url (only if navigate), value (only if fill). "
            "Skip any redundant login/auth. Prefer interacting with newly visible modal/form fields or closing success banners. Limit to 5 steps."
        )

    def _provider_call(build_fn):
        try:
            steps = build_fn()
            steps = _validate_steps(_extract_json_array(steps))
            return steps
        except Exception:
            return []

    # OpenAI
    if (provider in ["", "openai"]) and os.getenv("OPENAI_API_KEY"):
        # Try vision first if available
        if vision_data:
            content = _call_with_vision_openai(prompt, vision_data["b64"], model_override)
            if content:
                steps = _validate_steps(_extract_json_array(content))
                if steps:
                    return steps

        def _openai_call():
            import openai
            client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            model_name = model_override or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            resp = client.chat.completions.create(
                model=model_name,
                messages=[{"role": "system", "content": "You extend UI automation plans precisely."}, {"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=800,
            )
            return resp.choices[0].message.content
        steps = _provider_call(_openai_call)
        if steps:
            return steps

    # Anthropic
    if (provider in ["", "anthropic"]) and os.getenv("ANTHROPIC_API_KEY"):
        # Try vision first if available
        if vision_data:
            content = _call_with_vision_anthropic(prompt, vision_data["b64"], model_override)
            if content:
                steps = _validate_steps(_extract_json_array(content))
                if steps:
                    return steps

        def _anthropic_call():
            import anthropic
            client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
            model_name = model_override or os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-latest")
            resp = client.messages.create(
                model=model_name,
                max_tokens=800,
                temperature=0.1,
                messages=[{"role": "user", "content": prompt}],
            )
            return "".join(getattr(p, "text", "") for p in resp.content)
        steps = _provider_call(_anthropic_call)
        if steps:
            return steps

    # Gemini
    if (provider in ["", "google", "gemini"]) and os.getenv("GEMINI_API_KEY"):
        # Try vision first if available
        if vision_data:
            content = _call_with_vision_gemini(prompt, vision_data["bytes"], model_override)
            if content:
                steps = _validate_steps(_extract_json_array(content))
                if steps:
                    return steps

        def _gemini_call():
            import google.generativeai as genai
            genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
            model_name = model_override or os.getenv("GEMINI_MODEL", "gemini-1.5-pro")
            model = genai.GenerativeModel(model_name)
            resp = model.generate_content(prompt)
            return getattr(resp, "text", "")
        steps = _provider_call(_gemini_call)
        if steps:
            return steps

    return []  # No dynamic steps available


def get_login_steps(url: str, html: str, email: str) -> List[Dict[str, Any]]:
    """Generate AI-powered login steps for any website."""
    guidance = _extract_page_context(html)
    
    # Extract visible text to help AI understand what's happening
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        # Get main visible text (first 2000 chars to avoid token overload)
        page_text = soup.get_text(separator=" ", strip=True)[:2000]
    except Exception:
        page_text = ""
    
    schema = (
        "Return a JSON array of step objects. Each step MUST have: "
        "{ \"description\": string, \"action\": \"fill\" | \"click\" | \"press\" | \"wait\", "
        "\"selector\": string (visible text or aria-label for click, placeholder/label for fill), "
        "\"value\": string (only for fill), \"key\": string (only for press, e.g., 'Enter', 'Tab') }. "
        "For fill actions, use 'EMAIL' as value for email field and 'PASSWORD' for password field - these will be replaced with actual credentials."
    )
    
    rules = (
        "CRITICAL RULES FOR INTELLIGENT LOGIN: "
        "1) OBSERVE THE PAGE: Read the visible text to understand what the page is asking for. "
        "   - If you see 'We sent a code' or 'Check your email' or 'Enter code' → This is EMAIL VERIFICATION, NOT password. "
        "   - If you see 'verification code' or '6-digit code' → User needs to check email and enter code. "
        "   - If you see 'Password' field → Normal password entry. "
        "   - If you see 'Sign in' button but NO login form → This is a marketing page, click 'Sign in' to go to login page. "
        "2) MARKETING PAGE vs LOGIN PAGE: "
        "   - Marketing page: Has 'Sign in' button in header but no email/password fields → Click 'Sign in' to navigate "
        "   - Login page: Has email/password input fields → Fill credentials and submit "
        "3) EMAIL VERIFICATION FLOW: "
        "   - If page says 'code sent to email' or shows code input field: "
        "     → Generate a fill step for the code field with value='VERIFICATION_CODE' "
        "     → The system will prompt user to check their email "
        "4) MULTI-STEP LOGIN DETECTION: "
        "   - Email-only page (no password field) → Fill email, click Continue "
        "   - Password page (has password field) → Fill password, click Continue/Sign in "
        "   - Code verification page → Fill code, click Verify/Continue "
        "5) SSO BUTTONS: If you see 'Continue with Google/Microsoft/SAML', click that first. "
        "6) USE EXACT VISIBLE TEXT from clickables list for button selectors. "
        "7) DO NOT assume password comes after email - check what the page actually shows! "
        "8) HANDLE INTERRUPTIONS: If you see cookie banners or modals, they will be dismissed automatically."
    )
    
    prompt = (
        f"You are an intelligent login automation system.\n"
        f"ANALYZE the current page state and generate the EXACT steps needed for THIS SPECIFIC PAGE.\n\n"
        f"Current URL: {url}\n"
        f"User email: {email}\n\n"
        f"VISIBLE PAGE TEXT (read this carefully to understand what page is asking for):\n"
        f"{page_text}\n\n"
        f"AVAILABLE FORM ELEMENTS:\n{json.dumps(guidance, ensure_ascii=False, indent=2)}\n\n"
        f"{schema}\n{rules}\n\n"
        f"THINK STEP BY STEP:\n"
        f"1. What is this page asking for? (Email? Password? Verification code? SSO?)\n"
        f"2. What elements are available to interact with?\n"
        f"3. What is the logical next step based on page state?\n\n"
        f"Return ONLY the JSON array of steps for THIS PAGE'S current state."
    )
    
    # Try OpenAI first
    provider = os.getenv("PLANNER_PROVIDER", "openai").lower()
    if provider in ["", "openai"] and os.getenv("OPENAI_API_KEY"):
        try:
            import openai
            client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
            resp = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=1000
            )
            text = resp.choices[0].message.content.strip()
            steps = _extract_json_array(text)
            if steps:
                return steps
        except Exception as e:
            print(f"[yellow]⚠ AI login planning failed: {e}[/yellow]")
    
    # Fallback to basic heuristic if AI fails
    return [
        {"description": "Fill email field", "action": "fill", "selector": "Email", "value": "EMAIL"},
        {"description": "Click Continue or Sign in", "action": "click", "selector": "Continue"},
        {"description": "Fill password field", "action": "fill", "selector": "Password", "value": "PASSWORD"},
        {"description": "Click Sign in button", "action": "click", "selector": "Sign in"}
    ]
    
