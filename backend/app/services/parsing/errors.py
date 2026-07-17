"""Map parsing exceptions to actionable, Italian, user-facing messages (SPEC §5).

These strings surface in the Indicizzazione queue (see the mock), so they live close to
the parser rather than in the frontend i18n file. Keep them short and actionable.
"""

_PATTERNS: list[tuple[tuple[str, ...], str]] = [
    (("password", "encrypted", "not decrypted"), "PDF protetto da password"),
    (("no such file", "cannot open", "file not found"), "File original non trovato nel repository"),
    (("unsupported", "cannot convert", "no matching format"), "Formato non supportato"),
    (("tesseract",), "OCR non riuscito: verifica l'installazione di Tesseract"),
]


def actionable_message(exc: Exception) -> str:
    text = str(exc).lower()
    for needles, message in _PATTERNS:
        if any(n in text for n in needles):
            return message
    return "Errore durante l'elaborazione del documento"
