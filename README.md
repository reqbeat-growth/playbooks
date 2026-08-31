# BD playbooks: growth's interim build

Static per-agency BD playbook pages, generated nightly from the live Reqbeat API. One row in the target sheet = one page at `/{slug}/`. No servers, no framework, stdlib Python only.

This repo publishes to growth's own GitHub Pages for now, not `playbooks.reqbeat.com`. That subdomain is planned to be served from elsewhere, so until the handoff is defined, this repo is how growth ships pages and runs outreach without waiting on it. See **Migrating to playbooks.reqbeat.com** below.

## The full loop, atom by atom

```
1. Define ECP/ICP          which agencies to target (niche, geo, size, person B)
        │
2. Source agencies          directories → name, domain, niche, person_b_evidence
        │
3. Map to target sheet      ~30 sec/row: slug, role_query, geo, one verified trigger_note
        │
4. generate.py               1 call/agency → /v1/reqs/search (pulse comes embedded)
        │                    quality gates: domain present, not on PSL blocklist,
        │                    freshest req ≤ 14 days, ≥ 5 signals or no page at all
        ▼
5. docs/{slug}/index.html + docs/index.html (gallery) + sitemap.xml + robots.txt
        │
6. git push → GitHub Pages auto-deploy (~1 min)
        │
7. Find the operator         LinkedIn: ops, RevOps or automation owner, or a technical founder
        │
8. Send the DFY opener       link only, page carries the value (template below)
        ▼
9. They click → page          pre-built, personalized, live signals, no login, no ask
        │
10. CTA → reqbeat.com signup  utm_source=playbooks&utm_content={slug} → attributed
```

Steps 1-3 are the only manual work. 4-6 are one command. 7-8 repeat per agency. 9-10 run themselves.

## The opener (step 8)

This is not the standard first-touch format from `signal-first-outreach`: that skill's rule is deliberately no link in the first message, because the message itself has to carry the value. Here the link *is* the value, so the message is short and points at it:

> Built [Agency name] a live page: [URL]. [N] [niche] roles that opened in [geo] this week, company names and dates, no login. Ten more free where that came from if it's useful.

Rules: only send once the page is actually live (never promise a page that failed the signal gate). Never state a count the page itself doesn't show. No demo-call ask in this message: the page is the ask.

## Run locally

The key is read from the environment and is never stored in this repo. Do not paste it into a file here: the repo is public, and `build.yml` has a guard step that fails the build if a key literal shows up in a tracked file.

```bash
export REQBEAT_API_KEY="..."     # from your password manager, never committed
export TARGETS_URL="..."         # published-CSV link to the target sheet
python3 generate.py
open docs/index.html
```

Without `TARGETS_URL` both scripts fall back to a local `targets.csv`, which is gitignored. That is the offline path; the sheet is the source of truth.

To avoid retyping it every shell, put it in a `.env` file next to the script and source it. `.env` is in `.gitignore`, so it cannot be committed by accident:

```bash
echo 'export REQBEAT_API_KEY="..."' > .env
source .env && python3 generate.py
```

The build log prints one JSON line per page: `generated`, `skipped_thin_patch`, `paused` or `api_failed`.

## Deploy to GitHub

The repo is live at `reqbeat-growth/playbooks`. These are the steps that take it from a 404 to serving pages.

**1. Push the working tree.** The first push missed `LICENSE`, `qualify.py` and the whole `docs/` folder, which is why Pages had nothing to serve.

```bash
cd ~/Downloads && rm -rf pb && git clone https://github.com/reqbeat-growth/playbooks.git pb && unzip -o ~/Downloads/reqbeat-growth-playbooks.zip -d pb && cd pb && git add -A && git status --short
```

Expect four new files and three modified. Anything else, stop and look before committing.

```bash
cd ~/Downloads/pb && git commit -q -m "add missing files, harden key handling, fix headline" && git push && echo PUSHED
```

**2. Add both secrets.** Settings → Secrets and variables → **Actions** → New repository secret. Add `REQBEAT_API_KEY` (from your password manager) and `TARGETS_URL` (the sheet's published-CSV link). GitHub encrypts both, hides them from logs, and they never enter the git history.

The **Actions** tab specifically. Codespaces and Dependabot secrets are separate scopes and are invisible to workflows: a secret added there reads as empty at build time, and the run fails on auth or generates nothing.

**3. Turn on Pages.** Settings → Pages → Deploy from a branch → branch `main`, folder `/docs`. The placeholder in `docs/index.html` goes live within a minute, so the 404 clears before any real page is built.

**4. Run the build by hand once.** Actions tab → `build` → Run workflow. Do not wait for the 05:00 UTC cron: this manual run also confirms Actions is enabled and billable for this org. If the workflow never starts, that is the likely cause.

**5. Check the output.** A green run rewrites `docs/` and pushes a commit called `nightly build <date>`. Pages redeploys itself. Every row in the sheet with `status=ready` and five surviving signals becomes `https://reqbeat-growth.github.io/playbooks/{slug}/`. Rows still marked `draft` are skipped by design.

**If the build fails**, read the step name in the log:

| Step that failed | What it means |
|---|---|
| refuse to build if a key is hardcoded | a key literal is in a tracked file, remove it and rotate the key |
| generate pages, `REQBEAT_API_KEY is not set` | step 2 was skipped, or the secret name is misspelled |
| generate pages, `HTTP 403` | the key is wrong, revoked, or the wrong tier |
| commit and push | the workflow lacks `contents: write`, check the permissions block |

No DNS step and no CNAME file. Nothing here waits on anyone else.

Optional once the motion is validated: a short CNAME such as `bd.reqbeat.com` pointing at `reqbeat-growth.github.io` gives a cleaner link for outreach. That is a plain external CNAME: it is independent of how `playbooks.reqbeat.com` is served and does not block on that handoff. Put the hostname in `docs/CNAME` and set `SITE_URL` to match.

## Migrating to playbooks.reqbeat.com

The subdomain is expected to serve its per-agency pages the same way the rest of the site is generated, rather than from an externally pushed static folder. What that submission path looks like in practice is still being defined.

When it's answered, this script's role becomes the spec: same gates (5+ signals, 14-day freshness, PSL blocklist), same target-sheet schema, same takedown-via-`paused` behaviour, wherever they need to live to feed Reqbeat's generator. If the answer instead turns out to be "just point DNS at what growth already builds," migration is one line: set `SITE_URL=https://playbooks.reqbeat.com` in the workflow and hand over the CNAME. Either way, nothing built here is thrown away.

## Adding an agency (~30 seconds)

Add a row to the target sheet. It is not in this repo: the repo is public, and the sheet carries draft rows and outreach notes that should not be. The scripts read it over `TARGETS_URL`, the published-CSV link, kept as an Actions secret.

Treat that link as a credential, not a URL. A published sheet has no login: anyone holding the link reads every row.

| field | example | note |
|---|---|---|
| slug | aaron-wallis | kebab-case, becomes the URL |
| agency_name | Aaron Wallis Sales Recruitment | shown on the page |
| agency_domain | aaronwallis.co.uk | reference only |
| niche_label | tech sales | what the reader sees |
| role_query | sales | goes into /v1/reqs/search |
| geo | United Kingdom | country name; UK and GB also resolve |
| trigger_note | your Work For Us page is live seen 24 Aug | optional, verified fact only |
| status | ready | ready / draft / paused |

`draft` rows are ignored. `paused` replaces the page with a takedown note (use it when an agency asks; the promise is removal within 24 hours).

## Rules baked into the generator

- A page publishes only with 5+ fresh signals. A thin patch means no page, never an empty one.
- Companies without a served domain, and PSL-heavy household names (`psl_blocklist.txt`), never appear.
- Every page carries its pull date and the takedown promise in the footer.
- The claim link carries `utm_source=playbooks`, `utm_medium=page`, `utm_content={slug}`, matching the shared source convention.
- `SITE` (og:url, canonical, sitemap, robots.txt) is one env var, `SITE_URL`, never hardcoded, so the publish target moves without touching the template.
- Template changes go through PR review; the first three generated pages get a human read before the list scales (brand risk rule).
- Never send an outreach message pointing at a page before confirming it actually generated (check the build log for that slug).
