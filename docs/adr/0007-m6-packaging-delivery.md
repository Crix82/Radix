# ADR 0007 — M6: packaging e delivery

Contesto: milestone M6 (installer per Ubuntu 24, backup/restore round-trip, profilo CPU,
Caddy con TLS, guida di installazione). Obiettivo: una installazione on-prem riproducibile
e gestibile da un consulente IT generico.

- **Interruttore LLM bundled vs external via `COMPOSE_FILE`** (non profili). Il servizio
  `ollama` vive in `docker-compose.llm.yml` separato; l'override GPU in
  `docker-compose.gpu.yml`. `install.sh` scrive `COMPOSE_FILE` nel `.env`
  (`docker-compose.yml[:llm][:gpu]`), che Docker Compose legge da solo: `docker compose up -d`
  monta lo stack giusto senza flag. Scelta rispetto ai *compose profiles*: i profili si
  fondono male con il `depends_on` dell'override dev e avrebbero richiesto `COMPOSE_PROFILES`
  ovunque; la composizione di file lascia intatto lo stack dev (`make up`) e non aggiunge
  `depends_on: ollama` a api/worker (la resilienza è già nel client LLM con retry).
  Con `LLM_RUNTIME=external` nessun container LLM parte e api/worker usano `LLM_BASE_URL`.
- **GPU auto-rilevata, fallback CPU**. `install.sh` considera la GPU utilizzabile solo se
  `nvidia-smi` funziona **e** il Container Toolkit è agganciato a Docker (`docker info` cita
  `nvidia`, oppure è presente `nvidia-ctk`); in tal caso aggiunge `docker-compose.gpu.yml`.
  Il profilo CPU (SPEC §10 "Cliente entry") è il default e non richiede prerequisiti.
- **TLS self-signed interno** (`tls internal` in Caddy) come default: adatto a on-prem in
  LAN senza dominio pubblico, zero prerequisiti. Il certificato del cliente è documentato
  (mount `/certs` + `tls cert.pem key.pem`) ma non è il percorso predefinito.
- **`.env` generato via heredoc**, non per sostituzione su `.env.example`: robusto rispetto
  a caratteri speciali nelle password. Un `.env` esistente viene ricaricato come default in
  una re-esecuzione (idempotente sui segreti). Permessi `600`.
- **Backup**: `pg_dump --clean --if-exists` (dump autoconsistente DROP+CREATE) + **snapshot
  Qdrant via API** (creato dal container `api`, che ha già `qdrant-client`, ed estratto con
  `docker compose cp`) + tar del `repository` + copia di `.env`. La **page cache è esclusa**
  perché rigenerabile dai PDF. Nessun downtime per il backup.
- **Restore distruttivo e senza toccare il `.env` live**: ferma api/worker, ripristina
  Postgres (`psql`), recupera lo snapshot Qdrant (`recover_snapshot` con
  `file:///qdrant/snapshots/_restore.snapshot`), ripristina il repository, riavvia,
  healthcheck. Il `.env` in uso non viene sovrascritto (i segreti e il wiring restano quelli
  correnti); la copia del backup è `env.backup` nell'archivio.
- **Round-trip testato** (`deploy/test-backup-restore.sh`): registra il conteggio punti
  Qdrant, fa il backup, scrive una riga sentinella in `settings` (stato *dopo* il backup),
  ripristina e verifica che la sentinella sia sparita (Postgres riavvolto) e che il conteggio
  Qdrant combaci. Prova che il restore riporta davvero allo stato del backup.
- **Script deploy condivisi** via `deploy/_common.sh` (root dir, rilevamento `docker`/`sudo
  docker`, load `.env`, `require_running`). Gli script non entrano nei gate `ruff`/`mypy`
  (sono bash); verificati con `bash -n` (e `shellcheck` se disponibile, non obbligatorio).
