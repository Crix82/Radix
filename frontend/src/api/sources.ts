import { api } from "./client";
import type { DocumentOut } from "./indexing";

export type SourceType = "smb" | "local" | "upload";

export interface Source {
  id: number;
  type: SourceType;
  path: string;
  collection_id: number;
  enabled: boolean;
  status: string | null;
  last_sync_at: string | null;
  document_count: number;
}

export interface SourceCreate {
  type: SourceType;
  path?: string;
}

export interface UploadOut {
  created: DocumentOut[];
  unchanged: number;
}

export const listSources = () => api<Source[]>("/sources");

export const createSource = (body: SourceCreate) =>
  api<Source>("/sources", { method: "POST", body: JSON.stringify(body) });

export const updateSource = (id: number, body: { enabled?: boolean; path?: string }) =>
  api<Source>(`/sources/${id}`, { method: "PATCH", body: JSON.stringify(body) });

export const deleteSource = (id: number) =>
  api<void>(`/sources/${id}`, { method: "DELETE" });

export function uploadFiles(files: File[], sourceId?: number): Promise<UploadOut> {
  const form = new FormData();
  for (const file of files) form.append("files", file);
  if (sourceId !== undefined) form.append("source_id", String(sourceId));
  return api<UploadOut>("/uploads", { method: "POST", body: form });
}
