# Radix — Guida di installazione

Guida operativa per installare, aggiornare e mettere in sicurezza Radix su un server
del cliente. È scritta per un consulente IT generico: non serve conoscere il codice.

Radix è **on-premise**: gira interamente su un server del cliente, senza dipendenze da
servizi cloud. Tutti i componenti girano in container Docker orchestrati da Docker Compose.

---

## 1. Requisiti

**Sistema operativo**: Ubuntu Server 24.04 LTS pulito (le istruzioni valgono anche per
derivate Debian recenti).

**Hardware** (SPEC §10):

| Profilo | Hardware minimo | Modello LLM | Note |
|---|---|---|---|
| Entry (CPU) | 16 core, 64 GB RAM, NVMe 2 TB | Qwen3 4B Q4 | funziona senza GPU, risposte più lente |
| Standard (GPU) | GPU 16–24 GB, 64 GB RAM, NVMe 2–4 TB | 8–14B Q4/Q5 | consigliato |

**Rete**: accesso a Internet **solo durante l'installazione** (download immagini Docker e
modello LLM). A regime Radix funziona in LAN senza Internet.

**Prerequisiti software**: l'installer li installa da solo se assenti (Docker Engine,
Docker Compose plugin, openssl). Per l'accelerazione GPU va installato **prima** il
[NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html);
se manca, l'installer procede in modalità CPU.

---

## 2. Installazione

```bash
git clone <repo> radix && cd radix
./deploy/install.sh
```

L'installer (`deploy/install.sh`):

1. verifica/installa i prerequisiti (chiede conferma prima di installare Docker);
2. rileva la GPU NVIDIA e il Container Toolkit; se presenti usa la GPU, altrimenti CPU;
3. pone alcune domande e scrive il file di configurazione `.env` (vedi §3);
4. avvia lo stack (`docker compose up -d --build`);
5. se il modello LLM è **bundled**, ne effettua il download (`ollama pull`);
6. attende che l'API risponda `healthy` e stampa l'URL di accesso.

Al termine apri **`https://<dominio>/`**. Il certificato è **self-signed** (§5): il browser
mostrerà un avviso da accettare. Accedi con l'email/password admin impostate durante il wizard.

### Installazione non interattiva

Per automazioni/CI: `./deploy/install.sh --non-interactive`. Usa i valori già presenti
nelle variabili d'ambiente o nel `.env` esistente e genera i segreti mancanti.

---

## 3. Configurazione (`.env`)

L'installer genera `.env` (permessi `600`, contiene segreti). Riferimento completo con
commenti: `.env.example`. Campi principali:

| Variabile | Significato |
|---|---|
| `RADIX_DOMAIN` | hostname/dominio servito da Caddy |
| `POSTGRES_PASSWORD`, `JWT_SECRET` | segreti, generati automaticamente |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | admin creato al primo avvio (solo se non esistono utenti) |
| `LLM_RUNTIME` | `bundled` (Ollama nello stack) o `external` (endpoint gestito fuori) |
| `LLM_MODEL` | tag del modello (es. `qwen3.5:9b-instruct-q4_K_M`) |
| `LLM_BASE_URL` | endpoint OpenAI-compatibile (per `external`) |
| `COMPOSE_FILE` | assemblaggio dello stack — **gestito dall'installer**, vedi sotto |

### Interruttore LLM: bundled vs external

Docker Compose legge `COMPOSE_FILE` dal `.env`, quindi `docker compose up -d` monta lo
stack giusto senza flag aggiuntivi:

| Modalità | `COMPOSE_FILE` |
|---|---|
| LLM esterno | `docker-compose.yml` |
| Bundled, CPU | `docker-compose.yml:docker-compose.llm.yml` |
| Bundled, GPU | `docker-compose.yml:docker-compose.llm.yml:docker-compose.gpu.yml` |

Per passare a un LLM esterno dopo l'installazione: imposta `LLM_RUNTIME=external`,
`LLM_BASE_URL=<endpoint>`, `COMPOSE_FILE=docker-compose.yml`, poi `docker compose up -d`.

---

## 4. Gestione dello stack

```bash
docker compose ps                 # stato dei servizi
docker compose logs -f api        # log dell'API
docker compose restart api worker # riavvio applicativo
docker compose down               # arresto (i dati restano nei volumi in DATA_DIR)
docker compose up -d              # avvio
```

Tutti i dati persistono sotto `DATA_DIR` (default `./data`): `postgres/`, `qdrant/`,
`models/`, `repository/`, `pagecache/`.

---

## 5. TLS / certificati

Default: **certificato self-signed interno** di Caddy (`tls internal`) — zero prerequisiti,
adatto a una installazione on-prem in LAN senza dominio pubblico.

Per usare un **certificato del cliente**: monta i file nel container Caddy e sostituisci in
`deploy/caddy/Caddyfile`:

```
tls /certs/cert.pem /certs/key.pem
```

aggiungendo il mount in `docker-compose.yml` (servizio `caddy`):

```yaml
    volumes:
      - ./deploy/caddy/certs:/certs:ro
```

Poi `docker compose up -d caddy`.

---

## 6. Backup e restore

Backup completo (Postgres + indice vettoriale Qdrant + repository dei file + copia di
`.env`). La page cache è esclusa perché rigenerabile.

```bash
./deploy/backup.sh                 # crea backups/radix-<timestamp>.tar.gz
./deploy/backup.sh /mnt/nas/radix  # oppure in una destinazione specifica
```

Restore (**operazione distruttiva**: sovrascrive database, indice e repository):

```bash
./deploy/restore.sh backups/radix-20260718-101500.tar.gz
```

Chiede conferma digitando `restore` (salta con `--yes`). Il `.env` in uso **non** viene
sovrascritto; la copia di backup è disponibile come `env.backup` dentro l'archivio.

**Verifica round-trip** (a stack avviato, con un corpus indicizzato):

```bash
./deploy/test-backup-restore.sh
```

Consiglio: pianifica `deploy/backup.sh` via `cron` verso uno storage esterno e conserva
qualche rotazione.

---

## 7. Aggiornamenti

```bash
git pull
docker compose up -d --build      # ricostruisce le immagini e applica le migrazioni DB
```

Le migrazioni Alembic girano automaticamente all'avvio dell'API. **Esegui sempre un
backup prima di un aggiornamento.**

---

## 8. Troubleshooting

- **`docker: permission denied`** — l'utente non è nel gruppo `docker`. Esegui
  `newgrp docker` o riavvia la sessione (l'installer aggiunge l'utente al gruppo).
- **L'API resta `degraded`** — controlla i singoli componenti:
  `curl -sk https://<dominio>/api/v1/health`. Ogni componente (db/redis/qdrant/llm)
  riporta `status` e dettaglio dell'errore.
- **La chat non risponde / LLM in errore** — in modalità bundled verifica che il modello
  sia stato scaricato: `docker compose exec ollama ollama list`. Se manca:
  `docker compose exec ollama ollama pull <LLM_MODEL>`.
- **Risposte lente** — profilo CPU: normale (SPEC §10). Valuta una GPU o un modello più piccolo.
- **La GPU non viene usata** — installa il NVIDIA Container Toolkit e reimposta
  `COMPOSE_FILE` includendo `docker-compose.gpu.yml`, poi `docker compose up -d`.
