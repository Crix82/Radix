import { t } from "../i18n";

// Compact relative time for technical metadata (mock shows "2 min fa", "1 h fa", "adesso").
export function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const minutes = Math.floor((Date.now() - then) / 60_000);
  if (minutes < 1) return t.time.now;
  if (minutes < 60) return t.time.minutesAgo(minutes);
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return t.time.hoursAgo(hours);
  return t.time.daysAgo(Math.floor(hours / 24));
}

export function formatBytes(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${Math.round(bytes / 1024 ** 3)} GB`;
  if (bytes >= 1024 ** 2) return `${Math.round(bytes / 1024 ** 2)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}
