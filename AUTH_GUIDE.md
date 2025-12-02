# Real Authentication Guide

There are **3 ways** to handle real authentication with Agent B:

## Option 1: Use Your Chrome Session (Easiest) ⭐

**Best for:** Quick demos, already logged into sites

```powershell
# Close Chrome completely first!
python -m agent_b --use-session --task "Create a project in Linear"
```

**How it works:**
- Uses your actual Chrome profile with all your existing logins
- No need to enter credentials - already authenticated!
- **Important:** Chrome must be closed for this to work

**Pros:**
- Zero setup - uses your existing logins
- Works with 2FA, SSO, OAuth
- Most realistic workflow capture

**Cons:**
- Requires Chrome to be closed
- Can't run headless
- Uses your real data/accounts

---

## Option 2: Save & Reuse Cookies (Recommended) ⭐⭐

**Best for:** Repeated testing, CI/CD, sharing sessions

### Step 1: Save cookies once
```powershell
python save_cookies.py
```

Follow prompts:
1. Enter sites: `linear,notion,github`
2. Browser opens - log in to each site
3. Press Enter after logging in
4. Cookies saved to `cookies/linear.json`, etc.

### Step 2: Use saved cookies
```powershell
python -m agent_b --cookies cookies/linear.json --task "Create a project in Linear"
python -m agent_b --cookies cookies/notion.json --task "Filter database in Notion"
```

**Pros:**
- Reusable sessions
- Works headless
- Can share cookie files (be careful!)
- Bypasses 2FA after initial login

**Cons:**
- Cookies expire (usually 30-90 days)
- Need to re-save when expired

---

## Option 3: Environment Variables (Automated)

**Best for:** Public sites with simple auth, automation

### Setup credentials in `.env`:

```env
# Universal credentials (fallback for any site)
DEFAULT_EMAIL=your@email.com
DEFAULT_PASSWORD=YourPassword123!

# Per-domain credentials
LINEAR_APP_EMAIL=work@company.com
LINEAR_APP_PASSWORD=SecurePass456!

GITHUB_COM_EMAIL=github@email.com
GITHUB_COM_PASSWORD=GitPass789!

# Or use JSON file
CREDENTIALS_JSON=credentials.json
```

### Create `credentials.json`:
```json
{
  "linear.app": {
    "email": "work@company.com",
    "password": "SecurePass456!"
  },
  "github.com": {
    "email": "github@email.com",
    "password": "GitPass789!"
  },
  "notion.so": {
    "email": "notion@email.com",
    "password": "NotionPass!"
  }
}
```

### Run normally:
```powershell
python -m agent_b --task "Create a project in Linear"
```

**Pros:**
- Fully automated
- Works headless
- Good for CI/CD

**Cons:**
- Storing passwords in files (security risk)
- Doesn't work with 2FA/SSO
- Some sites block automated logins

---

## Quick Comparison

| Method | Ease | Security | 2FA/SSO | Headless | Reusable |
|--------|------|----------|---------|----------|----------|
| **Chrome Session** | ⭐⭐⭐ | ✅ Safe | ✅ Yes | ❌ No | ❌ No |
| **Saved Cookies** | ⭐⭐ | ⚠️ Medium | ✅ Yes | ✅ Yes | ✅ Yes |
| **Credentials** | ⭐ | ❌ Risky | ❌ No | ✅ Yes | ✅ Yes |

---

## Recommended Workflow

### For Live Demos:
```powershell
# Close Chrome, then:
python -m agent_b --use-session --task "your task here"
```

### For Testing/Development:
```powershell
# Save cookies once:
python save_cookies.py

# Then reuse:
python -m agent_b --cookies cookies/linear.json --task "Create project"
```

### For Automation/CI:
```powershell
# Setup .env with credentials, then:
python -m agent_b --headless --task "automated task"
```

---

## Troubleshooting

**"Could not use Chrome session"**
- Make sure Chrome is completely closed (check Task Manager)
- Try closing Chrome and running again

**"Cookies didn't work"**
- Cookies may have expired - re-save them
- Make sure you saved cookies for the correct site

**"Login failed"**
- Check credentials in `.env` are correct
- Site may require 2FA - use cookies method instead

---

## Examples

### Linear with Chrome session:
```powershell
python -m agent_b --use-session --task "How to create a project in Linear"
```

### Notion with saved cookies:
```powershell
python save_cookies.py  # Save once
python -m agent_b --cookies cookies/notion.json --task "Filter a database in Notion"
```

### GitHub with credentials:
```powershell
# In .env: GITHUB_COM_EMAIL and GITHUB_COM_PASSWORD
python -m agent_b --task "Create a repository in GitHub"
```

---

## Security Notes

⚠️ **Cookie files contain authentication tokens** - treat them like passwords:
- Don't commit to git (add `cookies/` to `.gitignore`)
- Don't share cookie files publicly
- Regenerate if compromised

⚠️ **Credential files** - never commit:
- Add `.env` to `.gitignore`
- Use environment variables in production
- Consider using secret managers (AWS Secrets, Azure Key Vault)

✅ **Chrome session method is safest** - no credentials stored, uses existing auth.
