"""Індексатор Telegram-каналів для Схемника. Запускається GitHub Actions за розкладом.

Гортає публічне веб-превʼю t.me/s/<канал>: спершу забирає нові пости, потім поступово
догортає стару історію (по BUDGET сторінок за запуск), доки не дійде до початку каналу.
Результат — data/<канал>.json і data/manifest.json, які читає сторінка.

Локально:  pip install requests beautifulsoup4 && python scripts/crawl.py
"""
import json
import os
import re
import sys
import time
from urllib.parse import quote

import requests
from bs4 import BeautifulSoup

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
BUDGET = int(os.getenv("PAGES_PER_CHANNEL", "250"))   # сторінок по ~20 постів на канал за запуск
DELAY = float(os.getenv("DELAY", "1.2"))
TIME_LIMIT = float(os.getenv("TIME_LIMIT_MIN", "300")) * 60
START = time.time()

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                                "(KHTML, like Gecko) Chrome/130.0 Safari/537.36",
                  "Accept-Language": "en-US,en;q=0.8"})

BOARDVIEW = {".brd", ".bdv", ".bv", ".cad", ".fz", ".tvw", ".asc", ".cst", ".gr", ".f2b", ".bvr", ".pcb", ".xzz"}
BIOS = {".bin", ".rom", ".fd", ".cap"}


def classify(name, text=""):
    n = (name or "").lower()
    ext = "." + n.rsplit(".", 1)[-1] if "." in n else ""
    if ext in BOARDVIEW:
        return "b"
    if ext == ".pdf":
        return "s"
    if ext in BIOS:
        return "i"
    blob = f"{name} {text}".upper()
    if re.search(r"BOARD\s*VIEW|\bBDV\b|\bBRD\b|\bTVW\b|\bCAD\b|\bFZ\b|\bBV\b", blob):
        return "b"
    if re.search(r"SCHEMATIC|СХЕМ|\bSCH\b|\bPDF\b", blob):
        return "s"
    if re.search(r"\bBIOS\b|\bDUMP\b|\.BIN\b", blob):
        return "i"
    return "o"


SPAM = re.compile(r"(👉?\s*JOIN\s*👉?|BoardViewer FREE DOWNLOAD:?|https?://t\.me/\S+|\*{5,}|┄+.*|@\w+)", re.I)


def clean_caption(t, name):
    t = SPAM.sub(" ", t or "")
    t = re.sub(r"\s+", " ", t).strip(" -|•")
    if t.upper() == (name or "").upper():
        return ""
    return t[:220]


def txt(el):
    return el.get_text(" ", strip=True) if el else ""


def parse_page(html):
    """-> (title, [item], min_id, max_id); item = [id, назва, опис, тип, розмір, дата, підномер]"""
    soup = BeautifulSoup(html, "html.parser")
    title = txt(soup.select_one(".tgme_channel_info_header_title"))
    items, ids = [], []
    for m in soup.select(".tgme_widget_message[data-post]"):
        post = m.get("data-post", "")
        try:
            mid = int(post.rsplit("/", 1)[1])
        except (IndexError, ValueError):
            continue
        ids.append(mid)
        cap = txt(m.select_one(".tgme_widget_message_text"))
        t = m.select_one("time[datetime]")
        date = t["datetime"][:10] if t else ""
        docs = m.select(".tgme_widget_message_document")
        for i, d in enumerate(docs):
            name = txt(d.select_one(".tgme_widget_message_document_title"))
            size = txt(d.select_one(".tgme_widget_message_document_extra"))
            items.append([mid, name, clean_caption(cap, name), classify(name, cap), size, date, i])
        if not docs:
            c = clean_caption(cap, "")
            if len(c) >= 8 and re.search(r"[A-Z0-9]{2,}[-.]?[A-Z0-9]{2,}", c.upper()):
                items.append([mid, c[:140], c[140:], "p", "", date, 0])
    return title, items, (min(ids) if ids else None), (max(ids) if ids else None)


def fetch(channel, before=None):
    url = f"https://t.me/s/{quote(channel)}" + (f"?before={before}" if before else "")
    for attempt in range(4):
        r = S.get(url, timeout=20)
        if r.status_code == 429:
            wait = int(r.headers.get("Retry-After", "30"))
            print(f"  429, чекаю {wait}s", flush=True)
            time.sleep(min(wait, 120))
            continue
        r.raise_for_status()
        return r.text
    raise RuntimeError("занадто багато 429")


def load(ch):
    p = os.path.join(DATA, f"{ch.lower()}.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"channel": ch, "title": "", "newest": 0, "oldest": 0, "complete": False, "items": []}


def save(st):
    st["items"].sort(key=lambda x: (-x[0], x[6]))
    with open(os.path.join(DATA, f"{st['channel'].lower()}.json"), "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, separators=(",", ":"))


def out_of_time():
    return time.time() - START > TIME_LIMIT


def crawl(ch, budget):
    st = load(ch)
    have = {(x[0], x[6]) for x in st["items"]}
    pages, added = 0, 0

    def add(items):
        n = 0
        for it in items:
            if (it[0], it[6]) not in have:
                have.add((it[0], it[6]))
                st["items"].append(it)
                n += 1
        return n

    # 1) Нові пости: від найсвіжіших вниз, доки не дійдемо до вже відомих
    prev_newest, before = st["newest"], None
    while pages < budget and not out_of_time():
        title, items, lo, hi = parse_page(fetch(ch, before))
        pages += 1
        if title:
            st["title"] = title
        if lo is None:
            break
        added += add(items)
        st["newest"] = max(st["newest"], hi)
        st["oldest"] = lo if not st["oldest"] else min(st["oldest"], lo) if not prev_newest else st["oldest"]
        if not prev_newest or lo <= prev_newest + 1 or lo <= 1:
            break
        before = lo
        time.sleep(DELAY)

    # 2) Догортаємо стару історію
    while st["newest"] and not st["complete"] and pages < budget and not out_of_time():
        if st["oldest"] <= 1:
            st["complete"] = True
            break
        time.sleep(DELAY)
        title, items, lo, hi = parse_page(fetch(ch, st["oldest"]))
        pages += 1
        if lo is None or lo >= st["oldest"]:
            st["complete"] = True
            break
        added += add(items)
        st["oldest"] = lo
    save(st)
    print(f"@{ch}: +{added}, всього {len(st['items'])}, сторінок {pages}, "
          f"{'історія повна' if st['complete'] else 'догорнуто до id ' + str(st['oldest'])}", flush=True)
    return st


def main():
    os.makedirs(DATA, exist_ok=True)
    with open(os.path.join(ROOT, "sources.json"), encoding="utf-8") as f:
        src = json.load(f)
    manifest = {"updated": time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime()), "channels": []}
    for c in src["telegram"]:
        ch = c["username"]
        try:
            st = crawl(ch, BUDGET)
        except Exception as e:
            print(f"@{ch}: помилка {e}", flush=True)
            st = load(ch)
        if st["items"] or st["title"]:
            manifest["channels"].append({
                "username": ch, "title": st["title"] or ch, "count": len(st["items"]),
                "complete": st["complete"], "file": f"data/{ch.lower()}.json",
                "v": st["newest"],
            })
    with open(os.path.join(DATA, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    sys.exit(main())
