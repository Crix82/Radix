// UI strings, Italian (default locale). Code and identifiers stay in English (SPEC §2).
export const it = {
  app: {
    name: "Radix",
    tagline: "on-premise",
    footPrivacy: "Tutti i dati sul tuo server",
    footNoExternal: "nessuna connessione esterna",
  },
  nav: {
    consultation: "Consultazione",
    administration: "Amministrazione",
    setup: "Setup",
    search: "Ricerca",
    chat: "Chat",
    sources: "Fonti",
    indexing: "Indicizzazione",
    users: "Utenti",
    onboarding: "Prima attivazione",
  },
  login: {
    title: "Accedi a Radix",
    subtitle: "La documentazione tecnica della tua azienda, interrogabile.",
    email: "Email",
    password: "Password",
    submit: "Accedi",
    error: "Credenziali non valide",
    rateLimited: "Troppi tentativi. Riprova tra qualche minuto.",
    genericError: "Errore di connessione. Riprova.",
  },
  common: {
    loading: "Caricamento…",
    logout: "Esci",
    comingSoon: "Disponibile in una prossima milestone",
  },
  pages: {
    search: {
      title: "Ricerca",
      subtitle: "Cerca nella documentazione indicizzata",
      placeholder: "La ricerca arriva con la milestone M3.",
    },
    chat: {
      title: "Chat",
      subtitle:
        "Risposte basate esclusivamente sui documenti indicizzati, con citazione alla pagina",
      placeholder: "La chat arriva con la milestone M4.",
    },
    sources: {
      title: "Fonti",
      subtitle:
        "Da dove Radix acquisisce i documenti. Le fonti attive sono monitorate in automatico.",
      placeholder: "La gestione delle fonti arriva con la milestone M1.",
    },
    indexing: {
      title: "Indicizzazione",
      subtitle:
        "Stato della pipeline: parsing, OCR, embedding e indice. Rilevamento automatico delle modifiche.",
      placeholder: "Lo stato della pipeline arriva con la milestone M1.",
    },
    users: {
      title: "Utenti",
      subtitle: "Chi può accedere e a quali collezioni. Massimo 20 utenti per installazione.",
      placeholder: "La gestione utenti arriva con la milestone M5.",
    },
    onboarding: {
      eyebrow: "PRIMA CONFIGURAZIONE",
      title: "Benvenuto in Radix",
      lead: "Tre passaggi e la documentazione tecnica della tua azienda diventa interrogabile. Tutto resta sul tuo server.",
      step1Title: "Collega una fonte",
      step1Desc: "Cartella di rete, cartella locale o caricamento diretto dei file.",
      step2Title: "Indicizzazione automatica",
      step2Desc: "Parsing, OCR e indice multilingua, senza alcun intervento manuale.",
      step3Title: "Fai la prima domanda",
      step3Desc: "Risposte con citazioni alla pagina esatta del documento originale.",
      cta: "Collega la prima fonte",
      note: "installazione locale · attivazione stimata: meno di una giornata",
    },
  },
} as const;
