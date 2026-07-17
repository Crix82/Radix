import { useEffect, useState } from "react";

import type { SourceType } from "../api/sources";
import { useCreateSource } from "../hooks/useSources";
import { t } from "../i18n";

const m = t.pages.sources.modal;

const OPTIONS: { type: SourceType; label: string; hint: string }[] = [
  { type: "smb", label: m.optSmb, hint: m.optSmbHint },
  { type: "local", label: m.optLocal, hint: m.optLocalHint },
  { type: "upload", label: m.optUpload, hint: m.optUploadHint },
];

export function AddSourceModal({ onClose }: { onClose: () => void }) {
  const [type, setType] = useState<SourceType>("smb");
  const [path, setPath] = useState("");
  const create = useCreateSource();

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const submit = () => {
    create.mutate(
      { type, ...(type === "upload" ? {} : { path }) },
      { onSuccess: onClose },
    );
  };
  const submitDisabled = create.isPending || (type !== "upload" && path.trim() === "");

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(20,38,45,.45)] p-5"
      onClick={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        className="card w-full max-w-[480px] px-6 py-[22px]"
        role="dialog"
        aria-modal="true"
        aria-labelledby="add-source-title"
      >
        <h3 id="add-source-title" className="mb-1 text-[16px] font-semibold">
          {m.title}
        </h3>
        <div className="mb-4 text-[12.5px] text-ink2">{m.subtitle}</div>

        <div className="mb-[14px] grid grid-cols-2 gap-2">
          {OPTIONS.map((opt) => (
            <button
              key={opt.type}
              type="button"
              onClick={() => setType(opt.type)}
              className={
                "rounded-sm border px-3 py-[10px] text-left text-[12.5px] font-semibold " +
                (type === opt.type ? "border-petrol bg-petrol-tint" : "border-line bg-surface")
              }
            >
              {opt.label}
              <small className="mt-[1px] block text-[11px] font-medium text-ink3">
                {opt.hint}
              </small>
            </button>
          ))}
          <button
            type="button"
            disabled
            className="rounded-sm border border-line bg-surface px-3 py-[10px] text-left text-[12.5px] font-semibold opacity-50"
          >
            {m.optCloud}
            <small className="mt-[1px] block text-[11px] font-medium text-ink3">
              {m.optCloudHint}
            </small>
          </button>
        </div>

        {type === "upload" ? (
          <p className="mb-4 font-mono text-[10.5px] text-ink3">{m.uploadHint}</p>
        ) : (
          <div className="mb-4">
            <label className="field-label" htmlFor="source-path">
              {m.pathLabel}
            </label>
            <input
              id="source-path"
              className="field-input font-mono text-[12px]"
              type="text"
              value={path}
              placeholder={type === "smb" ? m.pathPlaceholderSmb : m.pathPlaceholderLocal}
              onChange={(e) => setPath(e.target.value)}
              autoFocus
            />
            {type === "smb" && (
              <p className="mt-[6px] font-mono text-[10.5px] text-ink3">{m.pathHintSmb}</p>
            )}
          </div>
        )}

        {create.isError && <p className="mb-3 text-[12px] text-err">{m.error}</p>}

        <div className="flex justify-end gap-[10px]">
          <button type="button" className="btn-plain" onClick={onClose}>
            {m.cancel}
          </button>
          <button type="button" className="btn-primary" onClick={submit} disabled={submitDisabled}>
            {m.submit}
          </button>
        </div>
      </div>
    </div>
  );
}
