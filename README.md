# AI Wiki Site

Static website build of a personal AI research wiki.

## Local preview

```bash
python3 build_wiki_site.py
python3 -m http.server 8765 --bind 127.0.0.1
```

## Contents

- `index.html` — homepage
- `pages/` — rendered wiki pages
- `assets/` — CSS and search index
- `build_wiki_site.py` — generator script

This repository is intended to be served as a static site.
