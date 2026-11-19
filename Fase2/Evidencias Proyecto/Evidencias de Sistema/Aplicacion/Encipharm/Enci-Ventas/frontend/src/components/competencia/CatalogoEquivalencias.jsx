import { useEffect, useState } from "react";
import { useAuth } from "../../auth/authContext";
import {
  createCatalogoProducto,
  getCompetenciaCatalogo,
  getCompetenciaProductos,
  setCompetenciaEquivalentes,
} from "../../services/api";
import { apiMessage } from "../../utils/apiErrors";

const EMPTY = { nombre: "", sku: "", unidadMedida: "ml", cantidadPresentacion: "", precioLista: "", principios: "", categoria: "" };

/** Catalogo minimo de productos Encipharm (D5) y equivalencias con productos de la competencia. Supervisor y admin. */
function CatalogoEquivalencias({ onChanged }) {
  const { idToken: token } = useAuth();
  const [catalog, setCatalog] = useState([]);
  const [products, setProducts] = useState([]);
  const [form, setForm] = useState(EMPTY);
  const [competitorId, setCompetitorId] = useState("");
  const [selected, setSelected] = useState([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getCompetenciaCatalogo(token), getCompetenciaProductos(token, { pageSize: 100 })])
      .then(([cat, page]) => {
        if (cancelled) return;
        setCatalog(cat);
        setProducts(page.items);
      })
      .catch((error) => !cancelled && setMessage({ ok: false, text: apiMessage(error) }));
    return () => {
      cancelled = true;
    };
  }, [token]);

  function pickCompetitor(id) {
    setCompetitorId(id);
    setSelected((products.find((p) => p.id === id)?.equivalentes || []).map((e) => e.id));
  }

  const toggle = (id) => setSelected((current) => (current.includes(id) ? current.filter((x) => x !== id) : [...current, id]));
  const set = (key) => (event) => setForm((current) => ({ ...current, [key]: event.target.value }));

  async function run(action, success) {
    setBusy(true);
    setMessage(null);
    try {
      await action();
      setMessage({ ok: true, text: success });
      onChanged?.();
    } catch (error) {
      setMessage({ ok: false, text: apiMessage(error) });
    } finally {
      setBusy(false);
    }
  }

  const addProduct = (event) => {
    event.preventDefault();
    return run(async () => {
      const created = await createCatalogoProducto(token, {
        nombre: form.nombre,
        sku: form.sku || null,
        unidadMedida: form.unidadMedida,
        cantidadPresentacion: Number(form.cantidadPresentacion),
        precioLista: form.precioLista === "" ? null : Number(form.precioLista),
        principiosActivos: form.principios.split(",").map((p) => p.trim()).filter(Boolean),
        categoria: form.categoria || null,
      });
      setCatalog((list) => [...list, created]);
      setForm(EMPTY);
    }, "Producto Encipharm agregado.");
  };

  const saveEquivalents = () =>
    run(async () => {
      const updated = await setCompetenciaEquivalentes(token, competitorId, selected);
      setProducts((list) => list.map((p) => (p.id === updated.id ? updated : p)));
    }, "Equivalencias guardadas.");

  return (
    <div className="comp-manage">
      <form className="comp-form" onSubmit={addProduct} aria-label="Agregar producto Encipharm">
        <h4>Agregar producto Encipharm</h4>
        <div className="comp-form-grid">
          <label>Nombre<input value={form.nombre} onChange={set("nombre")} required maxLength={200} /></label>
          <label>SKU<input value={form.sku} onChange={set("sku")} maxLength={60} /></label>
          <label>Unidad de medida
            <select value={form.unidadMedida} onChange={set("unidadMedida")}>
              <option value="ml">ml</option>
              <option value="g">g</option>
              <option value="dosis">dosis</option>
            </select>
          </label>
          <label>Cantidad por envase<input type="number" min="0" step="any" value={form.cantidadPresentacion} onChange={set("cantidadPresentacion")} required /></label>
          <label>Precio de lista (CLP)<input type="number" min="0" step="any" value={form.precioLista} onChange={set("precioLista")} /></label>
          <label>Principios activos (coma)<input value={form.principios} onChange={set("principios")} /></label>
          <label>Categoría<input value={form.categoria} onChange={set("categoria")} maxLength={100} /></label>
        </div>
        <div className="comp-form-actions"><button type="submit" className="btn-primary" disabled={busy}>Agregar</button></div>
      </form>

      <div className="comp-form">
        <h4>Equivalencias</h4>
        <label>
          Producto de la competencia
          <select value={competitorId} onChange={(event) => pickCompetitor(event.target.value)}>
            <option value="">Selecciona…</option>
            {products.map((p) => <option key={p.id} value={p.id}>{`${p.competidor} · ${p.nombre}`}</option>)}
          </select>
        </label>
        {competitorId && (
          <>
            {catalog.length === 0 && <p>Primero agrega productos Encipharm al catálogo.</p>}
            <div className="comp-checks">
              {catalog.map((item) => (
                <label key={item.id}>
                  <input type="checkbox" checked={selected.includes(item.id)} onChange={() => toggle(item.id)} />
                  {item.nombre}
                </label>
              ))}
            </div>
            <div className="comp-form-actions"><button type="button" disabled={busy} onClick={saveEquivalents}>Guardar equivalencias</button></div>
          </>
        )}
      </div>
      {message && <p role={message.ok ? "status" : "alert"} className={message.ok ? "comp-ok" : "comp-error"}>{message.text}</p>}
    </div>
  );
}

export default CatalogoEquivalencias;
