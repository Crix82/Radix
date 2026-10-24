# ADR 0014 — Rifiuto solo se nessun passaggio è pertinente

Contesto (2026-10-24): sul test del cliente Qwen3.5 9B rifiutava tre domande (#18, #20, #21)
pur superando la soglia di similarità (0,61–0,68 contro 0,45). Leggendo la risposta intera, che
oggi viene troncata dopo la frase di rifiuto, il modello scriveva "Non presente…" e poi
spiegava che i passaggi contenevano il metodo (formula di valutazione delle perdite, rapporto
spire) ma "non i valori della domanda": trattava i dati dell'utente come conoscenza esterna, e
davanti a una copertura parziale sceglieva il rifiuto.

## Decisione

Il prompt di sistema (SPEC §8) cambia in due punti:

- la frase di rifiuto è **riservata** ai casi in cui nessun passaggio riguarda l'argomento; se il
  modello sta per spiegare che qualche passaggio ne parla, deve rispondere con quello e dire cosa
  manca;
- se la domanda fornisce dei dati e i passaggi contengono il metodo o la formula, il modello la
  applica e mostra il calcolo.

Provate tre varianti con una sonda sulle domande da recuperare e su quelle che devono essere
rifiutate (#25, #26, RS-55 dell'eval). Aggiungere solo le due regole al prompt originale non
cambiava nulla: il modello apriva comunque con la frase di rifiuto. Ha funzionato descrivere
*quando* la frase si usa, invece di ordinarla come risposta di ripiego.

## Misure

Excel del cliente (max 52), stesso indice della v5: **46/52** (prima 44). La #20 ora calcola
600.000 $ citando le pagine 28 e 82; nessun'altra risposta peggiora. Eval invariato: 10/10
citazioni, rifiuto RS-55 corretto, follow-up 4/4; #25 e #26 ancora rifiutate. Primo token
mediano 2,4 s.

Restano a 0 la #18 e la #21: le pagine attese (16 e 315) non arrivano nel contesto, quindi il
rifiuto lì è corretto rispetto a ciò che il modello vede. È un problema di ricerca.

## Conseguenze

- Risposte un po' più lunghe sulle domande parziali; il troncamento dopo la frase di rifiuto
  (rag.answer_stream) resta, per i casi in cui il modello la scrive comunque.
