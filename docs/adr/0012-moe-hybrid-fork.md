# ADR 0012 — Branch `moe-hybrid`: MoE grandi con esperti in RAM, come banco di confronto

Contesto (2026-10-22): il server di riferimento (AMD EPYC 7452 32 core, 247 GB RAM DDR4 su
un solo nodo NUMA, RTX 3070 Ti 8 GB su PCIe 4.0 x16) usa oggi Qwen3.5 9B tutto in VRAM: 43/52
sul test Excel del cliente, primo token ~2,3 s. Il rapporto in `docs/specs/` ("LLM open weight su
hardware limitato") sostiene che su una macchina così girano MoE da 100B–1T parametri tenendo
gli esperti instradati in RAM e attenzione, layer densi e KV cache in GPU, con la velocità di
scrittura dettata dalla banda della RAM. Il branch serve a misurarlo su Radix, non a sostituire
`main`.

## Decisioni

- **Branch nello stesso repository**, `moe-hybrid`, che resta vicino a `main` (si rifonda su
  `main` invece di divergere): l'unica differenza voluta è il runtime e il modello. Retrieval,
  contesto e prompt sono identici a `main`, così il confronto misura il modello e non altro.
- **Runtime: llama.cpp `llama-server`** (MIT), in `docker-compose.llamacpp.yml` al posto di
  `docker-compose.llm.yml`. Ollama non sa tenere gli esperti in RAM (nessun `--n-cpu-moe`).
  Immagine bloccata a un build preciso (`server-cuda-b11459`): un tag mobile cambierebbe il
  motore fra due misure da confrontare. Radix lo usa tramite il provider `llamacpp` (stessa API
  OpenAI di Ollama/vLLM); `LLM_TIMEOUT_S` alza il timeout di streaming, perché leggere un prompt
  RAG di ~6000 token con gli esperti in RAM può richiedere minuti.
- **Baseline: il posizionamento automatico di llama.cpp** (`--fit`, attivo di default), che il
  rapporto indica come riferimento gratuito da battere. Ogni variazione (thread, `-ub`,
  `--n-cpu-moe`, tipo di KV cache, budget di ragionamento) passa da `LLAMACPP_ARGS`, così ogni
  misura dichiara cosa è cambiato.
- **Stessi dati, stack alternati.** Sul server il branch vive in una worktree separata
  (`~/radix-moe`) con lo stesso `COMPOSE_PROJECT_NAME` e lo stesso `DATA_DIR` di `main`: stessi
  documenti indicizzati, stesso indice. I due stack non girano insieme (il MoE occupa quasi tutta
  la RAM e la GPU): si ferma uno e si avvia l'altro. I GGUF stanno fuori dai repository
  (`~/radix-models/gguf`).
- **Misure: tempi e qualità**, con gli strumenti già nel repo: `eval/qa_test.py` (Excel del
  cliente, 26 domande), `make eval` (citazioni, rifiuto, follow-up) e `eval/bench.py` (primo token,
  token/s). Energia esclusa per decisione (nessun wattmetro; RAPL su AMD non vede la DRAM).
- **Modelli, in ordine:** gpt-oss-120b MXFP4 (63 GB, Apache-2.0, l'unico misurato in letteratura
  con 8 GB di VRAM), DeepSeek-V4-Flash Q2 (~97 GB, MIT), Qwen3-235B-A22B Q4 (~134 GB,
  Apache-2.0). DeepSeek-V4-Flash Q8 (162 GB) e GLM-5.3-Flash Q4 (200 GB) richiedono prima più
  disco: il server ha un NVMe da 233 GB. Licenze verificate sulla scheda del modello al
  download (SPEC §14); MiniMax escluso (licenza non commerciale).

## Rischio principale

Radix è dominato dal *prefill*: ogni domanda porta ~6000 token di estratti. Il rapporto misura
il prefill con esperti in RAM a decine–poche centinaia di token/s in llama.cpp mainline, cioè un
primo token da decine di secondi a minuti; ik_llama.cpp e KTransformers vincono soprattutto lì
(2–10×), KTransformers però richiede 24 GB di VRAM e kernel AMX/AVX-512 che l'EPYC 7452 (solo
AVX2) non ha. La prima misura è quindi il primo token sul prompt RAG reale; leve successive:
`-ub` grande, ik_llama.cpp, un budget di contesto ridotto per un modello più capace.

## Misure

### gpt-oss-120b MXFP4 (2026-10-22, llama.cpp b11459, `--fit` automatico, 32 thread)

Prompt RAG reale di 5.399 token (estratti del libro di prova), cache dei prompt disattivata:

| Configurazione | Lettura (prefill) | Primo token stimato | Scrittura |
|---|---|---|---|
| default (`-ub 512`) | 160 tok/s | ~34 s | 33 tok/s |
| `-b/-ub 2048` | 410 tok/s | ~13 s | 35 tok/s |
| `-b/-ub 4096` | 527 tok/s | ~10 s | 33 tok/s |
| **`-b/-ub 8192`** | **723 tok/s** | **~7,5 s** | 32 tok/s |

VRAM 6,3–6,8 GB in tutti i casi. È la leva del rapporto (batch di prefill grande): +4,5× sul
prefill a costo nullo sulla scrittura, quindi diventa la configurazione del branch.

Test Excel con la configurazione default (prima del `-ub`): **44/52** contro 43/52 di `main`
(Qwen3.5 9B + traduzione), primo token mediano 32,6 s contro 2,3 s; `make eval` 10/10, rifiuto
ok, follow-up 4/4. Risolve i tre calcoli/confronti su cui Qwen rifiutava (#18, #20, #21), ma
**inventa un elenco di norme IEEE "valide nel 2026"** sulla domanda trappola #25. In ~40% delle
risposte cita nel proprio formato (`【11†L1-L3】`) invece di `[n]`: ora normalizzato da
`normalize_citations` prima dell'estrazione delle fonti.
