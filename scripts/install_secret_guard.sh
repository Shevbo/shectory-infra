#!/usr/bin/env bash
# Install pre-commit + pre-push hooks that block any commit/push containing common secret shapes.
# Idempotent — safe to run multiple times.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK_DIR="$REPO_ROOT/.git/hooks"
mkdir -p "$HOOK_DIR"

cat > "$HOOK_DIR/pre-commit" <<'EOF'
#!/usr/bin/env bash
# pre-commit: block obvious secret patterns in staged diff
set -euo pipefail
STAGED=$(git diff --cached --name-only --diff-filter=ACM)
[ -z "$STAGED" ] && exit 0
TMP=$(mktemp)
trap 'rm -f "$TMP"' EXIT
git diff --cached --unified=0 -- $STAGED > "$TMP"
# Patterns: TG bot, Google AIza, OpenAI sk-, ya29, GitHub PAT, generic 40+ char hex/b64 in key-like fields
if grep -nP '(?i)([0-9]{8,12}:[A-Za-z0-9_-]{30,}|AIza[A-Za-z0-9_-]{30,}|sk-(?:proj-|ant-|or-v1-)?[A-Za-z0-9_-]{20,}|ya29\.[A-Za-z0-9._-]{20,}|(?:ghp|gho|ghs)_[A-Za-z0-9_]{20,}|"?(api[_-]?key|apiKey|botToken|secret|password)"?\s*[:=]\s*"?[A-Za-z0-9_-]{20,})' "$TMP"; then
  echo "BLOCKED: potential secret in staged diff. To override (last resort): SKIP_SECRET_GUARD=1 git commit ..." >&2
  [ "${SKIP_SECRET_GUARD:-0}" = "1" ] && exit 0
  exit 1
fi
EOF
chmod +x "$HOOK_DIR/pre-commit"

cat > "$HOOK_DIR/pre-push" <<'EOF'
#!/usr/bin/env bash
# pre-push: last gate before remote
set -euo pipefail
while read local_ref local_sha remote_ref remote_sha; do
  [ "$local_sha" = "0000000000000000000000000000000000000000" ] && continue
  RANGE="${remote_sha}..${local_sha}"
  [ "$remote_sha" = "0000000000000000000000000000000000000000" ] && RANGE="$local_sha"
  if git log -p "$RANGE" 2>/dev/null | grep -nP '(?i)([0-9]{8,12}:[A-Za-z0-9_-]{30,}|AIza[A-Za-z0-9_-]{30,}|sk-(?:proj-|ant-|or-v1-)?[A-Za-z0-9_-]{20,}|ya29\.[A-Za-z0-9._-]{20,}|(?:ghp|gho|ghs)_[A-Za-z0-9_]{20,})'; then
    echo "BLOCKED: potential secret in push range $RANGE. SKIP_SECRET_GUARD=1 to override." >&2
    [ "${SKIP_SECRET_GUARD:-0}" = "1" ] && exit 0
    exit 1
  fi
done
EOF
chmod +x "$HOOK_DIR/pre-push"

echo "Installed:"
ls -la "$HOOK_DIR/pre-commit" "$HOOK_DIR/pre-push"
echo "Self-test (manual): create a file with a Google-key-shaped or TG-bot-token-shaped value, git add+commit — pre-commit must block."
