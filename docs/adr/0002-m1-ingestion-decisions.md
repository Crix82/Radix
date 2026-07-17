# ADR 0002 — M1: decisioni sull'ingestione e le fonti

Contesto: implementazione della milestone M1 (CRUD fonti, upload, watcher, dedupe, coda).

- **SMB = mount del filesystem.** La spec (§5) prevede "SMB via mount": il `path` di una
  fonte `smb` è il punto di mount sul server Radix, non un URL UNC. Nei container il mount
  deve stare sotto `/data/sources` (`SOURCES_DIR` in `.env`, montato su api e worker).
  Perché: nessuna dipendenza da client SMB in-process; il mount lo gestisce l'OS.
- **Collezione di default "Generale".** La modale del mock non ha un campo collezione;
  `POST /sources` e `POST /uploads` senza `collection_id` usano (creandola se serve) la
  collezione "Generale". La gestione vera delle collezioni arriva in M5.
- **Watcher = thread nel worker.** Un thread nel processo worker accoda `sync_source` per
  ogni fonte abilitata ogni `SYNC_INTERVAL_MIN` (default 5). Perché: niente dipendenza
  rq-scheduler, un solo processo da monitorare.
- **`documents.source_id` nullable con FK `ON DELETE SET NULL`** (migrazione 0002).
  `DELETE /sources` tombstona i documenti e cancella la riga fonte; i tombstone
  sopravvivono orfani. Perché: la storia dei documenti non si perde mai (SPEC §5).
- **File modificato = update in place.** Stessa `rel_path` con hash nuovo aggiorna la riga
  esistente (hash, size, stato `queued`); se il contenuto ripristina una versione
  tombstonata, quella riga viene resuscitata (il vincolo unico sul trio resta valido).
- **Upload: fonte singleton auto-creata.** `POST /uploads` senza `source_id` usa (o crea)
  la prima fonte `upload`. Il nome file del client viene ridotto al basename.
- **`parse_document` in M1 porta solo `queued → parsing`.** Il parser vero è M2; la DoD M1
  chiede di vedere l'avanzamento di stato attraverso la coda reale.
- **Test senza Postgres.** I tipi Postgres-only usano `with_variant` (JSONB/INET/BigInt
  autoincrement) così i test girano su SQLite in-memory; la tabella `chunks` (tsvector,
  regconfig) è esclusa dai test e resta Postgres-only.
- **Fixture PDF generate, non binarie a mano.** `tests/fixtures/generate_fixtures.py`
  (zero dipendenze) genera i 5 PDF checked-in; contengono già i contenuti attesi dalle
  DoD di M2/M3 (es. "coppia di serraggio ... testata" nel manuale RS-30).
