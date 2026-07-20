import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import * as conversationsApi from "../api/conversations";

const CONVERSATIONS_KEY = ["conversations"];

export function useConversations() {
  return useQuery({ queryKey: CONVERSATIONS_KEY, queryFn: conversationsApi.listConversations });
}

export function useConversation(id: number | undefined) {
  return useQuery({
    queryKey: [...CONVERSATIONS_KEY, id],
    queryFn: () => conversationsApi.getConversation(id as number),
    enabled: id !== undefined,
  });
}

/** Re-read the thread list after a turn changed a title or its recency ordering. */
export function useRefreshConversations() {
  const queryClient = useQueryClient();
  return () => void queryClient.invalidateQueries({ queryKey: CONVERSATIONS_KEY });
}

export function useDeleteConversation() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: conversationsApi.deleteConversation,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: CONVERSATIONS_KEY }),
  });
}
