import { client } from "./client";

export interface Me {
  id: number;
  name: string;
  email: string;
  role: "admin" | "employee";
  active: boolean;
  force_password_change: boolean;
  discipline_id: number | null;
  level_id: number | null;
}

export const authApi = {
  login: (email: string, password: string) =>
    client.post<Me>("/auth/login", { email, password }).then((r) => r.data),

  logout: () => client.post("/auth/logout"),

  me: () => client.get<Me>("/auth/me").then((r) => r.data),

  refresh: () => client.post<Me>("/auth/refresh").then((r) => r.data),
};
