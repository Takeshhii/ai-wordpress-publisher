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

---

## Русская версия

Автоматизированный конвейер SEO-контента: на входе брифы по ключевым словам, на
выходе — запланированные посты в WordPress с полной SEO-метой, без ручного
вмешательства.

### Проблема

У меня два контентозависимых сайта — мой стартап **[AIRA](https://student-aira.com)**
(помощь студентам с поиском работы) и сайт компании NFC-товаров (nfc-msk.ru) —
и ни у одного нет команды копирайтеров. Писать и планировать SEO-статьи вручную
не масштабируется дальше нескольких штук в неделю. Наивное решение
(сгенерировать всё и опубликовать разом) создаёт другую проблему: блог, который
выглядит так, будто его залили за ночь, а не ведёт живая команда — а это само по
себе слабый сигнал и для пользователей, и для поисковых систем.

### Решение

Конвейер, превращающий CSV с брифами по ключевым словам в полноценные статьи
WordPress — сгенерированные, размеченные под SEO и запланированные в темпе,
который читается как органический — без ручного шага между «бриф написан» и
«пост опубликован».

### Ключевые возможности

- **Генерация из брифа** через Claude CLI: заголовок, текст, рубрика, метки и
  Yoast SEO title / meta description / focus keyword — из структурированного
  брифа (основной ключ, дополнительные ключи, интент, каркас H2/H3, цели
  перелинковки, целевой объём).
- **Публикация напрямую в WordPress** через REST API с паролем приложения
  (ограниченный по правам, не логин аккаунта), со статусом `future` — публикует
  сам планировщик WordPress, поэтому скрипту не нужно быть запущенным в момент
  выхода поста.
- **Контролируемый темп** по каждому сайту: лимит `posts_per_day` и список
  слотов публикации, ближайший свободный слот выбирается автоматически (плюс
  случайное смещение в минутах), чтобы время выхода не выглядело скриптовым.
- **Возобновляемость и защита от дублей**: каждая сгенерированная статья
  кэшируется вместе со статусом публикации; всё, что уже опубликовано по
  данному ключу, пропускается автоматически — конвейер можно остановить,
  вернуться через несколько недель или дать вторую партию брифов без риска
  дублирующих постов.
- **Импорт готовых текстов** (`import_manual.py`) для статей, которые приходят
  уже написанными (обычно выгрузкой в `.xlsx`). Такие выгрузки часто шаблонны —
  десятки статей на одном каркасе абзацев с заменой ключевика, что создаёт риск
  near-duplicate content. Скрипт переписывает шаблонные куски через Claude CLI,
  сохраняя факты и структуру, затем дедуплицирует и планирует их так же, как
  сгенерированный контент.

### Архитектура

Темы (`topics/<site>.csv`) → генерация статьи через Claude CLI → публикация
через WordPress REST API со статусом `future`. Два независимых конфига сайтов
(AIRA, NFC MSK) работают из одного `config.json` — общий код, разные очереди
ключей, шаблоны промптов и темп публикации.

### Стек

Python (стандартная библиотека + `openpyxl` для импорта `.xlsx`), Claude CLI как
движок генерации, WordPress REST API + Yoast SEO для публикации.

### Команды и установка

Команды, структура файлов и установка — см. английскую версию выше, они общие
для обеих версий README. Для каждого сайта нужен **пароль приложения** WordPress
(Пользователи → Профиль → Пароли приложений), а не пароль от аккаунта.

### Моя роль

Спроектировал и построил весь конвейер один: схему брифов, шаг генерации,
интеграцию с WordPress, логику планирования и темпа, дедупликацию и
возобновляемость. Отдельно написал путь ручного импорта после того, как на
практике столкнулся с шаблонным `.xlsx`-контентом.

### Что было сложным

- Заставить поля Yoast корректно приниматься через REST API (без отдельного
  плагина или сниппета) — не сразу, потребовалось экспериментировать.
- Наивная версия этого (сгенерировать и сразу опубликовать) даёт блог, который
  читается как машинный сброс. Логика планирования и темпа существует именно
  ради этого — это небольшой кусок кода, но именно он определяет, как
  воспринимается результат.
- Шаблонный готовый контент (причина существования `import_manual.py`) —
  реальная повторяющаяся проблема ручных `.xlsx`-выгрузок; проход переписывания
  не опционален, если важно избежать near-duplicate content.
- Путь к Claude CLI в конфиге привязан к версии установленного приложения и
  ломается при каждом обновлении Claude Desktop — известная шероховатость, пока
  не автоматизирована.

### Статус

Активен, используется на обоих сайтах. С его помощью запланировано 100 статей
для AIRA и NFC-сайта (50 + 50) из ключевых брифов.

### Что дальше

- Автоматизировать определение пути к Claude CLI вместо ручной правки конфига
  после каждого обновления приложения.
- Добавить лёгкий шаг ревью перед переводом статьи из черновика в
  запланированные — для более ответственного контента.
