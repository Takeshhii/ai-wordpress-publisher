# AI WordPress Content Pipeline

`Python` `Claude CLI` `WordPress REST API` `Yoast SEO` — resumable, runs unattended

I run two content sites — **[AIRA](https://student-aira.com)**, my AI career-assistant
startup for students, and an NFC-products company site (nfc-msk.ru) — and neither
one has a content team. Writing and scheduling SEO articles by hand doesn't scale,
and I really didn't want to publish 50 posts in one afternoon and have the whole
blog look like it was dumped there overnight. So I built a pipeline that does the
whole thing: keyword brief in, scheduled WordPress post out, spread across the
week like a person would actually publish.

It handles both of my sites from one config file, and it auto-publishes straight
into WordPress — no copy-pasting drafts, no manual scheduling in wp-admin. I point
it at a CSV of keyword briefs and it takes care of generation, SEO metadata, and
publishing on its own.

## What it does, start to finish

```
topics/<site>.csv  →  Claude CLI writes the article  →  WordPress REST API
   (keyword brief)      (title, body, Yoast meta,          post_status: future
                         category, tags)                    → WP's own cron
                                                               publishes it later
```

1. **Briefs** — one row per article in `topics/<site>.csv`: main keyword, up to
   14 secondary keywords, search intent, category, an H2/H3 outline, internal
   links to weave in, target word count.
2. **Generation** — `pipeline.py` calls the Claude CLI per brief and gets back a
   full article plus Yoast SEO title/meta description/focus keyword.
3. **Auto-publishing to both sites** — posts go out through the WordPress REST
   API using an application password (never my actual account password), with
   `post_status: future`. WordPress's own scheduler releases them — the script
   doesn't need to be running when a post goes live.
4. **Pacing** — each site has its own `posts_per_day` and a list of publish
   times; the pipeline finds the next open slot (plus a few random minutes) so
   the timing doesn't look scripted. AIRA gets 4/day, the NFC site gets 3/day —
   I picked those numbers on purpose, I didn't want either blog to look like a
   content farm.
5. **Resumable** — every generated article is cached in `articles/<site>/*.json`.
   If a keyword's already published, it's skipped. I can kill the script
   mid-run, come back a week later, add more briefs, and re-run it — it won't
   double-publish anything.

## For when the content already exists

`import_manual.py` is for the times I already had text written — usually
exported to `.xlsx` by someone else. The recurring problem with those exports is
that they're heavily templated: dozens of articles built on the exact same
paragraph skeleton with just the keyword swapped in, which is a near-duplicate-
content SEO risk if you publish it as-is. The script runs the templated chunks
back through the Claude CLI to rewrite them while keeping the facts and
structure intact, dedupes against everything already live (by keyword, not row
number — the numbering never matches between a manual export and `topics/*.csv`),
and schedules the result the same way the main pipeline does.

## Commands I actually use

```bash
python pipeline.py status                       # what's generated / published, per site
python pipeline.py run --site aira               # work through the AIRA queue
python pipeline.py run --site nfc --limit 5      # just 5 for the NFC site
python pipeline.py publish-drafts --site aira    # flip script drafts to publish
python import_manual.py --site nfc --limit 5     # import pre-written .xlsx content
```

## Layout

```
pipeline.py                 generation + WordPress publishing, both sites
import_manual.py            import & de-templatize pre-written content
build_topics_batch*.py      generate a new batch of keyword-brief CSVs
prompts/                    per-site prompt templates
topics/                     keyword-brief queues (gitignored — it's business data)
articles/                   generated article cache / publish state (gitignored)
config.json                 site URLs, WP app passwords, model, schedule (gitignored)
config.example.json         same shape, no real credentials
```

## Setting it up

```bash
pip install -r requirements.txt
cp config.example.json config.json   # then fill in real URLs + WP application passwords
```

You need a WordPress **application password** per site (Users → Profile →
Application Passwords in wp-admin) — not your login password, WordPress will
happily generate a scoped one for exactly this.

## A couple of things I hit along the way

- Yoast accepts SEO meta straight through the REST API, no extra plugin/snippet
  needed — took me a while to confirm that, so noting it here.
- The Claude CLI path in `config.json` is tied to the installed app version and
  breaks every time Claude Desktop updates. Annoying, but easy to fix — just
  update the path.
- One article takes roughly 3–5 minutes to generate.

---

## Русская версия

У меня два контентных сайта — **AIRA**, мой стартап-AI-ассистент поиска работы
для студентов, и сайт NFC-услуг (nfc-msk.ru) — и ни у одного нет команды
копирайтеров. Писать и вручную ставить в расписание SEO-статьи не масштабируется,
а публиковать 50 постов за один вечер я тоже не хотел — блог сразу бы выглядел
так, будто его залили за ночь. Поэтому сделал конвейер, который делает всё сам:
на входе бриф по ключевым словам, на выходе — запланированный пост в WordPress,
растянутый по неделе, как будто публикует живой человек.

Он ведёт оба моих сайта из одного конфига и публикует прямо в WordPress сам —
без копипасты черновиков и без ручного планирования в админке. Я просто
подкидываю ему CSV с брифами по ключевым словам, а генерацию, SEO-мету и
публикацию на **оба сайта** — на nfc-msk.ru и student-aira.com — он делает сам.

## Как это работает целиком

Тема из `topics/<site>.csv` → генерация статьи через Claude CLI (заголовок,
текст, Yoast-мета) → **автопубликация в WordPress через REST API** со статусом
`future` — сам WordPress публикует по расписанию, скрипту не нужно быть
запущенным в момент выхода поста.

**Темп** — у каждого сайта свой `posts_per_day` и список времени публикации;
конвейер сам находит ближайший свободный слот (плюс случайные минуты), чтобы
время выхода не выглядело скриптово. AIRA — 4 поста в день, NFC — 3, специально
не больше, чтобы блог не превращался в контент-ферму.

**Возобновляемость** — каждая сгенерированная статья кэшируется в
`articles/<site>/*.json`. Уже опубликованные темы пропускаются автоматически.
Могу прервать скрипт, вернуться через неделю, докинуть новых брифов и
перезапустить — дублей не будет.

## Когда текст уже готов

`import_manual.py` — для случаев, когда текст уже написан (обычно выгружен в
`.xlsx` кем-то ещё). Частая проблема таких выгрузок — жёсткий шаблон: десятки
статей на одном каркасе абзацев с заменой только ключевика, что рискует
near-duplicate content по SEO. Скрипт переписывает шаблонные куски через Claude
CLI, сохраняя факты и структуру, дедуплицирует по ключевому слову (не по номеру
строки — нумерация в ручных файлах не совпадает с `topics/*.csv`) и планирует
публикацию так же, как основной конвейер.

**Стек:** Python (стандартная библиотека + `openpyxl` для xlsx), Claude CLI как
движок генерации, WordPress REST API + Yoast SEO meta для публикации на оба
сайта.

**Команды и структура** — см. английскую версию выше, файлы общие для обеих
версий README.

**По мелочи, что узнал по пути:** Yoast принимает SEO-мету прямо через REST API
без дополнительного сниппета — не сразу это выяснил, поэтому фиксирую здесь.
Путь к Claude CLI в `config.json` привязан к версии приложения и ломается при
каждом обновлении Claude Desktop — но чинится одной строкой. Одна статья
генерируется примерно 3–5 минут.
