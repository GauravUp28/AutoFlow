# Agent B - Fully Automated Web Workflow Capture System

## Overview

Agent B is a fully automated web automation system that can perform any workflow task on any website and capture screenshots at each step. It uses AI to generate automation steps dynamically, making it generalizable across different web applications without hardcoding.

## Key Features

✅ **Fully Automated** - No manual intervention required  
✅ **AI-Powered** - Dynamically generates automation steps using LLMs  
✅ **Smart URL Detection** - Automatically infers website from task description  
✅ **Screenshot Capture** - Captures every UI state, including non-URL states (modals, forms, etc.)  
✅ **Multi-AI Support** - Works with Gemini (FREE), OpenAI, or Claude  
✅ **Rule-Based Fallback** - Works even without API keys for common tasks  
✅ **Generalizable** - Works for ANY website and ANY task  

## Architecture

```
agent_b/
├── __main__.py           # Entry point and CLI
├── web_automation.py     # Playwright automation engine
├── llm_interpreter.py    # AI-powered step generation
├── url_inference.py      # Smart URL detection from task
├── ui_state_capturer.py  # Screenshot management
└── state_tracker.py      # UI change detection
```

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 2. Get API Key (FREE)

**Option 1: Google Gemini (Recommended - FREE)**
- Go to: https://makersuite.google.com/app/apikey
- Click "Create API key"
- Copy the key

**Option 2: OpenAI (Optional)**
- Go to: https://platform.openai.com/api-keys
- Create an API key

**Option 3: Anthropic Claude (Optional)**
- Go to: https://console.anthropic.com/
- Create an API key

### 3. Configure .env File

```bash
# Google Gemini (FREE tier - RECOMMENDED)
GEMINI_API_KEY=your-gemini-api-key-here

# Optional alternatives
OPENAI_API_KEY=your-openai-key
ANTHROPIC_API_KEY=your-anthropic-key
```

## Usage

### Basic Usage

```bash
python -m agent_b.__main__
```

Then enter your task when prompted:
```
Enter the task: Create a project in Linear
```

The system will:
1. Analyze the task and infer the URL (https://linear.app)
2. Open the browser and navigate
3. Generate automation steps using AI
4. Execute each step automatically
5. Capture screenshots at each stage
6. Save all screenshots organized by website and task

### Example Tasks

- **"Create an account in Github"**  
  → Opens github.com/signup, fills form, captures each step

- **"Create a project in Linear"**  
  → Opens linear.app, navigates to projects, creates project

- **"Download Python"**  
  → Opens python.org/downloads, shows download options

- **"Filter issues in Notion"**  
  → Opens notion.so, demonstrates filtering

## Output Structure

Screenshots are saved in an organized folder structure:

```
dataset/
├── github-com/
│   └── create-an-account/
│       ├── step_00_initial.png
│       ├── step_01_navigate.png
│       ├── step_02_click.png
│       ├── step_03_fill.png
│       └── step_04_final.png
├── linear-app/
│   └── create-a-project/
│       ├── step_00_initial.png
│       ├── step_01_click.png
│       └── step_02_final.png
└── ...
```

## How It Works

### 1. URL Inference
The system analyzes the task description using keyword matching to determine the appropriate website. Supports 40+ popular websites including:
- Development: GitHub, GitLab, Bitbucket
- Project Management: Linear, Jira, Asana, Trello
- Collaboration: Slack, Discord, Notion
- And many more...

### 2. AI Step Generation
The system sends the task and current page HTML to an LLM, which generates a structured list of automation steps:

```json
[
  {
    "description": "Navigate to signup page",
    "action": "navigate",
    "url": "/signup"
  },
  {
    "description": "Click signup button",
    "action": "click",
    "selector": "button:has-text('Sign up')"
  },
  {
    "description": "Fill username",
    "action": "fill",
    "selector": "input[name='username']",
    "value": "testuser"
  }
]
```

### 3. Automated Execution
Playwright executes each step:
- **navigate**: Go to a URL
- **click**: Click an element
- **fill**: Enter text into a field
- **wait**: Wait for an element to appear
- **scroll**: Scroll the page

### 4. Screenshot Capture
After each action, a screenshot is captured and saved with a descriptive filename indicating the step number and action type.

### 5. Error Handling
The system includes robust error handling:
- Timeout handling with retries
- Alternative clicking methods (force click)
- Continue on error to capture as much as possible
- Error screenshots for debugging

## Supported AI Models

### Priority Order:
1. **Google Gemini** (FREE tier available) - Recommended
2. **OpenAI GPT-3.5/4** (Requires credits)
3. **Anthropic Claude** (Requires credits)
4. **Rule-Based Fallback** (No API needed for common tasks)

## Advantages Over Hardcoded Solutions

✅ **No hardcoded selectors** - AI determines elements dynamically  
✅ **Works across websites** - Not limited to specific apps  
✅ **Handles UI changes** - Adapts to website updates  
✅ **Captures non-URL states** - Modals, popups, forms  
✅ **Extensible** - Easy to add new tasks and websites  

## Limitations & Future Improvements

### Current Limitations:
- Requires authentication for many sites (can be handled with pre-login)
- Complex multi-page workflows may need refinement
- Some dynamic SPAs require additional wait strategies

### Future Enhancements:
- Session management for authenticated workflows
- Visual element detection using computer vision
- Multi-tab support
- Parallel workflow execution
- Video recording option

## Testing

The system has been tested with various tasks:
- Account creation (Github, Gmail, etc.)
- Project management (Linear, Jira, Asana)
- Software downloads (Python, VS Code, Node.js)
- Web navigation and documentation

## Troubleshooting

### "Timeout Error"
- Increase timeout in `web_automation.py`
- Check internet connection
- Some sites have bot detection (use authenticated sessions)

### "No API Key Found"
- Make sure `.env` file exists in project root
- Check that API key is valid
- Try Gemini for free tier

### "Screenshot Not Captured"
- Check folder permissions
- Ensure `dataset/` folder is writable
- Verify Playwright is installed correctly

## Credits

Built for the Softlight Engineering Take-Home Assignment demonstrating:
- AI agent coordination
- Dynamic web automation
- State capture across UI workflows
- Generalizable system design
