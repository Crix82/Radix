import { api } from "./client";

export interface User {
  id: number;
  name: string;
  email: string;
  role: "admin" | "user";
  status: "active" | "invited" | "disabled";
}

export function login(email: string, password: string): Promise<User> {
  return api<User>("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
}

export function logout(): Promise<void> {
  return api<void>("/auth/logout", { method: "POST" });
}

export function me(): Promise<User> {
  return api<User>("/auth/me");
}
