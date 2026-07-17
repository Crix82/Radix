import { useRef, useState } from "react";

import type { Source } from "../api/sources";
import { AddSourceModal } from "../components/AddSourceModal";
import { PageHead } from "../components/Layout";
import { useSources, useToggleSource, useUploadFiles } from "../hooks/useSources";
import { t } from "../i18n";
import { formatRelative } from "../lib/time";

const s = t.pages.sources;

const TYPE_LABELS = { smb: s.typeSmb, local: s.typeLocal, upload: s.typeUpload } as const;

function statusChip(source: Source): { className: string; label: string } {
  if (!source.enabled) return { className: "chip-neutral", label: s.statusDisabled };
  if (source.status === "error") return { className: "chip-err", label: s.statusError };
  if (source.type === "upload") return { className: "chip-ok", label: s.statusActive };
  if (source.status === "ok") {
    return {
      className: "chip-ok",
      label: `${s.statusSynced} · ${formatRelative(source.last_sync_at)}`,
    };
  }
  return { className: "chip-neutral", label: s.statusPending };
}

function Toggle({ on, onChange }: { on: boolean; onChange: () => void }) {
  return (
    <button
      type="button"
      onClick={onChange}
      aria-label={s.toggleAria}
      aria-pressed={on}
      className={
        "relative h-[19px] w-[34px] flex-none rounded-full transition-colors " +
        (on ? "bg-ok" : "bg-[#C9D3D8]")
      }
    >
      <span
        className={
          "absolute top-[2.5px] h-[14px] w-[14px] rounded-full bg-white transition-all " +
          (on ? "left-[17px]" : "left-[3px]")
        }
      />
    </button>
  );
}

function UploadAction({ sourceId }: { sourceId: number }) {
  const upload = useUploadFiles();
  const inputRef = useRef<HTMLInputElement>(null);
  const [message, setMessage] = useState<string | null>(null);

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".pdf,.docx,.xlsx,.pptx,.html,.txt"
        className="hidden"
        onChange={(e) => {
          const files = Array.from(e.target.files ?? []);
          e.target.value = "";
          if (files.length === 0) return;
          upload.mutate(
            { files, sourceId },
            {
              onSuccess: (out) => setMessage(s.uploadDone(out.created.length, out.unchanged)),
              onError: () => setMessage(t.common.genericError),
            },
          );
        }}
      />
      <button
        type="button"
        className="act-link"
        disabled={upload.isPending}
        onClick={() => inputRef.current?.click()}
      >
        {upload.isPending ? t.common.loading : s.uploadFiles}
      </button>
      {message && <div className="mt-[2px] font-mono text-[10.5px] text-ink3">{message}</div>}
    </>
  );
}

export function SourcesPage() {
  const { data: sources, isLoading } = useSources();
  const toggle = useToggleSource();
  const [modalOpen, setModalOpen] = useState(false);

  return (
    <>
      <div className="flex items-start justify-between gap-4">
        <PageHead title={s.title} subtitle={s.subtitle} />
        <button type="button" className="btn-primary mt-1 flex-none" onClick={() => setModalOpen(true)}>
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.2"
            aria-hidden="true"
            className="h-4 w-4"
          >
            <path d="M12 5v14M5 12h14" />
          </svg>
          {s.add}
        </button>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="th">{s.colSource}</th>
              <th className="th">{s.colPath}</th>
              <th className="th">{s.colDocuments}</th>
              <th className="th">{s.colStatus}</th>
              <th className="th" />
            </tr>
          </thead>
          <tbody>
            {isLoading && (
              <tr>
                <td className="td text-ink3" colSpan={5}>
                  {t.common.loading}
                </td>
              </tr>
            )}
            {(sources ?? []).map((source) => {
              const chip = statusChip(source);
              return (
                <tr key={source.id}>
                  <td className="td font-semibold">{TYPE_LABELS[source.type]}</td>
                  <td className="td">
                    <span className="font-mono text-[12px]">
                      {source.type === "upload" ? s.uploadPath : source.path}
                    </span>
                  </td>
                  <td className="td">{source.document_count.toLocaleString("it-IT")}</td>
                  <td className="td">
                    <span className={chip.className}>{chip.label}</span>
                  </td>
                  <td className="td text-right">
                    {source.type === "upload" && source.enabled ? (
                      <UploadAction sourceId={source.id} />
                    ) : (
                      <Toggle
                        on={source.enabled}
                        onChange={() =>
                          toggle.mutate({ id: source.id, enabled: !source.enabled })
                        }
                      />
                    )}
                  </td>
                </tr>
              );
            })}
            {(["Google Drive", "SharePoint"] as const).map((name) => (
              <tr key={name}>
                <td className="td font-semibold text-ink3">{name}</td>
                <td className="td">
                  <span className="font-mono text-[12px] text-ink3">—</span>
                </td>
                <td className="td text-ink3">—</td>
                <td className="td">
                  <span className="chip-neutral">{s.comingV11}</span>
                </td>
                <td className="td text-right">
                  <button type="button" className="act-link opacity-50" disabled>
                    {s.connect}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modalOpen && <AddSourceModal onClose={() => setModalOpen(false)} />}
    </>
  );
}
