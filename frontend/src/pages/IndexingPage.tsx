import type { QueueItem } from "../api/indexing";
import { PageHead } from "../components/Layout";
import {
  useExcludeDocument,
  useIndexingQueue,
  useIndexingStats,
  useReindexDocument,
} from "../hooks/useIndexing";
import { t } from "../i18n";
import { formatBytes, formatRelative } from "../lib/time";

const x = t.pages.indexing;

const IN_PROGRESS = new Set(["parsing", "ocr", "chunking", "embedding"]);

function sourceLabel(item: QueueItem): string {
  if (item.source_type === "upload") return t.pages.sources.typeUpload.toLowerCase();
  if (item.source_path) return item.source_path.split("/").filter(Boolean).pop() ?? item.source_path;
  return "—";
}

function StatusCell({ item }: { item: QueueItem }) {
  const exclude = useExcludeDocument();
  if (item.status === "indexed") return <span className="chip-ok">{x.status.indexed}</span>;
  if (item.status === "error") {
    return (
      <>
        <span className="chip-err">{x.status.error}</span>
        <div className="mt-[2px] text-[11.5px] text-err">
          {item.error_msg}
          {" — "}
          <button
            type="button"
            className="act-link"
            disabled={exclude.isPending}
            onClick={() => exclude.mutate(item.id)}
          >
            {x.exclude}
          </button>
        </div>
      </>
    );
  }
  if (IN_PROGRESS.has(item.status)) {
    return (
      <>
        <span className="chip-petrol">{x.status[item.status]}</span>
        <div className="progress">
          <span className="progress-bar w-2/3 animate-pulse" />
        </div>
      </>
    );
  }
  return <span className="chip-neutral">{x.status[item.status]}</span>;
}

function ReindexAction({ item }: { item: QueueItem }) {
  const reindex = useReindexDocument();
  if (item.status !== "excluded" && item.status !== "error") return null;
  return (
    <button
      type="button"
      className="act-link"
      disabled={reindex.isPending}
      onClick={() => reindex.mutate(item.id)}
    >
      {x.reindex}
    </button>
  );
}

export function IndexingPage() {
  const { data: stats } = useIndexingStats();
  const { data: queue, isLoading } = useIndexingQueue();

  const spacePct =
    stats && stats.space_total_bytes > 0
      ? Math.min(100, (stats.space_used_bytes / stats.space_total_bytes) * 100)
      : 0;

  return (
    <>
      <PageHead title={x.title} subtitle={x.subtitle} />

      <div className="mb-[18px] grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div className="card px-4 py-[14px]">
          <div className="text-[21px] font-bold tracking-[-.01em]">
            {(stats?.documents_indexed ?? 0).toLocaleString("it-IT")}
          </div>
          <div className="mt-[1px] text-[11.5px] text-ink2">{x.statDocuments}</div>
        </div>
        <div className="card px-4 py-[14px]">
          <div className="text-[21px] font-bold tracking-[-.01em]">
            {stats ? formatBytes(stats.space_used_bytes) : "—"}{" "}
            <span className="text-[12px] font-normal text-ink3">
              / {stats ? formatBytes(stats.space_total_bytes) : "—"}
            </span>
          </div>
          <div className="mt-[1px] text-[11.5px] text-ink2">{x.statSpace}</div>
          <div className="progress mt-[9px] w-full">
            <span className="progress-bar bg-petrol" style={{ width: `${spacePct}%` }} />
          </div>
        </div>
        <div className="card px-4 py-[14px]">
          <div className="text-[21px] font-bold tracking-[-.01em]">{stats?.queued ?? 0}</div>
          <div className="mt-[1px] text-[11.5px] text-ink2">{x.statQueued}</div>
        </div>
        <div className="card px-4 py-[14px]">
          <div className="text-[21px] font-bold tracking-[-.01em] text-err">
            {stats?.errors ?? 0}
          </div>
          <div className="mt-[1px] text-[11.5px] text-ink2">{x.statErrors}</div>
        </div>
      </div>

      <div className="card overflow-x-auto">
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className="th">{x.colDocument}</th>
              <th className="th">{x.colSource}</th>
              <th className="th">{x.colStatus}</th>
              <th className="th">{x.colUpdated}</th>
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
            {!isLoading && (queue ?? []).length === 0 && (
              <tr>
                <td className="td py-8 text-center text-ink3" colSpan={5}>
                  {x.empty}
                </td>
              </tr>
            )}
            {(queue ?? []).map((item) => (
              <tr key={item.id}>
                <td className="td">
                  <span className="font-mono text-[12px] text-ink">{item.rel_path}</span>
                </td>
                <td className="td">
                  <span className="font-mono text-[12px] text-ink2">{sourceLabel(item)}</span>
                </td>
                <td className="td">
                  <StatusCell item={item} />
                </td>
                <td className="td">
                  <span className="font-mono text-[12px] text-ink2">
                    {item.status === "queued" ? "—" : formatRelative(item.updated_at)}
                  </span>
                </td>
                <td className="td text-right">
                  <ReindexAction item={item} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-3 font-mono text-[10.5px] text-ink3">{x.footnote}</p>
    </>
  );
}
