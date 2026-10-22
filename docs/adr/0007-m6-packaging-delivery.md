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
- **GPU anche al `worker`, non all'`api`** (2026-10-22, emerso al primo deploy su RTX 3070
  Ti 8 GB): l'override `docker-compose.gpu.yml` passava la GPU solo a Ollama, quindi parsing
  Docling ed embedding bge-m3 giravano su CPU. Ora la riceve anche il `worker` (Docling e
  `EMBED_DEVICE=auto` scelgono CUDA da soli). L'`api` resta su CPU: incorpora una query alla
  volta e una seconda copia di bge-m3 in VRAM, accanto al 9B, non starebbe su 8 GB senza
  rischiare l'offload parziale dell'LLM (SPEC §10). L'OCR Tesseract resta CPU in ogni caso.
- **GPU del worker solo da 12 GB in su; LLM sempre caricato** (2026-10-22, rivede la voce
  precedente). Misurato sulla RTX 3070 Ti 8 GB: dopo il primo documento il worker tiene in VRAM
  i modelli Docling e bge-m3 (~1,7 GB) fino al riavvio, e Qwen3.5 9B scende al 19% su CPU — la
  chat passa da 68 a 43 tok/s. La GPU del worker passa quindi in un override a parte,
  `docker-compose.gpu-worker.yml`, che `install.sh` aggiunge solo se la GPU più grande ha
  almeno 12 GB; sotto, il worker gira su CPU (un server multi-core lo regge: il libro di 481
  pagine si era indicizzato su CPU). Con la GPU tutta per l'LLM, `OLLAMA_KEEP_ALIVE=-1` di
  default: il modello resta caricato e la prima domanda dopo una pausa non aspetta più il
  ricaricamento (17–89 s misurati).
- **Timeout dei job di elaborazione a 6 ore** (2026-10-22). RQ interrompe un job dopo 180 s
  se non specificato, e l'interruzione cade *dentro* Docling, che la registra come pagina
  fallita: ogni documento oltre i 3 minuti (un libro scansionato in OCR, un manuale di 481
  pagine su CPU) finiva in errore come "Pipeline failed" senza traccia del timeout. Parsing ed
  embedding ora sono accodati con `job_timeout` di 6 ore; la sincronizzazione delle fonti
  resta col default.
