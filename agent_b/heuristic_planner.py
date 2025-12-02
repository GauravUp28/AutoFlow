from bs4 import BeautifulSoup
import re
from datetime import datetime
from agent_b.constants import AUTH_KEYWORDS, CREATION_AUTH_KEYWORDS


# Intent detection patterns
INTENT_PATTERNS = {
    "create": re.compile(r"\b(create|new|add|start|build)\b", re.I),
    "filter": re.compile(r"\b(filter|search|find|query)\b", re.I),
    "signin": re.compile(r"\b(sign in|log in|login|signin)\b", re.I),
    "signup": re.compile(r"\b(sign up|signup|register|create account|get started|start trial|start free)\b", re.I),
    "download": re.compile(r"\b(download|install|get)\b", re.I),
    "configure": re.compile(r"\b(configure|setup|set up|settings)\b", re.I),
    "view": re.compile(r"\b(view|see|show|display|open)\b", re.I),
}

# Object/target patterns
TARGET_PATTERNS = {
    "project": re.compile(r"\b(project|workspace|initiative)\b", re.I),
    "database": re.compile(r"\b(database|db|table|collection)\b", re.I),
    "account": re.compile(r"\b(account|profile)\b", re.I),
    "email": re.compile(r"\b(email|gmail|mail)\b", re.I),
    "file": re.compile(r"\b(file|document|doc)\b", re.I),
    "repository": re.compile(r"\b(repository|repositories|repo|repos)\b", re.I),
    "issue": re.compile(r"\b(issue|issues|ticket|bug)\b", re.I),
}

# Noise elements to ignore
NOISE_KEYWORDS = [
    "cookie", "consent", "privacy", "terms", "legal", "footer", "header",
    "navigation", "menu", "newsroom", "blog", "about", "company", "careers",
    "pricing", "contact", "support", "help center", "documentation", "docs",
    "social", "twitter", "facebook", "linkedin", "follow", "subscribe"
]

# Very generic or misleading labels to de-prioritize
EXCLUDE_BUTTON_LABELS = set([
    "home", "pricing", "learn more", "read more", "explore", "discover",
    "why", "what is", "contact", "support", "help", "careers",
])


def _extract_task_intent(task: str):
    """Extract the primary action intent and target object from task."""
    task_lower = task.lower()
    
    # Find primary intent
    intent = None
    for intent_name, pattern in INTENT_PATTERNS.items():
        if pattern.search(task_lower):
            intent = intent_name
            break
    
    # Find target object
    target = None
    for target_name, pattern in TARGET_PATTERNS.items():
        if pattern.search(task_lower):
            target = target_name
            break
    
    return intent, target


def _score_element_relevance(element_text: str, intent: str, target: str, task: str):
    """Score how relevant an element is to the task intent. Higher = more relevant.
    
    Special handling for action tasks (create/configure/filter):
    - Prioritize 'Sign in'/'Log in' (leads to existing workspace) over
    - 'Sign up'/'Create account' (leads to new account onboarding)
    """
    if not element_text:
        return -100
    
    el_lower = element_text.lower().strip()
    task_lower = task.lower()
    
    # Filter out noise
    if any(noise in el_lower for noise in NOISE_KEYWORDS):
        return -100
    
    # Filter out navigation/marketing
    if any(word in el_lower for word in ["learn more", "read more", "explore", "discover", "why", "what is"]):
        return -50

    # Exclude very generic navigation labels outright
    if el_lower.strip() in EXCLUDE_BUTTON_LABELS:
        return -60
    
    # Filter out long descriptive text (likely marketing/announcements)
    if len(el_lower) > 40:
        return -50
    
    # Filter out announcements and blog posts
    if any(word in el_lower for word in ["announcement", "blog", "post", "article", "update:", "new:"]):
        return -50
    
    # Special handling: For creation/modification tasks only
    action_intents = ["create", "configure", "edit", "add", "delete"]
    if any(action_intent in intent for action_intent in action_intents):
        # Penalize signup/create account buttons (they lead to onboarding, not task completion)
        if any(signup_kw in el_lower for signup_kw in ["sign up", "create account", "create an account", "get started free", "start free trial", "join free", "try free", "register"]):
            return -90  # Very strong penalty - completely wrong path
        # Boost sign in/log in (they lead to existing workspace where you can complete tasks)
        if any(signin_kw in el_lower for signin_kw in ["sign in", "log in", "login"]) and len(el_lower.split()) <= 3:
            return 70  # High score - correct path to workspace
        # Penalize generic nav labels that don't mention the target
        if el_lower in ["next", "continue", "start", "get started", "try"] and not any(t in el_lower for t in ["project", "repository", "issue"]):
            return -30
    
    # For filter/search intents, heavily penalize sign in buttons (public read-only actions)
    if intent in ["filter", "search"]:
        if any(signin_kw in el_lower for signin_kw in ["sign in", "log in", "login", "sign up", "create account"]):
            return -80  # Strong penalty - auth not needed for search
    
    score = 0
    
    # Intent match - but require it to be primary text, not buried in long string
    if intent == "create" and any(kw in el_lower for kw in ["create", "new", "add", "+"]):
        # Only score high if it's a short, clear action
        if len(el_lower.split()) <= 4:
            score += 50
        else:
            score += 10  # Weak match if buried in long text
    elif intent == "filter" and any(kw in el_lower for kw in ["filter", "search", "find"]):
        score += 50
    elif intent == "signup" and any(kw in el_lower for kw in ["sign up", "get started", "start free", "try", "register"]):
        if len(el_lower.split()) <= 5:
            score += 50
        else:
            score += 10
    elif intent == "signin" and any(kw in el_lower for kw in ["sign in", "log in", "login"]):
        score += 50
    elif intent == "download" and any(kw in el_lower for kw in ["download", "install"]):
        score += 50
    
    # Target object match
    if target == "project" and "project" in el_lower:
        if len(el_lower.split()) <= 4:
            score += 40
        else:
            score += 10
    elif target == "database" and any(kw in el_lower for kw in ["database", "table"]):
        score += 30
    elif target == "account" and "account" in el_lower:
        score += 30
    
    # Combined intent+target match
    if intent and target:
        intent_kw = intent.replace("_", " ")
        target_kw = target.replace("_", " ")
        if intent_kw in el_lower and target_kw in el_lower:
            # This is a strong signal - both intent and target in same element
            if len(el_lower.split()) <= 4:
                score += 60
            else:
                score += 20
    
    # Prefer shorter, more specific text
    word_count = len(el_lower.split())
    if word_count <= 3:
        score += 10
    elif word_count == 1 and el_lower in ["+", "×", "create", "new", "add"]:
        score += 20  # Single-word actions are usually buttons
    elif word_count > 10:
        score -= 20
    
    # Prefer button-like labels
    if el_lower in ["create", "new", "add", "filter", "search", "+", "submit", "continue", "next"]:
        score += 30
    
    # Exact matches for common action patterns
    if intent == "create" and target == "project":
        if el_lower in ["create project", "new project", "add project", "+", "create", "new"]:
            score += 80  # Very high boost for exact matches
        if "project" in el_lower and any(kw in el_lower for kw in ["create", "new", "add"]):
            score += 60
    if intent == "create" and target == "repository":
        if el_lower in ["create repository", "new repository", "new repo", "new", "+", "create"]:
            score += 80  # Very high boost
        if "repositor" in el_lower and any(kw in el_lower for kw in ["create", "new", "add"]):
            score += 60
    
    return score


def _find_actionable_elements(soup, intent: str, target: str, task: str):
    """Find the most relevant interactive elements for the task."""
    candidates = []
    
    # Determine minimum score threshold to avoid random clicks
    # Lower threshold for search/filter to detect subtle search triggers
    intent_threshold = 25 if intent in ["filter", "search"] else 35 if intent in ["create", "signup", "signin"] else 20
    
    # Find all interactive elements
    for el in soup.select("button, a, [role='button'], [role='link'], input[type='submit']"):
        text = (el.get_text(" ", strip=True) or "").strip()
        aria_label = el.get("aria-label", "")
        title = el.get("title", "")
        
        # Combine all text hints
        full_text = " ".join(filter(None, [text, aria_label, title]))
        
        if full_text:
            score = _score_element_relevance(full_text, intent, target, task)
            if score >= intent_threshold:
                candidates.append({
                    "text": text or aria_label or title,
                    "score": score,
                    "tag": el.name,
                    "aria_label": aria_label,
                })
    
    # Sort by relevance score
    candidates.sort(key=lambda x: x["score"], reverse=True)
    return candidates[:5]  # Top 5 most relevant


def _find_form_inputs(soup, intent: str, target: str):
    """Find relevant input fields for the task, filtering out noise."""
    inputs = []
    
    # Noise patterns to skip
    noise_patterns = [
        "newsletter", "subscribe", "email", "footer", "header", "nav",
        "cookie", "consent", "privacy", "marketing", "promo"
    ]
    
    # For search/filter tasks, aggressively find search inputs first
    if intent in ["filter", "search"]:
        for inp in soup.select("input[type='search'], [role='searchbox'], input[placeholder*='search' i], input[aria-label*='search' i]"):
            inp_type = inp.get("type", "search").lower()
            name = inp.get("name", "")
            placeholder = inp.get("placeholder", "")
            aria_label = inp.get("aria-label", "")
            inp_id = inp.get("id", "")
            
            hint = placeholder or aria_label or name or "search"
            
            # Build selector
            selector = None
            if inp_type == "search":
                selector = "input[type='search']"
            elif inp.get("role") == "searchbox":
                selector = "[role='searchbox']"
            elif name:
                selector = f"input[name='{name}']"
            elif inp_id:
                selector = f"#{inp_id}"
            elif placeholder:
                selector = f"input[placeholder*='{placeholder[:30]}']"
            
            if selector and not any(i["selector"] == selector for i in inputs):
                inputs.append({
                    "selector": selector,
                    "hint": hint,
                    "type": inp_type,
                })
    
    for inp in soup.select("input, textarea"):
        inp_type = inp.get("type", "text").lower()
        
        # Skip hidden, submit, buttons
        if inp_type in ["hidden", "submit", "button", "checkbox", "radio"]:
            continue
        
        name = inp.get("name", "")
        placeholder = inp.get("placeholder", "")
        aria_label = inp.get("aria-label", "")
        inp_id = inp.get("id", "")
        
        # Find label
        label_text = ""
        if inp_id:
            label = soup.find("label", {"for": inp_id})
            if label:
                label_text = label.get_text(" ", strip=True)
        
        hint = label_text or placeholder or aria_label or name
        if not hint:
            continue
        
        # Filter out noise fields (newsletter, footer email, etc.)
        hint_lower = hint.lower()
        if any(noise in hint_lower for noise in noise_patterns):
            continue

        # In create/configure flows, skip omnibox/assignment/search-like fields which are not part of creation forms
        if intent in ["create", "configure"] and any(k in hint_lower for k in ["assign", "search", "filter", "find"]):
            continue

        # Skip credential/password flows when task is not account/sign in related
        if intent == "create" and target == "project" and any(k in hint_lower for k in ["password", "email", "account", "username"]):
            continue
        if intent == "create" and target == "project" and inp_type == "password":
            continue
        
        # Filter out if in footer/header sections
        parent_str = str(inp.parent).lower() if inp.parent else ""
        if any(section in parent_str for section in ["footer", "header", "nav", "sidebar"]):
            continue
        
        # Build selector - prefer name over id for stability
        selector = None
        if name:
            selector = f"input[name='{name}']" if inp.name == "input" else f"textarea[name='{name}']"
        elif inp_id and not any(noise in inp_id.lower() for noise in noise_patterns):
            selector = f"#{inp_id}"
        elif placeholder:
            selector = f"input[placeholder*='{placeholder[:30]}']"
        
        # Search fallback augmentation
        if not selector and intent in ["filter", "search"] and inp_type == "text":
            # Potential search field indicators
            if any(k in hint_lower for k in ["search", "find", "query", "filter", "packages"]):
                selector = "input[placeholder*='search' i], input[name*='search' i], input[type='search']"

        if selector:
            # Check for duplicates
            if not any(i["selector"] == selector for i in inputs):
                inputs.append({
                    "selector": selector,
                    "hint": hint,
                    "type": inp_type,
                })
    
    return inputs[:3]  # Limit to top 3 most relevant


def generate_heuristic_steps(task: str, url: str|None, html: str|None, authenticated: bool = False):
    """Generate workflow steps that capture UI state transitions.
    
    Key insight for Softlight assignment:
    - We need to capture EVERY UI state change (modals, dropdowns, forms appearing)
    - Not just the final action, but the journey: button → modal → form → success
    - Each click/action triggers a state change that needs screenshot capture
    
    This planner:
    1. Extracts intent (create, filter, signup, etc.) and target (project, database, etc.)
    2. Finds primary action trigger (button/link that opens modal/form)
    3. Generates steps with state capture points: click → wait for modal → fill → submit
    4. Focuses on high-relevance elements only (ignores marketing/nav)
    """
    steps = []
    
    soup = None
    if html:
        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            soup = None
    
    if not soup:
        # No HTML to analyze
        return [
            {"description": "Wait for page load", "action": "wait", "selector": "body"},
            {"description": "Capture initial state", "action": "scroll"},
        ]
    
    # Extract task intent and target
    intent, target = _extract_task_intent(task)
    
    print(f"[dim]Detected intent: {intent}, target: {target}[/dim]")
    
    # Shared auth intent keywords (unified across planner and runner)
    task_needs_auth = any(keyword in task.lower() for keyword in AUTH_KEYWORDS)

    # Check if we're already in an authenticated workspace OR runner told us we are
    workspace_indicators = ["dashboard", "workspace", "new project", "new repository", "create project", "create repository", "settings", "profile"]
    page_text_lower = soup.get_text().lower() if soup else ""
    workspace_present = authenticated or any(ind in page_text_lower for ind in workspace_indicators)

    # Only pre-inject auth for create/configure intents IF we're NOT already authenticated
    if task_needs_auth and intent in ["create", "configure"] and not workspace_present and not authenticated:
        if soup.find(string=re.compile(r"\b(sign in|log in|login)\b", re.I)) and not soup.select("input[type='password']"):
            steps.append({"description": "Click Sign in to authenticate", "action": "click", "selector": "a:has-text('Sign in'), button:has-text('Sign in'), a:has-text('Log in'), button:has-text('Log in')"})
            steps.append({"description": "Wait for login page", "action": "wait", "selector": "body"})

    # Find relevant interactive elements
    clickable_candidates = _find_actionable_elements(soup, intent, target, task)
    # If we are authenticated/in workspace, drop any sign-in/login candidates entirely
    if clickable_candidates and (workspace_present or authenticated):
        before = len(clickable_candidates)
        clickable_candidates = [c for c in clickable_candidates if not re.search(r"\b(sign in|log in|login)\b", c.get("text",""), re.I)]
        if len(clickable_candidates) != before:
            print(f"[dim]  Filtered sign-in controls post-auth ({before}->{len(clickable_candidates)})[/dim]")
    if clickable_candidates:
        print(f"[dim]  Found {len(clickable_candidates)} clickable elements, top: '{clickable_candidates[0]['text']}'[/dim]")
    
    # Find relevant input fields
    input_fields = _find_form_inputs(soup, intent, target)
    # For create flows, ignore assignment/search-like inputs which are often omnibar fields
    if input_fields and intent in ["create", "configure"]:
        before_inp = len(input_fields)
        input_fields = [i for i in input_fields if not re.search(r"assign|search|filter|find", i.get("hint",""), re.I)]
        if len(input_fields) != before_inp:
            print(f"[dim]  Filtered non-creation inputs ({before_inp}->{len(input_fields)})[/dim]")
    if input_fields:
        print(f"[dim]  Found {len(input_fields)} input fields, top: '{input_fields[0]['hint']}'[/dim]")
    
    # If we can't find relevant action buttons for CREATE tasks, consider auth flow
    # These tasks require workspace access to complete
    task_needs_auth = any(keyword in task.lower() for keyword in AUTH_KEYWORDS)
    
    if not clickable_candidates and task_needs_auth and intent in ["create", "configure"]:
        sign_in_el = soup.find(string=re.compile(r"\b(sign in|log in|login)\b", re.I))
        if sign_in_el:
            steps.append({"description": "Capture initial state", "action": "wait", "selector": "body"})
            steps.append({
                "description": "Click Sign in to access app",
                "action": "click",
                "selector": "a:has-text('Sign in'), button:has-text('Sign in'), a:has-text('Log in'), button:has-text('Log in')",
            })
            steps.append({"description": "Wait for login page to load", "action": "wait", "selector": "body"})
            return steps

    # Build workflow steps with state capture focus
    steps.append({"description": "Capture initial page state", "action": "wait", "selector": "body"})

    # If intent is create AND task explicitly needs auth, add exploratory click to reach app/dashboard
    # BUT skip if we're clearly already past login (workspace_present already calculated above)
    creation_auth_needed = any(keyword in task.lower() for keyword in CREATION_AUTH_KEYWORDS)
    
    if intent == "create" and not clickable_candidates and creation_auth_needed and not workspace_present and not authenticated:
        # Look for Sign in first (pre-auth step added elsewhere), then generic exploratory buttons
        if soup.find(string=re.compile(r"\b(sign in|log in|login)\b", re.I)):
            steps.append({
                "description": "Click Sign in to authenticate and reach app area",
                "action": "click",
                "selector": "a:has-text('Sign in'), button:has-text('Sign in'), a:has-text('Log in'), button:has-text('Log in')",
            })
            steps.append({"description": "Wait for auth page or dashboard", "action": "wait", "selector": "body"})
        else:
            # Generic exploratory buttons
            steps.append({
                "description": "Explore primary CTA to reach application",
                "action": "click",
                "selector": "button:has-text('Get started'), a:has-text('Get started'), button:has-text('Try'), a:has-text('Try'), button:has-text('Explore'), a:has-text('Explore')",
            })
            steps.append({"description": "Wait for potential navigation", "action": "wait", "selector": "body"})
    
    # Add click actions for top-scoring elements
    # CRITICAL: Each click may open modal/dropdown/form - capture that state!
    # Only click the MOST relevant element (not multiple)
    if clickable_candidates:
        candidate = clickable_candidates[0]  # Top 1 most relevant only
        btn_text = candidate["text"]
        aria = candidate.get("aria_label", "")
        
        # Build selector
        if aria:
            selector = f"{candidate['tag']}[aria-label*='{aria[:30]}']"
        else:
            selector = f"{candidate['tag']}:has-text('{btn_text}')"
        
        steps.append({
            "description": f"Click '{btn_text}' to {intent} {target or 'item'}",
            "action": "click",
            "selector": selector,
        })
    
    # Add fill actions for discovered inputs
    # Each input fill is a state change that should be captured
    for inp in input_fields[:1]:  # Top 1 most relevant input only (not multiple duplicate fills)
        hint_lower = inp["hint"].lower()
        value = ""
        
        # Smart value generation based on field hint AND task context
        if "email" in hint_lower or inp["type"] == "email":
            value = "test@example.com"
        elif "name" in hint_lower and "first" in hint_lower:
            value = "Test"
        elif "name" in hint_lower and "last" in hint_lower:
            value = "User"
        elif "password" in hint_lower or inp["type"] == "password":
            value = "TestPass123!"
        elif "phone" in hint_lower or inp["type"] == "tel":
            value = "+1234567890"
        elif "search" in hint_lower or "query" in hint_lower or "filter" in hint_lower:
            # For search fields, extract search term from task
            # e.g., "Search for playwright in npm" → "playwright"
            search_term = ""
            task_lower = task.lower()
            # Extract search term from common patterns
            if "search for" in task_lower or "search and open" in task_lower:
                match = re.search(r"search (?:for|and open)\s+([a-z0-9._-]+)", task_lower)
                if match:
                    search_term = match.group(1)
            elif "open" in task_lower and "in" in task_lower:
                # e.g., "open playwright in npm" → "playwright"
                match = re.search(r"open\s+([a-z0-9._-]+)", task_lower)
                if match:
                    search_term = match.group(1)
            elif "filter" in task_lower:
                match = re.search(r"filter.*?for\s+([a-z0-9._-]+)", task_lower)
                if match:
                    search_term = match.group(1)
            # Fallback: extract the first meaningful token (not stop words)
            if not search_term:
                tokens = re.findall(r"\b([a-z0-9._-]{3,})\b", task_lower)
                stop = {"search", "open", "for", "and", "the", "in", "on", "from", "how", "to", "create", "filter"}
                search_term = next((t for t in tokens if t not in stop), "")
            value = search_term or "test"
        elif "name" in hint_lower or "title" in hint_lower or "project" in hint_lower:
            value = f"Auto {target or 'Item'} {datetime.now().strftime('%H%M%S')}"
        elif "description" in hint_lower or "desc" in hint_lower:
            value = f"Sample description for {target or 'item'}"
        else:
            value = "Test input"
        
        steps.append({
            "description": f"Type '{value}' in {inp['hint']}",
            "action": "fill",
            "selector": inp["selector"],
            "value": value,
        })
    
    # Add submit if we filled forms - this will trigger final state change
    if input_fields:
        steps.append({
            "description": "Submit search/form",
            "action": "click",
            "selector": "button[type='submit'], button:has-text('Search'), button:has-text('Submit'), button:has-text('Create'), button:has-text('Save'), button:has-text('Continue'), button:has-text('Next'), button:has-text('Done')",
        })

    # If intent is search/filter and no inputs were detected, synthesize a generic search attempt
    if intent in ["filter", "search"] and not input_fields:
        # Extract search term from task
        search_term = ""
        task_lower = task.lower()
        if "search for" in task_lower or "search and open" in task_lower:
            match = re.search(r"search (?:for|and open)\s+([a-z0-9._-]+)", task_lower)
            if match:
                search_term = match.group(1)
        elif "open" in task_lower and "in" in task_lower:
            match = re.search(r"open\s+([a-z0-9._-]+)", task_lower)
            if match:
                search_term = match.group(1)
        if not search_term:
            tokens = re.findall(r"\b([a-z0-9._-]{3,})\b", task_lower)
            stop = {"search", "open", "for", "and", "the", "in", "on", "from", "how", "to", "create", "filter"}
            search_term = next((t for t in tokens if t not in stop), "")
        
        steps.append({
            "description": "Focus generic search field",
            "action": "click",
            "selector": "input[type='search'], [role='searchbox'], input[placeholder*='search' i]",
        })
        steps.append({
            "description": f"Type '{search_term or 'test'}' in search field",
            "action": "fill",
            "selector": "input[type='search'], [role='searchbox'], input[placeholder*='search' i]",
            "value": (search_term or "test"),
        })
        steps.append({
            "description": "Submit search",
            "action": "click",
            "selector": "button:has-text('Search'), button[type='submit']",
        })
        steps.append({"description": "Wait for results state", "action": "wait", "selector": "body"})
    
    # If no meaningful actions found, add generic exploration
    # BUT if we found search inputs, don't add extra scrolls - let the fill happen
    if len([s for s in steps if s["action"] in ["click", "fill"]]) == 0:
        if not input_fields or intent not in ["filter", "search"]:
            steps.append({"description": "Scroll to explore page", "action": "scroll"})
            steps.append({"description": "Scroll to explore page", "action": "scroll"})

    return steps
