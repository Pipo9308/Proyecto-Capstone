import { useEffect, useState } from "react";
import { useAuth } from "../auth/authContext";
import { hasMinimumRole } from "../auth/roles";
import CatalogoEquivalencias from "../components/competencia/CatalogoEquivalencias";
import ReportarPrecio from "../components/competencia/ReportarPrecio";
import ReportesPendientes from "../components/competencia/ReportesPendientes";
import { getCompetenciaCatalogo, getCompetenciaComparativa, getCompetenciaResumen } from "../services/api";
import { apiMessage } from "../utils/apiErrors";
import { diffClass, formatDiff, perUnit } from "../utils/competencia";

const updatedLabel = (date) => (date ? `Actualizado ${date.toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" })}` : "");

function Block({ title, subtitle, loading, error, updatedAt, onRetry, children }) {
  return (
    <section className="competencia-section">
      <article className="card command-card">
        <div className="card-header">
          <div>
            <h3>{title}</h3>
            {subtitle && <p className="competition-card-sub">{subtitle}</p>}
          </div>
          {updatedAt && <small className="comp-updated">{updatedLabel(updatedAt)}</small>}
        </div>
        <div className="card-body competition-card-body">
          {loading ? (
            <p role="status">Cargando…</p>
          ) : error ? (
            <div role="alert" className="comp-error">
              {error} <button type="button" onClick={onRetry}>Reintentar</button>
            </div>
          ) : (
            children
          )}
        </div>
      </article>
    </section>
  );
}

function SummaryTable({ rows, label }) {
  if (rows.length === 0) return <p>Aún no hay precios aprobados.</p>;
  return (
    <div className="comp-table-wrap">
      <table className="comp-table">
        <thead>
          <tr>
            <th>{label}</th><th className="text-center">Productos</th>
            <th className="text-center">Precio promedio / unidad</th><th className="text-center">Dif. promedio vs Encipharm</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={`${row.clave}-${row.unidadMedida}-${row.moneda}`}>
              <td>{row.clave}</td>
              <td className="text-center">{row.productos}</td>
              <td className="text-center">{perUnit(row.precioPromedioPorUnidad, row.unidadMedida)}</td>
              <td className="text-center"><span className={`comp-price ${diffClass(row.diferenciaPromedioPct)}`}>{formatDiff(row.diferenciaPromedioPct)}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AnalisisCompetencia() {
  const { backendUser, idToken: token } = useAuth();
  const canReview = hasMinimumRole(backendUser?.rol, "supervisor");
  const [catalog, setCatalog] = useState({ items: [], loading: true, error: null });
  const [selectedId, setSelectedId] = useState("");
  const [comparativa, setComparativa] = useState({ data: null, loading: false, error: null, updatedAt: null });
  const comparing = comparativa.loading || (!comparativa.data && !comparativa.error);
  const [resumen, setResumen] = useState({ data: null, loading: true, error: null, updatedAt: null });
  const [refreshKey, setRefreshKey] = useState(0);

  // Las cargas viven dentro de los efectos y no muestran spinner al refrescar (no parpadea);
  // el spinner lo piden las acciones del usuario (reintentar, cambiar de producto).
  useEffect(() => {
    let cancelled = false;
    getCompetenciaCatalogo(token)
      .then((items) => {
        if (cancelled) return;
        setCatalog({ items, loading: false, error: null });
        setSelectedId((current) => current || items[0]?.id || "");
      })
      .catch((error) => !cancelled && setCatalog({ items: [], loading: false, error: apiMessage(error) }));
    return () => {
      cancelled = true;
    };
  }, [token, refreshKey]);

  useEffect(() => {
    let cancelled = false;
    getCompetenciaResumen(token)
      .then((data) => !cancelled && setResumen({ data, loading: false, error: null, updatedAt: new Date() }))
      .catch((error) => !cancelled && setResumen({ data: null, loading: false, error: apiMessage(error), updatedAt: null }));
    return () => {
      cancelled = true;
    };
  }, [token, refreshKey]);

  useEffect(() => {
    if (!selectedId) return undefined;
    let cancelled = false;
    getCompetenciaComparativa(token, selectedId)
      .then((data) => !cancelled && setComparativa({ data, loading: false, error: null, updatedAt: new Date() }))
      .catch((error) => !cancelled && setComparativa({ data: null, loading: false, error: apiMessage(error), updatedAt: null }));
    return () => {
      cancelled = true;
    };
  }, [token, selectedId, refreshKey]);

  const refresh = () => setRefreshKey((key) => key + 1);
  const retry = (setter) => () => {
    setter((current) => ({ ...current, loading: true, error: null }));
    refresh();
  };
  const retryCatalog = retry(setCatalog);
  const retryResumen = retry(setResumen);
  const retryComparativa = retry(setComparativa);
  const selectProduct = (id) => {
    setSelectedId(id);
    setComparativa((current) => ({ ...current, loading: true, error: null }));
  };
  const enci = comparativa.data?.productoEncipharm;
  const rows = comparativa.data?.equivalentes || [];

  return (
    <main className="page competencia-content">
      <Block
        title="Comparación de precios"
        subtitle="Precio por unidad de medida de un producto Encipharm frente a sus equivalentes. Solo cuentan los precios aprobados."
        loading={catalog.loading}
        error={catalog.error}
        onRetry={retryCatalog}
        updatedAt={comparativa.updatedAt}
      >
        {catalog.items.length === 0 ? (
          <p>
            Aún no hay productos Encipharm en el catálogo.{" "}
            {canReview ? "Agrégalos más abajo, en «Catálogo y equivalencias»." : "Pide a un supervisor que cargue el catálogo."}
          </p>
        ) : (
          <>
            <div className="comp-selectors">
              <label className="comp-selector-group">
                <span className="comp-selector-label">Producto Encipharm</span>
                <select className="comp-selector" value={selectedId} onChange={(event) => selectProduct(event.target.value)}>
                  {catalog.items.map((item) => <option key={item.id} value={item.id}>{item.nombre}</option>)}
                </select>
              </label>
            </div>
            {comparing ? (
              <p role="status">Cargando comparativa…</p>
            ) : comparativa.error ? (
              <div role="alert" className="comp-error">{comparativa.error} <button type="button" onClick={retryComparativa}>Reintentar</button></div>
            ) : (
              <div className="comp-table-wrap">
                <table className="comp-table">
                  <thead>
                    <tr>
                      <th>Empresa</th><th>Producto</th><th className="text-center">Precio / unidad</th>
                      <th className="text-center">Precio del dato</th><th className="text-center">Diferencia de Encipharm</th>
                    </tr>
                  </thead>
                  <tbody>
                    {enci && (
                      <tr>
                        <td><strong>Encipharm</strong></td>
                        <td>{enci.nombre}</td>
                        <td className="text-center">{perUnit(enci.precioPorUnidad, enci.unidadMedida)}</td>
                        <td className="text-center">precio de lista</td>
                        <td className="text-center">—</td>
                      </tr>
                    )}
                    {rows.length === 0 && (
                      <tr><td colSpan="5" className="text-center">Este producto aún no tiene equivalentes registrados.</td></tr>
                    )}
                    {rows.map((row) => (
                      <tr key={row.productoCompetenciaId}>
                        <td>{row.competidor}</td>
                        <td>{row.nombre}{row.presentacion ? ` · ${row.presentacion}` : ""}</td>
                        <td className="text-center">{perUnit(row.precioPorUnidad, enci?.unidadMedida)}</td>
                        <td className="text-center">{row.fechaPrecio ? `${row.fechaPrecio}${row.fuente ? ` · ${row.fuente}` : ""}` : "Sin precio aprobado"}</td>
                        <td className="text-center competition-diff" title={row.motivoSinDiferencia || ""}>
                          <span className={`comp-price ${diffClass(row.diferenciaPct)}`}>{formatDiff(row.diferenciaPct)}</span>
                          {row.motivoSinDiferencia && <small className="comp-reason"> {row.motivoSinDiferencia}</small>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <p className="competition-card-sub comp-note">Negativo: Encipharm es más barato. Positivo: Encipharm es más caro.</p>
              </div>
            )}
          </>
        )}
      </Block>

      <Block
        title="Comparación de composición"
        subtitle="Principios activos y concentración de cada producto equivalente."
        loading={catalog.loading || (Boolean(selectedId) && comparing)}
        error={comparativa.error}
        onRetry={retryComparativa}
        updatedAt={comparativa.updatedAt}
      >
        {!enci ? (
          <p>Selecciona un producto Encipharm para comparar su composición.</p>
        ) : (
          <div className="comp-composition-grid">
            {[{ id: "enci", empresa: "Encipharm", nombre: enci.nombre, principiosActivos: enci.principiosActivos, concentracion: enci.concentracion }, ...rows.map((row) => ({
              id: row.productoCompetenciaId, empresa: row.competidor, nombre: row.nombre,
              principiosActivos: row.principiosActivos, concentracion: row.concentracion, registroSag: row.registroSag,
            }))].map((item) => (
              <article className="comp-composition-card" key={item.id}>
                <div className="comp-composition-header"><strong>{item.empresa}</strong><span>{item.nombre}</span></div>
                <div className="comp-composition-list">
                  {item.principiosActivos.length === 0 && <span className="comp-ingredient-name">Sin principios activos registrados</span>}
                  {item.principiosActivos.map((name) => (
                    <div className="comp-ingredient" key={name}>
                      <span className="comp-ingredient-name">{name}</span>
                      <span className="comp-ingredient-value">{item.concentracion || "—"}</span>
                    </div>
                  ))}
                  {item.registroSag && <small>Registro SAG {item.registroSag}</small>}
                </div>
              </article>
            ))}
          </div>
        )}
      </Block>

      <Block
        title="Resumen por categoría y competidor"
        subtitle="Promedio del último precio aprobado de cada producto (por unidad de medida)."
        loading={resumen.loading}
        error={resumen.error}
        onRetry={retryResumen}
        updatedAt={resumen.updatedAt}
      >
        {resumen.data && (
          <>
            <h4>Por categoría</h4>
            <SummaryTable rows={resumen.data.porCategoria} label="Categoría" />
            <h4>Por competidor</h4>
            <SummaryTable rows={resumen.data.porCompetidor} label="Competidor" />
            {resumen.data.productosSinPrecio > 0 && (
              <p className="competition-card-sub">{resumen.data.productosSinPrecio} producto(s) aún sin precio aprobado.</p>
            )}
          </>
        )}
      </Block>

      <Block title="Reportar un precio" subtitle="Lo que ves en terreno alimenta esta comparación.">
        <ReportarPrecio onReported={refresh} />
      </Block>

      {canReview && (
        <>
          <Block title="Reportes pendientes de aprobación" subtitle="Solo los precios aprobados cuentan en las comparaciones.">
            <ReportesPendientes refreshKey={refreshKey} onReviewed={refresh} />
          </Block>
          <Block title="Catálogo y equivalencias" subtitle="Productos Encipharm y su equivalente en la competencia.">
            <CatalogoEquivalencias onChanged={refresh} />
          </Block>
        </>
      )}
    </main>
  );
}

export default AnalisisCompetencia;
