"""Lightweight language detection for it/en/de, falling back to 'simple'.

The FTS config (SPEC §4.1) only distinguishes italian/english/german/simple, so a
stopword-frequency heuristic is enough and keeps the dependency footprint at zero.
"""

import re


def _words(text: str) -> frozenset[str]:
    return frozenset(text.split())


# Frequent function words that are distinctive per language.
_STOPWORDS: dict[str, frozenset[str]] = {
    "it": _words(
        "il lo la i gli le un uno una di del della che non per con sono come alla "
        "nel nella dei delle è più questa questo essere anche ogni deve"
    ),
    "en": _words(
        "the a an of to and in is are be this that for with on as it not by from "
        "at which must each shall page section"
    ),
    "de": _words(
        "der die das den dem ein eine und ist sind zu von mit auf für nicht auch "
        "im werden wird sich oder aus nach bei durch muss"
    ),
}

_WORD_RE = re.compile(r"[a-zàáâäèéêëìíîïòóôöùúûüß'']+")


def detect_language(text: str) -> str:
    """Return 'it' | 'en' | 'de', or 'simple' when no language dominates."""
    words = _WORD_RE.findall(text.lower())
    if not words:
        return "simple"
    scores = {lang: sum(1 for w in words if w in stop) for lang, stop in _STOPWORDS.items()}
    best_lang = max(scores, key=lambda k: scores[k])
    best = scores[best_lang]
    if best == 0:
        return "simple"
    # Require a clear winner over the runner-up to avoid coin-flips on short/mixed text.
    runner_up = max(v for k, v in scores.items() if k != best_lang)
    if best == runner_up:
        return "simple"
    return best_lang
