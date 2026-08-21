# -*- coding: utf-8 -*-
"""
Импорт готовых текстов из xlsx (aira_37_ready_seo_texts.xlsx,
nfc_46_ready_seo_texts.xlsx): переписывает шаблонные/повторяющиеся куски
через Claude CLI, сохраняя структуру и факты, затем ставит статью в
отложенную публикацию (тем же способом, что и pipeline.py).

Темы, которые уже опубликованы или запланированы через основной конвейер
(pipeline.py run), пропускаются — сверка идёт по main_keyword.

Использование:
    python import_manual.py --site aira
    python import_manual.py --site nfc --limit 3
"""
import argparse
import json
import re
import time
from pathlib import Path

import openpyxl

import pipeline as pl

BASE = pl.BASE

SOURCES = {
    "aira": {
        "xlsx": "topics/aira_37_ready_seo_texts.xlsx",
        "sheet": "AIRA_Texts",
        "prompt": "prompts/rewrite_aira.txt",
        "id_field": "priority",
        "map": {
            "h1": "title", "main_keyword": "main_keyword",
            "secondary_keywords": "secondary_keywords", "category": "category",
            "internal_links": "internal_link", "draft_html": "html_for_wordpress",
            "tags": None,
        },
    },
    "nfc": {
        "xlsx": "topics/nfc_46_ready_seo_texts.xlsx",
        "sheet": "SEO_TEXTS_NFC",
        "prompt": "prompts/rewrite_nfc.txt",
        "id_field": "ID",
        "map": {
            "h1": "H1", "main_keyword": "Главный ключ",
            "secondary_keywords": "Доп. ключи", "category": "Категория",
            "internal_links": "Внутренняя ссылка",
            "draft_html": "HTML для WordPress", "tags": None,
        },
    },
}


def already_used_keywords(site):
    """main_keyword всех тем, уже сгенерированных основным конвейером
    (articles/<site>/*.json без префикса manual_)."""
    used = set()
    for p in (BASE / "articles" / site).glob("*.json"):
        if p.name.startswith("manual_"):
            continue
        art = json.loads(p.read_text(encoding="utf-8"))
        row = art.get("_source_row", {})
        kw = (row.get("main_keyword") or "").strip().lower()
        if kw:
            used.add(kw)
    return used


def load_manual_rows(site):
    cfg = SOURCES[site]
    wb = openpyxl.load_workbook(str(BASE / cfg["xlsx"]), read_only=True)
    ws = wb[cfg["sheet"]]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[0]
    data = [dict(zip(header, r)) for r in rows[1:] if r[0]]
    data.sort(key=lambda r: int(r[cfg["id_field"]]))
    return data


def build_row(site, raw):
    m = SOURCES[site]["map"]
    return {
        "h1": (raw.get(m["h1"]) or "").strip(),
        "main_keyword": (raw.get(m["main_keyword"]) or "").strip(),
        "secondary_keywords": (raw.get(m["secondary_keywords"]) or "").strip(),
        "category": (raw.get(m["category"]) or "").strip(),
        "internal_links": (raw.get(m["internal_links"]) or "").strip(),
        "tags": "",
    }


def build_prompt(site, row, draft_html):
    tmpl = (BASE / SOURCES[site]["prompt"]).read_text(encoding="utf-8")
    for field in ("h1", "main_keyword", "secondary_keywords", "category",
                  "internal_links"):
        tmpl = tmpl.replace(f"<<{field}>>", row[field])
    return tmpl.replace("<<draft_html>>", draft_html)


def rewrite(site, row, draft_html):
    prompt = build_prompt(site, row, draft_html)
    env = {k: v for k, v in pl.os.environ.items() if not k.startswith("CLAUDE")}
    cmd = [pl.CONFIG["claude_exe"], "-p", "--output-format", "text",
           "--model", pl.CONFIG.get("model", "sonnet"),
           "--permission-mode", "bypassPermissions"]
    r = pl.subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                          encoding="utf-8", errors="replace",
                          timeout=pl.CONFIG.get("generation_timeout_sec", 900),
                          env=env, cwd=str(BASE))
    if r.returncode != 0:
        raise RuntimeError(f"claude exit {r.returncode}: "
                           f"stdout={r.stdout[:300]!r} stderr={r.stderr[:200]!r}")
    art = pl.extract_json(r.stdout)
    for key in ("title", "content_html", "meta_title", "meta_description"):
        if not art.get(key):
            raise ValueError(f"в ответе модели нет поля {key}")
    if len(art["content_html"]) < 1500:
        raise ValueError(f"content_html подозрительно короткий "
                         f"({len(art['content_html'])} симв.) — похоже на "
                         f"обрезанный ответ, не публикую")
    if not art.get("slug"):
        art["slug"] = pl.slugify(row["main_keyword"])
    art["content_html"] = re.sub(r"</?h1[^>]*>", "", art["content_html"])
    return art


def run(site, limit):
    rows = load_manual_rows(site)
    id_field = SOURCES[site]["id_field"]
    used = already_used_keywords(site)
    done = 0
    pl.log(f"=== импорт готовых текстов {site}: {len(rows)} строк в файле ===")
    for raw in rows:
        row = build_row(site, raw)
        if not row["h1"] or not row["main_keyword"]:
            continue
        if row["main_keyword"].lower() in used:
            pl.log(f"[{raw[id_field]}] {row['main_keyword']}: пропуск — "
                   f"тема уже опубликована/запланирована основным конвейером")
            continue
        if limit and done >= limit:
            break
        path = BASE / "articles" / site / f"manual_{int(raw[id_field]):02d}_{pl.slugify(row['main_keyword'])}.json"
        art = None
        if path.exists():
            art = json.loads(path.read_text(encoding="utf-8"))
            if art.get("_wp_post_id"):
                continue
        label = f"[{raw[id_field]}] {row['main_keyword']}"
        try:
            if art is None:
                pl.log(f"{label}: переписываю уникальные части...")
                t0 = time.time()
                attempt = 0
                while True:
                    try:
                        draft_html = raw[SOURCES[site]["map"]["draft_html"]]
                        art = rewrite(site, row, draft_html)
                        break
                    except Exception as e:
                        attempt += 1
                        if attempt >= 20:
                            raise
                        wait = min(1800, 60 * 2 ** min(attempt - 1, 5))
                        pl.log(f"{label}: сбой (попытка {attempt}): "
                               f"{str(e)[:200]} — жду {wait // 60} мин")
                        time.sleep(wait)
                art["_source_row"] = row | {"priority": raw[id_field]}
                path.write_text(json.dumps(art, ensure_ascii=False, indent=1),
                                encoding="utf-8")
                pl.log(f"{label}: готово за {time.time()-t0:.0f}с, "
                       f"{len(art['content_html'])} символов")
            pl.log(f"{label}: планирование публикации...")
            post_id = pl.publish(site, row, art)
            path.write_text(json.dumps(art, ensure_ascii=False, indent=1),
                            encoding="utf-8")
            pl.log(f"{label}: OK, post_id={post_id}, слот={art.get('_scheduled_for')}")
            used.add(row["main_keyword"].lower())
            done += 1
        except Exception as e:
            pl.log(f"{label}: ОШИБКА: {e}")
    pl.log(f"=== {site}: импортировано и запланировано {done} ===")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", required=True, choices=list(SOURCES))
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    run(args.site, args.limit)
