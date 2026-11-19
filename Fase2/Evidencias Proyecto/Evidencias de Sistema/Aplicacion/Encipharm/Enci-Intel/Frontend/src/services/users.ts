import { api } from "./api";
import { toUiRole } from "../utils/role";

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function getUserRole(_uid: string) {
  try {
    const res = await api.get("/auth/me");
    const data = res.data.data;
    return toUiRole(data?.role);
  } catch (error) {
    console.error("Error fetching user role:", error);
    return "pendiente";
  }
}