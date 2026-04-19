#!/usr/bin/env python3
from __future__ import annotations
import re, json, html
from pathlib import Path
from datetime import datetime

WIKI = Path('/home/gazaz/wiki')
OUT = Path('/home/gazaz/wiki-site')

CONTENT_GROUPS = [
    ('meta', [WIKI / 'start-here.md', WIKI / '_meta' / 'topic-map.md']),
    ('entities', sorted((WIKI / 'entities').glob('*.md'))),
    ('concepts', sorted((WIKI / 'concepts').glob('*.md'))),
    ('comparisons', sorted((WIKI / 'comparisons').glob('*.md'))),
    ('queries', sorted((WIKI / 'queries').glob('*.md'))),
]
OPTIONAL_FILES = [WIKI / 'index.md', WIKI / 'log.md', WIKI / 'SCHEMA.md']
RAW_FILES = sorted((WIKI / 'raw').rglob('*.md'))

OUT.mkdir(parents=True, exist_ok=True)
(OUT / 'pages').mkdir(exist_ok=True)
(OUT / 'assets').mkdir(exist_ok=True)


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
    rel = path.relative_to(WIKI)
    return rel.with_suffix('').as_posix().replace('/', '__')


def page_url(slug: str) -> str:
    return f'pages/{slug}.html'


all_files = []
for _, files in CONTENT_GROUPS:
    all_files.extend(files)
all_files.extend([p for p in OPTIONAL_FILES if p.exists()])
all_files.extend(RAW_FILES)

slug_map = {p.stem: slug_for(p) for p in all_files}
full_slug_map = {p.relative_to(WIKI).with_suffix('').as_posix(): slug_for(p) for p in all_files}


def resolve_wikilink(target: str):
    target = target.strip()
    if target in slug_map:
        return page_url(slug_map[target])
    if target in full_slug_map:
        return page_url(full_slug_map[target])
    return None


def fmt_inline(text: str) -> str:
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
            return f'<a href="../{href}">{label}</a>'
        return f'<span class="broken-link">{label}</span>'

    text = re.sub(r'\[\[([^\]]+)\]\]', wl, text)
    return text


def markdown_to_html(md: str) -> str:
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
            headers = [fmt_inline(c.strip()) for c in table_rows[0].strip('|').split('|')]
            body_rows = table_rows[2:]
            out.append('<div class="table-wrap"><table><thead><tr>' + ''.join(f'<th>{h}</th>' for h in headers) + '</tr></thead><tbody>')
            for row in body_rows:
                cols = [fmt_inline(c.strip()) for c in row.strip('|').split('|')]
                out.append('<tr>' + ''.join(f'<td>{c}</td>' for c in cols) + '</tr>')
            out.append('</tbody></table></div>')
        else:
            for row in table_rows:
                out.append(f'<p>{fmt_inline(row)}</p>')
        table_rows = []
        in_table = False

    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('```'):
            flush_table()
            close_list()
            if not in_code:
                out.append('<pre><code>')
                in_code = True
            else:
                out.append('</code></pre>')
                in_code = False
            i += 1
            continue
        if in_code:
            out.append(html.escape(line) + '\n')
            i += 1
            continue
        if line.strip().startswith('|') and line.count('|') >= 2:
            close_list()
            in_table = True
            table_rows.append(line)
            i += 1
            continue
        else:
            flush_table()
        if not line.strip():
            close_list()
            out.append('')
            i += 1
            continue
        if line.startswith('#'):
            close_list()
            m = re.match(r'^(#{1,6})\s+(.*)$', line)
            if m:
                level = len(m.group(1))
                content = fmt_inline(m.group(2).strip())
                anchor = re.sub(r'[^a-z0-9]+', '-', strip_md(m.group(2).lower())).strip('-')
                out.append(f'<h{level} id="{anchor}">{content}</h{level}>')
                i += 1
                continue
        if re.match(r'^-\s+', line):
            if not in_list:
                out.append('<ul>')
                in_list = True
            item = re.sub(r'^-\s+', '', line)
            out.append(f'<li>{fmt_inline(item)}</li>')
            i += 1
            continue
        if re.match(r'^\d+\.\s+', line):
            close_list()
            items = []
            while i < len(lines) and re.match(r'^\d+\.\s+', lines[i]):
                items.append(re.sub(r'^\d+\.\s+', '', lines[i]))
                i += 1
            out.append('<ol>' + ''.join(f'<li>{fmt_inline(it)}</li>' for it in items) + '</ol>')
            continue
        if line.startswith('>'):
            close_list()
            out.append(f'<blockquote>{fmt_inline(line[1:].strip())}</blockquote>')
            i += 1
            continue
        if line.startswith('---') and set(line.strip()) == {'-'}:
            close_list()
            out.append('<hr />')
            i += 1
            continue
        close_list()
        out.append(f'<p>{fmt_inline(line)}</p>')
        i += 1
    flush_table()
    close_list()
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
for path in all_files:
    text = path.read_text()
    meta, body = parse_frontmatter(text)
    title = meta.get('title') or strip_md(next((ln for ln in body.splitlines() if ln.startswith('# ')), path.stem))
    category = path.parent.name if path.parent != WIKI else 'root'
    slug = slug_for(path)
    pages.append({
        'path': path,
        'slug': slug,
        'title': title,
        'body': body,
        'meta': meta,
        'category': category,
        'url': page_url(slug),
        'summary': extract_summary(body),
    })

page_lookup = {p['slug']: p for p in pages}
for p in pages:
    p['wikilinks'] = re.findall(r'\[\[([^\]|#]+)', p['body'])
for p in pages:
    p['backlinks'] = [q for q in pages if p['path'].stem in q['wikilinks'] and q['slug'] != p['slug']]

css = '''
:root {
  --bg: #0b1020;
  --panel: rgba(17, 24, 39, 0.88);
  --panel-2: rgba(30, 41, 59, 0.72);
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
.shell { display: grid; grid-template-columns: 320px 1fr; min-height: 100vh; }
.sidebar { position: sticky; top: 0; height: 100vh; overflow: auto; background: rgba(2,6,23,0.72); backdrop-filter: blur(18px); border-right: 1px solid var(--line); padding: 20px; }
.brand { display:flex; gap:12px; align-items:center; margin-bottom: 18px; }
.brand-badge { width:44px; height:44px; border-radius:14px; background: linear-gradient(135deg, var(--brand), var(--brand-2)); box-shadow: var(--shadow); }
.brand h1 { font-size: 1.15rem; margin:0; }
.brand p { margin:0; color: var(--muted); font-size:.92rem; }
.search { width:100%; border:1px solid var(--line); background: var(--panel); color:var(--text); border-radius:14px; padding:12px 14px; outline:none; margin: 10px 0 18px; }
.nav-section { margin: 18px 0; }
.nav-section h3 { color: var(--muted); font-size:.8rem; text-transform: uppercase; letter-spacing: .08em; margin: 0 0 8px; }
.nav-list { display:grid; gap:6px; }
.nav-link { display:block; padding:9px 11px; border-radius:12px; color:var(--text); background: transparent; }
.nav-link:hover, .nav-link.active { background: var(--panel-2); text-decoration:none; }
.main { padding: 30px; }
.hero { background: linear-gradient(180deg, rgba(125,211,252,.14), rgba(167,139,250,.08)); border:1px solid var(--line); border-radius: 24px; padding: 26px; margin-bottom: 20px; box-shadow: var(--shadow); }
.hero h1 { margin:0 0 10px; font-size: 2rem; }
.hero p { margin:0; color: var(--muted); max-width: 70ch; }
.cards { display:grid; grid-template-columns: repeat(auto-fit, minmax(220px,1fr)); gap: 14px; margin:20px 0; }
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
@media (max-width: 900px) {
  .shell { grid-template-columns: 1fr; }
  .sidebar { position: relative; height: auto; }
  .main { padding: 18px; }
  .aside-grid { grid-template-columns: 1fr; }
}
'''
(OUT / 'assets' / 'styles.css').write_text(css)

search_index = []
for p in pages:
    if p['category'] == 'raw':
        continue
    text = strip_md(re.sub(r'```.*?```', ' ', p['body'], flags=re.S))
    search_index.append({'title': p['title'], 'url': p['url'], 'category': p['category'], 'summary': p['summary'], 'text': text[:6000]})
(OUT / 'assets' / 'search-index.json').write_text(json.dumps(search_index, indent=2))

nav_sections = []
for section, files in CONTENT_GROUPS:
    items = []
    for f in files:
        s = slug_for(f)
        p = page_lookup[s]
        items.append((p['title'], p['url']))
    nav_sections.append((section.title(), items))
nav_sections.append(('Reference', [('Index', page_url(slug_for(WIKI / 'index.md'))), ('Log', page_url(slug_for(WIKI / 'log.md'))), ('Schema', page_url(slug_for(WIKI / 'SCHEMA.md')))]))

nav_html = '\n'.join(
    f"<div class='nav-section'><h3>{html.escape(name)}</h3><div class='nav-list'>" + ''.join(
        f"<a class='nav-link' href='../{url}'>{html.escape(title)}</a>" for title, url in items
    ) + "</div></div>" for name, items in nav_sections
)


def wrap_page(title: str, main_html: str):
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)} · AI Wiki</title>
  <link rel="stylesheet" href="../assets/styles.css" />
</head>
<body>
<div class="shell">
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-badge"></div>
      <div>
        <h1>AI Wiki</h1>
        <p>Friendly browser for your linked research wiki</p>
      </div>
    </div>
    <input id="search" class="search" placeholder="Search pages, topics, companies…" />
    <div id="search-results" class="search-results" hidden></div>
    {nav_html}
    <div class="footer">Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</div>
  </aside>
  <main class="main">
    {main_html}
  </main>
</div>
<script>
const input = document.getElementById('search');
const results = document.getElementById('search-results');
let indexCache = null;
async function getIndex() {{
  if (indexCache) return indexCache;
  const res = await fetch('../assets/search-index.json');
  indexCache = await res.json();
  return indexCache;
}}
input.addEventListener('input', async (e) => {{
  const q = e.target.value.trim().toLowerCase();
  if (!q) {{ results.hidden = true; results.innerHTML = ''; return; }}
  const idx = await getIndex();
  const matches = idx.filter(x => (x.title + ' ' + x.summary + ' ' + x.text).toLowerCase().includes(q)).slice(0, 10);
  results.hidden = false;
  results.innerHTML = matches.length ? matches.map(x => `<a class="result" href="../${{x.url}}"><strong>${{x.title}}</strong><small>${{x.category}}</small><div>${{x.summary}}</div></a>`).join('') : '<div class="result">No results yet.</div>';
}});
</script>
</body></html>'''

non_raw = [p for p in pages if p['category'] != 'raw']
counts = {}
for p in non_raw:
    counts[p['category']] = counts.get(p['category'], 0) + 1
featured_paths = [
    WIKI / 'start-here.md',
    WIKI / 'comparisons' / 'codex-vs-claude-code-vs-hermes-agent-architecture-trust-moats.md',
    WIKI / 'comparisons' / 'codex-vs-claude-code-and-open-agent-platforms.md',
]
featured = [next(p for p in pages if p['path'] == fp) for fp in featured_paths if fp.exists()]
recent = sorted(non_raw, key=lambda p: p['path'].stat().st_mtime, reverse=True)[:8]
main = f'''
<section class="hero">
  <h1>Explore your AI research wiki</h1>
  <p>A clean, remote-friendly website for browsing entities, concepts, comparisons, and research syntheses. Start with the guided entry points, then use search and backlinks to move through the graph.</p>
</section>
<section class="cards">
  <div class="card"><h3>{counts.get('entities',0)}</h3><p>Entities</p></div>
  <div class="card"><h3>{counts.get('concepts',0)}</h3><p>Concepts</p></div>
  <div class="card"><h3>{counts.get('comparisons',0)}</h3><p>Comparisons</p></div>
  <div class="card"><h3>{counts.get('queries',0)}</h3><p>Research queries</p></div>
</section>
<div class="aside-grid">
  <section class="panel">
    <h3>Best places to start</h3>
    {''.join(f'<a class="result" href="{p["url"]}"><strong>{html.escape(p["title"])}</strong><small>{p["category"]}</small><div>{html.escape(p["summary"])}</div></a>' for p in featured)}
  </section>
  <section class="panel">
    <h3>Recently updated</h3>
    {''.join(f'<a class="result" href="{p["url"]}"><strong>{html.escape(p["title"])}</strong><small>{p["category"]}</small><div>{html.escape(p["summary"])}</div></a>' for p in recent)}
  </section>
</div>
'''
index_nav = nav_html.replace('../', '')
(OUT / 'index.html').write_text(f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" /><title>AI Wiki</title><link rel="stylesheet" href="assets/styles.css" /></head>
<body><div class="shell"><aside class="sidebar"><div class="brand"><div class="brand-badge"></div><div><h1>AI Wiki</h1><p>Friendly browser for your linked research wiki</p></div></div><input id="search" class="search" placeholder="Search pages, topics, companies…" /><div id="search-results" class="search-results" hidden></div>{index_nav}<div class="footer">Generated {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}</div></aside><main class="main">{main}</main></div><script>
const input=document.getElementById('search'); const results=document.getElementById('search-results'); let indexCache=null; async function getIndex(){{ if(indexCache) return indexCache; const res=await fetch('assets/search-index.json'); indexCache=await res.json(); return indexCache; }} input.addEventListener('input', async (e)=>{{ const q=e.target.value.trim().toLowerCase(); if(!q){{results.hidden=true; results.innerHTML=''; return;}} const idx=await getIndex(); const matches=idx.filter(x => (x.title+' '+x.summary+' '+x.text).toLowerCase().includes(q)).slice(0,10); results.hidden=false; results.innerHTML = matches.length ? matches.map(x => `<a class="result" href="${{x.url}}"><strong>${{x.title}}</strong><small>${{x.category}}</small><div>${{x.summary}}</div></a>`).join('') : '<div class="result">No results yet.</div>'; }});
</script></body></html>''')

for p in pages:
    body_html = markdown_to_html(p['body'])
    sources = p['meta'].get('sources', '').strip()
    source_links = []
    if sources.startswith('[') and sources.endswith(']'):
        items = [x.strip() for x in sources[1:-1].split(',') if x.strip()]
        for item in items:
            raw_key = item.replace('.md', '').strip()
            href = resolve_wikilink(raw_key)
            if href:
                label = Path(item).stem.replace('-', ' ')
                source_links.append(f'<a class="chip" href="../{href}">{html.escape(label)}</a>')
    backlinks = ''.join(f'<a class="result" href="../{q["url"]}"><strong>{html.escape(q["title"])}</strong><small>{q["category"]}</small><div>{html.escape(q["summary"])}</div></a>' for q in p['backlinks'][:8]) or '<div class="muted">No backlinks yet.</div>'
    source_html = ''.join(source_links) or '<span class="muted">No linked source pages.</span>'
    meta_bits = []
    if p['category']:
        meta_bits.append(f'<span class="chip">{html.escape(p["category"])}</span>')
    if p['meta'].get('updated'):
        meta_bits.append(f'<span class="chip">Updated {html.escape(p["meta"]["updated"])}</span>')
    if p['meta'].get('type'):
        meta_bits.append(f'<span class="chip">{html.escape(p["meta"]["type"])}</span>')
    page_main = f'''
    <section class="content">
      <div class="meta">{''.join(meta_bits)}</div>
      <article>{body_html}</article>
    </section>
    <div class="aside-grid" style="margin-top:20px;">
      <section class="panel"><h3>Sources</h3>{source_html}</section>
      <section class="panel"><h3>Backlinks</h3>{backlinks}</section>
    </div>
    '''
    out_path = OUT / p['url']
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(wrap_page(p['title'], page_main))

print(f'Generated site with {len(pages)} pages at {OUT}')
