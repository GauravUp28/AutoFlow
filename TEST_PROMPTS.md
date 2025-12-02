# Test Prompts for Softlight Agent B

## How to Test

Run the agent:
```bash
python -m agent_b
```

Then paste ANY of these prompts when asked for a task.

---

## ✅ Recommended Test Cases (No Auth Required)

### Search Workflows
```
Search for playwright in npm
```
**Expected:** Opens npmjs.com → clicks search → types "playwright" → shows results
**Key States:** Homepage, search expanded, query typed, results

```
Search for requests in PyPI
```
**Expected:** Opens pypi.org → searches for "requests" package
**Key States:** Homepage, search field, results list

```
Search for Python programming language in Wikipedia
```
**Expected:** Opens wikipedia.org → searches → opens article
**Key States:** Homepage, search dropdown, article page

### Navigation Workflows
```
How to download Python from python.org
```
**Expected:** Opens python.org → clicks Downloads → shows download options
**Key States:** Homepage, downloads page, version selection

```
Open the checkboxes page in the-internet.herokuapp.com
```
**Expected:** Opens herokuapp testing site → navigates to checkboxes
**Key States:** Index, checkboxes demo page

### Form/Input Workflows
```
Add a new todo item in TodoMVC
```
**Expected:** Opens todomvc demo → types in input → adds todo
**Key States:** Empty list, input focused, todo added

---

## 🔐 Auth-Required Test Cases (Will attempt auto-login)

### Linear
```
How to create a project in Linear
```
**Expected:** Opens linear.app → attempts login → clicks "New Project" → fills form → submits
**Key States:** Login page, authenticated dashboard, project modal, form filled, success

```
Create a new issue in Linear
```
**Expected:** Authenticated Linear → clicks "New Issue" → fills title/description → creates
**Key States:** Dashboard, issue modal, form, created issue

### Notion
```
How to filter a database in Notion
```
**Expected:** Opens notion.so → attempts login → opens database → clicks filter → applies filter
**Key States:** Login, workspace, database, filter dropdown, filtered view

```
Create a new page in Notion
```
**Expected:** Authenticated Notion → clicks "New Page" → types title → saves
**Key States:** Sidebar, new page modal, editor, saved page

### GitHub
```
Create a new repository in GitHub
```
**Expected:** Opens github.com → login → clicks "New repo" → fills form → creates
**Key States:** Homepage, login, dashboard, new repo form, created repo

```
How to create an issue in GitHub
```
**Expected:** Authenticated GitHub → navigates to repo → clicks "New Issue" → fills → submits
**Key States:** Repo page, issues tab, new issue form, created issue

### Asana
```
How to create a task in Asana
```
**Expected:** Opens asana.com → login → clicks "Add Task" → fills details → saves
**Key States:** Login, project view, task form, task created

```
Create a project in Asana
```
**Expected:** Authenticated Asana → "New Project" → fills name → creates
**Key States:** Dashboard, project modal, form, project created

---

## 🎯 Testing Non-URL State Capture

These tasks specifically test modal/dropdown/form capture (the key Softlight requirement):

### Modals (No URL Change)
```
How to create a project in Linear
```
**Non-URL States:**
- Project creation modal appears (no URL)
- Form fields visible (no URL)
- Success message (may or may not have URL)

```
Create a new repository in GitHub
```
**Non-URL States:**
- New repo form is on same page
- Visibility dropdown opens (no URL)
- Description field expands (no URL)

### Dropdowns (No URL Change)
```
Search for playwright in npm
```
**Non-URL States:**
- Search field expands on click (no URL)
- Autocomplete suggestions appear (no URL)

```
How to filter a database in Notion
```
**Non-URL States:**
- Filter button opens dropdown menu (no URL)
- Filter options visible (no URL)
- Applied filter changes view (no URL, same page)

### Form Filling (No URL Change)
```
Add a new todo item in TodoMVC
```
**Non-URL States:**
- Input field focused (no URL)
- Todo item appears in list (no URL)

---

## 📊 Expected Output Structure

For each test, you'll get:
```
dataset/manual_navigation/[task-name]/
├── step_00_initial.png      # Initial page state
├── step_01_click.png         # After button click
├── step_02_wait.png          # After modal/dropdown appears
├── step_03_fill.png          # After form field filled
├── step_04_click.png         # After submit clicked
├── step_0N_final.png         # Final success state
├── steps_plan.json           # JSON workflow definition
└── steps_log.md              # Human-readable report
```

---

## 🚀 Quick Start

1. **Simple test (no auth):**
```bash
python -m agent_b
# Enter: Search for playwright in npm
```

2. **Auth test (with auto-login):**
```bash
python -m agent_b
# Enter: How to create a project in Linear
```

3. **View results:**
```bash
# Check the generated screenshots
explorer dataset\manual_navigation\[task-folder]
```

---

## 💡 Tips for Best Results

1. **Use action verbs:** "Create", "Search", "Filter", "Download", "Open"
2. **Include the service name:** "in Linear", "in npm", "from python.org"
3. **Be specific:** "Create a project" is better than "Use Linear"
4. **Natural language works:** The system understands conversational prompts

---

## 📝 What to Look For

### ✅ Success Indicators:
- Correct website opens automatically
- Relevant buttons/links are clicked
- Forms are filled with appropriate values
- Each UI state change has a screenshot
- Modal/dropdown appearances are captured
- Final state shows task completion

### ❌ What to Report:
- Wrong website opened
- Irrelevant elements clicked (marketing, cookies)
- Missing intermediate states
- Form fields not filled correctly
- Too many or too few screenshots
