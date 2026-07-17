"""Build an HTML snippet with the query terms highlighted (SPEC §7: amber highlight).

Pure and Postgres-free (no ts_headline), so hydration works the same in tests and prod.
Output is HTML-escaped except for the <b>…</b> markers we insert around matches.
"""

import html
import re

MAX_LEN = 240
_TOKEN_RE = re.compile(r"[0-9A-Za-zÀ-ÿ]+")


def _query_terms(query: str) -> list[str]:
    # Drop 1-char tokens; longer terms first so "serraggio" wins over "se" when wrapping.
    terms = {t.lower() for t in _TOKEN_RE.findall(query) if len(t) >= 2}
    return sorted(terms, key=len, reverse=True)


def make_snippet(text: str, query: str, max_len: int = MAX_LEN) -> str:
    text = " ".join(text.split())  # collapse whitespace/newlines
    terms = _query_terms(query)

    start = 0
    if terms:
        pattern = re.compile("|".join(re.escape(t) for t in terms), re.IGNORECASE)
        match = pattern.search(text)
        if match:
            start = max(0, match.start() - max_len // 3)

    window = text[start : start + max_len]
    prefix = "…" if start > 0 else ""
    suffix = "…" if start + max_len < len(text) else ""

    escaped = html.escape(window)
    if terms:
        # Terms are alphanumeric, so wrapping the escaped window is injection-safe.
        highlight = re.compile("|".join(re.escape(t) for t in terms), re.IGNORECASE)
        escaped = highlight.sub(lambda m: f"<b>{m.group(0)}</b>", escaped)
    return f"{prefix}{escaped}{suffix}"
