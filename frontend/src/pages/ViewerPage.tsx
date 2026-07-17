import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation, useNavigate, useParams } from "react-router-dom";

import { getDocument, pageImageUrl } from "../api/documents";
import { t } from "../i18n";

const v = t.pages.viewer;

interface ViewerState {
  bboxes?: Record<string, number[][]> | null;
  from?: "chat" | "ricerca" | "documents";
  title?: string | null;
  lang?: string | null;
}

function HighlightOverlay({ boxes }: { boxes: number[][] }) {
  return (
    <>
      {boxes.map(([x0, y0, x1, y1], i) => (
        <div
          key={i}
          className="pointer-events-none absolute rounded-[2px] border-2 border-amber bg-amber/25"
          style={{
            left: `${x0 * 100}%`,
            top: `${y0 * 100}%`,
            width: `${(x1 - x0) * 100}%`,
            height: `${(y1 - y0) * 100}%`,
          }}
        />
      ))}
    </>
  );
}

export function ViewerPage() {
  const { documentId, page } = useParams();
  const docId = Number(documentId);
  const currentPage = Number(page);
  const navigate = useNavigate();
  const state = (useLocation().state as ViewerState) ?? {};
  const [imgError, setImgError] = useState(false);

  const { data: doc } = useQuery({
    queryKey: ["document", docId],
    queryFn: () => getDocument(docId),
    enabled: Number.isFinite(docId),
  });

  const totalPages = doc?.pages ?? null;
  const title = doc?.title ?? state.title ?? `#${docId}`;
  const lang = doc?.lang ?? state.lang ?? null;
  const highlights = state.bboxes?.[String(currentPage)] ?? [];

  const backLabel =
    state.from === "chat" ? v.backToChat : state.from === "ricerca" ? v.backToSearch : v.back;

  const goToPage = (p: number) => {
    if (p >= 1 && (totalPages === null || p <= totalPages)) {
      navigate(`/viewer/${docId}/${p}`, { state });
    }
  };

  const thumbs = [-2, -1, 0, 1, 2]
    .map((d) => currentPage + d)
    .filter((p) => p >= 1 && (totalPages === null || p <= totalPages));

  return (
    <>
      <div className="mb-[18px] flex flex-wrap items-center gap-[14px]">
        <button type="button" className="btn-plain" onClick={() => navigate(-1)}>
          {backLabel}
        </button>
        <span className="text-[15px] font-semibold">{title}</span>
        {lang && <span className="badge-lang">{lang.toUpperCase()}</span>}
        <span className="font-mono text-[12px] text-ink2">{v.pageOf(currentPage, totalPages)}</span>
      </div>

      <div className="flex items-start gap-[18px]">
        <div className="flex flex-none flex-col gap-2">
          {thumbs.map((p) => (
            <button
              key={p}
              type="button"
              className={p === currentPage ? "thumb-on" : "thumb"}
              onClick={() => goToPage(p)}
            >
              {p}
            </button>
          ))}
        </div>

        <div className="card max-w-[680px] flex-1 overflow-hidden p-2">
          {imgError ? (
            <div className="px-5 py-10 text-center text-[13px] text-ink3">{v.pageError}</div>
          ) : (
            <div className="relative">
              <img
                src={pageImageUrl(docId, currentPage)}
                alt={`${title} — ${v.pageOf(currentPage, totalPages)}`}
                className="block w-full"
                onError={() => setImgError(true)}
              />
              <HighlightOverlay boxes={highlights} />
            </div>
          )}
        </div>
      </div>
    </>
  );
}
