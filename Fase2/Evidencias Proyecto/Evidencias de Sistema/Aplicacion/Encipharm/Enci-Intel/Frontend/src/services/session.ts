/**
 * Limpia la sesion y recarga: la app vuelve a la pantalla de login.
 * La usan el interceptor de axios y las llamadas que no pasan por axios
 * (el chat en streaming usa fetch), para que un token vencido se maneje igual.
 */
/**
 * Un 401 significa "sesion vencida" salvo en el propio login, donde solo indica
 * credenciales incorrectas y el usuario debe ver el mensaje, no una recarga.
 */
export function shouldExpireSession(status: number | undefined, url: string | undefined): boolean {
  if (status !== 401) return false;
  return !String(url ?? "").split("?")[0].endsWith("/auth/login");
}

export function handleSessionExpired() {
  localStorage.removeItem("enci_token");
  localStorage.removeItem("enci_role");
  localStorage.removeItem("enci_user");
  sessionStorage.clear();
  window.location.reload();
}
