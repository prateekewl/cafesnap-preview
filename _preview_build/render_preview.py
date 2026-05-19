#!/usr/bin/env python3
"""render_preview.py - render customer-facing Jinja templates to static HTML.

Used by scripts/refresh_preview.sh. Renders index/status/success/cancel/
terms (EN + ES) with SAFE placeholder context (no secrets, no DB, no live
Stripe), stamps a fixed non-interactive "PREVIEW" ribbon on every page,
copies the static/ assets, and rewrites root-absolute links so the site
works under the GitHub Pages subpath.

It imports ONLY translations.py (pure-Python i18n) from the source tree.
It NEVER imports app.py / database.py / stripe, so no secret/env/DB code
path runs. Output goes to --out; nothing in the source tree is modified.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from pathlib import Path

# ---- Pages base path -------------------------------------------------------
# Published to the dedicated PUBLIC repo github.com/prateekewl/cafesnap-preview
# (the private app repo's plan has no Pages). Project Pages site is served
# at /cafesnap-preview/. All root-absolute links/assets are rewritten to
# live under this prefix so the static copy resolves correctly.
PAGES_PREFIX = "/cafesnap-preview"

# Customer-facing pages to render. status/success/cancel are normally
# behind dynamic routes; we render their default/representative state.
PAGES = ["index", "status", "success", "cancel", "terms"]

# The non-interactive PREVIEW ribbon. Fixed, top of viewport, pointer-
# events:none so it can never be clicked/dismissed and can never be
# confused with the live site. High z-index to sit above sticky headers.
RIBBON_HTML = """
<div id="cafesnap-preview-ribbon" style="position:fixed;top:0;left:0;right:0;
z-index:2147483647;background:#b91c1c;color:#fff;text-align:center;
font:600 13px/1.45 -apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;
padding:6px 10px;letter-spacing:.3px;pointer-events:none;
box-shadow:0 1px 4px rgba(0,0,0,.35);">
PREVIEW - visual only, not the live site
</div>
<div id="cafesnap-preview-spacer" style="height:30px;"></div>
"""


def safe_context(src: Path, lang: str) -> dict:
    """Representative, secret-free context shared by every page.

    Mirrors what app.py's route handlers + _i18n_ctx() pass, but every
    backend-only value is a benign placeholder. No env vars, no DB, no
    Stripe keys.
    """
    sys.path.insert(0, str(src))
    from translations import get_translator, js_strings_for_lang  # noqa: E402

    # Real cafe-closure dates ship in the repo (public info, no secrets)
    # so the calendar greys them out exactly like production.
    closed = []
    cj = src / "data" / "cafe_closures.json"
    if cj.exists():
        try:
            closed = json.loads(cj.read_text()).get("closed_dates", []) or []
        except Exception:
            closed = []

    class _FakeURL:
        path = "/"

    class _FakeRequest:
        """Minimal stand-in for starlette Request used only by templates.
        Templates in this repo do not call request.url_for; they only read
        a couple of attributes via _i18n_ctx (already precomputed here)."""

        url = _FakeURL()
        query_params: dict = {}

    ctx = {
        "request": _FakeRequest(),
        # i18n bundle (same keys _i18n_ctx provides)
        "t": get_translator(lang),
        "lang": lang,
        "other_lang": "es" if lang == "en" else "en",
        "lang_switch_url": "/?lang=es" if lang == "en" else "/",
        "js_strings": js_strings_for_lang(lang),
        "google_site_verification": "",
        "bing_site_verification": "",
        # home() context
        "stripe_key": "pk_preview_static_disabled",   # obviously inert
        "price": 10.0,
        "price_cents": 1000,
        "closed_osaka_dates": closed,
        "meta_pixel_id": "",
        "google_ads_id": "",
        # success() context (representative "found" state)
        "booking_id": 1234,
        "customer_name": "Sample Visitor",
        "preferred_date": "2026-06-20",
        "paid_value": 10.0,
        "paid_currency": "GBP",
        "webhook_pending": False,
        "scanning_now": True,
        "not_found": False,
        "google_ads_conversion_id": "",
        "google_ads_conversion_label": "",
    }
    return ctx


# Patterns of values that must never appear in rendered output even if a
# template somehow referenced them. Belt-and-braces scrub.
SECRET_PATTERNS = [
    re.compile(r"sk_live_[0-9A-Za-z]+"),
    re.compile(r"sk_test_[0-9A-Za-z]+"),
    re.compile(r"rk_live_[0-9A-Za-z]+"),
    re.compile(r"whsec_[0-9A-Za-z]+"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),         # Google API keys
    re.compile(r"\b\d{6,}:[A-Za-z0-9_\-]{30,}\b"),  # Telegram bot tokens
    re.compile(r"xox[baprs]-[0-9A-Za-z\-]+"),       # Slack tokens
]


def scrub(html: str) -> str:
    for pat in SECRET_PATTERNS:
        html = pat.sub("[REDACTED]", html)
    return html


def neutralize_analytics(html: str) -> str:
    """Stop the static preview from polluting production analytics.

    The live templates hardcode a Google Analytics tag (gtag/G-...) and
    load gtag.js. On a preview site that would send fake pageviews +
    conversion events into the real GA property. Replace the GA loader
    src + neutralise gtag() calls so the preview is analytics-silent
    without changing the visible page at all.
    """
    # Disarm the gtag.js loader (keep the tag visually but point nowhere).
    html = re.sub(
        r'src="https://www\.googletagmanager\.com/gtag/js\?id=[^"]*"',
        'src="about:blank" data-preview-disabled-analytics="1"',
        html,
    )
    # Make window.gtag a harmless no-op before any inline gtag() runs.
    html = html.replace(
        "<head>",
        "<head>\n<script>window.gtag=function(){};"
        "window.dataLayer=window.dataLayer||[];</script>",
        1,
    )
    return html


def rewrite_paths(html: str) -> str:
    """Make root-absolute internal links resolve under the Pages subpath
    and as static .html files. Leaves external URLs untouched."""
    # Assets: /static/... -> /pokemon-cafe-bot/static/...
    html = re.sub(r'(["\'(])/static/', r'\1' + PAGES_PREFIX + '/static/', html)
    # Internal page links. href="/status..." -> /pokemon-cafe-bot/status.html...
    for page in ("status", "terms", "cancel", "success"):
        html = re.sub(
            r'href="/' + page + r'(?=["?#/])',
            f'href="{PAGES_PREFIX}/{page}.html',
            html,
        )
    # Guide links -> point at the live site (guides are not part of this
    # preview scope) so they are not dead 404s on Pages.
    html = re.sub(
        r'href="/guides/([A-Za-z0-9\-]+)"',
        r'href="https://cafesnapbot.com/guides/\1"',
        html,
    )
    html = re.sub(
        r'href="/guides/([A-Za-z0-9\-]+)\{% if',
        r'href="https://cafesnapbot.com/guides/\1"{# was: {% if',
        html,
    )
    # Bare home link href="/" (and the lang-qualified variant) -> index.html
    html = html.replace('href="/"', f'href="{PAGES_PREFIX}/index.html"')
    html = re.sub(
        r'href="/(\{% if lang)',
        f'href="{PAGES_PREFIX}/index.html?\\1',
        html,
    )
    return html


def inject_ribbon(html: str) -> str:
    """Insert the fixed PREVIEW ribbon right after <body ...>."""
    m = re.search(r"<body[^>]*>", html, flags=re.IGNORECASE)
    if m:
        i = m.end()
        return html[:i] + RIBBON_HTML + html[i:]
    # No <body> (shouldn't happen) - prepend.
    return RIBBON_HTML + html


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="source checkout root")
    ap.add_argument("--out", required=True, help="output dir for static site")
    ap.add_argument("--ref", default="origin/main")
    ap.add_argument("--commit", default="")
    args = ap.parse_args()

    src = Path(args.src).resolve()
    out = Path(args.out).resolve()
    tpl_dir = src / "templates"
    if not tpl_dir.is_dir():
        print(f"ERROR: {tpl_dir} not found", file=sys.stderr)
        return 1

    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(
        loader=FileSystemLoader(str(tpl_dir)),
        autoescape=select_autoescape(["html", "xml"]),
    )

    out.mkdir(parents=True, exist_ok=True)

    rendered = []
    for page in PAGES:
        tpl_name = f"{page}.html"
        if not (tpl_dir / tpl_name).exists():
            print(f"  skip (missing): {tpl_name}")
            continue
        for lang in ("en", "es"):
            ctx = safe_context(src, lang)
            try:
                html = env.get_template(tpl_name).render(**ctx)
            except Exception as e:
                print(f"  RENDER FAIL {tpl_name} [{lang}]: {e}", file=sys.stderr)
                raise
            html = rewrite_paths(html)
            html = scrub(html)
            html = neutralize_analytics(html)
            html = inject_ribbon(html)
            fname = f"{page}.html" if lang == "en" else f"{page}.es.html"
            (out / fname).write_text(html, encoding="utf-8")
            rendered.append(fname)
            print(f"  rendered {fname}  ({len(html):,} bytes)")

    # Static assets (favicons, og images, fonts). Public, no secrets.
    if (src / "static").is_dir():
        shutil.copytree(src / "static", out / "static", dirs_exist_ok=True)
        print("  copied static/ assets")

    # Carry the renderer + script onto gh-pages as reference (not executed
    # from there). Helps anyone inspecting the branch understand the build.
    scripts_out = out / "_preview_build"
    scripts_out.mkdir(exist_ok=True)
    for f in ("render_preview.py", "refresh_preview.sh"):
        sp = src / "scripts" / f
        if sp.exists():
            shutil.copy(sp, scripts_out / f)

    # Landing index at site root already = index.html (rendered). Add a
    # tiny README for anyone browsing the raw branch.
    (out / "README.md").write_text(
        "# CafeSnap PREVIEW site (static, $0 GitHub Pages)\n\n"
        f"Auto-generated from `{args.ref}` commit `{args.commit}`.\n\n"
        "Every page carries a fixed red PREVIEW ribbon. This is a VISUAL\n"
        "preview only: no live booking, no payment, no database. Do not\n"
        "confuse with production (cafesnapbot.com).\n\n"
        "Regenerate with `scripts/refresh_preview.sh <branch>` from a\n"
        "source checkout. Never edit this branch by hand.\n",
        encoding="utf-8",
    )

    print(f"\nRendered {len(rendered)} page(s) to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
