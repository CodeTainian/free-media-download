from __future__ import annotations

import html

from .analysis_models import WebsiteManifest, WebsiteTheme


_THEMES = {
    WebsiteTheme.EDITORIAL: {
        "background": "#f7f7f4",
        "surface": "#ffffff",
        "text": "#1d2925",
        "muted": "#62706a",
        "accent": "#c64e1a",
    },
    WebsiteTheme.LEARNING: {
        "background": "#f2f7f5",
        "surface": "#ffffff",
        "text": "#173c34",
        "muted": "#527168",
        "accent": "#2b7161",
    },
    WebsiteTheme.DOCUMENTARY: {
        "background": "#f4f0e8",
        "surface": "#fffdf8",
        "text": "#29251f",
        "muted": "#746b5e",
        "accent": "#9b4d2b",
    },
    WebsiteTheme.PRODUCT_BRIEF: {
        "background": "#f5f6fa",
        "surface": "#ffffff",
        "text": "#202433",
        "muted": "#666d80",
        "accent": "#4858a8",
    },
}


def _text(value: object) -> str:
    return html.escape(str(value), quote=True)


def render_website_html(
    manifest: WebsiteManifest,
    *,
    theme: WebsiteTheme | None = None,
) -> str:
    selected = theme or manifest.theme
    palette = _THEMES[selected]
    headings = (
        {
            "chapters": "章节",
            "ideas": "重要观点",
            "glossary": "术语表",
            "sources": "来源",
        }
        if manifest.language == "zh-CN"
        else {
            "chapters": "Chapters",
            "ideas": "Important ideas",
            "glossary": "Glossary",
            "sources": "Sources",
        }
    )
    chapters = "\n".join(
        (
            "<article class=\"card\">"
            f"<p class=\"time\">{chapter.start_seconds:.0f}s</p>"
            f"<h3>{_text(chapter.title)}</h3>"
            f"<p>{_text(chapter.summary.text)}</p>"
            "</article>"
        )
        for chapter in manifest.chapters
    )
    glossary = "\n".join(
        (
            "<article class=\"term\">"
            f"<dt>{_text(item.term)}</dt>"
            f"<dd>{_text(item.definition.text)}</dd>"
            "</article>"
        )
        for item in manifest.glossary
    )
    callouts = "\n".join(
        f"<blockquote>{_text(item.text)}</blockquote>" for item in manifest.callouts
    )
    sources = "\n".join(
        (
            "<li>"
            f"<a href=\"{_text(str(source.url))}\" rel=\"noreferrer\">"
            f"{_text(source.label)}</a>"
            "</li>"
        )
        for source in manifest.sources
    )
    return f"""<!doctype html>
<html lang="{_text(manifest.language)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="referrer" content="no-referrer">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'">
  <title>{_text(manifest.title)}</title>
  <style>
    :root {{
      --background: {palette["background"]};
      --surface: {palette["surface"]};
      --text: {palette["text"]};
      --muted: {palette["muted"]};
      --accent: {palette["accent"]};
    }}
    * {{ box-sizing: border-box; }}
    body {{
      background: var(--background);
      color: var(--text);
      font-family: ui-sans-serif, system-ui, sans-serif;
      line-height: 1.6;
      margin: 0;
    }}
    main {{ margin: 0 auto; max-width: 1120px; padding: 64px 24px 96px; }}
    header {{ max-width: 820px; padding: 48px 0 72px; }}
    .eyebrow, .time {{ color: var(--accent); font-size: .78rem; font-weight: 750; letter-spacing: .08em; text-transform: uppercase; }}
    h1 {{ font-size: clamp(2.5rem, 8vw, 5.5rem); letter-spacing: -.06em; line-height: .96; margin: 12px 0 28px; }}
    h2 {{ font-size: clamp(1.7rem, 4vw, 2.6rem); margin-top: 72px; }}
    .lead {{ color: var(--muted); font-size: 1.2rem; }}
    .grid {{ display: grid; gap: 18px; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }}
    .card, .term, blockquote {{ background: var(--surface); border: 1px solid color-mix(in srgb, var(--text) 12%, transparent); border-radius: 18px; margin: 0; padding: 24px; }}
    .card h3, .term dt {{ margin: 4px 0 10px; }}
    .term dd {{ color: var(--muted); margin: 0; }}
    blockquote {{ border-left: 4px solid var(--accent); font-size: 1.08rem; margin-bottom: 14px; }}
    a {{ color: var(--accent); }}
    @media (max-width: 560px) {{ main {{ padding: 32px 18px 64px; }} header {{ padding-top: 24px; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <p class="eyebrow">{_text(manifest.hero.eyebrow)}</p>
      <h1>{_text(manifest.hero.title)}</h1>
      <p class="lead">{_text(manifest.hero.subtitle)}</p>
    </header>
    <section aria-labelledby="chapters">
      <h2 id="chapters">{headings["chapters"]}</h2>
      <div class="grid">{chapters}</div>
    </section>
    <section aria-labelledby="ideas">
      <h2 id="ideas">{headings["ideas"]}</h2>
      {callouts}
    </section>
    <section aria-labelledby="glossary">
      <h2 id="glossary">{headings["glossary"]}</h2>
      <dl class="grid">{glossary}</dl>
    </section>
    <section aria-labelledby="sources">
      <h2 id="sources">{headings["sources"]}</h2>
      <ul>{sources}</ul>
    </section>
  </main>
</body>
</html>
"""
