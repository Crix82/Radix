# Radix — Specifica di sviluppo v1
**SPEC.md · 17 luglio 2026 · destinatario: Claude Code**
Documenti di riferimento nel repo: `docs/prd-piattaforma-ai-documentale-v0.1.md` (il *perché*), `docs/mock/radix-mock-v1.html` (il *come appare* — fonte di verità per la UI).

---

## 0. Come usare questo documento con Claude Code

1. Crea la cartella del repository `radix/` e copia dentro: questo file come `SPEC.md`, il PRD e il mock in `docs/`.
2. Apri Claude Code nella cartella del progetto (installazione e requisiti: https://docs.claude.com/en/docs/claude-code/overview).
3. Primo prompt suggerito: **"Leggi SPEC.md. Esegui la milestone M0 completa, poi fermati e mostrami l'esito dei check di Definition of Done."**
4. Procedi **una milestone per volta** (M0 → M6). Non passare alla successiva con test rossi.
5. A fine milestone: aggiorna `CLAUDE.md` se sono emerse nuove convenzioni, e la sezione CHANGELOG in fondo a questo file.

Regola per Claude Code: **questo documento contiene decisioni già prese, non opzioni.** Se una decisione si rivela impraticabile durante lo sviluppo, fermati, spiega il problema e proponi un'alternativa — non sostituirla in silenzio.

---

## 1. Contesto e obiettivo

Radix è una piattaforma di intelligenza documentale **interamente on-premise** per PMI industriali: ricerca ibrida e chat RAG multilingua sulla documentazione tecnica (manuali, bollettini, schede), con **citazioni cliccabili alla pagina esatta** ed evidenziazione del passaggio nel documento originale. Un'installazione serve fino a 500 GB di documenti, 20 utenti, 2 concorrenti, su un singolo nodo Docker Compose. Nessun dato lascia mai il server del cliente. Team di sviluppo: una persona + Claude Code — la **semplicità radicale è un requisito**, non una preferenza.

---

## 2. Decisioni bloccate

| Area | Decisione |
|---|---|
| Runtime backend | Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, Pydantic v2 |
| Job queue | Redis 7 + RQ, worker in container separato |
| Database | PostgreSQL 16 (metadati + full-text search) |
| Vector store | Qdrant (dense 1024, cosine, quantizzazione scalar int8, `on_disk: true`) |
| Parsing documenti | Docling (PDF, DOCX, XLSX, PPTX, HTML, TXT) |
| OCR | Tesseract, lingue `ita+eng+deu`, fallback automatico quando manca/è povero il text layer |
| Embeddings | `BAAI/bge-m3` (dense), device auto: CUDA se disponibile, altrimenti CPU |
| LLM | Astrazione `LLMProvider`; default **Ollama** (endpoint OpenAI-compatibile); produzione: vLLM intercambiabile via config |
| Modelli default | GPU 8 GB (dev): Qwen3.5 9B instruct Q4_K_M · Profilo CPU: Qwen3 4B instruct Q4 |
| Rendering pagine PDF | **pypdfium2** (PDFium). **Vietato PyMuPDF** (licenza AGPL, incompatibile) |
| Frontend | React 18 + Vite + TypeScript, TanStack Query, react-router, SSE per lo streaming chat |
| Stile UI | Tailwind CSS con i design token del mock (palette §7.2). Il mock è la fonte di verità visiva |
| Reverse proxy / TLS | Caddy (HTTPS con certificato self-signed o del cliente) |
| Auth | Sessioni JWT in cookie httpOnly, hash argon2id, ruoli `admin`/`user`, permessi per collezione |
| Licenze dipendenze | **Solo Apache-2.0 / MIT / BSD o equivalenti permissive.** Vietate AGPL, SSPL, BUSL, licenze non-commercial (§14) |
| Lingua | Codice, commenti, identificatori: **inglese**. Stringhe UI: **italiano** (file i18n, default `it`) |
| Telemetria | Nessuna. Zero chiamate verso l'esterno a runtime |

---

## 3. Architettura e struttura del repository

Monolite modulare: un'app FastAPI, un worker RQ, un frontend. Niente microservizi.

```
radix/
├── SPEC.md                    # questo documento
├── CLAUDE.md                  # convenzioni operative (generato in M0 da §12)
├── docker-compose.yml         # produzione
├── docker-compose.dev.yml     # override dev: hot reload, servizio ollama
├── .env.example
├── Makefile                   # up, down, logs, test, lint, eval, backup, restore
├── backend/
│   ├── app/
│   │   ├── api/               # router per dominio: auth, search, chat, documents, sources, indexing, users, audit
│   │   ├── core/              # config, security, db, deps
│   │   ├── models/            # SQLAlchemy + schemi Pydantic
│   │   └── services/          # search, rag, llm (providers/), embeddings, rendering, tagging
│   ├── worker/                # job RQ: sync_source, parse_document, embed_chunks, index_chunks
│   ├── tests/                 # pytest + fixtures/ (PDF di prova, incl. una scansione ITA)
│   └── pyproject.toml
├── frontend/                  # React + Vite + TS
├── deploy/
│   ├── install.sh             # setup su Ubuntu 24 pulita
│   ├── backup.sh · restore.sh
│   └── caddy/Caddyfile
├── docs/                      # prd-*.md · mock/radix-mock-v1.html · adr/ (decisioni prese in corsa)
└── eval/                      # questions.yaml · run_eval.py  (make eval)
```

Servizi Docker Compose: `caddy`, `api`, `worker`, `frontend` (build statici serviti da Caddy), `postgres`, `redis`, `qdrant`, `ollama` (solo profilo dev/GPU). Volumi persistenti: `data/{postgres,qdrant,repository,pagecache,models}`.

---

## 4. Modello dati

### 4.1 PostgreSQL

- `users(id, name, email UNIQUE, password_hash, role ENUM[admin,user], status ENUM[active,invited,disabled], created_at)`
- `collections(id, name UNIQUE)` — es. Manuali, Qualità, Formulazioni
- `user_collections(user_id, collection_id)` — permessi
- `sources(id, type ENUM[smb,local,upload], path, collection_id, enabled bool, status, last_sync_at)`
- `documents(id, source_id, collection_id, rel_path, title, lang, doc_type, content_hash, size_bytes, pages, status ENUM[queued,parsing,ocr,chunking,embedding,indexed,error,excluded], error_msg, created_at, updated_at, deleted_at)`
- `chunks(id, document_id, page_start, page_end, heading_path, text, bboxes JSONB, lang, tsv tsvector GENERATED)` — indice GIN su `tsv`; config FTS per lingua (`italian`/`english`/`german`, fallback `simple`)
- `tags(id, name, kind ENUM[doc_type,topic])` · `document_tags(document_id, tag_id, origin ENUM[auto,manual])`
- `audit_log(id, ts, user_id, action, object_type, object_id, meta JSONB, ip)` — append-only
- `settings(key PK, value JSONB)` — es. `refusal_threshold`

### 4.2 Qdrant

Collection `chunks`: vettore dense 1024 (cosine), quantizzazione int8, storage su disco. Payload: `{chunk_id, document_id, collection_id, page_start, lang, doc_type}` con indici payload su `collection_id`, `lang`, `doc_type`. L'id del punto = `chunk_id` (stessa chiave di Postgres).

---

## 5. Pipeline di indicizzazione

Stadi (job RQ, ognuno idempotente e riprocessabile): **discover → parse → (ocr) → chunk → embed → index**.

- **Discover** (`sync_source`): scandisce la fonte (SMB via mount, cartella locale, upload), calcola `content_hash` (sha256), deduplica per `(source_id, rel_path, content_hash)`. Nuovo o modificato → copia nel repository interno (`data/repository/{document_id}/original.ext`) e accoda. File rimosso → soft delete (tombstone) e rimozione dei punti da Qdrant. Watcher: scansione periodica (default 5 min, config).
- **Parse**: Docling estrae struttura (heading, tabelle) e testo con provenance (pagina + bbox). Se il text layer è assente o sotto soglia di qualità → ramo OCR (Tesseract) e ri-parse.
- **Chunk**: structure-aware sui path di heading, target 400–600 token, overlap ~60. Ogni chunk porta `page_start/end`, `bboxes` (coordinate normalizzate 0–1 per pagina), `heading_path`, `lang` (rilevata per documento, override per chunk se necessario).
- **Embed**: bge-m3 in batch; scrittura chunk su Postgres e upsert su Qdrant nella stessa transazione logica (Postgres prima, Qdrant poi; retry su Qdrant).
- **Rendering pagine**: pypdfium2 → PNG per pagina, generato lazy alla prima richiesta e cache su `data/pagecache/{document_id}/{page}.png`.
- **Stati e errori**: ogni transizione aggiorna `documents.status`; errori con messaggio *azionabile* (es. "PDF protetto da password"). Azioni API: `exclude`, `reindex`.
- **Tagging automatico** (leggero): `doc_type` da euristiche (estensione, pattern nel nome/contenuto); `topic` per similarità del centroide embeddings del documento con i tag definiti dall'admin. Origine `auto`, sempre correggibile a mano.

---

## 6. API (prefisso `/api/v1`)

- `POST /auth/login` · `POST /auth/logout` · `GET /me`
- `GET /search?q=&lang=&doc_type=&collection_id=` → `[{chunk_id, document:{id,title,lang,doc_type,rel_path}, page, snippet_html, score}]`
- `POST /chat` (SSE) — body `{messages:[...], filters:{lang?,doc_type?,collection_id?}}` → eventi `token` in streaming, poi `final {answer_md, citations:[{n, chunk_id, document_id, page, bboxes}]}`
- `GET /documents/{id}` · `GET /documents/{id}/pages/{n}.png` · `GET /documents/{id}/download`
- `GET /indexing/stats` (totali, spazio, coda, errori) · `GET /indexing/queue` · `POST /documents/{id}/exclude` · `POST /documents/{id}/reindex`
- `GET|POST|PATCH|DELETE /sources` · `POST /uploads` (multipart)
- `GET|POST|PATCH /users` · `GET|POST /collections` · `GET|POST /tags`
- `GET /audit?user_id=&action=&from=&to=` · `GET /health` (stato di api, db, redis, qdrant, llm)

**Permessi enforced sempre lato server**: ogni query su search/chat/documents filtra per le collezioni dell'utente (filtro Qdrant su `collection_id` + WHERE SQL). Mai fidarsi dei filtri del client.

---

## 7. Frontend

### 7.1 Schermate = mock, uno a uno
`docs/mock/radix-mock-v1.html` è la fonte di verità per layout, copy italiano, stati e micro-interazioni: **Onboarding** (prima attivazione), **Ricerca** (filtri lingua/tipo, snippet con evidenziazione, badge lingua, pagina in mono), **Chat** (citazioni ambra ①② cliccabili, pannello Fonti, stato di rifiuto), **Visualizzatore** (pagina renderizzata + overlay di evidenziazione dai `bboxes`, rail miniature, back contestuale), **Fonti** (+ modale aggiunta; Google Drive/SharePoint mostrati come "Disponibile nella v1.1", disabilitati), **Indicizzazione** (stat card, coda con stati, errore azionabile), **Utenti** (+ modale invito, permessi per collezione).

### 7.2 Design token (dal mock)
`petrol #0E5B66 · petrol-mid #2E8A97 · nav #14262D · amber #E5A13A (riservato a citazioni ed evidenziazioni) · amber-tint #FBF2DF · ink #182730 · ink2 #5D6E77 · bg #F1F4F6 · line #E0E6EA · ok #2F7D5B · err #BC4238` — radius 10/8, mono per metadati tecnici (percorsi, pagine, nomi file).

### 7.3 Comportamenti chiave
Chat in streaming con indicatore "sta cercando nei documenti"; click su citazione → viewer alla pagina giusta con highlight; il viewer ricorda da dove si arriva (chat o ricerca). L'onboarding compare quando non esiste alcuna fonte configurata.

---

## 8. Ricerca ibrida e RAG

- **Retrieval ibrido**: (a) dense su Qdrant, top 24; (b) FTS Postgres con `websearch_to_tsquery` nella lingua rilevata della query (fallback `simple`), top 24; fusione **RRF** (k=60); nessun reranker in v1 (estensione futura dietro interfaccia).
- **Contesto**: top 8 chunk fusi, max ~3.500 token, ognuno etichettato `[n]` con titolo documento e pagina.
- **Soglia di rifiuto**: se il miglior punteggio fuso < `refusal_threshold` (in `settings`, calibrata in M4 sull'eval set) → risposta fissa **senza chiamare l'LLM**: *"Non presente nella documentazione indicizzata."* + suggerimento di aggiungere la fonte.
- **Prompt di sistema** (base, in `services/rag/prompts.py`):

> Sei Radix, l'assistente documentale dell'azienda. Rispondi **esclusivamente** sulla base dei passaggi forniti nel contesto. Dopo ogni affermazione fattuale inserisci la citazione `[n]` del passaggio che la supporta. Rispondi nella lingua della domanda, anche se i documenti sono in un'altra lingua. Se il contesto copre solo in parte la domanda, dillo esplicitamente. Se il contesto non contiene la risposta, rispondi esattamente: "Non presente nella documentazione indicizzata." Non usare conoscenza esterna ai passaggi forniti.

- **Post-processing**: parse dei marcatori `[n]` → mappa alle citazioni; se il modello non cita, allega comunque le fonti usate nel contesto. Streaming SSE token-by-token; l'evento `final` porta le citazioni strutturate.
- **`LLMProvider`**: interfaccia `complete(messages, stream=True, json_schema=None)`; implementazioni `OllamaProvider` (default) e `VLLMProvider`; selezione e modello via env (`LLM_PROVIDER`, `LLM_MODEL`, `LLM_BASE_URL`).

---

## 9. Sicurezza, audit, backup

- Cookie di sessione httpOnly `SameSite=Lax`; argon2id; rate limit sul login; stessa origin dietro Caddy (niente CORS aperto).
- Audit (append-only) per: `login`, `search`, `chat`, `open_document`, `admin_change` — con utente, oggetto, timestamp, ip.
- `deploy/backup.sh`: `pg_dump` + snapshot Qdrant + tar del repository e della config → un archivio datato. `restore.sh`: percorso inverso, testato (round-trip in M6).
- Nessuna chiamata esterna a runtime; pull dei modelli solo in fase di installazione.

---

## 10. Configurazione e profili hardware

`.env` (esempi): `LLM_PROVIDER=ollama · LLM_MODEL=qwen3.5:9b-instruct-q4_K_M · EMBED_DEVICE=auto · OCR_LANGS=ita+eng+deu · SYNC_INTERVAL_MIN=5 · REFUSAL_THRESHOLD=… · DATA_DIR=./data`

| Profilo | Hardware | Modello LLM | Note |
|---|---|---|---|
| Dev / demo | laptop RTX 3070 Ti 8 GB | Qwen3.5 9B Q4 | tutto il modello in VRAM, mai offload parziale |
| Cliente entry (CPU) | 16 core, 64 GB RAM, NVMe 2 TB | Qwen3 4B Q4 | carichi leggeri |
| Cliente standard | GPU 16–24 GB, 64 GB RAM, NVMe 2–4 TB | 8–14B Q4/Q5 | consigliato |

---

## 11. Milestone e Definition of Done

> Una milestone per sessione di lavoro. DoD verificata (test verdi + check manuali) prima di passare alla successiva.

**M0 — Scaffold.** Struttura repo completa, compose (prod+dev) con tutti i servizi e healthcheck, migrazioni Alembic iniziali, `Makefile`, `.env.example`, CI locale (`make lint test`), `CLAUDE.md` generato da §12, frontend con shell (sidebar + routing + login).
*DoD:* `make up` → `GET /api/v1/health` 200 con tutti i componenti `ok`; la pagina di login si carica; `make test` verde.

**M1 — Ingestione e fonti.** CRUD sources, upload, watcher per cartella locale e mount SMB, repository interno, dedupe per hash, coda con stati esposti da `/indexing/*`; UI Fonti + modale + UI Indicizzazione (dati reali).
*DoD:* aggiungendo una cartella con i 5 PDF di fixture, compaiono 5 documenti che avanzano `queued → parsing`; rimozione di un file → tombstone.

**M2 — Parsing, OCR, chunking, rendering.** Docling + ramo OCR Tesseract; chunks con pagina, bbox e heading in Postgres; endpoint di rendering pagina PNG con cache.
*DoD:* la fixture scansionata in italiano produce testo OCR corretto; i chunk della fixture RS-30 hanno bbox validi a pagina nota; `GET /documents/{id}/pages/{n}.png` restituisce l'immagine.

**M3 — Indice e ricerca ibrida.** Embeddings bge-m3, upsert Qdrant, FTS, fusione RRF, `GET /search` con filtri e permessi; UI Ricerca completa dal mock.
*DoD:* la query di fixture "coppia di serraggio testata" ritorna il chunk atteso nei primi 3 risultati; ricerca cross-lingua (query IT, documento EN) funziona; latenza < 1,5 s in dev.

**M4 — Chat RAG e visualizzatore.** `/chat` SSE con citazioni strutturate, soglia di rifiuto calibrata, UI Chat + Viewer con overlay di evidenziazione e back contestuale; eval harness (`make eval`) con le prime 10 domande.
*DoD:* ≥ 8/10 domande dell'eval set rispondono con citazione al documento e pagina corretti; una domanda fuori corpus produce esattamente la frase di rifiuto; click su citazione → pagina giusta evidenziata.

**M5 — Utenti, permessi, audit, onboarding.** Gestione utenti/inviti/ruoli, collezioni e permessi enforced ovunque, audit log + consultazione, stats, flusso di onboarding al primo avvio.
*DoD:* test API e UI dimostrano che un utente `user` non vede né trova documenti di collezioni non assegnate; i 5 eventi di audit vengono registrati.

**M6 — Packaging e delivery.** `install.sh` per Ubuntu 24 pulita (prerequisiti, wizard `.env` minimo, pull modelli, `compose up`, healthcheck finale), backup/restore testati round-trip, profilo CPU verificato, Caddy con TLS, guida di installazione in `docs/` scritta per un consulente IT generico.
*DoD:* installazione completa su VM pulita in < 30 minuti senza interventi manuali oltre al wizard; backup → wipe → restore riporta il sistema allo stato precedente.

---

## 12. Convenzioni operative (→ `CLAUDE.md` in M0)

Codice, commenti e identificatori in inglese; stringhe UI in italiano via i18n. Type hints ovunque, `ruff` + `mypy` in `make lint`. Ogni service della pipeline e ogni endpoint hanno test pytest; niente merge con test rossi. Conventional commits. **Nessuna nuova dipendenza senza check licenza** (`make licenses`, vedi §14). Non implementare nulla della lista fuori scope (§13). Preferire sempre la soluzione più semplice che soddisfa la DoD: questo progetto è mantenuto da una persona. In caso di ambiguità nella spec: fermarsi e chiedere, proporre opzioni, non decidere in silenzio. Le decisioni prese in corsa si registrano in `docs/adr/` (una riga di contesto, la scelta, il perché).

---

## 13. Fuori scope v1 (non implementare)

Estrazione dati strutturati e template (Fase 2) · connettori Google Drive/SharePoint (v1.1: la UI li mostra disabilitati) · multi-tenant/SaaS · app mobile · editing dei documenti · fine-tuning · SSO/AD (solo predisposizione: auth locale ben isolata) · integrazioni gestionali · agenti autonomi · reranker (interfaccia predisposta, implementazione no).

---

## 14. Licenze — vincolo bloccante

Regola: solo licenze permissive (Apache-2.0, MIT, BSD e simili). Vietate AGPL, SSPL, BUSL, Elastic, non-commercial. Target `make licenses` esegue `pip-licenses` (backend) e `license-checker` (frontend) e fallisce su licenze vietate.

| Componente | Licenza attesa |
|---|---|
| FastAPI, Pydantic, SQLAlchemy, RQ, React, Vite, TanStack Query | MIT/BSD |
| Qdrant, vLLM, Tesseract, Caddy, pypdfium2/PDFium | Apache-2.0 / BSD |
| Docling, bge-m3 | MIT |
| Ollama | MIT |
| Modelli (Qwen3 / Qwen3.5, checkpoint esatti) | attesa Apache-2.0 — **verificare la licenza del checkpoint al momento del pull e annotarla in `docs/adr/`** |
| PyMuPDF | **AGPL — vietato.** Usare pypdfium2 |

---

## 15. CHANGELOG

- 2026-07-17 · v1 iniziale — scope: modulo Radix (PRD §4), milestone M0–M6.
- 2026-07-17 · Rinominata l'applicazione da "Knowledge" a "Radix" (spec, mock e struttura file aggiornati).
- 2026-07-17 · M0 Scaffold: struttura repo, compose prod+dev, migrazione Alembic iniziale, Makefile, CLAUDE.md, auth di base, shell frontend con login. `make lint`, `make test` (10 test) e `make licenses` verdi. Decisioni in `docs/adr/0001`.
- 2026-07-17 · M1 Ingestione e fonti: CRUD `/sources`, `POST /uploads`, discover con dedupe sha256 e repository interno, tombstone dei file rimossi, watcher periodico nel worker, `/indexing/stats|queue`, `exclude`/`reindex`; UI Fonti (tabella + modale dal mock) e UI Indicizzazione con dati reali. Migrazione 0002, 5 PDF di fixture generati. `make lint`, `make test` (43 test) e `make licenses` verdi. Decisioni in `docs/adr/0002`.
