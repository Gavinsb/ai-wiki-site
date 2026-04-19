# AI Wiki Site

Static website build of a personal AI research wiki.

## Local preview

```bash
python3 build_wiki_site.py
python3 -m http.server 8765 --bind 127.0.0.1
```

## Notes

- Main navigation hides raw source pages to keep reading focused.
- Raw source pages remain accessible from each page's source chips.
- GitHub Actions rebuilds the static site on pushes to `main`.
