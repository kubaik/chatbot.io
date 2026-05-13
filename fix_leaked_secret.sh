#!/usr/bin/env bash
# fix_leaked_secret.sh
# ─────────────────────────────────────────────────────────────────
# Run this ONCE locally to:
#   1. Remove docs/ from all git history (expunges the leaked token)
#   2. Add docs/ to .gitignore permanently
#   3. Force-push the cleaned history
#
# Prerequisites:
#   brew install git-filter-repo        # macOS
#   pip install git-filter-repo         # or via pip
#
# Usage:
#   chmod +x fix_leaked_secret.sh
#   ./fix_leaked_secret.sh
# ─────────────────────────────────────────────────────────────────

set -euo pipefail

echo ""
echo "═══════════════════════════════════════════════════"
echo "  Fix: Remove leaked secret from git history"
echo "═══════════════════════════════════════════════════"
echo ""

# ── Check git-filter-repo is available ──────────────────────────
if ! command -v git-filter-repo &>/dev/null; then
  echo "ERROR: git-filter-repo not found."
  echo ""
  echo "Install it first:"
  echo "  macOS:   brew install git-filter-repo"
  echo "  Linux:   pip install git-filter-repo"
  echo "  Windows: pip install git-filter-repo"
  exit 1
fi

# ── Confirm we're in the right repo ─────────────────────────────
echo "Working directory: $(pwd)"
echo "Repo:              $(git remote get-url origin 2>/dev/null || echo 'no remote')"
echo ""
read -r -p "Is this the correct repo? (y/N) " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { echo "Aborted."; exit 0; }

# ── Step 1: ensure docs/ is in .gitignore ───────────────────────
echo ""
echo "── Step 1: Updating .gitignore ─────────────────────────────"
if grep -qx "docs/" .gitignore 2>/dev/null; then
  echo "docs/ already in .gitignore — OK"
else
  echo "" >> .gitignore
  echo "# Built output — contains injected API tokens, never commit" >> .gitignore
  echo "docs/" >> .gitignore
  echo "Added docs/ to .gitignore"
fi

# ── Step 2: Remove docs/ from every commit in history ───────────
echo ""
echo "── Step 2: Rewriting git history (removing docs/) ──────────"
echo "This rewrites ALL commits — the SHA hashes will change."
echo ""
git filter-repo --path docs/ --invert-paths --force
echo "History rewrite complete."

# ── Step 3: Re-add remote (filter-repo removes it for safety) ───
echo ""
echo "── Step 3: Re-add remote origin ────────────────────────────"
read -r -p "Enter your remote URL (e.g. https://github.com/user/repo.git): " remote_url
git remote add origin "$remote_url"
echo "Remote set to: $remote_url"

# ── Step 4: Commit the updated .gitignore ───────────────────────
echo ""
echo "── Step 4: Commit updated .gitignore ───────────────────────"
git add .gitignore
git diff --staged --quiet || git commit -m "chore: add docs/ to .gitignore (prevent token leaks)"

# ── Step 5: Force push ──────────────────────────────────────────
echo ""
echo "── Step 5: Force push to origin/main ───────────────────────"
echo "WARNING: This rewrites remote history. Any collaborators"
echo "         must re-clone or run 'git fetch --all && git reset --hard origin/main'."
echo ""
read -r -p "Force push now? (y/N) " push_confirm
if [[ "$push_confirm" =~ ^[Yy]$ ]]; then
  git push origin main --force
  echo ""
  echo "✅ Done! History cleaned and pushed."
else
  echo ""
  echo "Skipped push. When ready, run:"
  echo "  git push origin main --force"
fi

# ── Step 6: Rotate your leaked key ──────────────────────────────
echo ""
echo "═══════════════════════════════════════════════════"
echo "  ⚠️  IMPORTANT: Rotate your leaked API key now"
echo "═══════════════════════════════════════════════════"
echo ""
echo "Even after history cleanup, the old key may have been"
echo "cached or scraped. Rotate it immediately:"
echo ""
echo "  GROQ:       console.groq.com → API Keys → Revoke & create new"
echo "  GitHub PAT: github.com/settings/tokens → Delete & regenerate"
echo "  Others:     Go to each provider's dashboard"
echo ""
echo "Then update the secret in:"
echo "  Repo → Settings → Secrets & Variables → Actions"
echo ""