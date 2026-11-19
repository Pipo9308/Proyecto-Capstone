import { api } from "./api";

export async function login(email: string, password: string) {
  const res = await api.post("/auth/login", { email, password });
  const data = res.data.data;
  
  if (data && data.token) {
    localStorage.setItem("enci_token", data.token);
    localStorage.setItem("enci_role", data.user.role);
    localStorage.setItem("enci_user", JSON.stringify(data.user));
    return data.user;
  }
  
  throw new Error("Login failed");
}

export async function logout() {
  localStorage.removeItem("enci_token");
  localStorage.removeItem("enci_role");
  localStorage.removeItem("enci_user");
  sessionStorage.clear();
}
