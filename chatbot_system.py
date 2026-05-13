#!/usr/bin/env python3
"""
chatbot_system.py — White-label AI Chatbot Builder
Mirrors the blog_system.py pattern: init / build / auto commands.

Usage:
    python chatbot_system.py init       # Create config.yaml from defaults
    python chatbot_system.py build      # Build static site into docs/
    python chatbot_system.py auto       # Full pipeline: validate → build → deploy-ready
    python chatbot_system.py verify     # Check secrets and config only

Providers (priority order):
    1. Mistral  — set MISTRAL_API_KEY
    2. GitHub   — set GIT_TOKEN
"""

import os
import sys
import json
import shutil
import logging
import argparse
import re
from pathlib import Path
from datetime import datetime, timezone

import yaml  # pip install pyyaml

# ─────────────────────────────────────────────
#  LOGGING  (same style as blog_system.py)
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
# BUILD_OUTPUT_DIR env var lets the workflow redirect output to _site/
# (which is not gitignored) so upload-pages-artifact doesn't hit the
# .gitignore block that protects docs/ from accidental token commits.
DOCS_DIR = ROOT / os.getenv("BUILD_OUTPUT_DIR", "docs")
STATIC_DIR = ROOT / "static"
CONFIG_FILE = ROOT / "config.yaml"
SECRETS_FILE = ROOT / ".secrets_cache.json"   # never committed (in .gitignore)

# ─────────────────────────────────────────────
#  DEFAULT CONFIG  (written by `init`)
# ─────────────────────────────────────────────
DEFAULT_CONFIG = {
    "bot": {
        "name":          "LocalBiz Assistant",
        "icon":          "🤖",
        "greeting":      "Hi! 👋 How can I help you today?",
        "system_prompt": (
            "You are a friendly assistant for LocalBiz. "
            "Help customers with opening hours, services, pricing, and bookings. "
            "Be concise and warm. If unsure, ask the customer to call us directly."
        ),
        "quick_replies": [
            "Opening hours",
            "Book appointment",
            "Pricing",
            "Location",
        ],
    },
    "theme": {
        "primary_color": "#1a1a2e",
        "accent_color":  "#e94560",
    },
    "models": {
        # Priority order — first available key wins.
        # Only Mistral and GitHub Models are supported.
        "providers": [
            {
                "name":        "mistral",
                "env_key":     "MISTRAL_API_KEY",
                "endpoint":    "https://api.mistral.ai/v1/chat/completions",
                "model":       "mistral-small-latest",
                "auth_header": "Bearer",
            },
            {
                "name":        "github",
                "env_key":     "GIT_TOKEN",
                "endpoint":    "https://models.github.ai/inference/chat/completions",
                "model":       "mistral-ai/Mistral-small",   # GitHub Models – Mistral-hosted
                "auth_header": "Bearer",
            },
        ]
    },
    "deploy": {
        "output_dir": "docs",
    },
}

# ─────────────────────────────────────────────
#  COMMAND: init
# ─────────────────────────────────────────────


def cmd_init():
    """Write default config.yaml if it doesn't exist."""
    if CONFIG_FILE.exists():
        log.info("config.yaml already exists — skipping init")
        return
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False,
                  allow_unicode=True, sort_keys=False)
    log.info("✅ config.yaml created — edit to customise your chatbot")
    log.info(
        "   Set MISTRAL_API_KEY or GIT_TOKEN in your environment / GitHub Secrets")


# ─────────────────────────────────────────────
#  COMMAND: verify
# ─────────────────────────────────────────────
def cmd_verify():
    """
    Check which API keys are available from environment.
    Mirrors the 'Verify secrets' step in the workflow YAML.
    Returns the first available provider config dict, or None.
    """
    cfg = load_config()
    providers = cfg["models"]["providers"]

    found = []
    missing = []
    for p in providers:
        val = os.getenv(p["env_key"], "")
        if val:
            found.append(p)
            log.info("OK : %-30s (%s)", p["env_key"], p["name"])
        else:
            missing.append(p)
            log.warning("MISSING: %-30s (%s)", p["env_key"], p["name"])

    if not found:
        log.error("No API keys found — chatbot will run in demo mode")
        log.error("  Set MISTRAL_API_KEY  for Mistral AI (primary)")
        log.error(
            "  Set GIT_TOKEN        for GitHub Models / Mistral-small (fallback)")
        return None

    winner = found[0]
    log.info("✅ Active provider → %s  model=%s",
             winner["name"], winner["model"])
    return winner


# ─────────────────────────────────────────────
#  COMMAND: build
# ─────────────────────────────────────────────
def cmd_build():
    """
    Build the static chatbot site into docs/.
    Reads config.yaml + resolves active provider → writes:
      docs/index.html          (chatbot UI)
      docs/static/js/chat.js   (API call logic, token injected)
      docs/static/css/chat.css (styles)
      docs/config.json         (public non-secret config for JS)
    """
    cfg = load_config()
    provider = cmd_verify()   # logs key status, returns winner or None

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "static" / "js").mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / "static" / "css").mkdir(parents=True, exist_ok=True)

    # ── public config (no secrets) ──────────────────────────────
    public_cfg = {
        "bot":   cfg["bot"],
        "theme": cfg["theme"],
        # which provider is active (name + model only, no key)
        "provider": {
            "name":     provider["name"] if provider else "demo",
            "model":    provider["model"] if provider else "none",
            "endpoint": provider["endpoint"] if provider else "",
        } if provider else {"name": "demo", "model": "none", "endpoint": ""},
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(DOCS_DIR / "config.json", "w") as f:
        json.dump(public_cfg, f, indent=2, ensure_ascii=False)

    # ── resolve token (injected into chat.js) ───────────────────
    token = ""
    if provider:
        token = os.getenv(provider["env_key"], "")

    # ── write files ─────────────────────────────────────────────
    write_css(cfg)
    write_js(cfg, provider, token)
    write_html(cfg, provider)

    log.info("✅ Build complete → %s/", DOCS_DIR)
    log.info("   index.html  ✓")
    log.info("   static/js/chat.js  ✓")
    log.info("   static/css/chat.css  ✓")
    log.info("   config.json  ✓")


# ─────────────────────────────────────────────
#  COMMAND: auto
# ─────────────────────────────────────────────
def cmd_auto():
    """Full pipeline: init if needed → verify → build."""
    cmd_init()
    cmd_build()
    verify_output()


# ─────────────────────────────────────────────
#  OUTPUT VERIFICATION  (mirrors 'Verify generated content' step)
# ─────────────────────────────────────────────
def verify_output():
    index = DOCS_DIR / "index.html"
    js = DOCS_DIR / "static" / "js" / "chat.js"
    css = DOCS_DIR / "static" / "css" / "chat.css"

    ok = True
    for f in [index, js, css]:
        if f.exists():
            log.info("OK  %s (%d bytes)", f.relative_to(
                ROOT), f.stat().st_size)
        else:
            log.error("MISSING  %s", f.relative_to(ROOT))
            ok = False

    if not ok:
        sys.exit(1)


# ─────────────────────────────────────────────
#  FILE WRITERS
# ─────────────────────────────────────────────
def load_config() -> dict:
    if not CONFIG_FILE.exists():
        log.warning("config.yaml not found — using defaults")
        return DEFAULT_CONFIG
    with open(CONFIG_FILE) as f:
        return yaml.safe_load(f)


def write_css(cfg: dict):
    p = cfg["theme"]["primary_color"]
    a = cfg["theme"]["accent_color"]
    css = f"""/* Auto-generated by chatbot_system.py — do not edit directly */
:root {{
  --brand-primary: {p};
  --brand-accent:  {a};
  --brand-light:   #f8f4f0;
  --brand-surface: #ffffff;
  --brand-muted:   #6b7280;
  --brand-border:  #e5e7eb;
  --chat-radius:   18px;
}}

*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'DM Sans',sans-serif;background:var(--brand-light);min-height:100vh;display:flex;flex-direction:column}}

header{{background:var(--brand-primary);color:white;padding:0 1.5rem;height:62px;display:flex;align-items:center;justify-content:space-between;position:sticky;top:0;z-index:100;box-shadow:0 2px 12px rgba(0,0,0,.15)}}
.header-brand{{display:flex;align-items:center;gap:10px}}
.header-avatar{{width:36px;height:36px;background:var(--brand-accent);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:18px}}
.header-name{{font-family:'Playfair Display',serif;font-size:17px;letter-spacing:.01em}}
.header-right{{display:flex;align-items:center;gap:12px}}
.header-status{{display:flex;align-items:center;gap:6px;font-size:12px;color:rgba(255,255,255,.65)}}
.status-dot{{width:7px;height:7px;background:#22c55e;border-radius:50%;animation:pulse 2s infinite}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.4}}}}
.model-badge{{font-size:11px;background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.2);color:rgba(255,255,255,.85);padding:3px 8px;border-radius:20px;cursor:pointer;transition:background .2s}}
.model-badge:hover{{background:rgba(255,255,255,.22)}}
.settings-btn{{background:none;border:none;color:rgba(255,255,255,.7);cursor:pointer;padding:6px;border-radius:8px;display:flex;transition:background .2s}}
.settings-btn:hover{{background:rgba(255,255,255,.1)}}

#chat-container{{flex:1;overflow-y:auto;padding:1.5rem 1rem;display:flex;flex-direction:column;gap:1rem;max-width:760px;width:100%;margin:0 auto}}
.message{{display:flex;gap:10px;max-width:78%;animation:fadeUp .25s ease}}
@keyframes fadeUp{{from{{opacity:0;transform:translateY(10px)}}to{{opacity:1;transform:translateY(0)}}}}
.message.user{{align-self:flex-end;flex-direction:row-reverse}}
.message.bot{{align-self:flex-start}}
.msg-avatar{{width:32px;height:32px;border-radius:50%;flex-shrink:0;display:flex;align-items:center;justify-content:center;font-size:15px;font-weight:600;margin-top:2px}}
.message.bot .msg-avatar{{background:var(--brand-primary);color:white}}
.message.user .msg-avatar{{background:var(--brand-accent);color:white}}
.msg-bubble{{padding:11px 15px;border-radius:var(--chat-radius);font-size:14.5px;line-height:1.65}}
.message.bot .msg-bubble{{background:var(--brand-surface);color:#1f2937;border:1px solid var(--brand-border);border-bottom-left-radius:4px}}
.message.user .msg-bubble{{background:var(--brand-primary);color:white;border-bottom-right-radius:4px}}
.msg-time{{font-size:10.5px;color:var(--brand-muted);margin-top:4px;display:block}}
.message.user .msg-time{{text-align:right}}

.typing-dots{{display:flex;gap:4px;align-items:center;padding:14px 16px}}
.typing-dots span{{width:7px;height:7px;background:var(--brand-muted);border-radius:50%;animation:bounce 1.2s infinite}}
.typing-dots span:nth-child(2){{animation-delay:.2s}}
.typing-dots span:nth-child(3){{animation-delay:.4s}}
@keyframes bounce{{0%,80%,100%{{transform:translateY(0)}}40%{{transform:translateY(-6px)}}}}

.quick-replies{{display:flex;flex-wrap:wrap;gap:8px;padding:0 0 .25rem 42px;animation:fadeUp .3s ease}}
.quick-btn{{background:white;border:1.5px solid var(--brand-primary);color:var(--brand-primary);padding:6px 14px;border-radius:50px;font-size:13px;font-family:'DM Sans',sans-serif;cursor:pointer;transition:all .18s;font-weight:500}}
.quick-btn:hover{{background:var(--brand-primary);color:white}}

#input-bar{{background:white;border-top:1px solid var(--brand-border);padding:.9rem 1rem;position:sticky;bottom:0}}
.input-inner{{max-width:760px;margin:0 auto;display:flex;gap:10px;align-items:center}}
#user-input{{flex:1;border:1.5px solid var(--brand-border);border-radius:50px;padding:10px 18px;font-size:14px;font-family:'DM Sans',sans-serif;outline:none;background:var(--brand-light);transition:border-color .2s}}
#user-input:focus{{border-color:var(--brand-primary)}}
#send-btn{{width:42px;height:42px;border-radius:50%;background:var(--brand-primary);border:none;color:white;cursor:pointer;display:flex;align-items:center;justify-content:center;transition:background .2s,transform .1s;flex-shrink:0}}
#send-btn:hover{{background:var(--brand-accent)}}
#send-btn:active{{transform:scale(.93)}}
#send-btn svg{{width:18px;height:18px}}

/* provider badge strip */
#provider-strip{{background:#f0fdf4;border-bottom:1px solid #bbf7d0;padding:6px 1.5rem;font-size:12px;color:#166534;display:flex;align-items:center;gap:8px}}
#provider-strip.demo{{background:#fffbeb;border-color:#fde68a;color:#92400e}}

/* config panel */
#config-panel{{position:fixed;top:0;right:0;width:320px;height:100%;background:white;border-left:1px solid var(--brand-border);padding:1.5rem;overflow-y:auto;z-index:200;transform:translateX(100%);transition:transform .3s ease;box-shadow:-4px 0 24px rgba(0,0,0,.08)}}
#config-panel.open{{transform:translateX(0)}}
.config-title{{font-family:'Playfair Display',serif;font-size:20px;margin-bottom:1.5rem;color:var(--brand-primary)}}
.config-section{{margin-bottom:1.2rem}}
.config-label{{font-size:12px;font-weight:600;color:var(--brand-muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px;display:block}}
.config-input{{width:100%;border:1.5px solid var(--brand-border);border-radius:10px;padding:9px 12px;font-size:13.5px;font-family:'DM Sans',sans-serif;outline:none;background:var(--brand-light);transition:border-color .2s}}
.config-input:focus{{border-color:var(--brand-primary)}}
textarea.config-input{{min-height:80px;resize:vertical}}
.apply-btn{{width:100%;background:var(--brand-primary);color:white;border:none;border-radius:10px;padding:11px;font-size:14px;font-weight:600;font-family:'DM Sans',sans-serif;cursor:pointer;margin-top:.5rem;transition:background .2s}}
.apply-btn:hover{{background:var(--brand-accent)}}
.close-config{{position:absolute;top:1rem;right:1rem;background:none;border:none;font-size:20px;cursor:pointer;color:var(--brand-muted)}}
#overlay{{display:none;position:fixed;inset:0;background:rgba(0,0,0,.25);z-index:150}}
#overlay.open{{display:block}}
.info-note{{font-size:11.5px;color:var(--brand-muted);margin-top:5px;line-height:1.5}}
code{{font-size:11px;background:#f3f4f6;padding:1px 4px;border-radius:4px}}
"""
    path = DOCS_DIR / "static" / "css" / "chat.css"
    path.write_text(css, encoding="utf-8")


def write_js(cfg: dict, provider: dict | None, token: str):
    """
    Write chat.js — token is baked in at build time.
    Supports two providers: Mistral (primary) and GitHub Models (fallback).
    GitHub Models uses the same OpenAI-compatible /chat/completions schema.
    Mistral's API is also OpenAI-compatible, so a single callAI() path works
    for both; the only difference is the Authorization header value and endpoint.
    """
    bot = cfg["bot"]
    quick_json = json.dumps(bot["quick_replies"], ensure_ascii=False)
    system = bot["system_prompt"].replace("`", r"\`").replace("\\", "\\\\")
    greeting = bot["greeting"].replace("`", r"\`")
    bot_name = bot["name"].replace("`", r"\`")
    bot_icon = bot["icon"]

    endpoint = provider["endpoint"] if provider else ""
    model_id = provider["model"] if provider else "demo"
    provider_name = provider["name"] if provider else "demo"
    auth_header = provider["auth_header"] if provider else "Bearer"

    safe_token = token.replace("`", "\\`").replace(
        "\\", "\\\\") if token else ""

    js = f"""/* Auto-generated by chatbot_system.py */
/* Provider: {provider_name} | Model: {model_id} | Built: {datetime.now(timezone.utc).isoformat()} */

const CHATBOT_TOKEN    = `{safe_token}`;
const CHATBOT_ENDPOINT = `{endpoint}`;
const CHATBOT_MODEL    = `{model_id}`;
const CHATBOT_PROVIDER = `{provider_name}`;
// Authorization scheme — both Mistral and GitHub Models use "Bearer"
const CHATBOT_AUTH_HDR = `{auth_header}`;

/* Runtime config (overridable via Settings panel) */
let CFG = {{
  name:        `{bot_name}`,
  icon:        `{bot_icon}`,
  system:      `{system}`,
  greeting:    `{greeting}`,
  quickReplies: {quick_json},
}};

/* Try loading overrides saved by the Settings panel */
try {{
  const saved = localStorage.getItem("chatbot_ui_config");
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

  document.getElementById("user-input").addEventListener("keydown", e => {{
    if (e.key === "Enter" && !e.shiftKey) {{ e.preventDefault(); send(); }}
  }});
}});

function applyMeta() {{
  document.getElementById("header-title").textContent = CFG.name;
  document.getElementById("header-icon").textContent  = CFG.icon;
  document.title = CFG.name;
  const badge = document.getElementById("model-badge");
  if (badge) badge.textContent = CHATBOT_MODEL;
}}

function renderProviderStrip() {{
  const strip = document.getElementById("provider-strip");
  if (!strip) return;
  if (!CHATBOT_TOKEN || CHATBOT_PROVIDER === "demo") {{
    strip.className = "demo";
    strip.innerHTML = `⚠️ Demo mode — no API key found. Set MISTRAL_API_KEY or GIT_TOKEN to enable live AI.`;
  }} else if (CHATBOT_PROVIDER === "mistral") {{
    strip.className = "";
    strip.innerHTML = `✅ Live AI &nbsp;·&nbsp; <strong>Mistral AI</strong> &nbsp;·&nbsp; ${{CHATBOT_MODEL}}`;
  }} else {{
    strip.className = "";
    strip.innerHTML = `✅ Live AI &nbsp;·&nbsp; <strong>GitHub Models</strong> (Mistral) &nbsp;·&nbsp; ${{CHATBOT_MODEL}}`;
  }}
}}

/* ── CHAT ── */
function showGreeting() {{
  addMsg("bot", CFG.greeting);
  setTimeout(renderQuickReplies, 400);
}}

function addMsg(role, text) {{
  const c = document.getElementById("chat-container");
  const w = document.createElement("div");
  w.className = "message " + role;
  const t = new Date().toLocaleTimeString([], {{hour:"2-digit",minute:"2-digit"}});
  w.innerHTML = `
    <div class="msg-avatar">${{role==="bot" ? CFG.icon : "You"}}</div>
    <div>
      <div class="msg-bubble">${{esc(text).replace(/\\n/g,"<br>")}}</div>
      <span class="msg-time">${{t}}</span>
    </div>`;
  c.appendChild(w);
  c.scrollTop = c.scrollHeight;
}}

function showTyping() {{
  const c = document.getElementById("chat-container");
  const el = document.createElement("div");
  el.id = "typing"; el.className = "message bot";
  el.innerHTML = `<div class="msg-avatar">${{CFG.icon}}</div>
    <div class="msg-bubble typing-dots"><span></span><span></span><span></span></div>`;
  c.appendChild(el); c.scrollTop = c.scrollHeight;
}}
function removeTyping() {{ document.getElementById("typing")?.remove(); }}

function renderQuickReplies() {{
  const c = document.getElementById("chat-container");
  const el = document.createElement("div");
  el.className = "quick-replies"; el.id = "qr";
  CFG.quickReplies.forEach(r => {{
    const btn = document.createElement("button");
    btn.className = "quick-btn"; btn.textContent = r;
    btn.onclick = () => {{ el.remove(); send(r); }};
    el.appendChild(btn);
  }});
  c.appendChild(el); c.scrollTop = c.scrollHeight;
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
  history.push({{ role:"user", content:text }});
  busy = true; showTyping();

  try {{
    const reply = await callAI();
    removeTyping(); addMsg("bot", reply);
    history.push({{ role:"assistant", content:reply }});
  }} catch(err) {{
    removeTyping();
    addMsg("bot", "⚠️ " + (err.message || "Connection error. Please try again."));
    console.error(err);
  }}
  busy = false;
}}

/* ── API CALL ──────────────────────────────────────────────────────────────
   Both Mistral AI and GitHub Models expose an OpenAI-compatible
   /v1/chat/completions endpoint, so a single fetch() path handles both.
   The endpoint URL, model name, and Bearer token are baked in at build time.
   ────────────────────────────────────────────────────────────────────────── */
async function callAI() {{
  /* Demo fallback — no token available */
  if (!CHATBOT_TOKEN || CHATBOT_PROVIDER === "demo") {{
    return demoReply(history[history.length-1]?.content || "");
  }}

  const messages = [
    {{ role:"system", content: CFG.system }},
    ...history
  ];

  const res = await fetch(CHATBOT_ENDPOINT, {{
    method: "POST",
    headers: {{
      "Content-Type":  "application/json",
      "Authorization": `${{CHATBOT_AUTH_HDR}} ${{CHATBOT_TOKEN}}`
    }},
    body: JSON.stringify({{
      model:       CHATBOT_MODEL,
      messages:    messages,
      max_tokens:  500,
      temperature: 0.7
    }})
  }});

  if (!res.ok) {{
    const err = await res.json().catch(() => ({{}}));
    throw new Error(err.error?.message || `HTTP ${{res.status}} — ${{CHATBOT_PROVIDER}}`);
  }}

  const data = await res.json();
  // Both Mistral and GitHub Models follow OpenAI's choices[].message.content shape
  return data.choices?.[0]?.message?.content?.trim()
    || "Sorry, I received an empty response.";
}}

/* ── DEMO REPLIES ── */
function demoReply(text) {{
  const t = text.toLowerCase();
  const map = {{
    "opening hours": "We're open Mon–Fri 9am–6pm, Sat 10am–4pm. Closed Sundays. 🕐",
    "book":          "Book at our website or call (555) 123-4567. Takes ~30 min. 📅",
    "pric":          "Packages from $49. Premium from $149/mo. Want a quote? 💰",
    "location":      "123 Main Street, downtown. Free parking on site. 📍",
  }};
  for (const [k,v] of Object.entries(map)) if (t.includes(k)) return v;
  return "I'm in demo mode — no API key was injected at build time. " +
    "Set MISTRAL_API_KEY (primary) or GIT_TOKEN (fallback) to enable live AI.";
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
  CFG.name        = document.getElementById("cfg-name").value.trim()  || CFG.name;
  CFG.icon        = document.getElementById("cfg-icon").value.trim()  || CFG.icon;
  CFG.system      = document.getElementById("cfg-system").value.trim();
  CFG.greeting    = document.getElementById("cfg-greeting").value.trim();
  CFG.quickReplies= document.getElementById("cfg-qr").value
    .split(",").map(s=>s.trim()).filter(Boolean);
  try {{ localStorage.setItem("chatbot_ui_config", JSON.stringify(CFG)); }} catch(e) {{}}
  applyMeta();
  resetChat();
  toggleConfig();
}}

function resetChat() {{
  history = [];
  document.getElementById("chat-container").innerHTML = "";
  showGreeting();
}}

/* ── UTIL ── */
function esc(t) {{
  return t.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}}
"""
    path = DOCS_DIR / "static" / "js" / "chat.js"
    path.write_text(js, encoding="utf-8")


def write_html(cfg: dict, provider: dict | None):
    bot = cfg["bot"]
    name = bot["name"]
    icon = bot["icon"]
    model = provider["model"] if provider else "demo"
    provider_name = provider["name"] if provider else "demo"

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&family=Playfair+Display:wght@500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="static/css/chat.css">
</head>
<body>

<!-- Provider / token status strip (populated by chat.js) -->
<div id="provider-strip">Loading…</div>

<!-- Header -->
<header>
  <div class="header-brand">
    <div class="header-avatar" id="header-icon">{icon}</div>
    <span class="header-name" id="header-title">{name}</span>
  </div>
  <div class="header-right">
    <span class="model-badge" id="model-badge" title="Active model">{model}</span>
    <div class="header-status"><div class="status-dot"></div>Online</div>
    <button class="settings-btn" onclick="toggleConfig()" title="Customise">
      <svg width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.8" viewBox="0 0 24 24">
        <path d="M12 15a3 3 0 100-6 3 3 0 000 6z"/>
        <path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06
                 a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09
                 A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06
                 A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09
                 A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06
                 A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09
                 a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06
                 A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09
                 a1.65 1.65 0 00-1.51 1z"/>
      </svg>
    </button>
  </div>
</header>

<!-- Chat -->
<div id="chat-container"></div>

<!-- Input -->
<div id="input-bar">
  <div class="input-inner">
    <input type="text" id="user-input" placeholder="Type your message…" autocomplete="off">
    <button id="send-btn" onclick="send()" aria-label="Send">
      <svg fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <path d="M22 2L11 13M22 2L15 22l-4-9-9-4 20-7z"/>
      </svg>
    </button>
  </div>
</div>

<!-- Config / Settings panel -->
<div id="overlay" onclick="toggleConfig()"></div>
<div id="config-panel">
  <button class="close-config" onclick="toggleConfig()">✕</button>
  <div class="config-title">Customise Bot</div>

  <div class="config-section">
    <label class="config-label">Business Name</label>
    <input class="config-input" id="cfg-name">
  </div>
  <div class="config-section">
    <label class="config-label">Icon / Emoji</label>
    <input class="config-input" id="cfg-icon">
  </div>
  <div class="config-section">
    <label class="config-label">System Prompt</label>
    <textarea class="config-input" id="cfg-system"></textarea>
  </div>
  <div class="config-section">
    <label class="config-label">Greeting</label>
    <input class="config-input" id="cfg-greeting">
  </div>
  <div class="config-section">
    <label class="config-label">Quick Replies (comma-separated)</label>
    <input class="config-input" id="cfg-qr">
  </div>
  <div class="config-section">
    <label class="config-label">Active Provider</label>
    <p class="info-note">
      Provider and model are set at <strong>build time</strong> via GitHub Secrets.<br>
      Active: <code>{provider_name}</code>
      &nbsp;→&nbsp; <code>{model}</code><br><br>
      Priority: <code>MISTRAL_API_KEY</code> → <code>GIT_TOKEN</code>
    </p>
  </div>

  <button class="apply-btn" onclick="applyConfig()">✓ Apply Changes</button>
</div>

<script src="static/js/chat.js"></script>
</body>
</html>
"""
    (DOCS_DIR / "index.html").write_text(html, encoding="utf-8")


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chatbot system builder")
    parser.add_argument(
        "command",
        choices=["init", "build", "auto", "verify"],
        help="Command to run"
    )
    args = parser.parse_args()

    commands = {
        "init":   cmd_init,
        "build":  cmd_build,
        "auto":   cmd_auto,
        "verify": cmd_verify,
    }
    commands[args.command]()
