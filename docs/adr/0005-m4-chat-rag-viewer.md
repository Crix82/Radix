# ADR 0005 — M4: chat RAG e visualizzatore

Contesto: milestone M4 (`/chat` SSE con citazioni, soglia di rifiuto, UI Chat + Viewer,
eval harness).

- **Un solo client LLM OpenAI-compatibile** (`OpenAICompatibleProvider`) dietro
  `OllamaProvider`/`VLLMProvider`: Ollama e vLLM espongono la stessa API
  `/chat/completions`, differiscono solo per base URL/modello via env. Selezione in
  `get_llm_provider()` da `LLM_PROVIDER`. Streaming SSE parsato token-by-token.
- **Rifiuto basato sulla similarità coseno densa del miglior chunk, non sul punteggio
  RRF.** La SPEC §8 dice "miglior punteggio fuso < soglia", ma il punteggio RRF è basato
  sul *rango* (1/(k+rank)) e non discrimina un match on-corpus da uno off-corpus: il top
  risultato vale ~1/61 comunque. La cosine densa di bge-m3 riflette la rilevanza
  semantica reale ed è il segnale corretto per rifiutare. Deviazione consapevole
  dall'implementazione letterale, l'intento della spec (rifiutare fuori corpus) è
  preservato. Soglia default 0.55, override nella tabella `settings`
  (`refusal_threshold`), calibrabile.
- **La frase di rifiuto è esatta e non chiama l'LLM** (`REFUSAL_PHRASE`, SPEC §8/DoD):
  se non ci sono chunk o la cosine è sotto soglia, l'evento `final` porta la frase e
  `refusal: true`, senza toccare il provider.
- **Citazioni robuste**: si parsano i marcatori `[n]` nella risposta e si mappano ai
  chunk di contesto; se il modello non cita, si allegano comunque tutte le fonti usate
  (SPEC §8). Ogni citazione porta titolo, lingua, pagina e bbox per il viewer e il
  pannello Fonti.
- **Contesto**: top 8 chunk fusi, budget ~3500 token (stima chars/4), ognuno etichettato
  `[n]` con titolo e pagina; lo storico della conversazione precede la domanda aumentata.
- **SSE via `StreamingResponse`** con sessione DB propria dentro il generatore (quella
  della request può chiudersi all'avvio dello streaming). Eventi `token` poi `final`.
- **Viewer**: rende il PNG di pagina (endpoint M2) con overlay dei rettangoli di
  evidenziazione dai bbox normalizzati (0–1 → percentuali), rail miniature e back
  contestuale (chat/ricerca via history). Il click su citazione naviga a
  `/viewer/:doc/:page` passando i bbox nello stato di navigazione.
- **Eval harness** (`eval/run_eval.py`, `make eval`): 10 domande in `questions.yaml`
  ancorate alle fixture (incluse una cross-lingua IT→EN, una IT→DE e una su OCR) più una
  domanda fuori corpus. Lo scoring verifica che una citazione punti al documento e alla
  pagina attesi; il punteggio di citazione è guidato dal retrieval (con fallback a tutte
  le fonti), quindi resta stabile anche con LLM piccoli. Nuova dipendenza dev: PyYAML (MIT).
