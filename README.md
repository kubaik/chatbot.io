# 🤖 AI Chatbot System

A white-label AI chatbot builder that mirrors your `blog_system.py` project structure.
**Python builds** the static site. **GitHub Actions** injects secrets. **GitHub Pages** hosts it.

---

## 📁 Project Structure

```
your-repo/
├── chatbot_system.py          ← Main builder (init / build / auto / verify)
├── config.yaml                ← Client config — name, colours, prompt, quick replies
├── requirements.txt           ← pyyaml
├── .gitignore
├── docs/                      ← Built output (committed by Actions bot)
│   ├── index.html
│   ├── config.json            ← Public config (no secrets)
│   └── static/
│       ├── js/chat.js         ← API logic (token baked in at build)
│       └── css/chat.css       ← Styles (colours from config.yaml)
└── .github/
    └── workflows/
        └── deploy.yml         ← Build + deploy pipeline
```

---

## ⚡ How It Works

```
config.yaml  +  GitHub Secrets
       ↓
chatbot_system.py auto
       ↓  reads first available key
docs/static/js/chat.js   ← token written in by Python (not sed)
docs/index.html
docs/static/css/chat.css
       ↓
GitHub Pages → live URL
```

No placeholder strings. No sed. Python reads `os.getenv()` and writes the token
directly into `chat.js` at build time. Source code never has a real token.

---

## 🔑 GitHub Secrets Setup

Go to **Repo → Settings → Secrets and variables → Actions → New repository secret**

Add **at least one** of these (priority order matches `config.yaml`):

| Secret Name          | Provider       | Get key at                 |
| -------------------- | -------------- | -------------------------- |
| `GITHUB_TOKEN_PAT`   | GitHub Models  | github.com/settings/tokens |
| `GROQ_API_KEY`       | Groq (Llama 3) | console.groq.com           |
| `GEMINI_API_KEY`     | Google Gemini  | aistudio.google.com        |
| `OPENROUTER_API_KEY` | OpenRouter     | openrouter.ai/keys         |
| `CEREBRAS_API_KEY`   | Cerebras       | cloud.cerebras.ai          |
| `MISTRAL_API_KEY`    | Mistral        | console.mistral.ai         |
| `NVIDIA_API_KEY`     | NVIDIA NIM     | build.nvidia.com           |

The workflow logs `OK` / `WARNING` for each — same as your blog project.

---

## 🎨 Customise Per Client

Edit `config.yaml`:

```yaml
bot:
  name: "Mario's Pizza Bot"
  icon: "🍕"
  greeting: "Ciao! 👋 What can I get you today?"
  system_prompt: >
    You are a helpful assistant for Mario's Pizza in Nairobi.
    Help customers with the menu, delivery areas, opening hours, and orders.
  quick_replies:
    - "View menu"
    - "Delivery areas"
    - "Opening hours"
    - "Place order"

theme:
  primary_color: "#c0392b"
  accent_color: "#e67e22"
```

Push → Actions rebuilds → live in ~60 seconds.

---

## 🛠️ Local Development

```bash
# Install deps
pip install -r requirements.txt

# Create config (first time)
python chatbot_system.py init

# Build (uses any keys set in your shell environment)
export GROQ_API_KEY=gsk_...
python chatbot_system.py build

# Verify output
python chatbot_system.py verify

# Open in browser
open docs/index.html
```

No key set → demo mode with canned responses (safe for UI testing).

---

## 🏗️ Commands

| Command                           | What it does                      |
| --------------------------------- | --------------------------------- |
| `python chatbot_system.py init`   | Write `config.yaml` from defaults |
| `python chatbot_system.py verify` | Log which secrets are available   |
| `python chatbot_system.py build`  | Build `docs/` from config + env   |
| `python chatbot_system.py auto`   | `init` + `build` + verify output  |

---

## 💰 Multi-Client Setup

One repo per client — each with its own secrets:

```
github.com/your-agency/
  ├── client-marios-pizza/      → marios.github.io/pizza-bot
  ├── client-dr-smith-dental/   → drsmith.github.io/dental-bot
  └── client-hair-studio/       → hairstudio.github.io/chat
```

Each repo: edit `config.yaml` + add one API key secret → push → done.

**Revenue:** $99–$399/month per client. API costs ~$0–$3/month (free tiers).
