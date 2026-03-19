"""
selector_audit.py — Selector Audit Report Generator
=====================================================
Fetches every active site from the DB, tests its selectors live,
and produces a polished selector_report.html.

Usage:
    python selector_audit.py                    # audit all active sites
    python selector_audit.py --limit 50         # first 50 sites
    python selector_audit.py --from-id 1 --to-id 100
    python selector_audit.py --include-inactive # include disabled sites too
    python selector_audit.py --output my_report.html
"""

import argparse
import sys
import os
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin

import requests
import certifi
from bs4 import BeautifulSoup

sys.path.insert(0, ".")
from database import get_connection
from logger import get_logger

log = get_logger("selector_audit")

FETCH_TIMEOUT = 8
MAX_WORKERS   = 20
OUTPUT_FILE   = "selector_report.html"
HEADERS       = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}


# =============================================================================
# DATA FETCHING
# =============================================================================

def get_sites(id_from=None, id_to=None, include_inactive=False, limit=None):
    conn = get_connection()
    try:
        cursor = conn.cursor(dictionary=True)
        where  = [] if include_inactive else ["1=1"]
        params = []

        if not include_inactive:
            where = ["active IN (0,1)"]   # all sites
        if id_from and id_to:
            where.append("id BETWEEN %s AND %s")
            params += [id_from, id_to]

        q = f"SELECT * FROM news_sites WHERE {' AND '.join(where)} ORDER BY id"
        if limit:
            q += f" LIMIT {int(limit)}"
        cursor.execute(q, params)
        return cursor.fetchall()
    finally:
        conn.close()


# =============================================================================
# LIVE SELECTOR TESTING
# =============================================================================

def fetch(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=FETCH_TIMEOUT,
                         verify=certifi.where())
        r.encoding = "utf-8"
        return r.text
    except requests.exceptions.SSLError:
        try:
            r = requests.get(url, headers=HEADERS, timeout=FETCH_TIMEOUT,
                             verify=False)
            r.encoding = "utf-8"
            return r.text
        except Exception:
            return None
    except Exception:
        return None


def audit_site(site):
    result = {
        "id":               site["id"],
        "name":             site["name"],
        "base_url":         site["base_url"],
        "active":           site["active"],
        "engine_type":      site.get("engine_type", "custom"),
        "article_selector": site.get("article_selector") or "",
        "title_selector":   site.get("title_selector")   or "",
        "content_selector": site.get("content_selector") or "",
        "success_count":    site.get("success_count", 0),
        "failure_count":    site.get("failure_count", 0),
        "stability_score":  site.get("stability_score", 0),
        "last_scraped":     site.get("last_scraped"),
        "last_error":       site.get("last_error") or "",
        # audit results
        "reachable":         False,
        "article_matches":   0,
        "title_ok":          False,
        "content_ok":        False,
        "sample_url":        "",
        "title_snippet":     "",
        "content_snippet":   "",
        "error":             "",
        "status":            "unknown",
    }

    art_sel  = result["article_selector"]
    ttl_sel  = result["title_selector"]
    cnt_sel  = result["content_selector"]

    # ── Fetch homepage ────────────────────────────────────────────────────────
    html = fetch(result["base_url"])
    if not html:
        result["error"]  = "Homepage unreachable (DNS/timeout/SSL)"
        result["status"] = "dead"
        return result

    result["reachable"] = True
    soup = BeautifulSoup(html, "html.parser")

    # ── Article selector ──────────────────────────────────────────────────────
    if art_sel:
        try:
            links = []
            for a in soup.select(art_sel):
                href = a.get("href")
                if href:
                    full = urljoin(result["base_url"], href)
                    if result["base_url"].split("//")[-1].split("/")[0] in full:
                        links.append(full)
            result["article_matches"] = len(links)
        except Exception as e:
            result["error"] = f"Article selector error: {e}"
    else:
        result["error"] = "No article selector stored"

    # ── Test title + content on first article ─────────────────────────────────
    sample_url = ""
    if result["article_matches"] > 0:
        sample_url = links[0]
        result["sample_url"] = sample_url

        article_html = fetch(sample_url)
        if article_html:
            asoup = BeautifulSoup(article_html, "html.parser")

            # Title
            if ttl_sel:
                try:
                    el = asoup.select_one(ttl_sel)
                    if el:
                        txt = el.get_text(strip=True)
                        if len(txt) > 5:
                            result["title_ok"]      = True
                            result["title_snippet"] = txt[:120]
                except Exception:
                    pass

            # Content
            if cnt_sel:
                try:
                    el = asoup.select_one(cnt_sel)
                    if el:
                        txt = el.get_text(strip=True)
                        if len(txt) > 50:
                            result["content_ok"]      = True
                            result["content_snippet"] = txt[:200]
                except Exception:
                    pass

    # ── Determine overall status ──────────────────────────────────────────────
    if not result["reachable"]:
        result["status"] = "dead"
    elif not art_sel or not ttl_sel or not cnt_sel:
        result["status"] = "no_selectors"
    elif result["article_matches"] == 0:
        result["status"] = "no_links"
    elif result["title_ok"] and result["content_ok"]:
        result["status"] = "ok"
    elif result["title_ok"] or result["content_ok"]:
        result["status"] = "partial"
    else:
        result["status"] = "broken"

    return result


# =============================================================================
# HTML REPORT
# =============================================================================

STATUS_META = {
    "ok":           ("✓ Working",       "#22c55e", "#dcfce7"),
    "partial":      ("⚡ Partial",       "#f59e0b", "#fef3c7"),
    "broken":       ("✗ Broken",        "#ef4444", "#fee2e2"),
    "no_links":     ("○ No Links",      "#8b5cf6", "#ede9fe"),
    "no_selectors": ("◌ No Selectors",  "#6b7280", "#f3f4f6"),
    "dead":         ("✗ Dead Site",     "#dc2626", "#fef2f2"),
    "unknown":      ("? Unknown",       "#9ca3af", "#f9fafb"),
}

def _esc(text):
    return (str(text)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def build_html(results, generated_at):
    total      = len(results)
    ok         = sum(1 for r in results if r["status"] == "ok")
    partial    = sum(1 for r in results if r["status"] == "partial")
    broken     = sum(1 for r in results if r["status"] in ("broken", "no_links"))
    dead       = sum(1 for r in results if r["status"] == "dead")
    no_sel     = sum(1 for r in results if r["status"] == "no_selectors")

    # Summary cards
    cards = [
        ("Total Sites",    total,   "#1e293b", "#f8fafc"),
        ("✓ Working",      ok,      "#166534", "#dcfce7"),
        ("⚡ Partial",     partial, "#92400e", "#fef3c7"),
        ("✗ Broken",       broken,  "#991b1b", "#fee2e2"),
        ("✗ Dead",         dead,    "#7f1d1d", "#fef2f2"),
        ("◌ No Selectors", no_sel,  "#374151", "#f3f4f6"),
    ]

    cards_html = "".join(f"""
        <div class="card" style="background:{bg};color:{fg}">
            <div class="card-num">{num}</div>
            <div class="card-label">{_esc(label)}</div>
        </div>""" for label, num, fg, bg in cards)

    # Table rows
    rows_html = ""
    for r in results:
        label, color, bg = STATUS_META.get(r["status"], STATUS_META["unknown"])
        active_badge = (
            '<span class="badge badge-on">Active</span>'
            if r["active"] else
            '<span class="badge badge-off">Disabled</span>'
        )
        art_cell = (
            f'<span class="match-num">{r["article_matches"]}</span>'
            if r["article_matches"] > 0 else
            '<span class="match-zero">0</span>'
        )
        chk = lambda v: '✓' if v else '✗'
        ok_cls = lambda v: 'cell-ok' if v else 'cell-fail'

        sample = (f'<a href="{_esc(r["sample_url"])}" target="_blank" '
                  f'class="sample-link">{_esc(r["sample_url"][:55])}…</a>'
                  if r["sample_url"] else '<span class="na">—</span>')

        title_snip   = _esc(r["title_snippet"])   or '<span class="na">—</span>'
        content_snip = _esc(r["content_snippet"])  or '<span class="na">—</span>'

        sel_info = (
            f'<div class="sel-row"><span class="sel-label">Art</span>'
            f'<code>{_esc(r["article_selector"][:50]) or "—"}</code></div>'
            f'<div class="sel-row"><span class="sel-label">Ttl</span>'
            f'<code>{_esc(r["title_selector"][:50]) or "—"}</code></div>'
            f'<div class="sel-row"><span class="sel-label">Cnt</span>'
            f'<code>{_esc(r["content_selector"][:50]) or "—"}</code></div>'
        )

        score = r.get("stability_score") or 0
        score_pct = int(float(score) * 100)
        score_color = "#22c55e" if score_pct >= 80 else "#f59e0b" if score_pct >= 40 else "#ef4444"

        last_scraped = str(r["last_scraped"])[:16] if r["last_scraped"] else "Never"

        rows_html += f"""
        <tr>
            <td>
                <div class="site-name">{_esc(r["name"][:40])}</div>
                <div class="site-url">
                    <a href="{_esc(r["base_url"])}" target="_blank">{_esc(r["base_url"])}</a>
                </div>
                <div class="site-meta">ID:{r["id"]} · {_esc(r["engine_type"])} · {active_badge}</div>
                <div class="site-meta">Scraped: {last_scraped}</div>
            </td>
            <td>
                <span class="status-pill" style="background:{bg};color:{color};border-color:{color}">
                    {label}
                </span>
                <div style="margin-top:6px">
                    <div class="score-bar">
                        <div class="score-fill" style="width:{score_pct}%;background:{score_color}"></div>
                    </div>
                    <div class="score-label">{score_pct}% stable</div>
                </div>
            </td>
            <td>{art_cell}</td>
            <td class="{ok_cls(r['title_ok'])}">{chk(r['title_ok'])}</td>
            <td class="{ok_cls(r['content_ok'])}">{chk(r['content_ok'])}</td>
            <td class="sel-cell">{sel_info}</td>
            <td class="sample-cell">{sample}</td>
            <td class="snippet-cell"><div class="snippet">{title_snip}</div></td>
            <td class="snippet-cell"><div class="snippet">{content_snip}</div></td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Selector Audit Report</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600&family=Sora:wght@300;400;600;700&display=swap');

  :root {{
    --bg:        #0f172a;
    --surface:   #1e293b;
    --surface2:  #263348;
    --border:    #334155;
    --text:      #e2e8f0;
    --muted:     #94a3b8;
    --accent:    #38bdf8;
    --ok:        #22c55e;
    --fail:      #ef4444;
    --warn:      #f59e0b;
    --radius:    10px;
    --mono:      'JetBrains Mono', monospace;
    --sans:      'Sora', sans-serif;
  }}

  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    font-family: var(--sans);
    background: var(--bg);
    color: var(--text);
    min-height: 100vh;
    padding: 32px 24px;
  }}

  /* ── Header ── */
  .header {{
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    margin-bottom: 32px;
    padding-bottom: 24px;
    border-bottom: 1px solid var(--border);
  }}
  .header-title {{
    font-size: 28px;
    font-weight: 700;
    letter-spacing: -0.5px;
    color: #f1f5f9;
  }}
  .header-title span {{ color: var(--accent); }}
  .header-sub {{
    font-size: 13px;
    color: var(--muted);
    margin-top: 4px;
    font-weight: 300;
  }}
  .header-time {{
    font-family: var(--mono);
    font-size: 12px;
    color: var(--muted);
    text-align: right;
  }}

  /* ── Summary cards ── */
  .cards {{
    display: flex;
    gap: 12px;
    flex-wrap: wrap;
    margin-bottom: 28px;
  }}
  .card {{
    border-radius: var(--radius);
    padding: 16px 20px;
    min-width: 130px;
    flex: 1;
  }}
  .card-num {{
    font-size: 32px;
    font-weight: 700;
    font-family: var(--mono);
    line-height: 1;
  }}
  .card-label {{
    font-size: 12px;
    margin-top: 6px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    opacity: 0.8;
  }}

  /* ── Filter bar ── */
  .filters {{
    display: flex;
    gap: 10px;
    margin-bottom: 20px;
    flex-wrap: wrap;
    align-items: center;
  }}
  .filter-btn {{
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--muted);
    padding: 6px 14px;
    border-radius: 20px;
    font-size: 12px;
    font-family: var(--sans);
    cursor: pointer;
    transition: all 0.15s;
    font-weight: 600;
  }}
  .filter-btn:hover, .filter-btn.active {{
    background: var(--accent);
    border-color: var(--accent);
    color: #0f172a;
  }}
  .search-box {{
    background: var(--surface);
    border: 1px solid var(--border);
    color: var(--text);
    padding: 6px 14px;
    border-radius: 20px;
    font-size: 13px;
    font-family: var(--sans);
    outline: none;
    width: 240px;
    margin-left: auto;
  }}
  .search-box:focus {{ border-color: var(--accent); }}
  .search-box::placeholder {{ color: var(--muted); }}

  /* ── Table ── */
  .table-wrap {{
    background: var(--surface);
    border-radius: var(--radius);
    border: 1px solid var(--border);
    overflow-x: auto;
  }}
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }}
  thead th {{
    background: var(--surface2);
    padding: 12px 14px;
    text-align: left;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: var(--muted);
    white-space: nowrap;
    border-bottom: 1px solid var(--border);
    position: sticky;
    top: 0;
    z-index: 10;
  }}
  tbody tr {{
    border-bottom: 1px solid var(--border);
    transition: background 0.1s;
  }}
  tbody tr:last-child {{ border-bottom: none; }}
  tbody tr:hover {{ background: rgba(56,189,248,0.04); }}
  td {{ padding: 12px 14px; vertical-align: top; }}

  /* ── Site cell ── */
  .site-name {{
    font-weight: 600;
    color: #f1f5f9;
    font-size: 13px;
    margin-bottom: 3px;
  }}
  .site-url a {{
    color: var(--accent);
    text-decoration: none;
    font-size: 11px;
    font-family: var(--mono);
  }}
  .site-url a:hover {{ text-decoration: underline; }}
  .site-meta {{
    font-size: 11px;
    color: var(--muted);
    margin-top: 3px;
  }}

  /* ── Status pill ── */
  .status-pill {{
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    border: 1px solid;
    letter-spacing: 0.3px;
    white-space: nowrap;
  }}

  /* ── Stability bar ── */
  .score-bar {{
    width: 80px;
    height: 4px;
    background: var(--border);
    border-radius: 2px;
    overflow: hidden;
    margin-top: 4px;
  }}
  .score-fill {{
    height: 100%;
    border-radius: 2px;
    transition: width 0.3s;
  }}
  .score-label {{
    font-size: 10px;
    color: var(--muted);
    margin-top: 2px;
    font-family: var(--mono);
  }}

  /* ── Match counts ── */
  .match-num {{
    background: rgba(34,197,94,0.15);
    color: var(--ok);
    font-family: var(--mono);
    font-weight: 700;
    font-size: 14px;
    padding: 2px 8px;
    border-radius: 6px;
  }}
  .match-zero {{
    background: rgba(239,68,68,0.15);
    color: var(--fail);
    font-family: var(--mono);
    font-weight: 700;
    font-size: 14px;
    padding: 2px 8px;
    border-radius: 6px;
  }}

  /* ── OK/Fail cells ── */
  .cell-ok   {{ color: var(--ok);   font-weight: 700; font-size: 16px; text-align: center; }}
  .cell-fail {{ color: var(--fail); font-weight: 700; font-size: 16px; text-align: center; }}

  /* ── Selector cell ── */
  .sel-cell {{ min-width: 200px; }}
  .sel-row {{ display: flex; align-items: baseline; gap: 6px; margin-bottom: 4px; }}
  .sel-label {{
    font-size: 9px;
    font-weight: 700;
    text-transform: uppercase;
    color: var(--muted);
    min-width: 24px;
    letter-spacing: 0.5px;
  }}
  code {{
    font-family: var(--mono);
    font-size: 10px;
    background: rgba(15,23,42,0.6);
    padding: 1px 5px;
    border-radius: 4px;
    color: #93c5fd;
    word-break: break-all;
  }}

  /* ── Sample URL ── */
  .sample-cell {{ min-width: 160px; max-width: 220px; }}
  .sample-link {{
    color: var(--accent);
    text-decoration: none;
    font-size: 11px;
    font-family: var(--mono);
    word-break: break-all;
    display: block;
  }}
  .sample-link:hover {{ text-decoration: underline; }}

  /* ── Snippet ── */
  .snippet-cell {{ min-width: 180px; max-width: 260px; }}
  .snippet {{
    font-size: 12px;
    color: var(--muted);
    line-height: 1.5;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }}

  /* ── Badges ── */
  .badge {{
    display: inline-block;
    font-size: 10px;
    font-weight: 700;
    padding: 1px 7px;
    border-radius: 10px;
    letter-spacing: 0.3px;
  }}
  .badge-on  {{ background: rgba(34,197,94,0.2);  color: var(--ok);  }}
  .badge-off {{ background: rgba(239,68,68,0.2);  color: var(--fail); }}

  .na {{ color: var(--border); font-style: italic; font-size: 12px; }}

  /* ── Row hidden by filter ── */
  tr.hidden {{ display: none; }}

  /* ── Footer ── */
  .footer {{
    text-align: center;
    margin-top: 28px;
    font-size: 12px;
    color: var(--muted);
    font-weight: 300;
  }}
</style>
</head>
<body>

<div class="header">
  <div>
    <div class="header-title">Selector <span>Audit</span> Report</div>
    <div class="header-sub">Nepal News Scraper · Live selector health check across all sites</div>
  </div>
  <div class="header-time">
    Generated<br>{_esc(generated_at)}
  </div>
</div>

<div class="cards">{cards_html}</div>

<div class="filters">
  <button class="filter-btn active" onclick="filterStatus('all', this)">All</button>
  <button class="filter-btn" onclick="filterStatus('ok', this)">✓ Working</button>
  <button class="filter-btn" onclick="filterStatus('partial', this)">⚡ Partial</button>
  <button class="filter-btn" onclick="filterStatus('broken', this)">✗ Broken</button>
  <button class="filter-btn" onclick="filterStatus('dead', this)">✗ Dead</button>
  <button class="filter-btn" onclick="filterStatus('no_selectors', this)">◌ No Selectors</button>
  <button class="filter-btn" onclick="filterStatus('no_links', this)">○ No Links</button>
  <input class="search-box" type="text" placeholder="Search site name or URL…"
         oninput="filterSearch(this.value)" id="searchBox">
</div>

<div class="table-wrap">
  <table id="auditTable">
    <thead>
      <tr>
        <th>Site</th>
        <th>Status</th>
        <th>Article<br>Matches</th>
        <th style="text-align:center">Title<br>Match</th>
        <th style="text-align:center">Content<br>Match</th>
        <th>Selectors</th>
        <th>Sample URL</th>
        <th>Title Snippet</th>
        <th>Content Snippet</th>
      </tr>
    </thead>
    <tbody id="tableBody">
      {rows_html}
    </tbody>
  </table>
</div>

<div class="footer">
  Nepal News Scraper · Selector Audit Report · {_esc(generated_at)}
</div>

<script>
  let currentStatus = 'all';
  let currentSearch = '';

  function applyFilters() {{
    const rows = document.querySelectorAll('#tableBody tr');
    rows.forEach(row => {{
      const status  = row.dataset.status || '';
      const text    = row.textContent.toLowerCase();
      const matchSt = currentStatus === 'all' || status === currentStatus;
      const matchSr = !currentSearch || text.includes(currentSearch.toLowerCase());
      row.classList.toggle('hidden', !(matchSt && matchSr));
    }});
  }}

  function filterStatus(status, btn) {{
    currentStatus = status;
    document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    applyFilters();
  }}

  function filterSearch(val) {{
    currentSearch = val;
    applyFilters();
  }}
</script>

</body>
</html>"""


# Inject data-status on each <tr> after building HTML
def inject_status_attrs(html, results):
    for r in results:
        status = r["status"]
        html = html.replace(
            f'<tr>\n        <td>\n            <div class="site-name">{_esc(r["name"][:40])}',
            f'<tr data-status="{status}">\n        <td>\n            <div class="site-name">{_esc(r["name"][:40])}',
            1
        )
    return html


# =============================================================================
# MAIN
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="Generate Selector Audit Report")
    parser.add_argument("--from-id",         type=int,  default=None)
    parser.add_argument("--to-id",           type=int,  default=None)
    parser.add_argument("--limit",           type=int,  default=None)
    parser.add_argument("--workers",         type=int,  default=MAX_WORKERS)
    parser.add_argument("--include-inactive",action="store_true")
    parser.add_argument("--output",          type=str,  default=OUTPUT_FILE)
    args = parser.parse_args()

    sites = get_sites(
        id_from=args.from_id,
        id_to=args.to_id,
        include_inactive=args.include_inactive,
        limit=args.limit,
    )
    log.info("Auditing %d sites with %d workers…", len(sites), args.workers)

    results   = []
    completed = 0

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        future_to_site = {executor.submit(audit_site, s): s for s in sites}
        for future in as_completed(future_to_site):
            completed += 1
            site = future_to_site[future]
            try:
                r = future.result()
                results.append(r)
                log.info("[%d/%d] %s → %s (%d links)",
                         completed, len(sites),
                         site["name"][:40], r["status"], r["article_matches"])
            except Exception as e:
                log.error("Audit failed for %s: %s", site["name"], e)

    # Sort: dead/broken first, then by stability score
    status_order = {"dead": 0, "broken": 1, "no_links": 2, "partial": 3,
                    "no_selectors": 4, "ok": 5, "unknown": 6}
    results.sort(key=lambda r: (status_order.get(r["status"], 9),
                                -(r.get("stability_score") or 0)))

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    html = build_html(results, generated_at)
    html = inject_status_attrs(html, results)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(html)

    ok      = sum(1 for r in results if r["status"] == "ok")
    broken  = sum(1 for r in results if r["status"] in ("broken", "dead", "no_links"))
    log.info("Report written → %s  (%d ok / %d broken / %d total)",
             args.output, ok, broken, len(results))
    print(f"\n✓ Report saved: {os.path.abspath(args.output)}")


if __name__ == "__main__":
    main()
