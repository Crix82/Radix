import { api } from "./client";
import type { DocumentStatus } from "./indexing";

export interface DocumentDetail {
  id: number;
  source_id: number | null;
  collection_id: number;
  rel_path: string;
  title: string | null;
  lang: string | null;
  doc_type: string | null;
  status: DocumentStatus;
  error_msg: string | null;
  size_bytes: number | null;
  pages: number | null;
  updated_at: string;
}

export const getDocument = (id: number) => api<DocumentDetail>(`/documents/${id}`);

export const pageImageUrl = (documentId: number, page: number) =>
  `/api/v1/documents/${documentId}/pages/${page}.png`;
