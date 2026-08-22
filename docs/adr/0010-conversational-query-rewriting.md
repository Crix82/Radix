# ADR 0010 — Riscrittura contestuale della query di retrieval

Contesto: post-M6. Il retrieval (`rag.answer_stream`) usava **solo l'ultimo messaggio utente**
come query. Lo storico (fino a 6 turni) entrava nel prompt dell'LLM, ma *dopo* il retrieval e la
soglia di rifiuto. Un follow-up come "e per la L12?" o "in quale pagina l'hai trovato?" non porta
con sé il soggetto stabilito dal thread: recupera rumore oppure finisce sotto soglia e viene
rifiutato senza nemmeno chiamare l'LLM, anche quando la risposta era nel turno precedente. Il
problema esiste da M4, ma la persistenza delle conversazioni (ADR 0008) incoraggia le chat
multi-turno e lo ha esposto. Decisione di prodotto rimandata il 2026-07-20 e presa il
2026-08-22 con il committente.

## Decisioni

- **Query rewriting con l'LLM, non euristiche.** Dal secondo turno in poi, prima del retrieval,
  `condense_question` chiede al provider di riscrivere la domanda come domanda autonoma (una
  chiamata breve, non-streaming, con gli ultimi `HISTORY_TURNS` turni troncati a
  `CONDENSE_TURN_CHARS`). Alternativa scartata: retrieval su "domanda precedente + attuale" e
  re-iniezione dei chunk citati nel turno prima, senza chiamata LLM. Costa zero latenza ma
  l'embedding della concatenazione si sporca ai cambi di argomento e, per far rispondere "in
  quale pagina?", avrebbe richiesto di **bypassare la soglia** sui follow-up, indebolendo la
  garanzia "fuori corpus → frase fissa senza LLM" (SPEC §8).
- **Retrieval su originale e riscritta: si tiene la classifica di quella che combacia meglio
  col corpus**, misurata dalla cosine densa del miglior hit — lo stesso segnale su cui si decide
  il rifiuto (ADR 0005); a parità vince l'originale. La riscrittura non sostituisce mai
  ciecamente la domanda: una riscrittura che deriva (il modello 1.5B ha perso "testata" in un
  caso e ha allucinato "capitale del Regno Mobile" in un altro) combacia peggio e perde. Costo:
  un embed e una query Qdrant in più — trascurabile rispetto alla chiamata LLM.
  **Scartata la fusione RRF delle due query**, che era la prima stesura: verificata con
  distrattori, il chunk atteso per "in quale pagina lo hai trovato?" passava da *assente dalla
  top-8* (domanda grezza) a rango 2 (riscritta) e **tornava assente nella fusione** — con k=60
  un chunk al rango 2 in una lista e basso nell'altra perde contro chunk mediocri presenti in
  entrambe. La fusione seppelliva proprio l'hit che la riscrittura serve a far emergere.
- **La soglia di rifiuto è invariata e opera sulla cosine migliore fra le due query.** Il
  contratto di rifiuto non cambia: una domanda fuori corpus resta fuori corpus anche riscritta
  ("qual è la capitale della Francia?" non acquista soggetto dal thread), e la riscrittura di un
  follow-up è una domanda autonoma come quelle su cui la soglia è stata calibrata (ADR 0005).
- **La riscrittura serve solo al retrieval.** Il prompt di risposta riporta le parole
  dell'utente (`Domanda: …`) più lo storico, come prima: un errore di riscrittura non può
  finire nella risposta, al massimo nel contesto recuperato, dove il grounding lo filtra.
- **Degrada sempre alla domanda originale.** Output vuoto, più lungo di `MAX_REWRITE_CHARS`,
  uguale alla frase di rifiuto, o un errore del provider → si recupera con la domanda grezza e
  si logga. La riscrittura è un aiuto al retrieval e non deve mai essere ciò che rompe un turno.
  Il primo turno non ha nulla da risolvere e non paga la chiamata.
- **Flag `RAG_QUERY_REWRITE` (default `true`).** È una chiamata LLM in più per ogni follow-up:
  ~1 s sul profilo GPU (reasoning già disattivato, ADR precedente), potenzialmente molto di più
  sul profilo CPU entry (SPEC §10). L'operatore può spegnerla e tornare al comportamento
  precedente senza redeploy del codice. Un'unica variabile d'ambiente, documentata in
  `.env.example` e nella guida; non nella tabella `settings` perché non è una taratura da
  calibrare a runtime come la soglia.
- **`ChatResult.retrieval_query`** espone la query usata dal retrieval. Diagnostico: lo stampa
  l'eval harness per capire *quale* riscrittura ha fallito; non viene inviato al client né
  salvato nello storico.
- **Eval multi-turno.** `eval/questions.yaml` acquisisce una sezione `conversations` (4 script:
  tre follow-up con pronomi/riferimenti impliciti e un cambio di argomento per verificare che
  la riscrittura non danneggi una domanda già autonoma); `run_eval.py` li rigioca come un
  thread e richiede ≥ 3/4 follow-up corretti oltre alla DoD M4 (≥ 8/10, rifiuto). Limite
  dichiarato: il corpus di fixture ha 7–8 chunk e `TOP_CONTEXT = 8`, quindi ogni query mette
  l'intero indice nel contesto e la sezione fa da guardia di regressione (la riscrittura non
  rompe i follow-up né un cambio di argomento), non da misura del guadagno. Scartato un criterio
  "prima citazione": senza marcatori `[n]` la prima citazione è il *vicino* a pagina precedente
  (l'espansione ai vicini emette la finestra in ordine di lettura), quindi fallirebbe a
  prescindere dalla riscrittura. Il guadagno è stato misurato a parte, con modelli reali
  (bge-m3 + Qwen2.5-1.5B via transformers, Qdrant in-memory, FTS esclusa) sulle fixture più
  24 chunk distrattori (31 chunk totali): rango del chunk atteso e cosine per domanda grezza,
  riscritta e scelta finale, più due follow-up fuori corpus che devono restare rifiutati. Vedi
  il CHANGELOG per i numeri.
- **Niente esempi nel prompt di riscrittura.** Nella prima stesura c'erano due esempi
  ("e per l'altro modello?", "in quale pagina?"); verificando con Qwen2.5-1.5B il modello ha
  copiato l'esempio nell'output riscrivendo un follow-up sul ciclo automatico in "in quale
  pagina si trova questo passaggio?". Tolti: la regola è descritta, non esemplificata.

## Rimane aperto

L'immagine da ~11,5 GB anche sul profilo CPU (stack `nvidia-*` portato da torch), annotato in
ADR 0009: scelta di prodotto separata, non toccata qui.
