# AI WordPress Content Pipeline

![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)
![Claude](https://img.shields.io/badge/LLM-Claude-D97757?logo=anthropic&logoColor=white)
![WordPress REST API](https://img.shields.io/badge/WordPress-REST%20API-21759B?logo=wordpress&logoColor=white)
![Yoast SEO](https://img.shields.io/badge/SEO-Yoast%20meta-A4286A)
![Resumable](https://img.shields.io/badge/pipeline-resumable-2ea44f)

**Task:** two content-heavy sites — **[AIRA](https://student-aira.com)** (an AI
career-assistant startup for students) and an NFC-services company site — needed a
steady stream of long-form, SEO-structured articles without a full-time content team
or a risk of publishing 50 posts in one burst.

**Result:** a resumable Python pipeline that takes a keyword brief, generates a
complete article (title, body, Yoast SEO meta, category, tags) through the Claude
CLI, and schedules it into WordPress at a controlled pace (3–4 posts/day, spread
across fixed time slots) — so publishing looks organic and the schedule survives
interruptions, restarts and re-runs without duplicating content. Used to plan and
schedule **100 articles** across both sites (50 + 50) from keyword briefs alone.

---

## How it works

```
topics/<site>.csv  →  Claude CLI generates article  →  WordPress REST API (draft/future)
   (keyword brief)      (title, body, Yoast meta,         with `future` post_status:
                         category, tags)                   WP's own scheduler
                                                            publishes it later
```

1. **Briefs** live in `topics/<site>.csv` — one row per article: main keyword + up
   to 14 secondary keywords, intent, category, an `H2/H3` outline
   (`required_blocks`), internal-linking targets and a target word count.
2. **Generation** (`pipeline.py`) calls the bundled **Claude CLI** (`claude -p`,
   model `sonnet`) per brief, producing a structured article plus Yoast SEO
   `title` / `meta description` / `focus keyword`.
3. **Publishing** goes through the **WordPress REST API** with an application
   password (never the account password). Posts are created with
   `post_status: future` — WordPress's own scheduler releases them, so the
   pipeline doesn't need to stay running.
4. **Pacing**: each site has `posts_per_day` and a list of `publish_times`; the
   pipeline finds the next free slot (± random minutes) so publish times don't
   look robotic.
5. **Resumable & dedup**: generated articles are cached as
   `articles/<site>/*.json`; any article whose `main_keyword` was already
   published is skipped automatically — safe to stop and re-run at any point,
   and safe to merge in a second batch of briefs later.

## Extra: importing pre-written content

`import_manual.py` handles the case where articles arrive already written
(e.g. exported to `.xlsx` by someone else) instead of being generated from a
brief. A common problem with such exports is **templated near-duplicate
content** — dozens of articles sharing the same paragraph structure with only
the keyword swapped. The script rewrites the templated passages through the
Claude CLI (keeping facts and structure intact), dedups by `main_keyword`
against everything already published, and schedules the result the same way
as the main pipeline.

## Commands

```bash
python pipeline.py status                       # generated / published summary
python pipeline.py run --site aira               # work through the AIRA queue
python pipeline.py run --site nfc --limit 5      # 5 articles for the NFC site
python pipeline.py publish-drafts --site aira    # flip script-created drafts to publish
python import_manual.py --site nfc --limit 5     # import pre-written articles
```

## Structure

```
pipeline.py                 generation + WordPress publishing
import_manual.py            import & de-templatize pre-written .xlsx content
build_topics_batch*.py       generate keyword-brief CSVs (topic research → briefs)
prompts/                    prompt templates per site (placeholders, e.g. <<field>>)
topics/                     keyword-brief queues, one CSV per site (gitignored — business data)
articles/                   generated article cache / publish state (gitignored)
config.json                 site URLs, WP application passwords, model, schedule (gitignored)
config.example.json         config shape without real credentials
```

## Setup

```bash
pip install -r requirements.txt
cp config.example.json config.json   # fill in real site URLs + WP application passwords
```

A WordPress **application password** (Users → Profile → Application Passwords) is
required per site — never the account login password.

---

## Русская версия

**Задача:** двум контентным сайтам — **AIRA** (AI-ассистент поиска работы для
студентов) и сайту NFC-услуг — нужен был стабильный поток объёмных
SEO-структурированных статей без штата копирайтеров и без риска выложить 50 постов
залпом.

**Результат:** возобновляемый Python-конвейер, который берёт бриф по ключевым
словам, генерирует полную статью (заголовок, текст, Yoast SEO мета, рубрика,
метки) через Claude CLI и ставит её в очередь публикации WordPress в контролируемом
темпе (3–4 поста в день по фиксированным слотам) — так публикации выглядят
органично, а расписание переживает прерывания и повторные запуски без дублей.
С его помощью запланировано **100 статей** на двух сайтах (50 + 50) — только из
ключевых брифов.

**Как это устроено:** темы (`topics/<site>.csv`) → генерация через Claude CLI
(заголовок, текст, Yoast-мета) → публикация через WordPress REST API с паролем
приложения (не паролем аккаунта), статус `future` — сам WordPress публикует по
расписанию. Каждой статье — свой слот из `publish_times`, не больше
`posts_per_day` в день. Конвейер возобновляемый: уже опубликованные темы
(по `main_keyword`) пропускаются автоматически.

**Дополнительно:** `import_manual.py` — для готовых текстов (например, выгрузка
в `.xlsx`), которые часто оказываются шаблонными почти-дублями; скрипт
переписывает повторяющиеся куски через Claude CLI, сохраняя факты и структуру,
и дедуплицирует по ключевому слову перед постановкой в очередь.

**Стек:** Python (стандартная библиотека + `openpyxl` для xlsx), Claude CLI как
LLM-движок генерации, WordPress REST API + Yoast SEO meta для публикации.

**Команды и структура** — см. английскую версию выше, конвейер и файлы общие для
обеих версий README.
