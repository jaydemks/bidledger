# Bidledger

A searchable, daily-refreshed index of open public tenders across the European Union.

The European Union publishes every public contract above threshold in *Tenders Electronic
Daily* (TED), the supplement to the Official Journal. The data is public and free, but it
is formatted for legal completeness rather than for the small companies that could win the
work. Bidledger takes the same feed and turns it into something you can search in ten
seconds: one page per notice, per sector and per country, sorted by closing date, with an
RSS feed for anything you want to follow.

**Live site:** https://jaydemks.github.io/bidledger

## How it works

```
scripts/sync.py              TED Search API   ->  data/notices/YYYY-MM.jsonl
scripts/build.py             the store        ->  site/  (notice, sector, country
                             and winner pages, RSS, sitemap index)
scripts/meta.py              CPV division and country lookup tables
scripts/preview.py           a single self-contained page, for sharing a snapshot

scripts/awards.py            past award notices, month by month, resumable
scripts/enrich_awards.py     values converted to euro at the ECB rate on the day,
                             with the impossible ones flagged rather than deleted
scripts/winners_aggregate.py 720,000 awards  ->  data/winners.json, small enough to commit
scripts/export_awards.py     the award store  ->  one flat CSV
scripts/health.py            one screen of checks against the live site

config.json                  brand, canonical URL, outbound links
```

A scheduled job pulls the notices published since the last run, drops the ones whose
deadline has passed, rewrites the affected pages and deploys. It is scheduled three
times a day — 05:17, 13:37 and 19:47 UTC — because GitHub's cron is best-effort and
quietly skips runs under load. The job is idempotent, so the later two normally find
nothing to do and cost nothing; they exist so that one dropped run does not cost a
day of freshness. The store is sharded by publication month so that historic files stop changing
and each day's commit stays small.

The daily index covers *calls for competition* only — contract notices, social and
special services notices, design contests, qualification systems, and prior information
notices used as a call for competition. Award notices, which name a winner after the
fact, are a separate pipeline with its own store and its own pages; see **Who wins the
work** and **The contract awards dataset** below.

## A free API

The main collections on the site are also JSON files, served by GitHub Pages with
`Access-Control-Allow-Origin: *`. No key or sign-up is required, and you can call them
from a browser. This is a static public service hosted on GitHub Pages, so clients should
cache responses and use it reasonably.

| Endpoint | What it returns |
|---|---|
| `/api/stats.json` | Counts and the build timestamp |
| `/api/countries.json` | Countries, with open tender counts |
| `/api/sectors.json` | The 45 CPV divisions, with counts |
| `/api/cpv.json` | Every CPV code in use: `[code, label, open]` |
| `/api/c/<ISO3>.json` | Open tenders in one country |
| `/api/s/<division>.json` | Open tenders in one CPV division |
| `/api/index.json` | Compact search index of every open tender |

```bash
# how many open construction tenders are there in Italy right now?
curl -s https://jaydemks.github.io/bidledger/api/c/ITA.json | jq '[.[] | select(.cpv_divisions[]=="45")] | length'
```

Full documentation, with the shape of a notice object:
https://jaydemks.github.io/bidledger/api.html

There is no query language — it is a static site, so you fetch a collection and filter it
yourself. Everything is rebuilt once a day; cache it rather than polling.

## Who wins the work

Open tenders say who is buying. A separate set of 992 pages says who has been
*winning*: for each country and sector with enough history, the companies that
took the most contracts over two years, the median award, and the most recent
ones — built from `data/winners.json`, an aggregate of the award store small
enough to live in the repository.

The award store itself (98 MB) is not in git. The pages only need the shape of
it, so `scripts/winners_aggregate.py` boils 720,000 rows down to 3.7 MB and the
build reads that.

## The contract awards dataset

Open tenders are half the record. The other half is who won them. Every contract
award published in the Official Journal over the last twelve months — 374,443 of
them, with the winning company, the buyer, the sector and the value converted to
euro at the ECB rate of the day — is published as a free dataset:

**https://huggingface.co/datasets/jaydem/eu-contract-awards**

It is built by `scripts/awards.py`, `scripts/enrich_awards.py` and
`scripts/export_awards.py` from the same TED API this site uses, asked with
`scope: ALL` so it returns the past rather than only what is open. The dataset
card documents the three traps in the source data — framework ceilings that make
cross-country sums meaningless, TED's `-1` sentinel for "not disclosed", and 168
values that are plainly typing mistakes — because a number quoted from this
without knowing them is a wrong number.

## The CPV vocabulary, as actually used

`scripts/cpv_labels.json` is the whole Common Procurement Vocabulary — all 9,454 codes
with their official English labels — as JSON, keyed by the eight-digit code without the
check digit.

It comes from the European Commission's own spreadsheet, `cpv_2008_ver_2013.xlsx`. That
file used to sit on SIMAP, which has since been retired, so it is no longer downloadable
from the URL most references still cite. The copy used here was cross-checked against the
3,365 codes that TED has actually published notices under, whose labels can be read
straight out of the notice titles: all 3,365 match the spreadsheet exactly, and none is
missing from it.

The site does not build a page for every code. Only the codes with tenders open against
them get one; the rest are answered by the explorer at `/cpv.html`, which searches the
full vocabulary in the browser. Thousands of near-empty pages would cost more in crawl
budget than they could ever return.

## Running it locally

```bash
WINDOW_DAYS=3 python scripts/sync.py     # a small pull, for testing
cd scripts && python build.py            # writes ../site
python -m http.server -d ../site 8000
```

## Deployment

The repository deploys itself to GitHub Pages through `.github/workflows/daily.yml`.
Two settings are required:

- *Settings → Actions → General → Workflow permissions*: **Read and write**
- *Settings → Secrets and variables → Actions → Variables*: `SITE_URL`, the canonical
  origin used for the sitemap and `<link rel="canonical">`

## Data, attribution and scope

Notices come from the [TED Search API](https://docs.ted.europa.eu/api/latest/index.html),
accessed anonymously, and are re-used under the European Commission's open data policy.
TED remains the authoritative source: every page here links back to the official notice,
and anything binding — specifications, annexes, exact deadlines — should be read there.

Bidledger is an independent project. It is not affiliated with, endorsed by, or
operated by the European Union or by any contracting authority.

The site sets no cookies, collects no personal data, has no analytics or tracking of
any kind, and makes no third-party requests at all: the typefaces are served from this
domain, so reading a page tells nobody but GitHub that you were here. The fonts are in
`assets/fonts/` under the SIL Open Font License.

There is no paid tier. The site, API, CSV and RSS feeds are public, and the contract
awards dataset linked above is free on Hugging Face.

## Licence

Code is MIT. The underlying procurement data belongs to its publishers and is redistributed
under the terms of the European Commission's open data policy.
