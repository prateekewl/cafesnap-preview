#!/usr/bin/env bash
# refresh_preview.sh - rebuild the $0-cost GitHub Pages PREVIEW site.
#
# WHAT THIS DOES
#   Renders the customer-facing Jinja templates (index/status/success/
#   cancel/terms) from a GIVEN git branch (or commit) of the PRIVATE app
#   repo to STATIC HTML, stamps a non-interactive "PREVIEW" ribbon on
#   every page, and force-pushes the rendered HTML to the DEDICATED
#   PUBLIC preview repo (prateekewl/cafesnap-preview). GitHub Pages then
#   serves it for free at:
#       https://prateekewl.github.io/cafesnap-preview/
#
#   Why a separate public repo: the app repo is PRIVATE and the account
#   plan does not offer Pages for private repos. Pages IS free for public
#   repos, so only the harmless rendered customer HTML (zero secrets,
#   zero bot code) is published there. The private app repo and its
#   `main` are NEVER touched or committed to by this tool.
#
# USAGE
#   scripts/refresh_preview.sh [<branch-or-ref>]
#       default ref: origin/main
#   Examples:
#       scripts/refresh_preview.sh                       # preview main
#       scripts/refresh_preview.sh fix/banner-font       # preview a branch
#       scripts/refresh_preview.sh origin/fix/site-copy  # remote branch
#
# REQUIREMENTS
#   - git, python3 with jinja2 (the repo .venv has it)
#   - `gh` authed (only used the first time to enable Pages)
#
# COST: $0. GitHub Pages is free for public repos. No Railway services.
set -euo pipefail

# Source (private app repo) is the local checkout this script lives in.
# Publish target is the dedicated PUBLIC preview repo.
PUBLISH_SLUG="prateekewl/cafesnap-preview"
PAGES_BRANCH="gh-pages"
REF="${1:-origin/main}"

# Resolve repo root from this script's location so it works from anywhere.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && git rev-parse --show-toplevel)"

# Pick a python that has jinja2. Prefer the repo .venv.
PY=""
for cand in "$REPO_ROOT/.venv/bin/python" python3 python; do
  if command -v "$cand" >/dev/null 2>&1 && "$cand" -c "import jinja2" >/dev/null 2>&1; then
    PY="$cand"; break
  fi
done
if [ -z "$PY" ]; then
  echo "ERROR: no python with jinja2 found (tried .venv, python3, python)." >&2
  exit 1
fi

echo "[refresh_preview] repo root : $REPO_ROOT"
echo "[refresh_preview] source ref: $REF"
echo "[refresh_preview] python    : $PY"

git -C "$REPO_ROOT" fetch origin --quiet || true

# Build into an isolated temp checkout of the requested ref so we never
# disturb the working tree or `main`.
WORK="$(mktemp -d /tmp/cafesnap-preview-build.XXXXXX)"
OUT="$(mktemp -d /tmp/cafesnap-preview-out.XXXXXX)"
cleanup() { git -C "$REPO_ROOT" worktree remove --force "$WORK" >/dev/null 2>&1 || true; rm -rf "$WORK" "$OUT"; }
trap cleanup EXIT

git -C "$REPO_ROOT" worktree add --detach "$WORK" "$REF" >/dev/null
BUILT_FROM="$(git -C "$WORK" rev-parse --short HEAD)"
echo "[refresh_preview] building from commit: $BUILT_FROM"

# Render. The renderer lives next to this script and is copied onto the
# preview repo too (handy reference), but it is only ever executed from a
# source checkout of the PRIVATE app repo.
"$PY" "$SCRIPT_DIR/render_preview.py" --src "$WORK" --out "$OUT" --ref "$REF" --commit "$BUILT_FROM"

# Publish: dedicated PUBLIC preview repo, gh-pages branch = rendered site.
# (The private app repo is never written to.)
PUB="$(mktemp -d /tmp/cafesnap-preview-pub.XXXXXX)"
trap 'cleanup; rm -rf "$PUB"' EXIT
git clone --quiet --no-checkout "https://github.com/${PUBLISH_SLUG}.git" "$PUB"
cd "$PUB"
if git ls-remote --exit-code --heads origin "$PAGES_BRANCH" >/dev/null 2>&1; then
  git checkout --quiet "$PAGES_BRANCH"
  git rm -rqf . >/dev/null 2>&1 || true
else
  git checkout --quiet --orphan "$PAGES_BRANCH"
  git rm -rqf . >/dev/null 2>&1 || true
fi

cp -R "$OUT"/. "$PUB"/
touch "$PUB/.nojekyll"   # serve _-prefixed paths + skip Jekyll build

git add -A
if git diff --cached --quiet; then
  echo "[refresh_preview] no changes to publish."
else
  git -c user.email="preview-bot@cafesnapbot.local" \
      -c user.name="CafeSnap Preview Bot" \
      commit --quiet -m "preview: render customer pages from ${REF} (${BUILT_FROM})"
  git push --quiet --force origin "$PAGES_BRANCH"
  echo "[refresh_preview] pushed gh-pages on ${PUBLISH_SLUG}."
fi

echo
echo "[refresh_preview] DONE. Preview URL:"
echo "    https://prateekewl.github.io/cafesnap-preview/"
echo "(Allow ~1 min for GitHub Pages to rebuild after a push.)"
