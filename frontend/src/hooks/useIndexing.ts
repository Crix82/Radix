import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import * as indexingApi from "../api/indexing";

// The pipeline advances on its own; poll while the page is open (SPEC §7.1: real data).
const POLL_MS = 4_000;

export function useIndexingStats() {
  return useQuery({
    queryKey: ["indexing-stats"],
    queryFn: indexingApi.getIndexingStats,
    refetchInterval: POLL_MS,
  });
}

export function useIndexingQueue() {
  return useQuery({
    queryKey: ["indexing-queue"],
    queryFn: indexingApi.getIndexingQueue,
    refetchInterval: POLL_MS,
  });
}

function useDocumentAction(action: (id: number) => Promise<unknown>) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: action,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["indexing-stats"] });
      void queryClient.invalidateQueries({ queryKey: ["indexing-queue"] });
    },
  });
}

export function useExcludeDocument() {
  return useDocumentAction(indexingApi.excludeDocument);
}

export function useReindexDocument() {
  return useDocumentAction(indexingApi.reindexDocument);
}
