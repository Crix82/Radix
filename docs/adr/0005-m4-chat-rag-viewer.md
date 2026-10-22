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
  preservato. **Calibrata sull'eval set** (M4): le domande rispondibili hanno cosine
  >= 0.52, quindi la default è **0.45** (margine + rifiuta query chiaramente estranee);
  override nella tabella `settings` (`refusal_threshold`). La domanda fuori corpus
  "RS-55" ha cosine 0.549 (vicinissima all'RS-30): la soglia da sola non la distingue, è
  il grounding dell'LLM a produrre la frase di rifiuto — verificato nell'eval.
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
- **Contesto di Ollama fissato a 8192 token** (2026-10-22, emerso al deploy su RTX 3070 Ti 8 GB):
  Ollama dimensiona il contesto dalla VRAM e sotto i 24 GB sceglie 4096. Il prompt RAG porta
  fino a `MAX_CONTEXT_TOKENS` = 3500 token di estratti, più system prompt, storico e risposta:
  sull'eval si misuravano già 3442 token per richiesta, e oltre 4096 Ollama taglia l'inizio del
  prompt senza errori. `OLLAMA_CONTEXT_LENGTH` (default 8192, sovrascrivibile da `.env`) nei
  compose bundled e dev. Il costo è solo memoria per la KV cache, non velocità.
- **Contesto: top 12, senza vicini, budget 6000 token; Ollama a 12288** (2026-10-22, test su
  un libro di 481 pagine con 26 domande in italiano su testo inglese, corpus con altri due
  libri dello stesso tema). La pagina attesa si piazzava spesso tra il 6° e il 12° posto, ma
  con top 8 + vicini ±1 in 3500 token al modello arrivavano solo i primi 2–4 risultati: pagina
  attesa nel contesto 12/25. Simulazione sul server: top 8 + vicini a 6000 token → 14/25;
  **top 12 senza vicini a 6000 → 19/25** (top 16 non aggiunge nulla). Scelta: `TOP_CONTEXT=12`,
  `MAX_CONTEXT_TOKENS=6000`, `NEIGHBOR_RADIUS=0` (il meccanismo resta, spento di default) e
  `OLLAMA_CONTEXT_LENGTH` di default 12288, perché 6000 token di estratti più system prompt,
  storico e risposta non stanno in 8192. Compromesso accettato: senza vicini un fatto spezzato
  tra due chunk adiacenti (il caso fattura che li aveva motivati) può tornare a mancare.
  Costo: primo token più lento (più prompt da leggere). La FTS non contribuisce mai su domande
  IT / testo EN (nessun termine in comune): resta utile sui corpus nella lingua delle domande.
  Restano fuori le domande con la pagina giusta molto in basso (rango 13–127): servirebbe un
  reranker o la traduzione della query, rimandati.
- **Fallback delle fonti limitato ai primi 3 estratti** (2026-10-22). Se il modello non mette
  marcatori `[n]`, prima si allegava l'intero contesto (oggi 12 chunk): nel test sul libro di
  481 pagine il pannello Fonti si riempiva di pagine di altri libri sullo stesso tema.
  `FALLBACK_SOURCES=3`: il contesto è in ordine di retrieval, quindi i primi sono i più
  pertinenti. La risposta resta sempre con fonti (SPEC §8), ma non con quelle irrilevanti.
