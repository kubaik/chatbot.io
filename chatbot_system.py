#!/usr/bin/env python3
"""
chatbot_system.py — Java Restaurant AI Chatbot Builder
Mirrors blog_system.py pattern: init / build / auto / verify commands.

Usage:
    python chatbot_system.py init     # Create config.yaml from defaults
    python chatbot_system.py build    # Build static site into _site/ or docs/
    python chatbot_system.py auto     # Full pipeline: init → build → verify
    python chatbot_system.py verify   # Check secrets and config only
"""

import os
import sys
import json
import logging
import argparse
from pathlib import Path
from datetime import datetime, timezone

import yaml

# ─────────────────────────────────────────────
#  LOGGING
# ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  PATHS
# ─────────────────────────────────────────────
ROOT = Path(__file__).parent
# BUILD_OUTPUT_DIR=_site in CI avoids the gitignore/upload-pages-artifact conflict
DOCS_DIR = ROOT / os.getenv("BUILD_OUTPUT_DIR", "docs")
CONFIG_FILE = ROOT / "config.yaml"

# ─────────────────────────────────────────────
#  DEFAULT CONFIG  (written by `init` if no config.yaml)
# ─────────────────────────────────────────────
DEFAULT_CONFIG = {
    "bot": {
        "name":    "Java Restaurant",
        "icon":    "☕",
        "greeting": (
            "Welcome to Java Restaurant! ☕🍽️\n"
            "I can help with our menu, reservations, opening hours, and more.\n"
            "How can I help you today?"
        ),
        "system_prompt": (
            "You are a warm assistant for Java Restaurant in Nairobi. "
            "Help guests with the menu, reservations, opening hours, and general queries. "
            "Be concise and friendly. Quote prices in KSh. "
            "For reservations collect: date, time, party size, name, phone."
        ),
        "quick_replies": [
            "Today's specials",
            "Book a table",
            "Opening hours",
            "Coffee menu",
            "Vegetarian options",
            "Find a branch",
        ],
    },
    "theme": {
        "primary_color": "#2C1810",
        "accent_color":  "#C8860A",
    },
    "models": {
        "providers": [
            {
                "name":        "github",
                "env_key":     "GIT_TOKEN",
                "endpoint":    "https://models.github.ai/inference/chat/completions",
                "model":       "gpt-4o",
                "auth_header": "Bearer",
            },
            {
                "name":        "mistral",
                "env_key":     "MISTRAL_API_KEY",
                "endpoint":    "https://api.mistral.ai/v1/chat/completions",
                "model":       "mistral-small-latest",
                "auth_header": "Bearer",
            },
        ]
    },
    "deploy": {"output_dir": "docs"},
}

# ─────────────────────────────────────────────
#  COMMANDS
# ─────────────────────────────────────────────


def cmd_init():
    if CONFIG_FILE.exists():
        log.info("config.yaml already exists — skipping init")
        return
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False,
                  allow_unicode=True, sort_keys=False)
    log.info("✅ config.yaml created")
    log.info(
        "   Set GIT_TOKEN (primary) or MISTRAL_API_KEY (fallback) in GitHub Secrets")


def cmd_verify():
    cfg = load_config()
    providers = cfg["models"]["providers"]
    found, missing = [], []

    for p in providers:
        if os.getenv(p["env_key"], ""):
            found.append(p)
            log.info("OK      %-28s (%s)", p["env_key"], p["name"])
        else:
            missing.append(p)
            log.warning("MISSING %-28s (%s)", p["env_key"], p["name"])

    if not found:
        log.error("No API keys found — chatbot will run in demo mode")
        log.error("  GIT_TOKEN      → GitHub Models / gpt-4o   (primary)")
        log.error("  MISTRAL_API_KEY → Mistral AI / mistral-small (fallback)")
        return None

    winner = found[0]
    log.info("✅ Active provider → %s  model=%s",
             winner["name"], winner["model"])
    return winner


def cmd_build():
    cfg = load_config()
    provider = cmd_verify()

    for sub in ["", "static/js", "static/css"]:
        (DOCS_DIR / sub).mkdir(parents=True, exist_ok=True)

    # public config.json (no secrets)
    public_cfg = {
        "bot":   cfg["bot"],
        "theme": cfg["theme"],
        "provider": {
            "name":     provider["name"] if provider else "demo",
            "model":    provider["model"] if provider else "none",
            "endpoint": provider["endpoint"] if provider else "",
        },
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    (DOCS_DIR / "config.json").write_text(
        json.dumps(public_cfg, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    token = os.getenv(provider["env_key"], "") if provider else ""

    write_css(cfg)
    write_js(cfg, provider, token)
    write_html(cfg, provider)

    log.info("✅ Build complete → %s/", DOCS_DIR)
    for f in ["index.html", "static/js/chat.js", "static/css/chat.css", "config.json"]:
        log.info("   %s  ✓", f)


def cmd_auto():
    cmd_init()
    cmd_build()
    verify_output()


def verify_output():
    ok = True
    for rel in ["index.html", "static/js/chat.js", "static/css/chat.css"]:
        f = DOCS_DIR / rel
        if f.exists():
            log.info("OK    %s (%d bytes)", rel, f.stat().st_size)
        else:
            log.error("MISSING  %s", rel)
            ok = False
    if not ok:
        sys.exit(1)


def load_config() -> dict:
    if not CONFIG_FILE.exists():
        log.warning("config.yaml not found — using defaults")
        return DEFAULT_CONFIG
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)


# ─────────────────────────────────────────────
#  CSS
# ─────────────────────────────────────────────
def write_css(cfg: dict):
    p = cfg["theme"]["primary_color"]   # #2C1810 espresso
    a = cfg["theme"]["accent_color"]    # #C8860A gold

    css = f"""/* Java Restaurant Chatbot — auto-generated by chatbot_system.py */
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=Playfair+Display:wght@500;600&display=swap');

:root {{
  --primary:      {p};
  --accent:       {a};
  --accent-light: #F5E6C8;
  --surface:      #FFFFFF;
  --bg:           #FAF7F2;
  --muted:        #6B7280;
  --border:       #E8E0D5;
  --radius:       18px;
  --shadow:       0 2px 16px rgba(44,24,16,.10);
}}

*, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

body {{
  font-family: 'DM Sans', sans-serif;
  background: var(--bg);
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  color: #1f2937;
}}

/* ── HEADER ── */
header {{
  background: var(--primary);
  color: white;
  padding: 0 1.5rem;
  height: 66px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky;
  top: 0;
  z-index: 100;
  box-shadow: var(--shadow);
}}
.header-brand {{ display: flex; align-items: center; gap: 12px; }}
.header-avatar {{
  width: 40px; height: 40px;
  background: var(--accent);
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 20px;
  box-shadow: 0 0 0 3px rgba(200,134,10,.30);
}}
.header-text {{ display: flex; flex-direction: column; }}
.header-name {{
  font-family: 'Playfair Display', serif;
  font-size: 17px;
  font-weight: 600;
  letter-spacing: .01em;
  line-height: 1.2;
}}
.header-tagline {{
  font-size: 11px;
  color: rgba(255,255,255,.60);
  letter-spacing: .03em;
}}
.header-right {{ display: flex; align-items: center; gap: 10px; }}
.header-status {{ display: flex; align-items: center; gap: 5px; font-size: 12px; color: rgba(255,255,255,.65); }}
.status-dot {{ width: 7px; height: 7px; background: #22c55e; border-radius: 50%; animation: pulse 2s infinite; }}
@keyframes pulse {{ 0%,100%{{opacity:1}} 50%{{opacity:.4}} }}
.model-badge {{
  font-size: 11px;
  background: rgba(255,255,255,.12);
  border: 1px solid rgba(255,255,255,.20);
  color: rgba(255,255,255,.85);
  padding: 3px 8px;
  border-radius: 20px;
  white-space: nowrap;
}}
.settings-btn {{
  background: none; border: none;
  color: rgba(255,255,255,.70);
  cursor: pointer; padding: 6px;
  border-radius: 8px; display: flex;
  transition: background .2s;
}}
.settings-btn:hover {{ background: rgba(255,255,255,.10); }}

/* ── PROVIDER STRIP ── */
#provider-strip {{
  padding: 7px 1.5rem;
  font-size: 12px;
  display: flex; align-items: center; gap: 8px;
  border-bottom: 1px solid #bbf7d0;
  background: #f0fdf4;
  color: #166534;
}}
#provider-strip.demo {{
  background: #fffbeb;
  border-color: #fde68a;
  color: #92400e;
}}

/* ── CHAT AREA ── */
#chat-container {{
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem 1rem 1rem;
  display: flex;
  flex-direction: column;
  gap: .9rem;
  max-width: 780px;
  width: 100%;
  margin: 0 auto;
}}

.message {{ display: flex; gap: 10px; max-width: 80%; animation: fadeUp .22s ease; }}
@keyframes fadeUp {{ from{{opacity:0;transform:translateY(8px)}} to{{opacity:1;transform:translateY(0)}} }}
.message.user {{ align-self: flex-end; flex-direction: row-reverse; }}
.message.bot  {{ align-self: flex-start; }}

.msg-avatar {{
  width: 32px; height: 32px;
  border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 15px; font-weight: 600; margin-top: 2px;
}}
.message.bot  .msg-avatar {{ background: var(--primary); color: white; }}
.message.user .msg-avatar {{ background: var(--accent);  color: white; font-size: 11px; }}

.msg-bubble {{
  padding: 11px 15px;
  border-radius: var(--radius);
  font-size: 14.5px;
  line-height: 1.65;
}}
.message.bot .msg-bubble {{
  background: var(--surface);
  color: #1f2937;
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
  box-shadow: 0 1px 4px rgba(44,24,16,.06);
}}
.message.user .msg-bubble {{
  background: var(--primary);
  color: white;
  border-bottom-right-radius: 4px;
}}
.msg-time {{ font-size: 10.5px; color: var(--muted); margin-top: 4px; display: block; }}
.message.user .msg-time {{ text-align: right; }}

/* typing */
.typing-dots {{ display: flex; gap: 4px; align-items: center; padding: 14px 16px; }}
.typing-dots span {{
  width: 7px; height: 7px;
  background: var(--muted);
  border-radius: 50%;
  animation: bounce 1.2s infinite;
}}
.typing-dots span:nth-child(2) {{ animation-delay: .2s; }}
.typing-dots span:nth-child(3) {{ animation-delay: .4s; }}
@keyframes bounce {{ 0%,80%,100%{{transform:translateY(0)}} 40%{{transform:translateY(-6px)}} }}

/* quick replies */
.quick-replies {{
  display: flex; flex-wrap: wrap; gap: 8px;
  padding: 0 0 .5rem 42px;
  animation: fadeUp .3s ease;
}}
.quick-btn {{
  background: white;
  border: 1.5px solid var(--accent);
  color: var(--primary);
  padding: 6px 14px;
  border-radius: 50px;
  font-size: 13px;
  font-family: 'DM Sans', sans-serif;
  cursor: pointer;
  transition: all .18s;
  font-weight: 500;
}}
.quick-btn:hover {{ background: var(--accent); color: white; border-color: var(--accent); }}

/* ── INPUT BAR ── */
#input-bar {{
  background: white;
  border-top: 1px solid var(--border);
  padding: .85rem 1rem;
  position: sticky; bottom: 0;
}}
.input-inner {{ max-width: 780px; margin: 0 auto; display: flex; gap: 10px; align-items: center; }}
#user-input {{
  flex: 1;
  border: 1.5px solid var(--border);
  border-radius: 50px;
  padding: 10px 18px;
  font-size: 14px;
  font-family: 'DM Sans', sans-serif;
  outline: none;
  background: var(--bg);
  transition: border-color .2s;
  color: #1f2937;
}}
#user-input:focus {{ border-color: var(--accent); }}
#user-input::placeholder {{ color: var(--muted); }}

#send-btn {{
  width: 42px; height: 42px;
  border-radius: 50%;
  background: var(--accent);
  border: none; color: white;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background .2s, transform .1s;
  flex-shrink: 0;
  box-shadow: 0 2px 8px rgba(200,134,10,.35);
}}
#send-btn:hover  {{ background: #A87008; }}
#send-btn:active {{ transform: scale(.93); }}
#send-btn svg    {{ width: 18px; height: 18px; }}

/* ── CONFIG PANEL ── */
#config-panel {{
  position: fixed; top: 0; right: 0;
  width: 320px; height: 100%;
  background: white;
  border-left: 1px solid var(--border);
  padding: 1.5rem;
  overflow-y: auto;
  z-index: 200;
  transform: translateX(100%);
  transition: transform .3s ease;
  box-shadow: -4px 0 24px rgba(44,24,16,.10);
}}
#config-panel.open {{ transform: translateX(0); }}
.config-title {{
  font-family: 'Playfair Display', serif;
  font-size: 20px;
  margin-bottom: 1.5rem;
  color: var(--primary);
}}
.config-section {{ margin-bottom: 1.1rem; }}
.config-label {{
  font-size: 11.5px; font-weight: 600;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: .06em;
  margin-bottom: 5px;
  display: block;
}}
.config-input {{
  width: 100%;
  border: 1.5px solid var(--border);
  border-radius: 10px;
  padding: 9px 12px;
  font-size: 13.5px;
  font-family: 'DM Sans', sans-serif;
  outline: none;
  background: var(--bg);
  transition: border-color .2s;
  color: #1f2937;
}}
.config-input:focus {{ border-color: var(--accent); }}
textarea.config-input {{ min-height: 90px; resize: vertical; }}
.apply-btn {{
  width: 100%;
  background: var(--primary);
  color: white; border: none;
  border-radius: 10px;
  padding: 11px;
  font-size: 14px; font-weight: 600;
  font-family: 'DM Sans', sans-serif;
  cursor: pointer;
  margin-top: .5rem;
  transition: background .2s;
}}
.apply-btn:hover {{ background: var(--accent); }}
.close-config {{
  position: absolute; top: 1rem; right: 1rem;
  background: none; border: none;
  font-size: 20px; cursor: pointer;
  color: var(--muted);
}}
#overlay {{
  display: none; position: fixed; inset: 0;
  background: rgba(0,0,0,.25); z-index: 150;
}}
#overlay.open {{ display: block; }}
.info-note {{ font-size: 11.5px; color: var(--muted); margin-top: 5px; line-height: 1.5; }}
code {{ font-size: 11px; background: #f3f4f6; padding: 1px 5px; border-radius: 4px; }}

/* ── SUGGESTED ITEMS CARD ── */
.menu-card {{
  background: var(--accent-light);
  border: 1px solid #E8C878;
  border-radius: 12px;
  padding: 10px 14px;
  margin-top: 6px;
  font-size: 13px;
}}
.menu-card-title {{ font-weight: 600; color: var(--primary); margin-bottom: 6px; font-size: 13.5px; }}
.menu-item {{ display: flex; justify-content: space-between; padding: 3px 0; border-bottom: 1px solid rgba(200,134,10,.20); }}
.menu-item:last-child {{ border-bottom: none; padding-bottom: 0; }}
.menu-item-name {{ color: #2C1810; }}
.menu-item-price {{ color: var(--accent); font-weight: 600; font-size: 12.5px; }}
"""
    (DOCS_DIR / "static" / "css" / "chat.css").write_text(css, encoding="utf-8")


# ─────────────────────────────────────────────
#  JS
# ─────────────────────────────────────────────
def write_js(cfg: dict, provider: dict | None, token: str):
    bot = cfg["bot"]
    quick_json = json.dumps(bot["quick_replies"], ensure_ascii=False)
    system = bot["system_prompt"].replace(
        "\\", "\\\\").replace("`", "\\`").replace("\n", "\\n")
    greeting = bot["greeting"].replace("\\", "\\\\").replace(
        "`", "\\`").replace("\n", "\\n")
    bot_name = bot["name"].replace("`", "\\`")
    bot_icon = bot["icon"]
    endpoint = provider["endpoint"] if provider else ""
    model_id = provider["model"] if provider else "demo"
    provider_name = provider["name"] if provider else "demo"
    auth_header = provider["auth_header"] if provider else "Bearer"
    safe_token = token.replace("\\", "\\\\").replace(
        "`", "\\`") if token else ""
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Demo fallback responses — realistic for a restaurant
    js = f"""/* Java Restaurant Chatbot — auto-generated by chatbot_system.py */
/* Provider: {provider_name} | Model: {model_id} | Built: {built} */

const CHATBOT_TOKEN    = `{safe_token}`;
const CHATBOT_ENDPOINT = `{endpoint}`;
const CHATBOT_MODEL    = `{model_id}`;
const CHATBOT_PROVIDER = `{provider_name}`;
const CHATBOT_AUTH_HDR = `{auth_header}`;

let CFG = {{
  name:         `{bot_name}`,
  icon:         `{bot_icon}`,
  system:       `{system}`,
  greeting:     `{greeting}`,
  quickReplies:  {quick_json},
}};

try {{
  const saved = localStorage.getItem("java_chatbot_cfg");
  if (saved) CFG = {{ ...CFG, ...JSON.parse(saved) }};
}} catch(e) {{}}

let history = [];
let busy    = false;

/* ── INIT ── */
document.addEventListener("DOMContentLoaded", () => {{
  applyMeta();
  renderProviderStrip();
  showGreeting();
  syncConfigPanel();
  document.getElementById("user-input")
    .addEventListener("keydown", e => {{
      if (e.key === "Enter" && !e.shiftKey) {{ e.preventDefault(); send(); }}
    }});
}});

function applyMeta() {{
  document.getElementById("header-title").textContent = CFG.name;
  document.getElementById("header-icon").textContent  = CFG.icon;
  document.getElementById("model-badge").textContent  = CHATBOT_MODEL;
  document.title = CFG.name;
}}

function renderProviderStrip() {{
  const s = document.getElementById("provider-strip");
  if (!s) return;
  if (!CHATBOT_TOKEN || CHATBOT_PROVIDER === "demo") {{
    s.className   = "demo";
    s.textContent = "⚠️ Demo mode — set GIT_TOKEN or MISTRAL_API_KEY in GitHub Secrets to enable live AI.";
  }} else {{
    s.className   = "";
    const label   = CHATBOT_PROVIDER === "github" ? "GitHub Models" : "Mistral AI";
    s.innerHTML   = `✅ Live AI &nbsp;·&nbsp; <strong>${{label}}</strong> &nbsp;·&nbsp; ${{CHATBOT_MODEL}}`;
  }}
}}

/* ── GREETING ── */
function showGreeting() {{
  addMsg("bot", CFG.greeting);
  setTimeout(renderQuickReplies, 500);
}}

/* ── MESSAGE RENDERING ── */
function addMsg(role, text) {{
  const c = document.getElementById("chat-container");
  const w = document.createElement("div");
  w.className = "message " + role;
  const t = new Date().toLocaleTimeString([], {{hour:"2-digit", minute:"2-digit"}});
  const avatar = role === "bot" ? CFG.icon : "You";
  const bubbleHTML = formatBotText(text);
  w.innerHTML = `
    <div class="msg-avatar">${{avatar}}</div>
    <div>
      <div class="msg-bubble">${{bubbleHTML}}</div>
      <span class="msg-time">${{t}}</span>
    </div>`;
  c.appendChild(w);
  c.scrollTop = c.scrollHeight;
}}

/* Format bot text — convert newlines and basic markdown bold */
function formatBotText(text) {{
  return esc(text)
    .replace(/\\n/g, "<br>")
    .replace(/\\*\\*(.+?)\\*\\*/g, "<strong>$1</strong>");
}}

function showTyping() {{
  const c  = document.getElementById("chat-container");
  const el = document.createElement("div");
  el.id = "typing"; el.className = "message bot";
  el.innerHTML = `<div class="msg-avatar">${{CFG.icon}}</div>
    <div class="msg-bubble typing-dots"><span></span><span></span><span></span></div>`;
  c.appendChild(el);
  c.scrollTop = c.scrollHeight;
}}

function removeTyping() {{ document.getElementById("typing")?.remove(); }}

function renderQuickReplies() {{
  const c  = document.getElementById("chat-container");
  const el = document.createElement("div");
  el.className = "quick-replies"; el.id = "qr";
  CFG.quickReplies.forEach(r => {{
    const btn = document.createElement("button");
    btn.className = "quick-btn";
    btn.textContent = r;
    btn.onclick = () => {{ el.remove(); send(r); }};
    el.appendChild(btn);
  }});
  c.appendChild(el);
  c.scrollTop = c.scrollHeight;
}}

/* ── SEND ── */
async function send(override) {{
  if (busy) return;
  const inp  = document.getElementById("user-input");
  const text = (override || inp.value).trim();
  if (!text) return;
  document.getElementById("qr")?.remove();
  inp.value = "";
  addMsg("user", text);
  history.push({{ role: "user", content: text }});
  busy = true;
  showTyping();

  try {{
    const reply = await callAI();
    removeTyping();
    addMsg("bot", reply);
    history.push({{ role: "assistant", content: reply }});
  }} catch(err) {{
    removeTyping();
    addMsg("bot", "⚠️ " + (err.message || "Connection error — please try again."));
    console.error("[Java Chatbot]", err);
  }}
  busy = false;
}}

/* ── API CALL ────────────────────────────────────────────────────────────
   Both GitHub Models and Mistral use the OpenAI-compatible
   /chat/completions schema — single fetch path handles both.
   Endpoint, model, and token are baked in at build time by Python.
   ─────────────────────────────────────────────────────────────────────── */
async function callAI() {{
  if (!CHATBOT_TOKEN || CHATBOT_PROVIDER === "demo") {{
    await sleep(600);
    return demoReply(history[history.length - 1]?.content || "");
  }}

  const res = await fetch(CHATBOT_ENDPOINT, {{
    method: "POST",
    headers: {{
      "Content-Type":  "application/json",
      "Authorization": `${{CHATBOT_AUTH_HDR}} ${{CHATBOT_TOKEN}}`
    }},
    body: JSON.stringify({{
      model:       CHATBOT_MODEL,
      messages: [
        {{ role: "system", content: CFG.system }},
        ...history
      ],
      max_tokens:  600,
      temperature: 0.5
    }})
  }});

  if (!res.ok) {{
    const err = await res.json().catch(() => ({{}}));
    throw new Error(err.error?.message || `HTTP ${{res.status}} from ${{CHATBOT_PROVIDER}}`);
  }}

  const data = await res.json();
  return data.choices?.[0]?.message?.content?.trim()
    || "Sorry, I didn't get a response. Please try again.";
}}

/* ── DEMO REPLIES ── */
function demoReply(text) {{
  const t = text.toLowerCase();
  if (t.includes("special") || t.includes("today"))
    return "Today's specials:\\n\\n**Breakfast special:** Acai Bowl with granola — KSh 850\\n**Lunch special:** Grilled Tilapia with coconut rice — KSh 1,400\\n**Coffee of the day:** Java Signature Cold Brew — KSh 450\\n\\nWould you like to make a reservation? 😊";
  if (t.includes("book") || t.includes("reserv") || t.includes("table"))
    return "I'd love to help you reserve a table! 🍽️\\n\\nPlease share:\\n• Date & time\\n• Number of guests\\n• Your name & phone number\\n\\nOr call us directly: **+254 700 000 000**";
  if (t.includes("hour") || t.includes("open") || t.includes("close"))
    return "Our opening hours:\\n\\n☕ **Mon–Fri:** 7:00 AM – 10:00 PM\\n☕ **Saturday:** 7:30 AM – 10:30 PM\\n☕ **Sunday:** 8:00 AM – 9:00 PM\\n\\nAll Nairobi branches follow the same schedule.";
  if (t.includes("coffee") || t.includes("cappucc") || t.includes("espresso") || t.includes("latte"))
    return "Our coffee menu:\\n\\n• Espresso — KSh 250\\n• Cappuccino — KSh 350\\n• Flat White — KSh 380\\n• Java Signature Cold Brew — KSh 450\\n• Dawa (lemon, ginger, honey) — KSh 320\\n\\n☕ Happy Hour: 3–5 PM weekdays — 20% off all coffee drinks!";
  if (t.includes("veg") || t.includes("vegan") || t.includes("plant"))
    return "Our vegetarian & vegan options:\\n\\n🥗 **Acai Bowl** — KSh 850 (vegan)\\n🥗 **Veggie Buddha Bowl** — KSh 900 (vegan)\\n🥑 **Avocado Toast** with poached eggs — KSh 750 (vegetarian)\\n🍝 **Pasta of the Day** — KSh 950 (ask for veggie version)\\n\\nGluten-free bread available on request (+KSh 100).";
  if (t.includes("branch") || t.includes("location") || t.includes("where") || t.includes("find"))
    return "Java Restaurant has multiple branches across Nairobi:\\n\\n📍 **Westlands** (flagship) — free parking\\n📍 **Sarit Centre** — free parking\\n📍 **Village Market**\\n📍 **Two Rivers Mall**\\n📍 **Karen**\\n\\nFor the nearest branch, visit our website or call **+254 700 000 000**.";
  if (t.includes("wifi") || t.includes("wi-fi") || t.includes("internet"))
    return "Yes! Free WiFi is available at all Java Restaurant branches. 📶\\nAsk your server for the password when you arrive.";
  if (t.includes("park"))
    return "🅿️ Free parking is available at our **Westlands** and **Sarit Centre** branches.\\nOther branches have paid mall parking nearby.";
  if (t.includes("price") || t.includes("menu") || t.includes("cost") || t.includes("ksh"))
    return "Here are some menu highlights:\\n\\n**Breakfast** (served all day):\\n• Full English Breakfast — KSh 950\\n• Java Pancakes — KSh 650\\n\\n**Mains:**\\n• Nyama Choma Platter — KSh 1,800\\n• Java Burger — KSh 1,100\\n\\n**Desserts:**\\n• Chocolate Lava Cake — KSh 650\\n\\nWould you like the full menu or info on a specific dish?";
  return "Thanks for reaching out to Java Restaurant! ☕\\n\\nI'm in demo mode right now, so my answers are limited. For full AI responses, the GIT_TOKEN secret needs to be configured in GitHub.\\n\\nIn the meantime, try asking about: **opening hours, coffee menu, vegetarian options, reservations, or our branches**.";
}}

/* ── SETTINGS PANEL ── */
function toggleConfig() {{
  document.getElementById("config-panel").classList.toggle("open");
  document.getElementById("overlay").classList.toggle("open");
}}

function syncConfigPanel() {{
  document.getElementById("cfg-name").value    = CFG.name;
  document.getElementById("cfg-icon").value    = CFG.icon;
  document.getElementById("cfg-system").value  = CFG.system;
  document.getElementById("cfg-greeting").value= CFG.greeting;
  document.getElementById("cfg-qr").value      = CFG.quickReplies.join(", ");
}}

function applyConfig() {{
  CFG.name         = document.getElementById("cfg-name").value.trim()    || CFG.name;
  CFG.icon         = document.getElementById("cfg-icon").value.trim()    || CFG.icon;
  CFG.system       = document.getElementById("cfg-system").value.trim();
  CFG.greeting     = document.getElementById("cfg-greeting").value.trim();
  CFG.quickReplies = document.getElementById("cfg-qr").value
    .split(",").map(s => s.trim()).filter(Boolean);
  try {{ localStorage.setItem("java_chatbot_cfg", JSON.stringify(CFG)); }} catch(e) {{}}
  applyMeta();
  resetChat();
  toggleConfig();
}}

function resetChat() {{
  history = [];
  document.getElementById("chat-container").innerHTML = "";
  showGreeting();
}}

/* ── UTILS ── */
function esc(t) {{
  return t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}}
function sleep(ms) {{ return new Promise(r => setTimeout(r, ms)); }}
"""
    (DOCS_DIR / "static" / "js" / "chat.js").write_text(js, encoding="utf-8")


# ─────────────────────────────────────────────
#  HTML
# ─────────────────────────────────────────────
def write_html(cfg: dict, provider: dict | None):
    bot = cfg["bot"]
    name = bot["name"]
    icon = bot["icon"]
    model = provider["model"] if provider else "demo"
    provider_name = provider["name"] if provider else "demo"
    tagline = "Nairobi's favourite café-restaurant"
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="description" content="{name} — AI-powered chat assistant for reservations, menu queries, and more.">
  <title>{name}</title>
  <!-- Fonts preloaded for performance -->
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=Playfair+Display:wght@500;600&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="static/css/chat.css">
</head>
<body>

  <!-- Provider / token status strip — populated by chat.js -->
  <div id="provider-strip">Loading…</div>

  <!-- Header -->
  <header>
    <div class="header-brand">
      <div class="header-avatar" id="header-icon">{icon}</div>
      <div class="header-text">
        <span class="header-name" id="header-title">{name}</span>
        <span class="header-tagline">{tagline}</span>
      </div>
    </div>
    <div class="header-right">
      <span class="model-badge" id="model-badge" title="Active AI model">{model}</span>
      <div class="header-status">
        <div class="status-dot"></div>
        Online
      </div>
      <button class="settings-btn" onclick="toggleConfig()" title="Customise bot" aria-label="Settings">
        <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M12 15a3 3 0 100-6 3 3 0 000 6z"/>
          <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83
                   2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33
                   1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09
                   A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06
                   a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15
                   a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09
                   A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06
                   a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68
                   a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09
                   a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06
                   a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9
                   a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09
                   a1.65 1.65 0 00-1.51 1z"/>
        </svg>
      </button>
    </div>
  </header>

  <!-- Chat messages -->
  <div id="chat-container" role="log" aria-live="polite" aria-label="Chat messages"></div>

  <!-- Input bar -->
  <div id="input-bar">
    <div class="input-inner">
      <input
        type="text"
        id="user-input"
        placeholder="Ask about our menu, hours, reservations…"
        autocomplete="off"
        aria-label="Type your message"
        maxlength="500"
      >
      <button id="send-btn" onclick="send()" aria-label="Send message">
        <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true">
          <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z"/>
        </svg>
      </button>
    </div>
  </div>

  <!-- Settings / config panel -->
  <div id="overlay" onclick="toggleConfig()" aria-hidden="true"></div>
  <div id="config-panel" role="dialog" aria-label="Customise chatbot">
    <button class="close-config" onclick="toggleConfig()" aria-label="Close settings">✕</button>
    <div class="config-title">Customise Bot</div>

    <div class="config-section">
      <label class="config-label" for="cfg-name">Restaurant Name</label>
      <input class="config-input" id="cfg-name" placeholder="Java Restaurant">
    </div>
    <div class="config-section">
      <label class="config-label" for="cfg-icon">Icon / Emoji</label>
      <input class="config-input" id="cfg-icon" placeholder="☕">
    </div>
    <div class="config-section">
      <label class="config-label" for="cfg-system">System Prompt</label>
      <textarea class="config-input" id="cfg-system" rows="5"></textarea>
    </div>
    <div class="config-section">
      <label class="config-label" for="cfg-greeting">Greeting Message</label>
      <input class="config-input" id="cfg-greeting">
    </div>
    <div class="config-section">
      <label class="config-label" for="cfg-qr">Quick Replies (comma-separated)</label>
      <input class="config-input" id="cfg-qr">
    </div>
    <div class="config-section">
      <label class="config-label">Active Provider</label>
      <p class="info-note">
        Set at <strong>build time</strong> via GitHub Secrets.<br>
        Active: <code>{provider_name}</code> → <code>{model}</code><br>
        Priority: <code>GIT_TOKEN</code> → <code>MISTRAL_API_KEY</code>
      </p>
    </div>
    <button class="apply-btn" onclick="applyConfig()">✓ Apply Changes</button>
  </div>

  <!-- Built info (hidden, useful for debugging) -->
  <!-- Built: {built} | Provider: {provider_name} | Model: {model} -->

  <script src="static/js/chat.js"></script>
</body>
</html>
"""
    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Java Restaurant Chatbot Builder")
    parser.add_argument(
        "command",
        choices=["init", "build", "auto", "verify"],
        help="Command to run"
    )
    args = parser.parse_args()
    {"init": cmd_init, "build": cmd_build, "auto": cmd_auto,
        "verify": cmd_verify}[args.command]()
