# ADR 0011 — Ricerca cross-lingua: la domanda tradotta in inglese, fusa con l'originale

Contesto: primo test su un corpus reale (2026-10-22) — un libro tecnico inglese di 481 pagine
("Electric Power Transformer Engineering") con 26 domande in italiano, in un corpus con altri due
libri dello stesso tema. Dopo l'allargamento del contesto (ADR 0005, top 12 senza vicini) la
pagina attesa arrivava al modello 19 volte su 25; le mancanti erano in classifica al 13°–127°
posto.

## Decisione

- **Da una domanda non inglese si ricava anche la versione inglese** (`translate_question`,
  una chiamata breve non-streaming all'LLM con `TRANSLATE_PROMPT`; nessuna chiamata se la
  domanda è già inglese per `detect_language`). Dal secondo turno si traduce la domanda
  riscritta (ADR 0010).
- **Le classifiche delle due lingue si fondono con RRF** (dense + FTS dell'originale, dense +
  FTS della traduzione). A differenza della riscrittura, che può derivare e per questo vince
  "la migliore delle due", la traduzione porta lo stesso significato e le due lingue fanno
  emergere pagine diverse.
- La **soglia di rifiuto continua a leggere la cosine della domanda originale**, come è stata
  calibrata (ADR 0005); il prompt di risposta riporta le parole dell'utente.
- Fallisce in modo innocuo: errore del provider, output vuoto o troppo lungo → si cerca senza
  traduzione. Disattivabile con `RAG_QUERY_TRANSLATE=false` (default `true`).

## Perché

Misurato sul server (stessa configurazione di contesto, pagina attesa nel contesto su 25):

| Strategia | Pagina attesa |
|---|---|
| solo domanda italiana (prima) | 19 |
| migliore delle due (meccanismo ADR 0010) | 20 |
| solo traduzione inglese | 20 |
| **fusione RRF delle due** | **22** |

Restano fuori una domanda con risposta corretta da un'altra sezione, un calcolo su una figura e
la domanda trappola che deve essere rifiutata. Costo: ~0,5 s per domanda (Qwen3.5 9B su RTX
3070 Ti, misurato con il modello in parte su CPU).

Alternative scartate nella stessa giornata: **reranker** bge-reranker-v2-m3 (nessun guadagno,
19/25 con 50 o 200 candidati; non entra in 8 GB accanto all'LLM, ~1 min/domanda su CPU) e
**ragionamento acceso** (36/52 contro 43/52, primo token ~47 s).

## Note

- La FTS non trovava nulla neppure sulle domande tradotte: `websearch_to_tsquery` mette in AND
  tutte le parole, e una domanda in linguaggio naturale non compare mai intera in un chunk. Oggi
  la parte lessicale aiuta solo con domande fatte di parole chiave. Da rivedere a parte (OR con
  ranking), senza toccare questa decisione.
- Una traduzione può sbagliare un termine (visto: "LTC" reso come "LCC"); la fusione con
  l'originale lo assorbe.
