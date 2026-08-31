#!/usr/bin/env python3
"""Qualify targets.csv against the live corpus. Read-only, writes nothing.

Two checks per row:

  1. Person B   is the agency ITSELF hiring an ops, RevOps, automation or
                growth role right now? This is the strongest evidence there
                is, and it is the one channel web research cannot cover.
  2. Depth      would a page for this row survive the five-signal gate?
                Runs the same query generate.py would run and counts what
                gets through the domain, blocklist and freshness gates.

Usage:
    export REQBEAT_API_KEY="..."          # from your password manager
    python3 qualify.py                     # all rows
    python3 qualify.py searchability       # one row by slug

Nothing is written back. Read the output, then set status=ready by hand on
the rows you want live.
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
BASE = "https://api.reqbeat.com"
KEY = os.environ.get("REQBEAT_API_KEY", "")
MIN_SIGNALS = 5
MAX_AGE_DAYS = 14

# Titles that mean a technical operator, not back-office administration.
# Deliberately narrow: "Operations Director" at a recruitment agency usually
# means contracts and payroll, so it does not appear here.
OPS_ROLES = [
    "revenue operations",
    "sales operations",
    "marketing operations",
    "growth engineer",
    "automation",
]


def api(path, params):
    if not KEY:
        sys.exit("REQBEAT_API_KEY is not set")
    qs = urllib.parse.urlencode(params)
    req = urllib.request.Request(f"{BASE}{path}?{qs}", headers={"X-API-Key": KEY})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"_error": f"HTTP {e.code}"}
    except Exception as e:  # noqa: BLE001
        return {"_error": str(e)}


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
        d = datetime.date.fromisoformat(str(iso)[:10])
    except ValueError:
        return 999
    return (datetime.date.today() - d).days


def check_depth(row, blocklist):
    """Count how many signals survive the same gates generate.py applies."""
    data = api("/v1/reqs/search", {"role": row["role_query"], "geo": row["geo"], "limit": 15})
    if "_error" in data:
        return None, data["_error"]
    kept = 0
    for c in data.get("companies", []):
        dom = (c.get("company_domain") or "").lower()
        if not dom or dom in blocklist:
            continue
        req0 = (c.get("matched_reqs") or [{}])[0]
        if age_days(req0.get("first_seen")) > MAX_AGE_DAYS:
            continue
        kept += 1
    return kept, None


def check_person_b(row):
    """Is this agency itself hiring an ops or automation role?

    Searches the corpus for each ops title in the agency's country, then
    looks for the agency's own domain among the results.
    """
    domain = row["agency_domain"].lower().strip()
    hits = []
    for title in OPS_ROLES:
        data = api("/v1/reqs/search", {"role": title, "geo": row["geo"], "limit": 25})
        if "_error" in data:
            continue
        for c in data.get("companies", []):
            if (c.get("company_domain") or "").lower() == domain:
                req0 = (c.get("matched_reqs") or [{}])[0]
                hits.append({
                    "searched": title,
                    "title": req0.get("title") or req0.get("raw_title"),
                    "first_seen": str(req0.get("first_seen", ""))[:10],
                })
        time.sleep(0.6)
    return hits


def load_targets():
    """Rows from TARGETS_URL (published-sheet CSV) if set, else local targets.csv."""
    url = os.environ.get("TARGETS_URL", "")
    if url:
        with urllib.request.urlopen(url, timeout=30) as r:
            text = r.read().decode("utf-8")
    else:
        text = (ROOT / "targets.csv").read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else None
    blocklist = load_blocklist()
    rows = load_targets()
    if only:
        rows = [r for r in rows if r["slug"] == only]
        if not rows:
            sys.exit(f"no row with slug {only}")

    print(f"{'slug':<28} {'signals':>7}  {'gate':<6}  person B")
    print("-" * 88)
    calls = 0
    for row in rows:
        depth, err = check_depth(row, blocklist)
        calls += 1
        if err:
            print(f"{row['slug']:<28} {'-':>7}  {'ERR':<6}  {err}")
            continue
        gate = "PASS" if depth >= MIN_SIGNALS else "THIN"
        hits = check_person_b(row)
        calls += len(OPS_ROLES)
        if hits:
            note = "HIRING OPS: " + "; ".join(
                f"{h['title']} seen {h['first_seen']}" for h in hits
            )
        else:
            note = "no ops role in corpus right now"
        print(f"{row['slug']:<28} {depth:>7}  {gate:<6}  {note}")
        time.sleep(0.6)

    print("-" * 88)
    print(f"{calls} API calls used. Free tier allows 100 per rolling 24h.")
    print("THIN means a page would not publish; change role_query or drop the row.")
    print("HIRING OPS is the strongest person-B evidence there is. Promote those rows first.")


if __name__ == "__main__":
    main()
