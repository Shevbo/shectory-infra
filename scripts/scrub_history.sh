#!/usr/bin/env bash
# Scrub .openclaw/openclaw.json (and any other listed files) from full git history.
# USE ONLY AFTER ROTATING ALL LEAKED SECRETS — see SECURITY_INCIDENT_2026-05-29.md
#
# Safety:
# - Creates a tagged backup ref before rewriting
# - Refuses to run on uncommitted changes
# - Refuses to run if origin has commits ahead of local
# - Uses --force-with-lease (not --force) so concurrent pushes are detected

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PATHS_TO_PURGE=(
  ".openclaw/openclaw.json"
)

echo "=== Repo: $REPO_ROOT ==="
if ! command -v git-filter-repo >/dev/null 2>&1; then
  echo "git-filter-repo not installed."
  echo "Install: pip install --user git-filter-repo  (or apt: git-filter-repo on newer distros)"
  exit 2
fi

# Refuse on dirty tree
if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Working tree has uncommitted changes. Commit/stash first."
  exit 3
fi

# Refuse if remote is ahead
git fetch origin
LOCAL=$(git rev-parse HEAD)
REMOTE=$(git rev-parse origin/main)
BASE=$(git merge-base HEAD origin/main)
if [[ "$LOCAL" != "$REMOTE" && "$BASE" != "$REMOTE" ]]; then
  echo "Remote main has commits not in local. Pull/merge first."
  exit 4
fi

TAG="pre-scrub-$(date -u +%Y%m%d-%H%M%S)"
git tag "$TAG" HEAD
echo "Backup tag: $TAG (delete after verification: git tag -d $TAG)"

ARGS=()
for p in "${PATHS_TO_PURGE[@]}"; do
  ARGS+=(--path "$p")
done

echo "Running: git filter-repo --invert-paths ${ARGS[*]} --force"
git filter-repo --invert-paths "${ARGS[@]}" --force

# filter-repo strips origin to prevent accidental push. Restore.
git remote add origin git@github.com:Shevbo/shectory-infra.git 2>/dev/null || true

echo "Pushing with --force-with-lease ..."
git push origin main --force-with-lease

echo "Done. Backup tag: $TAG (locally only). Verify github UI shows no .openclaw/openclaw.json in any commit."
