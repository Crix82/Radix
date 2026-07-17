import { useState } from "react";
import { useMutation } from "@tanstack/react-query";

import { search, type SearchResult } from "../api/search";
import { PageHead } from "../components/Layout";
import { t } from "../i18n";

const s = t.pages.search;

const LANGS = [
  { value: undefined, label: s.langAll },
  { value: "it", label: "IT" },
  { value: "en", label: "EN" },
  { value: "de", label: "DE" },
] as const;

// Relevance dots (mock: .rel) — filled by score relative to the top hit.
function RelevanceDots({ score, top }: { score: number; top: number }) {
  const filled = top > 0 ? Math.max(1, Math.ceil((score / top) * 3)) : 1;
  return (
    <span className="ml-auto inline-flex gap-[3px]" aria-label={`Rilevanza ${filled}/3`}>
      {[0, 1, 2].map((i) => (
        <i
          key={i}
          className={`h-[5px] w-[5px] rounded-full ${i < filled ? "bg-petrol-mid" : "bg-line"}`}
        />
      ))}
    </span>
  );
}

function ResultCard({ result, top }: { result: SearchResult; top: number }) {
  const { document: doc } = result;
  return (
    <button type="button" className="result">
      <div className="mb-[5px] flex flex-wrap items-center gap-2">
        <span className="text-[14px] font-semibold text-ink">{doc.title ?? doc.rel_path}</span>
        {doc.lang && <span className="badge-lang">{doc.lang.toUpperCase()}</span>}
        {doc.doc_type && <span className="chip-neutral">{doc.doc_type}</span>}
        <RelevanceDots score={result.score} top={top} />
      </div>
      <div
        className="res-snip mb-[7px] text-[12.5px] text-ink2"
        dangerouslySetInnerHTML={{ __html: result.snippet_html }}
      />
      <div className="flex items-center gap-[10px]">
        <span className="font-mono text-[11px] text-ink2">
          {s.pageAbbr} {result.page}
        </span>
        <span className="font-mono text-[11px] text-ink3">{doc.rel_path}</span>
      </div>
    </button>
  );
}

export function SearchPage() {
  const [query, setQuery] = useState("");
  const [lang, setLang] = useState<string | undefined>(undefined);
  const searchMutation = useMutation({
    mutationFn: (q: string) => search({ q, lang }),
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim()) searchMutation.mutate(query.trim());
  };

  const results = searchMutation.data;
  const top = results && results.length > 0 ? results[0].score : 0;

  return (
    <>
      <PageHead title={s.title} subtitle={s.subtitle} />

      <form className="mb-[14px] flex gap-[10px]" onSubmit={submit}>
        <div className="search-box">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            aria-hidden="true"
            className="h-[17px] w-[17px] flex-none text-ink3"
          >
            <circle cx="11" cy="11" r="7" />
            <path d="m20 20-3.5-3.5" />
          </svg>
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={s.inputPlaceholder}
            aria-label={s.inputLabel}
          />
        </div>
        <button type="submit" className="btn-primary" disabled={!query.trim()}>
          {s.submit}
        </button>
      </form>

      <div className="mb-5 flex flex-wrap items-center gap-2">
        <span className="f-label">{s.filterLang}</span>
        {LANGS.map((l) => (
          <button
            key={l.label}
            type="button"
            className={lang === l.value ? "f-chip-on" : "f-chip"}
            onClick={() => {
              setLang(l.value);
              if (query.trim()) searchMutation.mutate(query.trim());
            }}
          >
            {l.label}
          </button>
        ))}
      </div>

      {searchMutation.isPending && <div className="text-[13px] text-ink3">{s.searching}</div>}
      {searchMutation.isError && <div className="text-[13px] text-err">{s.error}</div>}

      {!searchMutation.isPending && !searchMutation.isError && (
        <>
          {results === undefined && <div className="text-[13px] text-ink3">{s.initial}</div>}
          {results && results.length === 0 && (
            <div className="card px-5 py-10 text-center text-[13px] text-ink3">
              {s.empty}
              <div className="mt-1 text-ink3">{s.emptyHint}</div>
            </div>
          )}
          {results && results.length > 0 && (
            <>
              <div className="mb-3 text-[12px] text-ink3">{s.resultsCount(results.length)}</div>
              <div className="flex flex-col gap-[10px]">
                {results.map((r) => (
                  <ResultCard key={r.chunk_id} result={r} top={top} />
                ))}
              </div>
            </>
          )}
        </>
      )}
    </>
  );
}
