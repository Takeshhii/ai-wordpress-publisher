# -*- coding: utf-8 -*-
"""
Конвейер автогенерации и публикации статей в WordPress.

Использование:
    python pipeline.py run --site aira --limit 2   # сгенерировать и опубликовать 2 статьи
    python pipeline.py run --site nfc              # все статьи сайта
    python pipeline.py status                      # сводка по очередям
"""
import argparse
import base64
import csv
import datetime
import json
import os
import random
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = Path(__file__).parent
CONFIG = json.loads((BASE / "config.json").read_text(encoding="utf-8"))


def _resolve_claude_exe():
    """claude.exe лежит в .../claude-code/<версия>/claude.exe, и версия меняется
    при каждом обновлении Claude Desktop. Если путь из config.json не существует —
    берём самую свежую доступную версию автоматически."""
    configured = Path(CONFIG["claude_exe"])
    if configured.exists():
        return str(configured)
    root = configured.parent.parent  # .../claude-code
    if root.is_dir():
        def ver_key(p):
            try:
                return tuple(int(x) for x in p.name.split("."))
            except ValueError:
                return (0,)
        cands = sorted((d for d in root.iterdir()
                        if d.is_dir() and (d / "claude.exe").exists()),
                       key=ver_key, reverse=True)
        if cands:
            found = str(cands[0] / "claude.exe")
            print(f"[config] claude.exe не найден по пути из config.json, "
                  f"использую {found}")
            return found
    return str(configured)  # пусть упадёт с понятной ошибкой


CONFIG["claude_exe"] = _resolve_claude_exe()

TRANSLIT = str.maketrans({
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
    "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
    "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
    "ф": "f", "х": "h", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
    "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
})

_term_cache = {}


def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def slugify(text):
    s = text.lower().translate(TRANSLIT)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s[:80] or "post"


# ---------------------------------------------------------------- WordPress

def wp_request(site, method, endpoint, payload=None):
    cfg = CONFIG["sites"][site]
    url = cfg["url"].rstrip("/") + "/wp-json/wp/v2/" + endpoint
    auth = base64.b64encode(
        f"{cfg['user']}:{cfg['app_password']}".encode()).decode()
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Basic " + auth,
        "Content-Type": "application/json",
        "User-Agent": "autopublisher/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"raw": body[:500]}


def ensure_term(site, taxonomy, name):
    """Вернуть id рубрики/метки, создав её при необходимости."""
    name = name.strip()
    if not name:
        return None
    key = (site, taxonomy, name.lower())
    if key in _term_cache:
        return _term_cache[key]
    status, res = wp_request(
        site, "GET", f"{taxonomy}?search={urllib.parse.quote(name)}&per_page=50")
    tid = None
    if status == 200:
        for t in res:
            if t["name"].lower() == name.lower():
                tid = t["id"]
                break
    if tid is None:
        status, res = wp_request(site, "POST", taxonomy, {"name": name})
        if status in (200, 201):
            tid = res["id"]
        elif isinstance(res, dict) and res.get("code") == "term_exists":
            tid = res["data"]["term_id"]
        else:
            log(f"  ! не удалось создать {taxonomy} '{name}': {status} {res}")
    _term_cache[key] = tid
    return tid


# ---------------------------------------------------------------- Генерация

def load_topics(site):
    cfg = CONFIG["sites"][site]
    rows = []
    with open(BASE / cfg["topics"], encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if (row.get("site") or "").strip():
                rows.append(row)
    rows.sort(key=lambda r: int(r.get("priority") or 999))
    return rows


def article_path(site, row):
    prio = int(row.get("priority") or 0)
    return BASE / "articles" / site / f"{prio:02d}_{slugify(row['main_keyword'])}.json"


def build_prompt(site, row):
    tmpl = (BASE / CONFIG["sites"][site]["prompt"]).read_text(encoding="utf-8")
    for field in ("content_type", "title", "h1", "main_keyword",
                  "secondary_keywords", "intent", "category", "tags",
                  "internal_links", "word_count", "required_blocks",
                  "style_notes"):
        tmpl = tmpl.replace(f"<<{field}>>", (row.get(field) or "").strip())
    return tmpl


def extract_json(text):
    """Достать JSON-объект из ответа модели (на случай обёрток)."""
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError("в ответе нет JSON-объекта")
    raw = m.group(0)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # частая проблема: реальные переносы строк внутри строк JSON
        fixed = re.sub(r"(?<!\\)\n", " ", raw)
        return json.loads(fixed)


def generate(site, row):
    prompt = build_prompt(site, row)
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE")}
    cmd = [CONFIG["claude_exe"], "-p", "--output-format", "text",
           "--model", CONFIG.get("model", "sonnet"),
           "--permission-mode", "bypassPermissions"]
    r = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                       encoding="utf-8", errors="replace",
                       timeout=CONFIG.get("generation_timeout_sec", 900),
                       env=env, cwd=str(BASE))
    if r.returncode != 0:
        raise RuntimeError(f"claude exit {r.returncode}: "
                           f"stdout={r.stdout[:300]!r} stderr={r.stderr[:200]!r}")
    art = extract_json(r.stdout)
    for key in ("title", "content_html", "meta_title", "meta_description"):
        if not art.get(key):
            raise ValueError(f"в ответе модели нет поля {key}")
    if len(art["content_html"]) < 1500:
        raise ValueError(f"content_html подозрительно короткий "
                         f"({len(art['content_html'])} симв.) — похоже на "
                         f"обрезанный ответ, не публикую")
    if not art.get("slug"):
        art["slug"] = slugify(row["main_keyword"])
    art["_source_row"] = {k: row.get(k) for k in row}
    return art


# ---------------------------------------------------------------- Публикация

def next_slot(site):
    """Первый свободный слот отложенной публикации: не больше
    posts_per_day статей в день, время из publish_times + случайные минуты."""
    per_day = CONFIG["sites"][site].get("posts_per_day", 3)
    times = CONFIG.get("publish_times",
                       ["09:40", "12:20", "15:10", "18:30"])[:per_day]
    status, res = wp_request(
        site, "GET",
        "posts?status=future&per_page=100&orderby=date&order=asc&context=edit")
    counts = {}
    if status == 200:
        for p in res:
            day = p["date"][:10]
            counts[day] = counts.get(day, 0) + 1
    day = datetime.date.today() + datetime.timedelta(days=1)
    while counts.get(day.isoformat(), 0) >= per_day:
        day += datetime.timedelta(days=1)
    hh, mm = map(int, times[counts.get(day.isoformat(), 0)].split(":"))
    return (f"{day.isoformat()}T{hh:02d}:{mm + random.randint(0, 19):02d}:"
            f"{random.randint(0, 59):02d}")


def publish(site, row, art):
    cat_id = ensure_term(site, "categories", row.get("category", ""))
    tag_ids = [t for t in (ensure_term(site, "tags", name)
                           for name in (row.get("tags") or "").split(","))
               if t]
    payload = {
        "title": art["title"],
        "slug": art["slug"],
        "content": art["content_html"],
        "excerpt": art.get("excerpt", ""),
        "status": CONFIG["sites"][site].get("post_status", "draft"),
        "meta": {
            "_yoast_wpseo_title": art["meta_title"],
            "_yoast_wpseo_metadesc": art["meta_description"],
            "_yoast_wpseo_focuskw": (row.get("main_keyword") or "").strip(),
        },
    }
    if cat_id:
        payload["categories"] = [cat_id]
    if tag_ids:
        payload["tags"] = tag_ids
    if payload["status"] == "future":
        payload["date"] = next_slot(site)
        art["_scheduled_for"] = payload["date"]
        log(f"  слот публикации: {payload['date']}")

    status, res = wp_request(site, "POST", "posts", payload)
    if status == 400 and isinstance(res, dict) and "meta" in str(res.get("data", "")):
        log("  ! Yoast-мета не зарегистрирована в REST, публикую без неё "
            "(нужен сниппет register_post_meta)")
        payload.pop("meta")
        art["_meta_skipped"] = True
        status, res = wp_request(site, "POST", "posts", payload)
    if status not in (200, 201):
        raise RuntimeError(f"WP {status}: {json.dumps(res, ensure_ascii=False)[:500]}")
    art["_wp_post_id"] = res["id"]
    art["_wp_link"] = res.get("link", "")
    return res["id"]


# ---------------------------------------------------------------- Команды

def already_used_keywords(site):
    """main_keyword всех тем, для которых уже есть опубликованная статья
    в articles/<site>/ — включая статьи, импортированные import_manual.py."""
    used = set()
    for p in (BASE / "articles" / site).glob("*.json"):
        art = json.loads(p.read_text(encoding="utf-8"))
        if not art.get("_wp_post_id"):
            continue
        kw = (art.get("_source_row", {}).get("main_keyword") or "").strip().lower()
        if kw:
            used.add(kw)
    return used


def cmd_run(site, limit, delay):
    rows = load_topics(site)
    used = already_used_keywords(site)
    done = 0
    log(f"=== {site}: {len(rows)} тем в очереди ===")
    for row in rows:
        if limit and done >= limit:
            break
        if (row.get("main_keyword") or "").strip().lower() in used:
            log(f"[{row['priority']}] {row['main_keyword']}: пропуск — "
               f"тема уже опубликована (в т.ч. через import_manual.py)")
            continue
        path = article_path(site, row)
        art = None
        if path.exists():
            art = json.loads(path.read_text(encoding="utf-8"))
            if art.get("_wp_post_id"):
                continue  # уже опубликована
        label = f"[{row['priority']}] {row['main_keyword']}"
        try:
            if art is None:
                log(f"{label}: генерация...")
                t0 = time.time()
                attempt = 0
                while True:
                    try:
                        art = generate(site, row)
                        break
                    except Exception as e:
                        attempt += 1
                        if attempt >= 20:
                            raise
                        wait = min(1800, 60 * 2 ** min(attempt - 1, 5))
                        log(f"{label}: сбой генерации (попытка {attempt}): "
                            f"{str(e)[:200]} — жду {wait // 60} мин")
                        time.sleep(wait)
                path.write_text(json.dumps(art, ensure_ascii=False, indent=1),
                                encoding="utf-8")
                log(f"{label}: сгенерировано за {time.time()-t0:.0f}с, "
                    f"{len(art['content_html'])} символов HTML")
            log(f"{label}: публикация черновика...")
            post_id = publish(site, row, art)
            path.write_text(json.dumps(art, ensure_ascii=False, indent=1),
                            encoding="utf-8")
            log(f"{label}: OK, post_id={post_id}")
            done += 1
            if delay:
                time.sleep(delay)
        except Exception as e:
            log(f"{label}: ОШИБКА: {e}")
            (BASE / "logs" / f"error_{site}_{row['priority']}.txt").write_text(
                f"{type(e).__name__}: {e}", encoding="utf-8")
    log(f"=== {site}: готово, обработано {done} ===")


def cmd_publish_drafts(site):
    """Перевести все опубликованные скриптом черновики в publish."""
    flipped = 0
    for path in sorted((BASE / "articles" / site).glob("*.json")):
        art = json.loads(path.read_text(encoding="utf-8"))
        post_id = art.get("_wp_post_id")
        if not post_id:
            continue
        status, res = wp_request(site, "GET", f"posts/{post_id}?context=edit")
        if status != 200:
            log(f"post {post_id}: не найден ({status}), пропускаю")
            continue
        if res.get("status") == "publish":
            continue
        status, res = wp_request(site, "POST", f"posts/{post_id}",
                                 {"status": "publish"})
        if status in (200, 201):
            log(f"post {post_id}: опубликован -> {res.get('link', '')}")
            flipped += 1
        else:
            log(f"post {post_id}: ОШИБКА {status}: {str(res)[:300]}")
    log(f"=== {site}: переведено в publish: {flipped} ===")


def cmd_status():
    for site in CONFIG["sites"]:
        rows = load_topics(site)
        gen = pub = 0
        for row in rows:
            p = article_path(site, row)
            if p.exists():
                gen += 1
                if json.loads(p.read_text(encoding="utf-8")).get("_wp_post_id"):
                    pub += 1
        print(f"{site}: тем {len(rows)}, сгенерировано {gen}, опубликовано {pub}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--site", required=True, choices=list(CONFIG["sites"]))
    run.add_argument("--limit", type=int, default=0)
    run.add_argument("--delay", type=int, default=5,
                     help="пауза между статьями, сек")
    sub.add_parser("status")
    pd = sub.add_parser("publish-drafts")
    pd.add_argument("--site", required=True, choices=list(CONFIG["sites"]))
    args = ap.parse_args()
    if args.cmd == "run":
        cmd_run(args.site, args.limit, args.delay)
    elif args.cmd == "publish-drafts":
        cmd_publish_drafts(args.site)
    else:
        cmd_status()


if __name__ == "__main__":
    main()
