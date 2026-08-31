#!/usr/bin/env python3
"""Playbook page generator for playbooks.reqbeat.com.

Reads targets.csv, pulls live signals from the Reqbeat API, applies quality
gates, renders one static page per agency into docs/, plus a gallery index
and sitemap. Designed to run nightly in GitHub Actions with the API key in
the REQBEAT_API_KEY secret. No other dependencies, stdlib only.

Gates (a page is published only if all pass):
  - company has a domain and is not on the PSL blocklist
  - newest matched req is 14 days old or fresher
  - at least 5 signal rows survive the gates
"""
import csv
import datetime
import io
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).parent
DOCS = ROOT / "docs"
BASE = "https://api.reqbeat.com"
KEY = os.environ.get("REQBEAT_API_KEY", "")
MIN_SIGNALS = 5
MAX_AGE_DAYS = 14
SLEEP_BETWEEN_CALLS = 0.6
# Interim: growth's own Pages URL. Swap to https://playbooks.reqbeat.com only
# once the handoff question is answered and this becomes the real
# publish target: one env var, no code change.
SITE = os.environ.get("SITE_URL", "https://reqbeat-growth.github.io/playbooks")

SIG_ROW = """    <div class="sig">
      <span class="co">%%CO%%</span> <span class="role">&mdash; %%ROLE%%</span>
      <div class="meta">detected on %%BOARD%% &middot; first seen %%SEEN%% &middot; %%REQS%% open reqs &middot; %%SURGE%%</div>
    </div>
"""

GONE_PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8"><meta name="robots" content="noindex">
<title>Page removed</title></head>
<body style="font-family:sans-serif;max-width:660px;margin:80px auto;padding:0 24px;color:#111417">
<p>This page was taken down at the agency's request. Removal happens within 24 hours of any ask.</p>
<p><a href="/">All playbooks</a></p>
</body></html>
"""


def log(event, **kw):
    print(json.dumps({"event": event, **kw}, ensure_ascii=False))


def val(x):
    """Pulse fields arrive wrapped ({value, source_board, observed_at}) or plain."""
    if isinstance(x, dict):
        return x.get("value")
    return x


def api(path, params):
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{BASE}{path}?{qs}", headers={"X-API-Key": KEY})
    for attempt in (1, 2):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt == 1:
                time.sleep(5)
                continue
            log("api_error", path=path, code=e.code)
            return None
        except Exception as e:  # noqa: BLE001 - network failure should not kill the batch
            log("api_error", path=path, error=str(e))
            return None
    return None


def load_targets():
    """Rows from TARGETS_URL (published-sheet CSV) if set, else local targets.csv."""
    url = os.environ.get("TARGETS_URL", "")
    if url:
        with urllib.request.urlopen(url, timeout=30) as r:
            text = r.read().decode("utf-8")
    else:
        text = (ROOT / "targets.csv").read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def load_blocklist():
    p = ROOT / "psl_blocklist.txt"
    if not p.exists():
        return set()
    return {
        line.strip().lower()
        for line in p.read_text().splitlines()
        if line.strip() and not line.startswith("#")
    }


def age_days(iso):
    if not iso:
        return 999
    try:
        d = datetime.date.fromisoformat(iso[:10])
    except ValueError:
        return 999
    return (datetime.date.today() - d).days


def fmt_date(iso):
    try:
        return datetime.date.fromisoformat(iso[:10]).strftime("%d %b").lstrip("0")
    except ValueError:
        return iso[:10]


def esc(s):
    import html as _html

    return _html.escape(str(s or ""), quote=True)


def build_page(row, blocklist, template):
    slug = row["slug"].strip()
    out_dir = DOCS / slug

    if row.get("status", "").strip() == "paused":
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "index.html").write_text(GONE_PAGE)
        return "paused", 0

    data = api(
        "/v1/reqs/search",
        {"role": row["role_query"], "geo": row["geo"], "limit": 15},
    )
    if not data:
        return "api_failed", 0

    sigs = []
    for c in data.get("companies", []):
        dom = (c.get("company_domain") or "").lower()
        if not dom or dom in blocklist:
            continue
        reqs = c.get("matched_reqs") or [{}]
        req0 = reqs[0]
        seen = req0.get("first_seen", "")
        if age_days(seen) > MAX_AGE_DAYS:
            continue
        pulse = c.get("pulse", {})
        title = req0.get("title") or req0.get("raw_title") or "open role"
        boards = req0.get("boards") or ["source board"]
        open_reqs = val(pulse.get("open_req_count")) or 0
        surge = bool(val(pulse.get("is_surge")))
        sigs.append(
            {
                "co": dom.split(".")[0].capitalize(),
                "role": title.strip(),
                "board": boards[0],
                "seen": fmt_date(seen),
                "reqs": open_reqs,
                "surge": surge,
            }
        )

    if len(sigs) < MIN_SIGNALS:
        return "skipped_thin_patch", len(sigs)

    sigs.sort(key=lambda s: (not s["surge"], -s["reqs"]))
    rows_html = ""
    for s in sigs:
        row_html = (
            SIG_ROW.replace("%%CO%%", esc(s["co"]))
            .replace("%%ROLE%%", esc(s["role"]))
            .replace("%%BOARD%%", esc(s["board"]))
            .replace("%%SEEN%%", esc(s["seen"]))
            .replace("%%REQS%%", str(s["reqs"]))
            .replace(
                "%%SURGE%%",
                '<span class="up">&uarr; surge</span>' if s["surge"] else "active",
            )
        )
        rows_html += row_html

    trigger = row.get("trigger_note", "").strip()
    trigger_block = (
        f'<p class="gray" style="margin-top:18px; font-size:14px;">One signal about you: {esc(trigger)}. '
        "An agency investing in growth is planning to win more clients. That is why this page exists.</p>"
        if trigger
        else ""
    )

    today = datetime.date.today()
    page = (
        template.replace("%%AGENCY%%", esc(row["agency_name"]))
        .replace("%%NICHE%%", esc(row["niche_label"]))
        .replace("%%GEO%%", esc(row["geo"]))
        .replace("%%SIGNALS%%", rows_html)
        .replace("%%N_COMPANIES%%", str(len(sigs)))
        .replace("%%N_REQS%%", str(sum(s["reqs"] for s in sigs)))
        .replace("%%N_SURGE%%", str(sum(1 for s in sigs if s["surge"])))
        .replace("%%PULLED%%", today.strftime("%d %b %Y").lstrip("0"))
        .replace("%%YEAR%%", str(today.year))
        .replace("%%SLUG%%", esc(slug))
        .replace("%%SITE%%", SITE)
        .replace("%%TRIGGER_BLOCK%%", trigger_block)
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(page)
    return "generated", len(sigs)


def write_gallery(generated):
    items = ""
    for g in generated:
        items += (
            f'    <div class="sig"><a class="co" href="/{g["slug"]}/">{esc(g["agency"])}</a>'
            f'<div class="meta">{esc(g["niche"])} &middot; {g["n"]} live signals &middot; rebuilt nightly</div></div>\n'
        )
    gallery = (ROOT / "gallery_template.html").read_text().replace("%%ITEMS%%", items)
    gallery = gallery.replace("%%PULLED%%", datetime.date.today().strftime("%d %b %Y").lstrip("0"))
    (DOCS / "index.html").write_text(gallery)

    urls = [f"{SITE}/"] + [f"{SITE}/{g['slug']}/" for g in generated]
    sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
    for u in urls:
        sm += f"  <url><loc>{u}</loc></url>\n"
    sm += "</urlset>\n"
    (DOCS / "sitemap.xml").write_text(sm)

    (DOCS / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n")


def main():
    if not KEY:
        print("REQBEAT_API_KEY is not set", file=sys.stderr)
        sys.exit(1)

    template = (ROOT / "template.html").read_text()
    blocklist = load_blocklist()
    DOCS.mkdir(exist_ok=True)

    generated = []
    for row in load_targets():
        slug = (row.get("slug") or "").strip()
        status = (row.get("status") or "").strip()
        if not slug or status not in ("ready", "generated", "paused"):
            continue
        outcome, n = build_page(row, blocklist, template)
        log("page", slug=slug, outcome=outcome, signals=n)
        if outcome == "generated":
            generated.append(
                {"slug": slug, "agency": row["agency_name"], "niche": row["niche_label"], "n": n}
            )
        time.sleep(SLEEP_BETWEEN_CALLS)

    write_gallery(generated)
    log("done", pages=len(generated))


if __name__ == "__main__":
    main()
