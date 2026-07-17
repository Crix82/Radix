import { api } from "./client";

export interface SearchDocumentRef {
  id: number;
  title: string | null;
  lang: string | null;
  doc_type: string | null;
  rel_path: string;
}

export interface SearchResult {
  chunk_id: number;
  document: SearchDocumentRef;
  page: number;
  snippet_html: string;
  score: number;
}

export interface SearchParams {
  q: string;
  lang?: string;
  doc_type?: string;
  collection_id?: number;
}

export function search(params: SearchParams): Promise<SearchResult[]> {
  const qs = new URLSearchParams({ q: params.q });
  if (params.lang) qs.set("lang", params.lang);
  if (params.doc_type) qs.set("doc_type", params.doc_type);
  if (params.collection_id !== undefined) qs.set("collection_id", String(params.collection_id));
  return api<SearchResult[]>(`/search?${qs.toString()}`);
}
