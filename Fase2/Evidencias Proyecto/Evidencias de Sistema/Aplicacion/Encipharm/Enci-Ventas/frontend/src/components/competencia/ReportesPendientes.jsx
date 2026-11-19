import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../../auth/authContext";
import { getPreciosCompetencia, revisarPrecioCompetencia } from "../../services/api";
import { apiMessage } from "../../utils/apiErrors";
import { money } from "../../utils/commercialAnalytics";

/** Cola de revision de precios reportados (RF-04.05): supervisor y admin aprueban o descartan. */
function ReportesPendientes({ refreshKey = 0, onReviewed }) {
  const { idToken: token } = useAuth();
  const [state, setState] = useState({ items: [], total: 0, loading: true, error: null });
  const [working, setWorking] = useState(null);

  const load = useCallback(async () => {
    setState((current) => ({ ...current, loading: true, error: null }));
    try {
      const page = await getPreciosCompetencia(token, { estado: "pendiente", pageSize: 50 });
      setState({ items: page.items, total: page.total, loading: false, error: null });
    } catch (error) {
      setState({ items: [], total: 0, loading: false, error: apiMessage(error) });
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  async function review(item, approve) {
    setWorking(item.id);
    try {
      await revisarPrecioCompetencia(token, item.id, approve);
      await load();
      onReviewed?.();
    } catch (error) {
      setState((current) => ({ ...current, error: apiMessage(error) }));
    } finally {
      setWorking(null);
    }
  }

  if (state.loading && state.items.length === 0) return <p>Cargando reportes…</p>;

  return (
    <div>
      {state.error && <p role="alert" className="comp-error">{state.error}</p>}
      {!state.error && state.items.length === 0 && <p>No hay reportes pendientes.</p>}
      {state.items.length > 0 && (
        <div className="comp-table-wrap">
          <table className="comp-table">
            <thead>
              <tr><th>Producto</th><th>Precio</th><th>Por unidad</th><th>Fuente</th><th>Reportó</th><th /></tr>
            </thead>
            <tbody>
              {state.items.map((item) => (
                <tr key={item.id}>
                  <td>{item.competidor} · {item.productoNombre}</td>
                  <td>{money(item.precio)} {item.moneda}</td>
                  <td>{money(item.precioPorUnidad)} / {item.unidadMedida}</td>
                  <td>{item.fuente || "—"} <small>({item.fechaPrecio})</small></td>
                  <td>{item.reportadoPorNombre || "—"}</td>
                  <td className="comp-actions">
                    <button type="button" disabled={working === item.id} onClick={() => review(item, true)}>Aprobar</button>
                    <button type="button" disabled={working === item.id} onClick={() => review(item, false)}>Descartar</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {state.total > state.items.length && <p>Mostrando {state.items.length} de {state.total}.</p>}
        </div>
      )}
    </div>
  );
}

export default ReportesPendientes;
