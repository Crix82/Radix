# ADR 0013 — Tabelle indicizzate e brani con il loro capitolo

Contesto (2026-10-23): sul test del cliente (26 domande, libro di 481 pagine) due domande sono
sbagliate da tutti i modelli provati, da Qwen3.5 9B a gpt-oss-120b. Non è il modello: una sonda
di sola ricerca (`retrieval_probe.py`, nessuna risposta generata) mostra due difetti
dell'indicizzazione.

- **#7, limiti di sovratemperatura:** la pagina 24 arriva nel contesto (6° posto), ma la tabella
  2.1.1 con i valori (65 / 80 / 65 °C) non c'è. Docling la legge correttamente; il nostro adapter
  prende il campo `text` di ogni elemento e le tabelle (`TableItem`) non ne hanno uno, quindi
  **ogni tabella di ogni documento veniva scartata** in silenzio. Restavano solo didascalie e
  note a piè di tabella.
- **#11, prese dei trasformatori a secco:** il brano giusto esiste ("two taps above and two taps
  below rated voltage… 10%") ma non dice "dry-type": lo dice il capitolo "2.5 Dry-Type
  Transformers". Docling assegna lo stesso livello a tutti i titoli di un PDF, quindi il percorso
  dei titoli era solo "2.5.1 Transformer Taps"; e il percorso, pur salvato, non entrava né
  nell'embedding né nel prompt. La pagina era al 21° posto.

## Decisione

- **Tabelle → markdown.** Un elemento senza testo ma con `export_to_markdown` diventa una tabella
  markdown compatta (senza gli spazi di allineamento), con pagina, bbox e titolo come gli altri
  blocchi. **Ogni tabella è un brano a sé**: Docling spesso la attacca al paragrafo successivo
  (la 2.1.1 finiva sotto "2.1.2.2 Insulation Classes") e, mescolata a quel testo, la ricerca non
  la proponeva per una domanda sulle temperature.
- **Gerarchia dei titoli dalla numerazione.** Un titolo che inizia con "2.5", "2.5.1", "3." ha
  come livello la profondità del numero; un titolo non numerato (riga d'autore, "References")
  si annida sotto la sezione numerata corrente invece di cancellarla. Senza numerazione restano
  i livelli di Docling. Numeri di capitolo fino a due cifre, così anni e quantità ("2004 edition",
  "100 MVA") non contano come sezioni.
- **Il brano viaggia con il suo capitolo.** L'embedding si calcola su "percorso dei titoli + testo"
  (`contextual_text`); il testo salvato resta quello della pagina, perché citazioni ed evidenziazioni
  puntano a ciò che è stampato. Nel prompt l'intestazione di ogni passaggio aggiunge
  `sezione: …`, così il modello sa di cosa parla un brano breve.
- La ricerca per parole chiave resta com'è: oggi non restituisce nulla con domande in linguaggio
  naturale (AND di tutte le parole, ADR 0011), ma passarla in OR da sola peggiora la sonda (18
  pagine attese nei primi 12 invece di 20). Va ripensata a parte.

## Conseguenze

- I vettori vanno a Qdrant a blocchi di 256 punti: con i brani in più il libro da 957 pagine
  superava in una sola richiesta il limite di 32 MB di Qdrant (bug latente, ora coperto da test).
- Le modifiche valgono solo per i documenti rielaborati: dopo l'aggiornamento un'installazione
  esistente deve rilanciare l'indicizzazione (pulsante "Reindicizza" per documento, o tutti in
  coda). Su CPU il libro di prova da 481 pagine richiede circa 40 minuti.

## Misure

Test del cliente (26 domande, massimo 52 punti), Qwen3.5 9B, server con RTX 3070 Ti:

- Sonda di sola ricerca, pagina attesa nei primi 12 brani: da 20 a 21 domande su 25; #7 pagina
  24 dal 6° al 1° posto, #11 pagina 124 dal 21° al 3° posto.
- Excel con tabelle e titoli (tabelle ancora unite al testo): **45/52** (prima 43). #11 corretta;
  #7 a 0 perché la tabella era nel brano sull'isolamento. Eval invariato: 10/10 citazioni,
  rifiuto corretto, follow-up 4/4; primo token mediano 2,6 s.
- Tabelle come brani a sé: misura in corso.
