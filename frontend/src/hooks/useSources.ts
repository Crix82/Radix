import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import * as sourcesApi from "../api/sources";

const SOURCES_KEY = ["sources"];
const INDEXING_KEYS = [["indexing-stats"], ["indexing-queue"]];

function useInvalidateIngest() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: SOURCES_KEY });
    for (const key of INDEXING_KEYS) void queryClient.invalidateQueries({ queryKey: key });
  };
}

export function useSources() {
  return useQuery({
    queryKey: SOURCES_KEY,
    queryFn: sourcesApi.listSources,
    refetchInterval: 10_000,
  });
}

export function useCreateSource() {
  const invalidate = useInvalidateIngest();
  return useMutation({ mutationFn: sourcesApi.createSource, onSuccess: invalidate });
}

export function useToggleSource() {
  const invalidate = useInvalidateIngest();
  return useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      sourcesApi.updateSource(id, { enabled }),
    onSuccess: invalidate,
  });
}

export function useUploadFiles() {
  const invalidate = useInvalidateIngest();
  return useMutation({
    mutationFn: ({ files, sourceId }: { files: File[]; sourceId?: number }) =>
      sourcesApi.uploadFiles(files, sourceId),
    onSuccess: invalidate,
  });
}
