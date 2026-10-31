"""Render the payload into two self-contained HTML pages (same approach as OVERHANG).

``index.html`` is evidence-gated: everything on it links to a registered trial.
``claims.html`` holds what has been said: the claims ledger, speculative topics and the
news links that did not pass the gate (SPEC K4, K5). One template switched on ``page``.
"""

from __future__ import annotations

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

TEMPLATES = Path(__file__).resolve().parent / "templates"
PAGES = {"main": "index.html", "claims": "claims.html"}


def _cross_links(html: str, page: str) -> str:
    """Point an in-page ``#id`` that lives on the other page at that page."""
    ids = set(re.findall(r'\sid="([^"]+)"', html))
    other = PAGES["main"] if page == "claims" else PAGES["claims"]

    def fix(m: re.Match) -> str:
        return m.group(0) if m.group(1) in ids else f'href="{other}#{m.group(1)}"'

    return re.sub(r'href="#([^"]+)"', fix, html)


def render(payload: dict, out: Path) -> Path:
    env = Environment(
        loader=FileSystemLoader(TEMPLATES),
        autoescape=select_autoescape(["html", "j2"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    styles = (TEMPLATES / "styles.css").read_text(encoding="utf-8")
    for page, name in PAGES.items():
        html = env.get_template("page.html.j2").render(
            p=payload, page=page, styles=styles
        )
        (out.parent / name).write_text(_cross_links(html, page), encoding="utf-8")
    return out
