#!/usr/bin/env python3
"""Local demo run of generate.py's exact page-building logic, using sample
data in place of a live API call (this sandbox has no network path to
api.reqbeat.com). Produces the same docs/{slug}/index.html + docs/index.html
gallery the real nightly build would, so the format and gates can be
inspected without a key. Every generated page carries a visible demo banner
so it is never mistaken for a live pull.

Sample company names below are fictional placeholders, not real companies.
"""
import datetime
import sys

sys.path.insert(0, ".")
import generate as g  # noqa: E402

TODAY = datetime.date.today()


def days_ago(n):
    return (TODAY - datetime.timedelta(days=n)).isoformat()


# Shape matches the real /v1/reqs/search response, confirmed against live
# curl output during the getting-started smoke test.
SAMPLE_COMPANIES = [
    {
        "company_domain": "northbridge-analytics.co.uk",
        "matched_reqs": [{"title": "Account Executive", "boards": ["greenhouse"], "first_seen": days_ago(2)}],
        "pulse": {"open_req_count": 4, "is_surge": True},
    },
    {
        "company_domain": "quillfield.co",
        "matched_reqs": [{"title": "Sales Development Rep", "boards": ["lever"], "first_seen": days_ago(1)}],
        "pulse": {"open_req_count": 6, "is_surge": True},
    },
    {
        "company_domain": "harborlane.io",
        "matched_reqs": [{"title": "Enterprise Sales Manager", "boards": ["ashby"], "first_seen": days_ago(5)}],
        "pulse": {"open_req_count": 2, "is_surge": False},
    },
    {
        "company_domain": "marrowdata.co.uk",
        "matched_reqs": [{"title": "Sales Ops Lead", "boards": ["workable"], "first_seen": days_ago(3)}],
        "pulse": {"open_req_count": 3, "is_surge": False},
    },
    {
        "company_domain": "redstonecloud.io",
        "matched_reqs": [{"title": "Mid-Market AE", "boards": ["greenhouse"], "first_seen": days_ago(8)}],
        "pulse": {"open_req_count": 1, "is_surge": False},
    },
    {
        "company_domain": "fenwickops.com",
        "matched_reqs": [{"title": "Head of Sales", "boards": ["lever"], "first_seen": days_ago(10)}],
        "pulse": {"open_req_count": 2, "is_surge": True},
    },
]

DEMO_BANNER = (
    '<div style="background:#111417;color:#fff;font-family:ui-monospace,'
    "SFMono-Regular,Menlo,Consolas,monospace;font-size:12px;padding:10px 24px;"
    'text-align:center;letter-spacing:.02em">'
    "DEMO BUILD &mdash; sample companies, not a live API pull. "
    "Real nightly build replaces this banner entirely.</div>"
)


def fake_api(path, params):
    g.log("mock_api_call", path=path, params=params)
    return {"companies": SAMPLE_COMPANIES}


def main():
    g.api = fake_api  # swap the network call, nothing else in generate.py changes
    template = (g.ROOT / "template.html").read_text()
    blocklist = g.load_blocklist()
    g.DOCS.mkdir(exist_ok=True)

    generated = []
    import csv

    with open(g.ROOT / "targets.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            slug = (row.get("slug") or "").strip()
            status = (row.get("status") or "").strip()
            if not slug or status not in ("ready", "generated", "paused"):
                continue
            outcome, n = g.build_page(row, blocklist, template)
            g.log("page", slug=slug, outcome=outcome, signals=n)
            if outcome == "generated":
                generated.append({"slug": slug, "agency": row["agency_name"], "niche": row["niche_label"], "n": n})
                # stamp the demo banner into the page that was just written
                out = g.DOCS / slug / "index.html"
                html = out.read_text()
                out.write_text(html.replace("<body>", "<body>\n" + DEMO_BANNER))

    g.write_gallery(generated)
    gallery = g.DOCS / "index.html"
    gallery.write_text(gallery.read_text().replace("<body>", "<body>\n" + DEMO_BANNER))
    g.log("done", pages=len(generated))


if __name__ == "__main__":
    main()
