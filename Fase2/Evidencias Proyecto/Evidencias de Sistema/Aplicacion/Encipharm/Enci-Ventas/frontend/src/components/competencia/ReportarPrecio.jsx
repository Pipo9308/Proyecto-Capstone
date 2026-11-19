import { useEffect, useState } from "react";
import { useAuth } from "../../auth/authContext";
import { hasMinimumRole } from "../../auth/roles";
import { createCompetenciaProducto, getCompetenciaProductos, reportarPrecioCompetencia } from "../../services/api";
import { apiMessage } from "../../utils/apiErrors";

const NEW = "__nuevo__";
const EMPTY_PRODUCT = { competidor: "", nombre: "", presentacion: "", unidadMedida: "ml", cantidadPresentacion: "", principios: "", categoria: "" };
const today = () => new Date().toISOString().slice(0, 10);

/** Reporte de precio de un producto de la competencia (RF-04.05). El vendedor queda "pendiente" de aprobacion. */
function ReportarPrecio({ onReported }) {
  const { backendUser, idToken: token } = useAuth();
  const autoApproved = hasMinimumRole(backendUser?.rol, "supervisor");
  const [products, setProducts] = useState([]);
  const [productId, setProductId] = useState("");
  const [product, setProduct] = useState(EMPTY_PRODUCT);
  const [price, setPrice] = useState({ precio: "", fuente: "", fechaPrecio: today() });
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    let cancelled = false;
    getCompetenciaProductos(token, { pageSize: 100 })
      .then((page) => !cancelled && setProducts(page.items))
      .catch(() => !cancelled && setProducts([]));
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function submit(event) {
    event.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      let id = productId;
      if (productId === NEW) {
        const created = await createCompetenciaProducto(token, {
          competidor: product.competidor,
          nombre: product.nombre,
          presentacion: product.presentacion || null,
          unidadMedida: product.unidadMedida,
          cantidadPresentacion: Number(product.cantidadPresentacion),
          principiosActivos: product.principios.split(",").map((p) => p.trim()).filter(Boolean),
          categoria: product.categoria || null,
        });
        id = created.id;
        setProducts((list) => [...list, created]);
        setProductId(created.id);
      }
      await reportarPrecioCompetencia(token, id, {
        precio: Number(price.precio),
        fuente: price.fuente || null,
        fechaPrecio: price.fechaPrecio || null,
      });
      setMessage({
        ok: true,
        text: autoApproved ? "Precio registrado y aprobado." : "Precio enviado: queda pendiente de aprobación de un supervisor.",
      });
      setPrice({ precio: "", fuente: "", fechaPrecio: today() });
      setProduct(EMPTY_PRODUCT);
      onReported?.();
    } catch (error) {
      setMessage({ ok: false, text: apiMessage(error) });
    } finally {
      setBusy(false);
    }
  }

  const setP = (key) => (event) => setProduct((current) => ({ ...current, [key]: event.target.value }));
  const setPr = (key) => (event) => setPrice((current) => ({ ...current, [key]: event.target.value }));

  return (
    <form className="comp-form" onSubmit={submit} aria-label="Reportar precio">
      <label>
        Producto de la competencia
        <select value={productId} onChange={(event) => setProductId(event.target.value)} required>
          <option value="">Selecciona…</option>
          {products.map((item) => (
            <option key={item.id} value={item.id}>{`${item.competidor} · ${item.nombre}${item.presentacion ? ` (${item.presentacion})` : ""}`}</option>
          ))}
          <option value={NEW}>+ Producto nuevo</option>
        </select>
      </label>

      {productId === NEW && (
        <fieldset className="comp-form-grid">
          <legend>Producto nuevo</legend>
          <label>Competidor<input value={product.competidor} onChange={setP("competidor")} required maxLength={160} /></label>
          <label>Nombre comercial<input value={product.nombre} onChange={setP("nombre")} required maxLength={200} /></label>
          <label>Presentación<input value={product.presentacion} onChange={setP("presentacion")} maxLength={120} placeholder="Frasco 500 ml" /></label>
          <label>Unidad de medida
            <select value={product.unidadMedida} onChange={setP("unidadMedida")}>
              <option value="ml">ml</option>
              <option value="g">g</option>
              <option value="dosis">dosis</option>
            </select>
          </label>
          <label>Cantidad por envase<input type="number" min="0" step="any" value={product.cantidadPresentacion} onChange={setP("cantidadPresentacion")} required /></label>
          <label>Principios activos (separados por coma)<input value={product.principios} onChange={setP("principios")} /></label>
          <label>Categoría<input value={product.categoria} onChange={setP("categoria")} maxLength={100} /></label>
        </fieldset>
      )}

      <div className="comp-form-grid">
        <label>Precio (CLP)<input type="number" min="0" step="any" value={price.precio} onChange={setPr("precio")} required /></label>
        <label>Fuente<input value={price.fuente} onChange={setPr("fuente")} maxLength={240} placeholder="Cotización de cliente, lista de precios…" /></label>
        <label>Fecha del precio<input type="date" max={today()} value={price.fechaPrecio} onChange={setPr("fechaPrecio")} /></label>
      </div>

      <div className="comp-form-actions">
        <button type="submit" className="btn-primary" disabled={busy || !productId}>{busy ? "Enviando…" : "Reportar precio"}</button>
        {message && <span role={message.ok ? "status" : "alert"} className={message.ok ? "comp-ok" : "comp-error"}>{message.text}</span>}
      </div>
    </form>
  );
}

export default ReportarPrecio;
