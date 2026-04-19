#!/usr/bin/env bash
set -euo pipefail

export PATH="$HOME/.local/bin:$PATH"

SITE_DIR="/home/gazaz/wiki-site"
LOG_PREFIX="[wiki-site-sync]"

cd "$SITE_DIR"

echo "$LOG_PREFIX rebuilding static site"
python3 build_wiki_site.py

if [ -d __pycache__ ]; then
  rm -rf __pycache__
fi
find . -type d -name __pycache__ -prune -exec rm -rf {} + || true
find . -type f -name '*.pyc' -delete || true

git add .
if git diff --cached --quiet; then
  echo "$LOG_PREFIX no changes to commit"
  exit 0
fi

echo "$LOG_PREFIX committing updates"
GIT_EDITOR=true git commit -m "Sync wiki site"

echo "$LOG_PREFIX pushing to origin/main"
git push origin main

echo "$LOG_PREFIX done"
