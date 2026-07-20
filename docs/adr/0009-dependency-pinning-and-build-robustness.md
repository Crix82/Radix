# ADR 0009 — Pinning delle dipendenze e robustezza del build

Contesto: post-M6, emerso provando ad avviare lo stack per una verifica UI. `make up` è fallito
con un errore di hash di pip durante `pip install .`, e l'indagine ha portato a due problemi
distinti che condividono la stessa radice.

## Il sintomo

```
ERROR: THESE PACKAGES DO NOT MATCH THE HASHES FROM THE REQUIREMENTS FILE.
    unknown package:
        Expected sha256 6dc0b3fd…   Got bc0df35c…
```

Messaggio allarmante ("someone may have tampered with them"), ma le prove escludono la
manomissione: l'hash **atteso** cambiava a ogni tentativo (`6dc0b3fd…`, poi `2b3c89c8…`), quindi
falliva un pacchetto diverso ogni volta — se un artefatto su PyPI fosse stato sostituito,
l'atteso sarebbe costante. In più, il download diretto di un wheel da 206 MB dentro un container
ha dato due volte su due l'hash esatto pubblicato da PyPI, e il disco aveva 916 GB liberi.

Conclusione: **corruzione intermittente** durante una sessione di download di ~2,5 GB (torch
526 MB + stack CUDA), coerente con l'instabilità nota dell'integrazione WSL/Docker Desktop su
questa macchina. Il messaggio di pip è generico, non una rilevazione di tampering.

## Decisioni

- **Lockfile `backend/requirements.lock` con pin esatti**, installato con `--no-deps`. Tutte le
  dipendenze in `pyproject.toml` sono lower bound aperti (`>=`): un `pip install .` non
  vincolato risolve quel che è più recente il giorno del build. L'immagine non è riproducibile e
  può cambiare **tra la verifica e l'installazione dal cliente** — inaccettabile per un prodotto
  on-premise consegnato via `install.sh`. Il lock congela la risoluzione realmente verificata
  (provenienza: `pip freeze` dell'immagine M6 del 2026-07-18, 156 pacchetti).
  `pyproject.toml` resta la dichiarazione d'intento con i lower bound; il lock è ciò che si
  installa. Rigenerazione con `make lock`, che risolve **dentro `python:3.12-slim`** — la stessa
  base del Dockerfile — perché una risoluzione sull'host può differire per wheel di piattaforma
  o patch di Python.
- **Cache mount BuildKit al posto di `--no-cache-dir`** per lo strato delle dipendenze. Il
  problema pratico non è solo che un download si corrompe: è che si corrompe dopo 9 minuti e
  costringe a riscaricare tutti i 2,5 GB. Con `--mount=type=cache,target=/root/.cache/pip` i
  wheel già scaricati restano su disco e un ritentativo riprende invece di ripartire. La cache
  non finisce nello strato dell'immagine, quindi il motivo originale di `--no-cache-dir` (non
  gonfiare l'immagine) è preservato.
- **Lo strato delle dipendenze viene prima del codice.** Il `COPY` del lockfile precede il
  `COPY` di `app/`, così una modifica al codice non invalida lo strato da 2,5 GB.
- **Niente `--require-hashes`.** Servirebbe `pip-compile --generate-hashes` (nuova dipendenza da
  sottoporre a check licenza) e non risolverebbe il problema osservato: pip *già* verifica gli
  hash contro i metadati dell'indice — è esattamente ciò che ha prodotto l'errore. Aggiungerebbe
  cerimonia senza cambiare l'esito.

## Il difetto più grave: SPEC §9 non era vera

Provando l'immagine appena costruita con un parse Docling reale su un PDF di fixture e
`docker run --network none`, il parse **fallisce**: `huggingface_hub` tenta di scaricare il
modello layout e non risolve il DNS. La stessa prova sull'immagine **M6 intatta fallisce
identicamente** — quindi è un difetto preesistente, non una regressione.

Causa: `docling-tools models download` popola `/root/.cache/docling/models`, ma a runtime
`LayoutModel.download_models()` risolve via `snapshot_download` nella **cache HuggingFace**.
Sono due posti diversi. L'immagine M6 spediva 1,3 GB di modelli nella cache sbagliata e poi
scaricava comunque il layout dall'Hub al primo documento.

SPEC §9 dichiara *"Nessuna chiamata esterna a runtime; pull dei modelli solo in fase di
installazione"*. Non era vero. La DoD M6 è passata perché la macchina di verifica aveva
internet e il download è avvenuto in silenzio al primo uso; su un cliente air-gapped o con
firewall in uscita — il caso d'uso che il prodotto vende — l'indicizzazione del **primo
documento** sarebbe fallita. Stesso schema del tag Ollama: la DoD passava senza che la garanzia
fosse vera.

Correzione: `app.services.parsing.warm_models()` costruisce **gli stessi converter che costruisce
il servizio** (entrambe le varianti OCR) e chiama `initialize_pipeline`. Per costruzione scarica
esattamente ciò che il runtime risolve, senza dover indovinare un elenco di modelli. Il
Dockerfile chiama quella, non la CLI.

Effetto collaterale positivo: la CLI scaricava anche gli engine rapidocr/easyocr, che Radix non
tocca mai (l'OCR è Tesseract via `TesseractCliOcrOptions`), e i modelli cinesi di rapidocr
vengono da `modelscope.cn` — host che ha mandato in timeout un build da qui. Siccome
`install.sh` costruisce sulla macchina del cliente, quell'host stava sul percorso critico di
ogni installazione per modelli che poi si buttavano.

Numeri onesti, a parità di metrica (somma dei layer; la colonna SIZE di `docker images` non è
comparabile su immagini buildx con manifest list): 12,32 GB → 11,51 GB. Il guadagno di spazio è
modesto (~0,8 GB); il punto è la correttezza — 1,3 GB di modelli inutili spariscono e il primo
documento non richiede più la rete.

Guardie: `test_image_bakes_models_through_the_runtime_path` impedisce il ritorno alla CLI.
La verifica vera resta manuale ed è quella che ha trovato il bug — parse di una fixture con
`--network none`; nessun controllo statico l'avrebbe rilevato. Da rieseguire prima di ogni
consegna.

## Secondo difetto trovato nello stesso giro: il tag del modello in `install.sh`

`install.sh` esegue `docker compose up -d --build`, cioè **costruisce sulla macchina del
cliente**: il download da 2,5 GB e la sua fragilità cadono esattamente dentro la DoD M6
("installazione su VM pulita in < 30 minuti senza interventi manuali"). È questo che rende il
punto precedente bloccante e non cosmetico.

Leggendo `install.sh` è emerso che il fix M6 del tag 404 (`qwen3.5:9b-instruct-q4_K_M` non
esiste sul registry Ollama) aveva aggiornato `.env.example`, `config.py`, la guida e lo SPEC —
ma **non `install.sh`**, che è precisamente il file che scrive il `.env` di un cliente nuovo.
Il wizard proponeva ancora il tag morto (righe 136 e 143); `ollama pull` falliva e l'installer
si limitava a un `warn`, quindi lo stack risultava "installato" ma senza modello e con la chat
non funzionante. Verificato contro il registry: `9b-instruct-q4_K_M` → HTTP 404,
`9b-q4_K_M` → HTTP 200.

Causa sistemica: gli script di `deploy/` stanno fuori dal gate ruff/mypy e nessun test li
leggeva, quindi una costante duplicata tra app e provisioning poteva divergere in silenzio.
Guardia aggiunta: `tests/test_deploy_consistency.py` confronta il tag offerto da `install.sh` e
da `.env.example` con il default di `app.core.config`. Verificata reintroducendo il bug (il test
fallisce) e ripristinando (passa).

## Non deciso qui

L'immagine pesa **19,4 GB**, perché `sentence-transformers` → `torch` porta l'intero stack
`nvidia-*` (CUDA 13). Non è una regressione recente: l'immagine M6 verificata aveva già
`torch==2.13.0` con CUDA 13. Il profilo CPU (SPEC §10 "Cliente entry") non ha alcun bisogno di
quei ~2,5 GB, e wheel CPU-only li eliminerebbero — ma `EMBED_DEVICE=auto` (SPEC §2) prevede
esplicitamente di usare la GPU quando c'è, quindi separare l'immagine in varianti CPU/GPU è una
**scelta di prodotto**, non una correzione. Lasciata al committente.
