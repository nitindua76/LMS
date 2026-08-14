import { client } from "./client";

export interface Me {
  id: number;
  name: string;
  email: string;
  cpf: string | null;
  auth_provider: "local" | "sso";
  role: "admin" | "employee";
  active: boolean;
  force_password_change: boolean;
  discipline_id: number | null;
  level_id: number | null;
  can_create_rooms: boolean;
}

export const authApi = {
  // `identifier` is a CPF for SSO-authenticated employees, or an email for
  // the small set of local-password accounts kept as a break-glass path —
  // the backend decides which by looking the value up, not by its shape.
  login: (identifier: string, password: string) =>
    client.post<Me>("/auth/login", { identifier, password }).then((r) => r.data),

  logout: () => client.post("/auth/logout"),

  me: () => client.get<Me>("/auth/me").then((r) => r.data),

  refresh: () => client.post<Me>("/auth/refresh").then((r) => r.data),
};
