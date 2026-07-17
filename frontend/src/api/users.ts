import { api } from "./client";

export type UserRole = "admin" | "user";
export type UserStatus = "active" | "invited" | "disabled";

export interface UserDetail {
  id: number;
  name: string;
  email: string;
  role: UserRole;
  status: UserStatus;
  collection_ids: number[];
}

export interface Collection {
  id: number;
  name: string;
  document_count: number;
}

export interface InviteUser {
  name: string;
  email: string;
  role: UserRole;
  collection_ids: number[];
  password?: string;
}

export const listUsers = () => api<UserDetail[]>("/users");

export const inviteUser = (body: InviteUser) =>
  api<UserDetail>("/users", { method: "POST", body: JSON.stringify(body) });

export const updateUser = (id: number, body: Partial<InviteUser> & { status?: UserStatus }) =>
  api<UserDetail>(`/users/${id}`, { method: "PATCH", body: JSON.stringify(body) });

export const listCollections = () => api<Collection[]>("/collections");
