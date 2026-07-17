# ADR 0004 — M3: indice e ricerca ibrida

Contesto: milestone M3 (embeddings bge-m3, upsert Qdrant, FTS, fusione RRF, `GET /search`
con filtri e permessi; UI Ricerca).

- **Embeddings via sentence-transformers (Apache-2.0).** `BAAI/bge-m3` caricato in modo
  lazy e cachato (`functools.lru_cache`), device auto (CUDA se disponibile), vettori
  L2-normalizzati (cosine == dot). L'import di torch resta fuori dai unit test.
- **Vector store Qdrant** (`app/services/vectorstore.py`): collection `chunks` 1024 cosine,
  quantizzazione scalar int8, `on_disk`; indici payload su `collection_id`/`lang`/`doc_type`;
  id del punto = `chunk_id`. `ensure_collection` idempotente; `embed_chunks` fa
  delete-then-upsert (reindex idempotente).
- **Ricerca ibrida composabile** (`app/services/search`): `dense_search` e `fts_search`
  ritornano liste ordinate di chunk id; `fuse_and_hydrate` applica RRF (k=60) e idrata da
  Postgres. Endpoint e test iniettano fake per i due retriever; la fusione (`fusion.py`) e
  lo snippet (`snippet.py`) sono puri e testati su SQLite. Il vero FTS/dense gira in un
  test `slow` e nella verifica DoD su Docker.
- **FTS con `websearch_to_tsquery` nella lingua della query.** `query_regconfig` mappa la
  lingua rilevata a `italian`/`english`/`german`, fallback `simple`. Le query di sole
  parole-chiave (senza stopword) cadono su `simple`: il dense copre comunque il cross-lingua.
- **Snippet in Python, non `ts_headline`.** Highlighter puro (escape HTML + `<b>` sui
  termini) così l'idratazione è identica in test e produzione e non dipende da Postgres.
- **Permessi enforced due volte** (SPEC §6): filtro `collection_id` nel retrieval (Qdrant +
  WHERE FTS) e di nuovo in `fuse_and_hydrate` (`WHERE d.status='indexed' AND deleted_at IS
  NULL AND collection_id IN …`). Postgres è la fonte di verità: punti Qdrant obsoleti
  (documenti esclusi/cancellati) vengono comunque esclusi dai risultati. Admin = nessun
  vincolo; utente = solo le sue `user_collections`; utente senza collezioni = zero risultati.
- **Pipeline completata fino a `indexed`.** `parse_document` accoda `embed_chunks`; questo
  porta lo stato `chunking → embedding → indexed`. Il tombstone dei file rimossi elimina i
  punti Qdrant (best-effort nel worker); l'esclusione si affida al filtro di stato.
- **UI Ricerca**: filtro Lingua funzionante; il filtro Tipo (Manuali/Schede/Bollettini) è
  rimandato all'auto-tagging (`doc_type` è nullo finché il tagging non esiste), per non
  offrire filtri che non tornano risultati.

## Decisione licenze: driver Postgres pg8000 (BSD-3) al posto di psycopg (LGPL-3.0)

Durante M3 è emerso che `psycopg` (driver dello scaffold M0) è **LGPL-3.0-only**, in
conflitto con SPEC §14 ("solo permissive", vincolo bloccante), e che `make licenses` non
lo intercettava (`--fail-on` faceva match esatto, non catturava `LGPL-3.0-only`).

- **Scelta**: sostituito con **pg8000** (`postgresql+pg8000://`), puro Python, BSD-3.
  Rispetta il vincolo senza indebolirlo con un'eccezione. Alternativa scartata: documentare
  un'eccezione LGPL (legittima per linking dinamico, ma la spec vuole esplicitamente solo
  permissive).
- **Gate irrobustito**: `pip-licenses --partial-match` (così `GPL` cattura `LGPL-3.0-only`,
  `AGPL-3.0`, ecc.) con `--fail-on` esteso a `Proprietary`; le librerie NVIDIA CUDA (portate
  da torch, proprietarie ma ridistribuibili per uso commerciale sotto CUDA EULA) sono in
  allowlist esplicita. Verificato che il gate fallisce senza l'allowlist.
