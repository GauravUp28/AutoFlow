+39# Softlight Agent B - Demo Guide

## Overview
This agent automatically identifies websites from natural language prompts, navigates the live application, and captures screenshots of **every UI state** - including modals, forms, and dropdowns that don't have URLs.

**Key Features:**
- ✅ **No hardcoded websites** - works with ANY web app
- ✅ **Automatic website identification** from task description
- ✅ **Captures non-URL states** - modals, dropdowns, forms appearing
- ✅ **Intelligent authentication** - attempts login with sample credentials
- ✅ **Real-time workflow capture** - screenshots at each state transition

---

## How It Works

### 1. Website Identification (No Hardcoding)
The agent extracts brand names from your prompt and tries common domain patterns:

**Example prompts:**
- "How do I create a project in Linear?"
  → Tries: `linear.app`, `app.linear.com`, `linear.com`, etc.

- "How do I filter a database in Notion?"
  → Tries: `notion.so`, `www.notion.so`, `notion.com`, etc.

- "How do I create an issue in GitHub?"
  → Tries: `github.com`, `app.github.com`, `github.io`, etc.

**P6-attern-based domain trying (generalized):**
```
For action tasks (create, filter, add, etc.):
1. {brand}.app
2. app.{brand}.com
3. www.{brand}.com
4. {brand}.io
5. {brand}.so
6. {brand}.ai
7. {brand}.co

Plus browser-side search fallback if all patterns fail.
```

### 2. UI State Capture (Including Non-URL States)

The agent captures screenshots at **every state transition:**

**Example: "Create a project in Linear"**
1. ✅ Initial page load (URL: linear.app)
2. ✅ After clicking "Sign in" button (login page appears)
3. ✅ After filling credentials (form filled state)
4. ✅ After authentication (dashboard loads)
5. ✅ After clicking "New Project" (modal appears - **no URL!**)
6. ✅ After filling project name (form filled state - **no URL!**)
7. ✅ After clicking "Create" (success state)

**Key insight:** Each action triggers a wait for DOM changes (modals, dropdowns) before capturing the next screenshot.

### 3. Authentication Handling

**Automatic login with sample credentials:**
- Detects login gates using heuristics (password field, "Sign in" text)
- Attempts login with: `test@example.com` / `TestPass123!`
- Tries common login URL patterns: `/login`, `/signin`, `/auth/login`, etc.
- Updates workflow plan after successful authentication

**For demo/testing:** Set your own credentials in `.env`:
```bash
DEFAULT_EMAIL=your@email.com
DEFAULT_PASSWORD=yourpassword
```

---

## Running Test Workflows

### Example 1: Create Project (Linear)
```bash
python -m agent_b
# Prompt: How do I create a project in Linear?
```

**Expected captures:**
- Landing page
- Login screen
- Authenticated dashboard
- "New Project" modal appearing
- Form fields filled
- Project created confirmation

### Example 2: Filter Database (Notion)
```bash
python -m agent_b
# Prompt: How do I filter a database in Notion?
```

**Expected captures:**
- Notion homepage
- Login/signup flow
- Workspace view
- Database page
- Filter dropdown appearing
- Filter options visible
- Filtered results

### Example 3: Create Issue (GitHub)
```bash
python -m agent_b
# Prompt: How do I create an issue in GitHub?
```

**Expected captures:**
- GitHub homepage
- Repository page
- "New Issue" button clicked
- Issue form appearing
- Form fields filled
- Issue created

### Example 4: Add Todo (TodoMVC - No Auth)
```bash
python -m agent_b
# Prompt: Add a todo in TodoMVC React demo
```

**Expected captures:**
- TodoMVC app loaded
- Input field focused
- Todo entered
- Todo added to list
- Filters visible

### Example 5: Search Packages (npm - No Auth)
```bash
python -m agent_b
# Prompt: Search for playwright package in npm
```

**Expected captures:**
- npm homepage
- Search box filled
- Search results appearing
- Package page loaded
- Tabs/sections visible

---

## Architecture Highlights

### No Hardcoding - Fully Generalizable

**Brand Extraction:**
- Detects capitalized words (Linear, Notion, GitHub)
- Recognizes "in [Brand]" patterns
- Works with ANY brand name in the prompt

**Domain Pattern Matching:**
- Tries 7+ common TLD patterns (.com, .app, .io, .so, .ai, .co)
- Prioritizes app/authenticated subdomains for action tasks
- Falls back to browser-based search if patterns fail

**Authentication:**
- Generic login detection (password field, "Sign in" text)
- Generic login URL patterns (/login, /signin, /auth, etc.)
- Works with any site's login flow

**Element Detection:**
- Intent extraction: create, filter, signup, download, configure, etc.
- Target extraction: project, database, issue, account, etc.
- Relevance scoring: filters out navigation, marketing, cookies
- Works with any app's UI structure

### State Transition Detection

After each click:
1. Wait for DOM changes
2. Detect new elements: `dialog`, `[role='dialog']`, `[role='menu']`, `.modal`, `form`
3. Capture screenshot of new state
4. Wait for animations/transitions to complete

---

## Output Structure

Each workflow generates:
```
dataset/manual_navigation/{task-slug}/
├── step_00_initial.png          # Initial page state
├── step_00_auth_success.png     # (if auth required)
├── step_01_wait.png              # After first action
├── step_02_click.png             # Button clicked (modal appears)
├── step_03_wait.png              # Modal fully visible
├── step_04_fill.png              # Form field filled
├── step_05_click.png             # Submit clicked
├── step_06_wait.png              # Success state
├── step_07_final.png             # Final state
├── steps_plan.json               # Generated workflow plan
└── steps_log.md                  # Human-readable report
```

---

## Testing with Public Sites (No Auth Required)

If you want to avoid authentication complexity, test with these public sites:

1. **TodoMVC** (https://todomvc.com/examples/react)
   - Prompt: "Add three todos in TodoMVC and mark one as completed"

2. **The Internet** (https://the-internet.herokuapp.com)
   - Prompt: "Open the Checkboxes page and tick both checkboxes"

3. **DemoQA** (https://demoqa.com)
   - Prompt: "Open Text Box and fill all fields"

4. **npm** (https://www.npmjs.com)
   - Prompt: "Search for playwright and open the package page"

5. **Wikipedia** (https://en.wikipedia.org)
   - Prompt: "Search for Python programming language"

---

## Meeting Softlight Assignment Requirements

✅ **Handles any request at runtime** - no hardcoded tasks
✅ **Works across different web apps** - pattern-based, not site-specific
✅ **Captures non-URL states** - modals, dropdowns, forms detected via DOM changes
✅ **Generalizable approach** - brand extraction, domain patterns, intent detection all work for unseen apps
✅ **Real-time navigation** - live page inspection, not pre-recorded flows
✅ **Captures 3-5 UI states per workflow** - each action triggers screenshot capture

---

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run agent
python -m agent_b

# Enter any task:
# - "How do I create a project in Linear?"
# - "How do I filter a database in Notion?"
# - "How do I create an issue in GitHub?"
# - "Add a todo in TodoMVC"
# - "Search for react in npm"
```

Screenshots will be saved in `dataset/manual_navigation/{task-name}/`
