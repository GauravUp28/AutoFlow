# AutoFlow – AI-Only Generalized UI State Capture

AutoFlow automatically navigates live web apps, performs the requested task, and captures screenshots of every UI state (including non-URL states like modals, forms, transient success banners). No hardcoding of sites or workflows. All step planning is performed by an LLM (OpenAI / Anthropic / Gemini) – no heuristic fallback.

## Quickstart (Windows PowerShell)

```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium
python -m autoflow
```

Enter any task when prompted, for example:
- Search for playwright in npm
- How to create a project in Linear
- How to filter a database in Notion
- Download Python from python.org

Outputs are saved under `dataset/<site-slug>/<task-slug>/` including per-step screenshots, a JSON plan, and a markdown log.

## 🔐 Authentication (Minimal, AI-Centric)

AutoFlow supports **3 ways** to handle real authentication:

The system prompts for credentials only when required (task contains auth keywords and login surface detected). Provide them interactively or through env vars:
```env
DEFAULT_EMAIL=your@email.com
DEFAULT_PASSWORD=YourPassword123!
```
Optional per-domain overrides still supported (`LINEAR_APP_EMAIL`, `GITHUB_COM_EMAIL`, etc.). Session/cookie persistence has been removed in AI-only mode for determinism.

## Alternative: Manual Credentials
Create a `.env` in the project root if the site requires auth:

```env
DEFAULT_EMAIL=test@example.com
DEFAULT_PASSWORD=TestPass123!
# Optional per-site overrides (domain-level)
GITHUB_COM_EMAIL=you@example.com
GITHUB_COM_PASSWORD=yourpassword
# Or brand-level
GITHUB_EMAIL=you@example.com
GITHUB_PASSWORD=yourpassword
# Or JSON mapping file
CREDENTIALS_JSON=credentials.json
```

Example `credentials.json`:
```json
{
	"github.com": {"email": "you@example.com", "password": "yourpassword"},
	"linear.app": {"email": "user@company.com", "password": "secret"}
}
```

## What’s Inside (AI-Only)
- `autoflow/web_automation.py`: Orchestrates URL inference, authentication, AI planning loop, dynamic re-planning, state capture.
- `autoflow/llm_interpreter.py`: LLM planner + dynamic replan API (`get_steps_and_selectors`, `get_dynamic_steps`).
- `autoflow/url_inference.py`: Pattern & search-based host discovery (brand → domain).
- `autoflow/ui_state_capturer.py`: Screenshot helper (smart capture mode).
- `autoflow/state_tracker.py`: Lightweight DOM change utilities.
- (Removed) `heuristic_planner.py`: Eliminated in AI-only implementation.

## LLM Configuration

Set one provider (keys in `.env` or shell):

```env
PLANNER_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini
```
or
```env
PLANNER_PROVIDER=anthropic
ANTHROPIC_API_KEY=... 
ANTHROPIC_MODEL=claude-3-5-sonnet-latest
```
or
```env
PLANNER_PROVIDER=gemini
GEMINI_API_KEY=...
GEMINI_MODEL=gemini-1.5-pro
```

Optional:
```env
CAPTURE_MODE=smart   # (default) only capture meaningful state changes
# CAPTURE_MODE=all   # capture after every step
```

If the LLM fails, a minimal 2-step placeholder plan is used (wait + scroll) – no heuristics.

## Environment Variables (General)

Optional variables to refine behavior:

- `HEADLESS=1` – Force headless mode (disables Chrome session reuse)
- `DEFAULT_EMAIL`, `DEFAULT_PASSWORD` – Generic auth fallback credentials
- `DEFAULT_FIRST_NAME`, `DEFAULT_LAST_NAME`, `DEFAULT_USERNAME` – Form fill defaults
- `VERBOSE_DOMAIN_LOGS=1` – Show detailed domain scoring, rejection reasons during URL selection (keep off for clean runs; enable for debugging wrong domain picks)

Unified auth gating is driven by constants in `autoflow/constants.py` (`AUTH_KEYWORDS`, `CREATION_AUTH_KEYWORDS`). Tasks containing any of those tokens are treated as requiring workspace access; read-only tasks (search/view/download) will not be forced through login.

## Assignment Mapping (Softlight Requirements)

| Requirement | Implementation |
|-------------|----------------|
| Capture non-URL states (modals/forms/success) | DOM diff + emergence signals trigger layer & success screenshots; dynamic AI replan inserts follow-up steps |
| Generalize across apps | Brand → domain inference + AI interpreting task + dynamic replan on newly surfaced UI |
| 3–5 workflows | Run tasks (e.g., “create project in Linear”, “filter issues in Linear”, “create repository in GitHub”, “search package in npm”) generating datasets under `dataset/` |
| No hardcoding of tasks | Task string parsed; AI plans steps; no static workflow maps |
| Real-time adaptation | On modal/success detection, `get_dynamic_steps()` requests additional targeted steps |
| Deliver dataset | Per-task folder: screenshots (`smart` filtered), `steps_plan.json`, `steps_log.md`, `run_summary.json` |

## Dataset Artifacts
Each task directory contains:
- `steps_plan.json` – Initial AI plan
- `step_XX_<action>.png` – Smart-captured transitions
- `step_XX_layer.png` / `step_XX_success.png` – Non-URL emergent states
- `steps_log.md` – Human-readable execution log
- `run_summary.json` – Aggregated counts (layers, success states, total steps)

For deeper reasoning context see `SOFTLIGHT_SOLUTION.md`; sample prompts in `TEST_PROMPTS.md`.
