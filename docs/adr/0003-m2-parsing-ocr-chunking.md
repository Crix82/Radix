# ADR 0003 — M2: parsing, OCR, chunking, rendering

Contesto: milestone M2 (Docling + ramo OCR Tesseract; chunk con pagina/bbox/heading;
endpoint di rendering pagina PNG con cache).

- **Confine `DocumentParser` con import lazy di Docling.** `app/services/parsing/base.py`
  definisce un modello normalizzato (`ParsedDocument`/`ParsedBlock`/`BBox`) indipendente
  da Docling; l'adapter reale (`docling_parser.py`) importa Docling/torch solo quando
  serve. Perché: il chunker e i suoi test non tirano torch, e `make test` resta veloce
  (unit su SQLite in millisecondi). L'integrazione reale è un test `slow` che si
  auto-salta se Docling/Tesseract non sono presenti, e gira su Docker.
- **Decisione OCR pilotata da una sonda del text layer.** `textlayer.py` estrae il testo
  per pagina con pypdfium2; se la media di caratteri per pagina è sotto soglia
  (`MIN_CHARS_PER_PAGE=40`) il documento va sul ramo OCR (Docling con
  `TesseractCliOcrOptions`, full-page). Perché: la scelta "text layer assente/povero →
  OCR" (SPEC §5) diventa logica pura e testabile, separata dal parser.
- **Tesseract via CLI, non tesserocr.** Docling usa `TesseractCliOcrOptions` (shell su
  `tesseract`), così l'immagine installa solo i pacchetti apt (`tesseract-ocr` + ita/eng/deu)
  senza compilare binding Python.
- **Chunking approssimato a ~4 caratteri/token.** Nessun tokenizer in M2: i confini dei
  chunk (target 400–600, overlap ~60) usano una stima chars/4. Perché: il tokenizer vero
  di bge-m3 serve solo in fase di embedding (M3); per delimitare i chunk la stima basta.
  Un blocco più grande del massimo resta un chunk unico: la provenienza (pagina/bbox) non
  va spezzata a metà.
- **Rilevamento lingua euristico (it/en/de/simple).** `lang.py` conta stopword: la config
  FTS distingue solo queste quattro, quindi niente dipendenza `langdetect`.
- **Stato terminale M2 = `chunking`.** Dopo la scrittura dei chunk il documento resta in
  `chunking` (non esiste uno stato "chunked"); M3 (embed→index) lo porterà a `indexed`.
- **Messaggi d'errore azionabili in italiano, lato backend** (`parsing/errors.py`). Es.
  "PDF protetto da password". Compaiono nella coda di Indicizzazione (vedi mock), quindi
  stanno vicino al parser e non nel file i18n del frontend — eccezione consapevole alla
  regola "stringhe UI solo via i18n".
- **Rendering PDF-only con pypdfium2 e cache atomica.** PNG per pagina generato lazy alla
  prima richiesta e scritto con `tmp`+`replace` in `data/pagecache/{doc}/{page}.png`; i
  formati non-PDF rispondono 415. PyMuPDF resta vietato (SPEC §14).
- **Fixture scansionata generata, non binaria a mano.** `generate_scanned_fixture.py`
  rasterizza un PDF di testo italiano (pypdfium2) e lo re-incapsula come PDF solo-immagine
  (Pillow): nessun text layer → il ramo OCR scatta davvero.
- **Modelli Docling pre-scaricati in fase di build** (`docling-tools models download` nel
  Dockerfile) per rispettare "nessuna chiamata esterna a runtime" (SPEC §9).
- **Nota dimensioni immagine:** `pip install .` porta torch (build CUDA di default, ~2 GB).
  L'ottimizzazione a torch CPU-only per il profilo CPU è rimandata (non è nella DoD M2).
