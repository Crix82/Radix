"""RAG prompts (SPEC §8). The system prompt is the grounding contract for the assistant."""

SYSTEM_PROMPT = (
    "Sei Radix, l'assistente documentale dell'azienda. Rispondi esclusivamente sulla base "
    "dei passaggi forniti nel contesto. Dopo ogni affermazione fattuale inserisci la "
    "citazione [n] del passaggio che la supporta. Rispondi nella lingua della domanda, "
    "anche se i documenti sono in un'altra lingua. Se il contesto copre solo in parte la "
    "domanda, dillo esplicitamente. Se il contesto non contiene la risposta, rispondi "
    'esattamente: "Non presente nella documentazione indicizzata." Non usare conoscenza '
    "esterna ai passaggi forniti."
)

# Exact refusal answer returned without calling the LLM (SPEC §8, DoD).
REFUSAL_PHRASE = "Non presente nella documentazione indicizzata."

# Conversational query rewriting (ADR 0010): a follow-up is condensed into a standalone
# question before retrieval, so the retriever — and the refusal threshold — see a query that
# carries the subject the thread established. The rewrite is used for retrieval only.
# No worked examples in the prompt: a small model copies them into its output (seen with
# Qwen2.5-1.5B, which rewrote an unrelated follow-up into the example question).
CONDENSE_PROMPT = (
    "Riscrivi l'ultima domanda dell'utente come domanda autonoma, comprensibile senza la "
    "conversazione precedente: sostituisci pronomi e riferimenti impliciti con ciò a cui si "
    "riferiscono (il prodotto, il documento, l'argomento di cui si stava parlando), usando solo "
    "la conversazione. Conserva il significato e le parole chiave della domanda originale. Se "
    "la domanda è già autonoma, o cambia argomento, restituiscila identica. Mantieni la lingua "
    "della domanda. Non rispondere alla domanda e non aggiungere commenti: restituisci "
    "soltanto la domanda riscritta, su una riga."
)

# Cross-lingual retrieval (ADR 0011): the question is also translated into English and both
# versions are searched, then fused. Italian questions over English manuals otherwise rank the
# right page too low: bge-m3 is multilingual but scores cross-language pairs lower, and the
# lexical search finds no shared words at all. The translation is used for retrieval only.
TRANSLATE_PROMPT = (
    "Translate the user's question into English for a search engine over technical documents. "
    "Keep technical terms, product names, codes, numbers and units unchanged. "
    "Output only the translated question, on one line, nothing else."
)
