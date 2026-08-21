# AI WordPress Content Pipeline

Automated SEO content and publishing pipeline: keyword briefs go in, scheduled
WordPress posts with full SEO metadata come out, unattended.

## Problem

I run two content-dependent sites — my startup **[AIRA](https://student-aira.com)**
(job-search/career assistance for students) and an NFC-products company site
(nfc-msk.ru) — and neither has a content team. Writing and scheduling SEO
articles by hand doesn't scale past a handful a week. The naive fix (generate
everything, publish it all at once) creates a different problem: a blog that
looks like it was dumped online overnight instead of published by a real team,
which is itself a weak signal for both users and search engines.

## Solution

A pipeline that turns a CSV of keyword briefs into fully-formed WordPress
articles — generated, SEO-tagged, and scheduled at a pace that reads as
organic — with no manual step between "brief written" and "post live."

## Key features

- **Brief-to-article generation** through the Claude CLI: title, body, category,
  tags, and Yoast SEO title/meta-description/focus-keyword, from a structured
  keyword brief (main keyword, secondary keywords, search intent, H2/H3 outline,
  internal-link targets, target word count).
- **Direct WordPress publishing** via the REST API using an application
  password (scoped, never the account login), with `post_status: future` —
  WordPress's own scheduler releases the post, so the pipeline doesn't need to
  be running when it goes live.
- **Controlled pacing**, per site: a `posts_per_day` limit and a list of
  publish-time slots, with the next open slot picked automatically (plus a
  random offset in minutes) so publish times don't look scripted.
- **Resumable and dedup-safe**: every generated article is cached with its
  publish state; anything already published for a given keyword is skipped
  automatically, so the pipeline can be stopped, resumed weeks later, or fed a
  second batch of briefs without risk of duplicate posts.
- **Manual-content import path** (`import_manual.py`) for articles that arrive
  pre-written (commonly as `.xlsx` exports). These exports are frequently
  templated — dozens of articles sharing one paragraph skeleton with the
  keyword swapped — which is a near-duplicate-content risk. This script rewrites
  the templated passages through the Claude CLI while preserving facts and
  structure, then dedupes and schedules them the same way as generated content.

## Architecture

```
topics/<site>.csv  →  pipeline.py: Claude CLI generates article  →  WordPress REST API
   (keyword brief)      (title, body, Yoast meta, category, tags)     post_status: future
                                                                       → WP's own scheduler
                                                                          publishes it later
```

Two independent site configs (AIRA, NFC MSK) run off one `config.json` — same
codebase, different keyword queues, prompt templates, and publish cadence per
site.

## Tech stack

Python (standard library + `openpyxl` for `.xlsx` import), the Claude CLI as
the generation engine, WordPress REST API + Yoast SEO for publishing.

## How it works

```bash
python pipeline.py status                       # generated / published summary, per site
python pipeline.py run --site aira               # work through the AIRA queue
python pipeline.py run --site nfc --limit 5      # 5 articles for the NFC site
python pipeline.py publish-drafts --site aira    # flip script-created drafts to publish
python import_manual.py --site nfc --limit 5     # import pre-written .xlsx content
```

```
pipeline.py                 generation + WordPress publishing, both sites
import_manual.py            import & de-templatize pre-written content
build_topics_batch*.py      generate a new batch of keyword-brief CSVs
prompts/                    per-site prompt templates
topics/                     keyword-brief queues (gitignored — business data)
articles/                   generated article cache / publish state (gitignored)
config.json                 site URLs, WP app passwords, model, schedule (gitignored)
config.example.json         same shape, no real credentials
```

Setup:

```bash
pip install -r requirements.txt
cp config.example.json config.json   # fill in real site URLs + WP application passwords
```

A WordPress **application password** per site (Users → Profile → Application
Passwords) is required — not the account login password.

## My role

Designed and built the full pipeline solo: the brief schema, the generation
step, the WordPress integration, the scheduling/pacing logic, and the
de-duplication and resume logic. Also wrote the manual-import path after
running into templated `.xlsx` content in practice.

## Challenges / lessons

- Getting Yoast's SEO fields to accept values through the REST API cleanly
  (no separate plugin/snippet needed) took some trial and error to confirm.
- The naive version of this (generate + publish immediately) produces a blog
  that reads as machine-dumped. The scheduling/pacing logic exists specifically
  to fix that — it's a small piece of code but it's the part that actually
  matters for how the output is perceived.
- Templated pre-written content (`import_manual.py`'s reason for existing) is a
  real, recurring problem with manual `.xlsx` exports — the rewrite pass isn't
  optional if you care about avoiding near-duplicate-content SEO issues.
- The Claude CLI path in config is tied to the installed app version and breaks
  on every Claude Desktop update — a known rough edge, not yet automated away.

## Status

Active, in use for both sites. Used to plan and schedule 100 articles across
AIRA and the NFC site (50 + 50) from keyword briefs.

## Future improvements

- Automate the Claude CLI path resolution instead of hand-editing config after
  every app update.
- Add a lightweight review/approval step before articles move from draft to
  scheduled, for higher-stakes content.

---

*Note: `topics/`, `articles/`, and `config.json` are gitignored — they hold
business data (keyword lists, generated content, live credentials) rather than
code. `config.example.json` shows the config shape without real values.*
