# ADR 0008 — Persistenza delle conversazioni di chat

Contesto: post-M6. La chat era completamente stateless — il thread viveva nello stato React di
`ChatPage`, il client rimandava l'intero array `messages` a ogni turno e un reload della pagina
lo cancellava. Richiesta: uno storico per utente, come ChatGPT/Claude. La persistenza chat non
è nello SPEC (né in scope né nella lista fuori scope §13), quindi è un'estensione oltre v1
decisa esplicitamente con il committente.

## Decisioni

- **Due tabelle, non una.** `conversations` (proprietario, titolo, `deleted_at`) e
  `chat_messages` (ruolo, contenuto, `citations` JSONB, `refusal`). Le citazioni sono salvate
  **così come sono state restituite al client**, non ricalcolate alla riapertura: il retrieval
  può dare risultati diversi dopo un re-index, e uno storico che cambia risposta a posteriori
  non è uno storico. Costo: qualche KB per turno, accettabile.
- **Scope minimale**: salva, riprendi, elenca, elimina. Niente rinomina, niente titolo generato
  dall'LLM (il titolo è la prima domanda troncata a 80 caratteri — evita una seconda inferenza
  per conversazione sul modello bundled), niente ricerca nello storico. SPEC §1: la semplicità
  radicale è un requisito.
- **Retention illimitata con cancellazione dall'utente**, soft-delete via `deleted_at` come per
  `documents`. Nessun job di purge periodico: sarebbe un job schedulato in più e una soglia da
  scegliere, per un archivio che cresce di kilobyte.
- **L'admin legge le conversazioni di tutti, ma non le cancella.** In un contesto industriale
  serve poter verificare cosa il sistema ha risposto. È però sorveglianza, quindi è
  **dichiarata nella UI** (stringa `nav.conversations.adminNotice` in sidebar) e nella guida di
  installazione: non deve essere una scoperta. La cancellazione resta solo al proprietario —
  l'accesso in lettura non si estende a distruggere i thread altrui.
- **La history diventa autoritativa lato server.** Con un `conversation_id`, i turni precedenti
  si leggono dal DB e quanto il client manda in `messages` viene ignorato (si usa solo l'ultima
  domanda). Prima il client poteva iniettare nel prompt turni mai avvenuti — con la chat
  stateless era un limite intrinseco, ora che i turni esistono sul server non c'è motivo di
  fidarsi del client. Test: `test_history_comes_from_the_db_not_from_the_client`.
- **Cap di 6 turni replayati** (`HISTORY_TURNS`). `build_messages` non aveva alcun limite: non
  esplodeva solo perché il client ripartiva da zero ogni sessione. Con thread persistenti una
  conversazione lunga farebbe crescere il prompt senza freno, a scapito del budget di contesto
  del retrieval (`MAX_CONTEXT_TOKENS = 3500`).
- **Evento SSE `meta` prima del primo token**, con `conversation_id` e titolo. Non basta
  appenderlo al payload `final`: un rifiuto non emette alcun token e il client deve poter
  adottare l'id (e aggiornare la URL a `/chat/:id`) in ogni caso, il prima possibile.
- **Il turno assistant si scrive nella sessione del generator SSE**, non in quella di richiesta:
  quest'ultima può chiudersi appena lo streaming parte (commento già presente in `chat.py`).
  Il turno utente si scrive prima, insieme alla riga di audit.
- **Audit e storico restano separati.** L'`audit_log` continua a registrare l'evento `chat`
  (ora anche con `object_type=conversation`): è append-only e non si cancella, lo storico sì.
  Due archivi con cicli di vita opposti, non se ne accorpa uno nell'altro.

## Trappola emersa: le migrazioni devono essere idempotenti

La `0001` costruisce lo schema con `Base.metadata.create_all()`, cioè dai modelli **correnti**.
Su un'installazione pulita crea quindi anche le tabelle introdotte dalle migrazioni successive,
e un `CREATE TABLE` in `0004` fallirebbe con *"relation already exists"* — proprio nel percorso
di `install.sh`. Non lo si vede su un DB già popolato né dai test su SQLite.

La `0002` (ALTER su colonna già nullable) e la `0003` (drop + re-add di `tsv`) erano
idempotenti per caso. La `0004` lo è per costruzione: crea ogni tabella solo se assente, ed è un
no-op in modalità offline (`--sql`), dove non si può ispezionare il DB e la `0001` emette già i
`CREATE TABLE`. Guardia di regressione: `test_no_table_is_created_twice`.

Alternativa scartata: congelare la `0001` su un elenco statico di tabelle. È più corretto in
teoria, ma riscrive una migrazione già applicata in produzione e sposta soltanto il problema
(una futura `ADD COLUMN` ricadrebbe nello stesso caso). Con un solo manutentore, il vincolo
"ogni migrazione idempotente rispetto ai modelli correnti" è più economico da rispettare che una
riscrittura dello schema iniziale.

Verificato su Postgres 16 reale: `upgrade head` su DB vuoto (13 tabelle) e su installazione
ferma a `0003`; roundtrip JSONB delle citazioni e CASCADE da `users` a conversazioni e turni.
