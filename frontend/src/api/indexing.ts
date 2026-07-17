import { api } from "./client";
import type { SourceType } from "./sources";

export type DocumentStatus =
  | "queued"
  | "parsing"
  | "ocr"
  | "chunking"
  | "embedding"
  | "indexed"
  | "error"
  | "excluded";

export interface DocumentOut {
  id: number;
  source_id: number | null;
  collection_id: number;
  rel_path: string;
  title: string | null;
  status: DocumentStatus;
  error_msg: string | null;
  size_bytes: number | null;
  updated_at: string;
}

export interface IndexingStats {
  documents_indexed: number;
  queued: number;
  errors: number;
  space_used_bytes: number;
  space_total_bytes: number;
}

export interface QueueItem {
  id: number;
  rel_path: string;
  source_type: SourceType | null;
  source_path: string | null;
  status: DocumentStatus;
  error_msg: string | null;
  updated_at: string;
}

export const getIndexingStats = () => api<IndexingStats>("/indexing/stats");

export const getIndexingQueue = () => api<QueueItem[]>("/indexing/queue");

export const excludeDocument = (id: number) =>
  api<DocumentOut>(`/documents/${id}/exclude`, { method: "POST" });

export const reindexDocument = (id: number) =>
  api<DocumentOut>(`/documents/${id}/reindex`, { method: "POST" });
