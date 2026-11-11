"""Тест індексатора без мережі:  python tests/test_crawl.py"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
os.environ["DELAY"] = "0"
import crawl  # noqa: E402

crawl.DATA = tempfile.mkdtemp()
TOP = [95]


def page(before):
    hi = (before - 1) if before else TOP[0]
    ids = [i for i in range(max(1, hi - 19), hi + 1)]
    msgs = "".join(
        f'<div class="tgme_widget_message" data-post="testch/{i}"><div class="tgme_widget_message_document">'
        f'<div class="tgme_widget_message_document_title">LA-K{i:03d}P BOARDVIEW.rar</div>'
        f'<div class="tgme_widget_message_document_extra">1 MB</div></div>'
        f'<div class="tgme_widget_message_text">👉JOIN 👉 https://t.me/x rev {i}</div>'
        f'<time datetime="2025-01-01T00:00:00+00:00"></time></div>' for i in ids)
    return f'<div class="tgme_channel_info_header_title"><span>Test</span></div>{msgs}'


crawl.fetch = lambda ch, before=None: page(before)


def test_full_then_incremental():
    st = crawl.crawl("testch", budget=100)
    assert st["complete"] and len(st["items"]) == 95, (st["complete"], len(st["items"]))
    assert st["items"][0][3] == "b" and st["items"][0][2] == "rev 95"   # спам вирізано
    TOP[0] = 130                                                       # зʼявилось 35 нових постів
    st = crawl.crawl("testch", budget=100)
    assert len(st["items"]) == 130 and st["newest"] == 130


def test_budget_resume():
    TOP[0] = 95
    crawl.DATA = tempfile.mkdtemp()
    st = crawl.crawl("testch", budget=2)
    assert not st["complete"] and len(st["items"]) == 40
    st = crawl.crawl("testch", budget=10)
    assert st["complete"] and len(st["items"]) == 95


def test_parse_real_fixture():
    html = open(os.path.join(ROOT, "tests", "tg_search.html"), encoding="utf-8").read()
    title, items, lo, hi = crawl.parse_page(html)
    assert title.startswith("schematics") and lo == 39001 and hi == 40211
    kinds = {i[0]: i[3] for i in items}
    assert kinds[40211] == "b" and kinds[40210] == "s" and kinds[39001] == "p"


if __name__ == "__main__":
    for n, f in list(globals().items()):
        if n.startswith("test_"):
            f()
            print("ok", n)
