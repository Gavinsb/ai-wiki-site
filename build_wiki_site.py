#!/usr/bin/env python3
from __future__ import annotations
import html
import json
import re
from datetime import datetime
from pathlib import Path

WIKI = Path('/home/gazaz/wiki')
OUT = Path('/home/gazaz/wiki-site')

VISIBLE_GROUPS = [
    ('Meta', [WIKI / 'start-here.md', WIKI / '_meta' / 'topic-map.md']),
    ('Entities', sorted((WIKI / 'entities').glob('*.md'))),
    ('Concepts', sorted((WIKI / 'concepts').glob('*.md'))),
    ('Comparisons', sorted((WIKI / 'comparisons').glob('*.md'))),
    ('Queries', sorted((WIKI / 'queries').glob('*.md'))),
]
REFERENCE_FILES = [WIKI / 'index.md', WIKI / 'log.md', WIKI / 'SCHEMA.md']
RAW_FILES = sorted((WIKI / 'raw').rglob('*.md'))
ALL_FILES = [p for _, files in VISIBLE_GROUPS for p in files] + [p for p in REFERENCE_FILES if p.exists()] + RAW_FILES

OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'pages').mkdir(exist_ok=True)
(OUT / 'assets').mkdir(exist_ok=True)
(OUT / '.github' / 'workflows').mkdir(parents=True, exist_ok=True)


def parse_frontmatter(text: str):
    if text.startswith('---\n'):
        end = text.find('\n---\n', 4)
        if end != -1:
            raw = text[4:end]
            body = text[end + 5:]
            meta = {}
            for line in raw.splitlines():
                if ':' in line:
                    k, v = line.split(':', 1)
                    meta[k.strip()] = v.strip()
            return meta, body
    return {}, text


def strip_md(s: str) -> str:
    s = re.sub(r'`([^`]+)`', r'\1', s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'\1', s)
    s = re.sub(r'\*([^*]+)\*', r'\1', s)
    s = re.sub(r'\[\[([^\]|]+)\|([^\]]+)\]\]', r'\2', s)
    s = re.sub(r'\[\[([^\]]+)\]\]', r'\1', s)
    s = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', r'\1', s)
    return s.strip()


def slug_for(path: Path) -> str:
    return path.relative_to(WIKI).with_suffix('').as_posix().replace('/', '__')


def page_url(slug: str) -> str:
    return f'pages/{slug}.html'


slug_map = {p.stem: slug_for(p) for p in ALL_FILES}
full_slug_map = {p.relative_to(WIKI).with_suffix('').as_posix(): slug_for(p) for p in ALL_FILES}


def resolve_wikilink(target: str):
    target = target.strip()
    if target in slug_map:
        return page_url(slug_map[target])
    if target in full_slug_map:
        return page_url(full_slug_map[target])
    return None


def fmt_inline(text: str, level: str = 'page') -> str:
    text = html.escape(text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\*\*([^*]+)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*([^*]+)\*', r'<em>\1</em>', text)
    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', lambda m: f'<a href="{html.escape(m.group(2), quote=True)}" target="_blank" rel="noreferrer">{m.group(1)}</a>', text)

    def wl(m):
        inner = m.group(1)
        if '|' in inner:
            target, label = inner.split('|', 1)
        else:
            target, label = inner, inner
        href = resolve_wikilink(target)
        label = html.escape(label)
        if href:
            prefix = '../' if level == 'page' else ''
            return f'<a href="{prefix}{href}">{label}</a>'
        return f'<span class="broken-link">{label}</span>'

    return re.sub(r'\[\[([^\]]+)\]\]', wl, text)


def markdown_to_html(md: str, level: str = 'page') -> str:
    lines = md.splitlines()
    out = []
    in_list = False
    in_code = False
    in_table = False
    table_rows = []

    def close_list():
        nonlocal in_list
        if in_list:
            out.append('</ul>')
            in_list = False

    def flush_table():
        nonlocal in_table, table_rows
        if not in_table:
            return
        if len(table_rows) >= 2:
            headers = [fmt_inline(c.strip(), level) for c in table_rows[0].strip('|').split('|')]
            body_rows = table_rows[2:]
            out.append('<div class="table-wrap"><table><thead><tr>' + ''.join(f'<th>{h}</th>' for h in headers) + '</tr></thead><tbody>')
            for row in body_rows:
                cols = [fmt_inline(c.strip(), level) for c in row.strip('|').split('|')]
                out.append('<tr>' + ''.join(f'<td>{c}</td>' for c in cols) + '</tr>')
            out.append('</tbody></table></div>')
        table_rows = []
        in_table = False

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('```'):
            flush_table(); close_list()
            out.append('<pre><code>' if not in_code else '</code></pre>')
            in_code = not in_code
            i += 1
            continue
        if in_code:
            out.append(html.escape(line) + '\n')
            i += 1
            continue
        if line.strip().startswith('|') and line.count('|') >= 2:
            close_list(); in_table = True; table_rows.append(line); i += 1; continue
        else:
            flush_table()
        if not line.strip():
            close_list(); out.append(''); i += 1; continue
        if line.startswith('#'):
            close_list()
            m = re.match(r'^(#{1,6})\s+(.*)$', line)
            if m:
                lvl = len(m.group(1))
                content = fmt_inline(m.group(2).strip(), level)
                anchor = re.sub(r'[^a-z0-9]+', '-', strip_md(m.group(2).lower())).strip('-')
                out.append(f'<h{lvl} id="{anchor}">{content}</h{lvl}>')
                i += 1; continue
        if re.match(r'^-\s+', line):
            if not in_list:
                out.append('<ul>'); in_list = True
            item = re.sub(r'^-\s+', '', line)
            out.append(f'<li>{fmt_inline(item, level)}</li>')
            i += 1; continue
        if re.match(r'^\d+\.\s+', line):
            close_list()
            items = []
            while i < len(lines) and re.match(r'^\d+\.\s+', lines[i]):
                items.append(re.sub(r'^\d+\.\s+', '', lines[i])); i += 1
            out.append('<ol>' + ''.join(f'<li>{fmt_inline(it, level)}</li>' for it in items) + '</ol>')
            continue
        if line.startswith('>'):
            close_list(); out.append(f'<blockquote>{fmt_inline(line[1:].strip(), level)}</blockquote>'); i += 1; continue
        if line.startswith('---') and set(line.strip()) == {'-'}:
            close_list(); out.append('<hr />'); i += 1; continue
        close_list(); out.append(f'<p>{fmt_inline(line, level)}</p>'); i += 1
    flush_table(); close_list()
    if in_code:
        out.append('</code></pre>')
    return '\n'.join(out)


def extract_summary(body: str) -> str:
    for line in body.splitlines():
        s = strip_md(line)
        if s and not s.startswith('#') and not s.startswith('---'):
            return s[:220]
    return ''


pages = []
for path in ALL_FILES:
    meta, body = parse_frontmatter(path.read_text())
    title = meta.get('title') or strip_md(next((ln for ln in body.splitlines() if ln.startswith('# ')), path.stem))
    category = path.parent.name if path.parent != WIKI else 'root'
    pages.append({
        'path': path,
        'slug': slug_for(path),
        'url': page_url(slug_for(path)),
        'title': title,
        'meta': meta,
        'body': body,
        'summary': extract_summary(body),
        'category': category,
        'is_raw': path in RAW_FILES,
        'stem': path.stem,
    })

for p in pages:
    p['wikilinks'] = re.findall(r'\[\[([^\]|#]+)', p['body'])
for p in pages:
    p['backlinks'] = [q for q in pages if p['stem'] in q['wikilinks'] and q['slug'] != p['slug']]

visible_pages = [p for p in pages if not p['is_raw']]
search_index = [
    {
        'title': p['title'],
        'url': p['url'],
        'category': p['category'],
        'summary': p['summary'],
        'tags': p['meta'].get('tags', ''),
        'text': strip_md(re.sub(r'```.*?```', ' ', p['body'], flags=re.S))[:7000],
    }
    for p in visible_pages
]
(OUT / 'assets' / 'search-index.json').write_text(json.dumps(search_index, indent=2))

css = '''
:root {
  --bg: #0b1020;
  --panel: rgba(15, 23, 42, 0.88);
  --panel-2: rgba(30, 41, 59, 0.82);
  --panel-3: rgba(51, 65, 85, 0.55);
  --text: #e5eefc;
  --muted: #9fb2d9;
  --brand: #7dd3fc;
  --brand-2: #a78bfa;
  --line: rgba(148, 163, 184, 0.18);
  --link: #93c5fd;
  --chip: rgba(125, 211, 252, 0.12);
  --shadow: 0 10px 30px rgba(0,0,0,0.28);
}
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; background: radial-gradient(circle at top, #16213e 0%, #0b1020 55%); color: var(--text); font: 16px/1.6 Inter, ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }
a { color: var(--link); text-decoration: none; }
a:hover { text-decoration: underline; }
body.nav-open { overflow: hidden; }
.topbar { display:none; }
.shell { display: grid; grid-template-columns: 320px 1fr; min-height: 100vh; }
.sidebar { position: sticky; top: 0; height: 100vh; overflow: auto; background: rgba(2,6,23,0.72); backdrop-filter: blur(18px); border-right: 1px solid var(--line); padding: 20px; }
.brand { display:flex; gap:12px; align-items:center; margin-bottom: 18px; }
.brand-badge { width:44px; height:44px; border-radius:14px; background: linear-gradient(135deg, var(--brand), var(--brand-2)); box-shadow: var(--shadow); }
.brand h1 { font-size: 1.15rem; margin:0; }
.brand p { margin:0; color: var(--muted); font-size:.92rem; }
.search { width:100%; border:1px solid var(--line); background: var(--panel); color:var(--text); border-radius:14px; padding:12px 14px; outline:none; }
.filter-row { display:flex; gap:8px; flex-wrap:wrap; margin: 12px 0 16px; }
.filter-chip { cursor:pointer; border:1px solid var(--line); background: var(--panel-2); color: var(--muted); border-radius:999px; padding:6px 10px; font-size:.82rem; }
.filter-chip.active { background: linear-gradient(135deg, rgba(125,211,252,.22), rgba(167,139,250,.22)); color: var(--text); }
.nav-section { margin: 18px 0; }
.nav-section h3 { color: var(--muted); font-size:.8rem; text-transform: uppercase; letter-spacing: .08em; margin: 0 0 8px; }
.nav-list { display:grid; gap:6px; }
.nav-link { display:block; padding:9px 11px; border-radius:12px; color:var(--text); background: transparent; }
.nav-link:hover, .nav-link.active { background: var(--panel-3); text-decoration:none; }
.main { padding: 30px; }
.hero { background: linear-gradient(180deg, rgba(125,211,252,.14), rgba(167,139,250,.08)); border:1px solid var(--line); border-radius: 24px; padding: 26px; margin-bottom: 20px; box-shadow: var(--shadow); }
.hero h1 { margin:0 0 10px; font-size: 2rem; }
.hero p { margin:0; color: var(--muted); max-width: 70ch; }
.cards { display:grid; grid-template-columns: repeat(auto-fit, minmax(180px,1fr)); gap: 14px; margin:20px 0; }
.card { background: var(--panel); border:1px solid var(--line); border-radius: 20px; padding: 18px; box-shadow: var(--shadow); }
.card h3 { margin:0 0 6px; font-size:1rem; }
.card p, .muted { color: var(--muted); }
.content { background: var(--panel); border:1px solid var(--line); border-radius: 24px; padding: 28px; box-shadow: var(--shadow); }
.meta { display:flex; flex-wrap:wrap; gap:10px; margin: 0 0 20px; }
.chip { display:inline-flex; align-items:center; gap:6px; border:1px solid var(--line); background: var(--chip); color: var(--muted); border-radius:999px; padding:6px 10px; font-size:.85rem; margin: 0 8px 8px 0; }
article h1, article h2, article h3 { scroll-margin-top: 24px; }
article h1 { font-size: 2rem; margin-top:0; }
article h2 { margin-top: 1.8rem; padding-top: .2rem; border-top:1px solid rgba(148,163,184,.12); }
article p, article li, article blockquote { max-width: 78ch; }
article code { background: rgba(15,23,42,.8); border:1px solid var(--line); border-radius: 8px; padding: .1rem .35rem; }
pre { background:#081120; padding:16px; border-radius:18px; overflow:auto; border:1px solid var(--line); }
blockquote { margin: 1rem 0; padding: 0.2rem 0 0.2rem 1rem; border-left:4px solid var(--brand); color: var(--muted); }
.table-wrap { overflow:auto; }
table { width:100%; border-collapse: collapse; }
th, td { border-bottom:1px solid var(--line); padding:10px 12px; text-align:left; vertical-align:top; }
.aside-grid { display:grid; grid-template-columns: 1.4fr .8fr; gap:20px; }
.panel { background: var(--panel); border:1px solid var(--line); border-radius: 20px; padding: 18px; box-shadow: var(--shadow); }
.panel h3 { margin-top:0; }
.footer { color: var(--muted); margin-top:18px; font-size:.9rem; }
.broken-link { opacity:.7; text-decoration: line-through; }
.search-results { display:grid; gap:10px; margin: 10px 0 18px; }
.result { display:block; padding:12px 14px; border-radius:14px; border:1px solid var(--line); background: var(--panel); }
.result small { color: var(--muted); display:block; }
.note { font-size:.9rem; color: var(--muted); }
@media (max-width: 900px) {
  .topbar { display:flex; align-items:center; justify-content:space-between; padding:14px 16px; position:sticky; top:0; z-index:30; backdrop-filter: blur(18px); background: rgba(2,6,23,.85); border-bottom:1px solid var(--line); }
  .mobile-brand { display:flex; align-items:center; gap:10px; font-weight:700; }
  .menu-btn { appearance:none; border:1px solid var(--line); background: var(--panel); color: var(--text); border-radius:12px; padding:10px 12px; }
  .shell { grid-template-columns: 1fr; }
  .sidebar { position: fixed; inset: 60px 0 0 0; height:auto; transform: translateX(-100%); transition: transform .2s ease; z-index: 40; }
  body.nav-open .sidebar { transform: translateX(0); }
  .main { padding: 18px; }
  .aside-grid { grid-template-columns: 1fr; }
}
'''
(OUT / 'assets' / 'styles.css').write_text(css)

nav_sections = []
for label, files in VISIBLE_GROUPS:
    items = []
    for f in files:
        page = next(p for p in pages if p['path'] == f)
        items.append((page['title'], page['url']))
    nav_sections.append((label, items))
nav_sections.append(('Reference', [(next(p for p in pages if p['path'] == f)['title'], next(p for p in pages if p['path'] == f)['url']) for f in REFERENCE_FILES if f.exists()]))


def build_nav(level='page'):
    prefix = '../' if level == 'page' else ''
    parts = []
    for label, items in nav_sections:
        parts.append(f"<div class='nav-section'><h3>{html.escape(label)}</h3><div class='nav-list'>")
        for title, url in items:
            parts.append(f"<a class='nav-link' href='{prefix}{url}'>{html.escape(title)}</a>")
        parts.append('</div></div>')
    return ''.join(parts)

filters_js = json.dumps([
    {'key': 'all', 'label': 'All'},
    {'key': 'entities', 'label': 'Entities'},
    {'key': 'concepts', 'label': 'Concepts'},
    {'key': 'comparisons', 'label': 'Comparisons'},
    {'key': 'queries', 'label': 'Queries'},
    {'key': 'root', 'label': 'Guides'},
])


def shell_html(main_html: str, title: str, level='page'):
    prefix = '../' if level == 'page' else ''
    search_path = prefix + 'assets/search-index.json'
    nav = build_nav(level)
    generated = datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" /><title>{html.escape(title)} · AI Wiki</title><link rel="stylesheet" href="{prefix}assets/styles.css" /></head>
<body>
<div class="topbar"><div class="mobile-brand"><div class="brand-badge" style="width:28px;height:28px"></div><span>AI Wiki</span></div><button class="menu-btn" id="menuBtn">Menu</button></div>
<div class="shell">
<aside class="sidebar" id="sidebar">
  <div class="brand"><div class="brand-badge"></div><div><h1>AI Wiki</h1><p>Friendly browser for your linked research wiki</p></div></div>
  <input id="search" class="search" placeholder="Search pages, topics, companies…" />
  <div id="filters" class="filter-row"></div>
  <div id="search-results" class="search-results" hidden></div>
  <div class="note">Raw source pages are hidden from the main navigation, but remain available from each page’s source links.</div>
  {nav}
  <div class="footer">Generated {generated}</div>
</aside>
<main class="main">{main_html}</main>
</div>
<script>
const FILTERS = {filters_js};
const input = document.getElementById('search');
const results = document.getElementById('search-results');
const filtersEl = document.getElementById('filters');
const menuBtn = document.getElementById('menuBtn');
let indexCache = null; let activeFilter = 'all';
function renderFilters() {{
  filtersEl.innerHTML = FILTERS.map(f => `<button class="filter-chip ${'{'}f.key === activeFilter ? 'active' : ''{'}'}" data-key="${'{'}f.key{'}'}">${'{'}f.label{'}'}</button>`).join('');
  filtersEl.querySelectorAll('.filter-chip').forEach(btn => btn.addEventListener('click', () => {{ activeFilter = btn.dataset.key; renderFilters(); runSearch(); }}));
}}
async function getIndex() {{ if (indexCache) return indexCache; const res = await fetch('{search_path}'); indexCache = await res.json(); return indexCache; }}
async function runSearch() {{
  const q = input.value.trim().toLowerCase();
  if (!q) {{ results.hidden = true; results.innerHTML = ''; return; }}
  const idx = await getIndex();
  let matches = idx.filter(x => (x.title + ' ' + x.summary + ' ' + x.text + ' ' + x.tags).toLowerCase().includes(q));
  if (activeFilter !== 'all') matches = matches.filter(x => x.category === activeFilter);
  matches = matches.slice(0, 12);
  results.hidden = false;
  results.innerHTML = matches.length ? matches.map(x => `<a class="result" href="{prefix}${'{'}x.url{'}'}"><strong>${'{'}x.title{'}'}</strong><small>${'{'}x.category{'}'}</small><div>${'{'}x.summary{'}'}</div></a>`).join('') : '<div class="result">No results yet.</div>';
}}
input.addEventListener('input', runSearch);
renderFilters();
if (menuBtn) menuBtn.addEventListener('click', () => document.body.classList.toggle('nav-open'));
document.querySelectorAll('.nav-link').forEach(a => a.addEventListener('click', () => document.body.classList.remove('nav-open')));
</script></body></html>'''

counts = {}
for p in visible_pages:
    counts[p['category']] = counts.get(p['category'], 0) + 1
featured = [p for p in visible_pages if p['slug'] in {'start-here', 'comparisons__codex-vs-claude-code-vs-hermes-agent-architecture-trust-moats', 'comparisons__codex-vs-claude-code-and-open-agent-platforms'}]
recent = sorted(visible_pages, key=lambda p: p['path'].stat().st_mtime, reverse=True)[:8]
home_main = f'''<section class="hero"><h1>Explore your AI research wiki</h1><p>A clean, remote-friendly website for browsing entities, concepts, comparisons, and research syntheses. Start with the guided entry points, then use search, filters, and backlinks to move through the graph.</p></section><section class="cards"><div class="card"><h3>{counts.get('entities',0)}</h3><p>Entities</p></div><div class="card"><h3>{counts.get('concepts',0)}</h3><p>Concepts</p></div><div class="card"><h3>{counts.get('comparisons',0)}</h3><p>Comparisons</p></div><div class="card"><h3>{counts.get('queries',0)}</h3><p>Research queries</p></div></section><div class="aside-grid"><section class="panel"><h3>Best places to start</h3>{''.join(f'<a class="result" href="{p["url"]}"><strong>{html.escape(p["title"])}</strong><small>{p["category"]}</small><div>{html.escape(p["summary"])}</div></a>' for p in featured)}</section><section class="panel"><h3>Recently updated</h3>{''.join(f'<a class="result" href="{p["url"]}"><strong>{html.escape(p["title"])}</strong><small>{p["category"]}</small><div>{html.escape(p["summary"])}</div></a>' for p in recent)}</section></div>'''
(OUT / 'index.html').write_text(shell_html(home_main, 'AI Wiki', level='root'))

for p in pages:
    body_html = markdown_to_html(p['body'], level='page')
    meta_bits = []
    if p['category']: meta_bits.append(f'<span class="chip">{html.escape(p["category"])}</span>')
    if p['meta'].get('updated'): meta_bits.append(f'<span class="chip">Updated {html.escape(p["meta"]["updated"])}</span>')
    if p['meta'].get('type'): meta_bits.append(f'<span class="chip">{html.escape(p["meta"]["type"])}</span>')
    sources = p['meta'].get('sources', '').strip()
    source_links = []
    if sources.startswith('[') and sources.endswith(']'):
        items = [x.strip() for x in sources[1:-1].split(',') if x.strip()]
        for item in items:
            href = resolve_wikilink(item.replace('.md', ''))
            if href:
                source_links.append(f'<a class="chip" href="../{href}">{html.escape(Path(item).stem.replace("-", " "))}</a>')
    backlinks = ''.join(f'<a class="result" href="../{q["url"]}"><strong>{html.escape(q["title"])}</strong><small>{q["category"]}</small><div>{html.escape(q["summary"])}</div></a>' for q in p['backlinks'][:10]) or '<div class="muted">No backlinks yet.</div>'
    source_html = ''.join(source_links) or '<span class="muted">No linked source pages.</span>'
    page_main = f'<section class="content"><div class="meta">{"".join(meta_bits)}</div><article>{body_html}</article></section><div class="aside-grid" style="margin-top:20px;"><section class="panel"><h3>Sources</h3>{source_html}</section><section class="panel"><h3>Backlinks</h3>{backlinks}</section></div>'
    out_path = OUT / p['url']
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(shell_html(page_main, p['title'], level='page'))
