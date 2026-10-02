"""Reading mode: finds out whether a page is an article and pulls the article out of it.

Both steps use Mozilla's Readability (the engine behind Firefox Reader View), vendored in
engine/vendor/readability under the Apache License 2.0. The scripts run in JBrowser's isolated
world (BRIDGE_WORLD): they read the page's DOM, the page can't see or change them. The article is
shown by ui/reader_view.py in a separate page where no script from the website can run.
"""
from __future__ import annotations

import html
import json
import re
from functools import lru_cache
from pathlib import Path

VENDOR = Path(__file__).with_name("vendor") / "readability"

# Reading mode is offered for pages with at least this much readable text (characters). Readability's
# own default (140) also matches short news briefs and forum posts; the offer should feel earned.
MIN_ARTICLE_CHARS = 900

FONTS = {
    "serif": "Charter, 'Bitstream Charter', 'Sitka Text', Cambria, Georgia, serif",
    "sans": "'Segoe UI Variable Text', 'Segoe UI', system-ui, sans-serif",
}
THEMES = ("auto", "light", "sepia", "dark")
ZOOM_STEPS = (0.8, 0.9, 1.0, 1.1, 1.2, 1.35, 1.5, 1.7)
MAX_HTML = 1_900_000      # QWebEnginePage.setHtml() can't show more than 2 MB


@lru_cache(maxsize=None)
def _vendor(name: str) -> str:
    try:
        return (VENDOR / name).read_text("utf-8")
    except OSError:
        return ""


def available() -> bool:
    return bool(_vendor("Readability.js")) and bool(_vendor("Readability-readerable.js"))


def readerable_js() -> str:
    """Evaluates to true when the page is probably an article."""
    return ("(function () { 'use strict';\n" + _vendor("Readability-readerable.js") +
            f"\ntry {{ return document.body ? isProbablyReaderable(document, {{ minContentLength: 140, "
            f"minScore: {MIN_ARTICLE_CHARS ** 0.5:.0f} }}) : false; }} catch (e) {{ return false; }}\n}})()")


def extract_js() -> str:
    """Evaluates to a JSON string with the article (title, byline, content, ...) or null."""
    return ("(function () { 'use strict';\n" + _vendor("Readability.js") + """
try {
  var doc = document.cloneNode(true);
  var a = new Readability(doc, { charThreshold: 300, keepClasses: false }).parse();
  if (!a || !a.content) return null;
  return JSON.stringify({ title: a.title || document.title || '', byline: a.byline || '',
    siteName: a.siteName || '', content: a.content, lang: a.lang || document.documentElement.lang || '',
    dir: a.dir || '', length: a.length || 0, excerpt: a.excerpt || '', published: a.publishedTime || '' });
} catch (e) { return null; }
})()""")


def parse_result(result) -> dict | None:
    if not isinstance(result, str) or not result:
        return None
    try:
        data = json.loads(result)
    except ValueError:
        return None
    return data if isinstance(data, dict) and data.get("content") else None


def reading_minutes(chars: int) -> int:
    """About 1300 characters (~230 words) a minute, a typical silent-reading speed."""
    return max(1, round(chars / 1300))


_DATA_IMG = re.compile(r"""<img\b[^>]*\bsrc\s*=\s*["']data:[^"']{2000,}["'][^>]*>""", re.IGNORECASE)


def render(article: dict, url: str, font: str, theme: str, dark_app: bool, accent: str) -> str:
    """The reading-mode page. The site's HTML has already been cleaned by Readability; the CSP below
    also stops any script, frame, form or plugin that might be left."""
    title = html.escape(article.get("title") or "")
    meta = [html.escape(m) for m in (article.get("siteName"), article.get("byline")) if m]
    minutes = reading_minutes(int(article.get("length") or 0))
    meta.append(f"{minutes} min read")
    lang = html.escape(article.get("lang") or "", quote=True)
    direction = "rtl" if article.get("dir") == "rtl" else "ltr"
    body = article.get("content") or ""
    page = _TEMPLATE.format(
        lang=lang, dir=direction, title=title, meta=" · ".join(meta), body=body, accent=accent,
        url=html.escape(url, quote=True), host=html.escape(re.sub(r"^https?://(www\.)?", "", url).split("/")[0]),
        cls=classes(font, theme, dark_app), serif=FONTS["serif"], sans=FONTS["sans"])
    if len(page.encode("utf-8")) > MAX_HTML:
        page = _DATA_IMG.sub("", page)            # large inline pictures first
    if len(page.encode("utf-8")) > MAX_HTML:
        cut = page.encode("utf-8")[:MAX_HTML].decode("utf-8", "ignore")
        page = cut[:cut.rfind("<")] + "<p class='jb-note'>The rest of this article is too long for reading " \
                                      "mode. Leave reading mode to see all of it.</p></article></body></html>"
    return page


def classes(font: str, theme: str, dark_app: bool) -> str:
    if theme not in THEMES or theme == "auto":
        theme = "dark" if dark_app else "light"
    return f"jb-{theme} jb-{'sans' if font == 'sans' else 'serif'}"


_TEMPLATE = """<!doctype html>
<html lang="{lang}" dir="{dir}" class="{cls}"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src http: https: data:;
 media-src http: https:; style-src 'unsafe-inline'; font-src data:; form-action 'none'; frame-src 'none'">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
:root {{ --accent: {accent}; }}
html.jb-light {{ --bg: #ffffff; --fg: #1b1b1f; --muted: #5f6068; --rule: #e3e3e8; --code: #f3f3f6; }}
html.jb-sepia {{ --bg: #f6efe2; --fg: #3b2f22; --muted: #7a6a55; --rule: #e2d6c0; --code: #efe5d3; }}
html.jb-dark  {{ --bg: #1d1d22; --fg: #e6e6ea; --muted: #a0a0aa; --rule: #34343c; --code: #2a2a31; }}
html {{ background: var(--bg); color: var(--fg); }}
html.jb-serif body {{ font-family: {serif}; }}
html.jb-sans body {{ font-family: {sans}; }}
body {{ margin: 0; padding: 48px 28px 96px; font-size: 19px; line-height: 1.68; -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility; overflow-wrap: break-word; }}
article {{ max-width: 680px; margin: 0 auto; }}
header {{ margin-bottom: 30px; padding-bottom: 22px; border-bottom: 1px solid var(--rule); }}
.jb-host {{ font: 600 12px/1.4 'Segoe UI', system-ui, sans-serif; letter-spacing: .06em; text-transform: uppercase;
  color: var(--accent); text-decoration: none; }}
h1.jb-title {{ font-size: 2.05em; line-height: 1.18; margin: 10px 0 12px; letter-spacing: -.01em; }}
.jb-meta {{ font: 14px/1.5 'Segoe UI', system-ui, sans-serif; color: var(--muted); }}
h1, h2, h3, h4 {{ line-height: 1.3; margin: 1.6em 0 .5em; }}
h2 {{ font-size: 1.45em; }} h3 {{ font-size: 1.2em; }}
p, ul, ol, blockquote, figure, pre, table {{ margin: 0 0 1.15em; }}
a {{ color: var(--accent); text-decoration-thickness: 1px; text-underline-offset: 2px; }}
img, video, svg {{ max-width: 100%; height: auto; border-radius: 6px; }}
figure {{ margin-left: 0; margin-right: 0; }}
figcaption, .caption {{ font: 14px/1.5 'Segoe UI', system-ui, sans-serif; color: var(--muted); margin-top: 6px; }}
blockquote {{ margin-left: 0; padding: 2px 0 2px 18px; border-left: 3px solid var(--accent); color: var(--muted); }}
pre, code {{ font-family: 'Cascadia Mono', Consolas, monospace; font-size: .86em; background: var(--code);
  border-radius: 5px; }}
code {{ padding: .1em .35em; }} pre {{ padding: 12px 14px; overflow-x: auto; }} pre code {{ padding: 0; }}
table {{ border-collapse: collapse; width: 100%; font-size: .9em; display: block; overflow-x: auto; }}
th, td {{ border: 1px solid var(--rule); padding: 6px 9px; text-align: start; }}
hr {{ border: 0; border-top: 1px solid var(--rule); margin: 2em 0; }}
.jb-note {{ color: var(--muted); font-style: italic; }}
::selection {{ background: color-mix(in srgb, var(--accent) 35%, transparent); }}
</style></head>
<body><article>
<header><a class="jb-host" href="{url}">{host}</a><h1 class="jb-title">{title}</h1><div class="jb-meta">{meta}</div></header>
{body}
</article></body></html>"""
