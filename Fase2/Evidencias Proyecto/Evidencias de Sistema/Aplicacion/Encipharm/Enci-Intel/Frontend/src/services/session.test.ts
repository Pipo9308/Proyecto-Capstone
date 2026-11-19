import assert from "node:assert/strict";
import { beforeEach, test } from "node:test";
import { handleSessionExpired, shouldExpireSession } from "./session.ts";

class MemoryStorage {
  private data = new Map<string, string>();
  getItem(key: string) { return this.data.has(key) ? this.data.get(key)! : null; }
  setItem(key: string, value: string) { this.data.set(key, value); }
  removeItem(key: string) { this.data.delete(key); }
  clear() { this.data.clear(); }
}

let reloads = 0;
const g = globalThis as unknown as Record<string, unknown>;

beforeEach(() => {
  reloads = 0;
  g.localStorage = new MemoryStorage();
  g.sessionStorage = new MemoryStorage();
  g.window = { location: { reload: () => { reloads += 1; } } };
});

test("un 401 limpia el token, el rol y el usuario, y recarga a la pantalla de login", () => {
  const ls = g.localStorage as MemoryStorage;
  ls.setItem("enci_token", "jwt-vencido");
  ls.setItem("enci_role", "admin");
  ls.setItem("enci_user", "{}");
  ls.setItem("preferencia-ajena", "se-queda");
  (g.sessionStorage as MemoryStorage).setItem("enci_role", "admin");

  handleSessionExpired();

  assert.equal(ls.getItem("enci_token"), null);
  assert.equal(ls.getItem("enci_role"), null);
  assert.equal(ls.getItem("enci_user"), null);
  assert.equal(ls.getItem("preferencia-ajena"), "se-queda");
  assert.equal((g.sessionStorage as MemoryStorage).getItem("enci_role"), null);
  assert.equal(reloads, 1);
});

test("un 401 del login (credenciales malas) no cuenta como sesion vencida", () => {
  assert.equal(shouldExpireSession(401, "/auth/login"), false);
  assert.equal(shouldExpireSession(401, "/auth/login?x=1"), false);
});

test("un 401 de cualquier otro endpoint si vence la sesion; otros codigos no", () => {
  assert.equal(shouldExpireSession(401, "/alerts/"), true);
  assert.equal(shouldExpireSession(403, "/alerts/"), false);
  assert.equal(shouldExpireSession(undefined, undefined), false);
});

test("es idempotente: sin sesion guardada tambien recarga sin fallar", () => {
  handleSessionExpired();
  assert.equal(reloads, 1);
});
