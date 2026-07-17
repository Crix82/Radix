import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import * as usersApi from "../api/users";

export function useUsers() {
  return useQuery({ queryKey: ["users"], queryFn: usersApi.listUsers });
}

export function useCollections() {
  return useQuery({ queryKey: ["collections"], queryFn: usersApi.listCollections });
}

export function useInviteUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: usersApi.inviteUser,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}

export function useUpdateUser() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, ...body }: { id: number } & Parameters<typeof usersApi.updateUser>[1]) =>
      usersApi.updateUser(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["users"] }),
  });
}
