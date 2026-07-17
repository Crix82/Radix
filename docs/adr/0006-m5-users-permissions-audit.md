# ADR 0006 — M5: utenti, permessi, audit, onboarding

Contesto: milestone M5 (gestione utenti/inviti/ruoli, collezioni, permessi enforced
ovunque, audit log + consultazione, onboarding al primo avvio).

- **Modello invito/attivazione senza email** (on-prem, SPEC §9). `POST /users` crea
  l'utente: con `password` → `active`; senza → `invited` (nessun hash, non può accedere).
  L'attivazione avviene quando un admin imposta la password via `PATCH /users/{id}`
  (`invited → active`). Non implementiamo token di attivazione via email: il sistema è
  interamente locale e l'admin provisiona gli account. La UI mostra "Invito inviato" per
  gli utenti `invited`, coerente col mock.
- **Permessi per collezione enforced lato server ovunque** (SPEC §6), riusando
  `allowed_collection_ids` (admin = nessun vincolo; utente = solo le sue
  `user_collections`; utente senza collezioni = niente):
  - Ricerca e chat filtrano già in retrieval + idratazione (M3/M4).
  - `GET /documents/{id}` e `/pages/{n}.png` ora verificano la collezione: un documento di
    una collezione non assegnata risponde **404** (l'esistenza è nascosta, non 403).
- **`open_document` audit**: emesso su `GET /documents/{id}` (chiamato dal viewer
  all'apertura). Non si audita ogni immagine di pagina per non gonfiare il log. Con questo
  i **5 eventi** SPEC §9 sono coperti: `login` (M0), `search` (M3), `chat` (M4),
  `open_document` (M5), `admin_change` (fonti M1, utenti/collezioni M5).
- **Consultazione audit**: `GET /audit?user_id=&action=&from=&to=&limit` (admin), con
  l'email dell'utente via join. Solo API (il mock non ha una schermata audit).
- **Anti-lockout**: un admin non può declassare o disattivare il proprio account
  (`PATCH /users/{self}` con role≠admin o status≠active → 409). Limite di 20 utenti per
  installazione (SPEC §1).
- **Onboarding al primo avvio** (SPEC §7.3): la rotta `/` reindirizza a `/onboarding`
  solo se l'utente è admin e non esiste alcuna fonte; altrimenti a `/search`. La CTA
  "Collega la prima fonte" porta a `/sources`. Gli utenti non-admin non vedono l'onboarding.
