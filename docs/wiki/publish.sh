#!/bin/sh
# Build the wiki from docs/ and push it to the GitHub wiki repository.
# The wiki must exist: GitHub → repository → Wiki → "Create the first page" (once, any content).
set -eu
cd "$(dirname "$0")/../.."
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
git clone --quiet "${WIKI_REPO:-git@github.com:xarxfy/x-tools.wiki.git}" "$TMP/wiki"
python3 docs/wiki/build.py "$TMP/wiki" >/dev/null
cd "$TMP/wiki"
git add -A
if git diff --cached --quiet; then echo "Wiki is up to date."; exit 0; fi
git -c user.name="${GIT_AUTHOR_NAME:-X-TOOLS}" -c user.email="${GIT_AUTHOR_EMAIL:-noreply@example.com}" \
  commit --quiet -m "Update wiki from docs/ ($(git -C "$OLDPWD" rev-parse --short HEAD))"
git push --quiet origin HEAD
echo "Wiki published."
