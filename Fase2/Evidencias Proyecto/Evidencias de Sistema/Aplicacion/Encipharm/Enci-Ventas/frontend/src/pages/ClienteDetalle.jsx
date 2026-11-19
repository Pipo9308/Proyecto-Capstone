import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useAuth } from "../auth/authContext";
import LoadingState from "../components/LoadingState";
import useCachedQuery, { invalidateCachedQuery } from "../hooks/useCachedQuery";
import PhoneInput from "../components/PhoneInput";
import { regionesChile } from "../data/regionesChile";
import { deleteCliente, getCliente, getInteracciones, getOportunidades, getPropuestas, updateCliente } from "../services/api";
import VendedorSelect from "../components/VendedorSelect";
import { fieldErrorsFromApi } from "../utils/apiFieldErrors";
import { getFriendlyApiError } from "../utils/apiErrors";
import { rutError } from "../utils/rut";
import {
  CLIENTE_ESTADOS,
  clienteInitialForm,
  validateClienteForm,
} from "../utils/clienteForm";

function ClienteDetalle() {
  const { clienteId } = useParams();
  const { idToken } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState(clienteInitialForm);
  const [fieldErrors, setFieldErrors] = useState({});
  const [historial, setHistorial] = useState({
    interacciones: [],
    oportunidades: [],
    propuestas: [],
  });
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const clienteQuery = useCachedQuery(
    `cliente-detalle:${clienteId}`,
    async () => {
      const [cliente, interacciones, oportunidades, propuestas] = await Promise.all([
        getCliente(idToken, clienteId),
        getInteracciones(idToken, { clienteId }),
        getOportunidades(idToken, { clienteId }),
        getPropuestas(idToken, { clienteId }),
      ]);
      return { cliente, interacciones, oportunidades, propuestas };
    },
    { enabled: Boolean(idToken && clienteId), initialData: null },
  );
  const loading = clienteQuery.loading;

  useEffect(() => {
    if (!clienteQuery.data) return;
    const { cliente, interacciones, oportunidades, propuestas } = clienteQuery.data;
    queueMicrotask(() => {
      setForm({
        nombre: cliente.nombre || "",
        empresa: cliente.empresa || "",
        rut: cliente.rut || "",
        vendedorUid: cliente.vendedorUid || "",
        email: cliente.email || "",
        telefono: cliente.telefono || "",
        rubro: cliente.rubro || "",
        region: cliente.region || "",
        estado: cliente.estado || "En proceso",
      });
      setHistorial({ interacciones, oportunidades, propuestas });
    });
  }, [clienteQuery.data]);

  const handleChange = (event) => {
    setForm({
      ...form,
      [event.target.name]: event.target.value,
    });
  };

  // Un cliente anterior sin RUT puede seguir editandose sin completarlo; si ya tiene uno, es obligatorio.
  const requireRut = Boolean(clienteQuery.data?.cliente?.rut);

  const handleRutBlur = () => {
    if (form.rut.trim()) setFieldErrors((current) => ({ ...current, rut: rutError(form.rut) || undefined }));
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
    setSuccess("");

    const validation = validateClienteForm(form, { requireRut });
    setFieldErrors(validation.errors);
    if (!validation.isValid) {
      setError("Corrige los campos marcados antes de guardar.");
      return;
    }

    try {
      setSaving(true);
      const updated = await updateCliente(idToken, clienteId, validation.payload);
      invalidateCachedQuery("clientes:");
      invalidateCachedQuery(`cliente-detalle:${clienteId}`);
      setSuccess(`Cliente ${updated.empresa} actualizado correctamente.`);
    } catch (saveError) {
      const apiFieldErrors = fieldErrorsFromApi(saveError);
      if (Object.keys(apiFieldErrors).length > 0) {
        setFieldErrors(apiFieldErrors);
        setError("Corrige los campos marcados antes de guardar.");
      } else {
        setError(getFriendlyApiError(saveError));
      }
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    const confirmed = window.confirm("Eliminar este cliente del CRM?");
    if (!confirmed) return;

    try {
      setDeleting(true);
      await deleteCliente(idToken, clienteId);
      navigate("/clientes", {
        replace: true,
        state: { notice: "Cliente eliminado correctamente." },
      });
    } catch (deleteError) {
      setError(getFriendlyApiError(deleteError));
      setDeleting(false);
    }
  };

  const disabled = loading || saving || deleting;

  return (
    <main className="page">
      <section className="header header-row">
        <div>
          <h1>Detalle de Cliente</h1>
          <p>Consulta y actualizacion de datos base del CRM</p>
        </div>

        <div className="header-actions">
          <Link to={`/calendario?clienteId=${encodeURIComponent(clienteId)}`}>
            <button className="btn-secondary" type="button">
              Agendar visita
            </button>
          </Link>
          <Link to="/clientes">
            <button className="btn-secondary" type="button">
              Volver
            </button>
          </Link>
        </div>
      </section>

      {loading && <LoadingState />}
      {error && (
        <section className="notice notice-error" role="alert">
          <strong>Operacion no completada</strong>
          <span>{error}</span>
        </section>
      )}
      {success && (
        <section className="notice notice-success" role="status">
          <strong>Cliente actualizado</strong>
          <span>{success}</span>
        </section>
      )}

      {!loading && <form className="form form-card" onSubmit={handleSubmit}>
        <label>
          Nombre del contacto *
          <input name="nombre" maxLength={120} value={form.nombre} onChange={handleChange} disabled={disabled} />
          {fieldErrors.nombre && <small className="field-error">{fieldErrors.nombre}</small>}
        </label>

        <label>
          Empresa *
          <input name="empresa" maxLength={160} value={form.empresa} onChange={handleChange} disabled={disabled} />
          {fieldErrors.empresa && <small className="field-error">{fieldErrors.empresa}</small>}
        </label>

        <label>
          {requireRut ? "RUT *" : "RUT"}
          <input name="rut" placeholder="12.345.678-5" maxLength={16} value={form.rut} onChange={handleChange} onBlur={handleRutBlur} disabled={disabled} />
          {fieldErrors.rut && <small className="field-error">{fieldErrors.rut}</small>}
        </label>

        <label>
          Email (opcional)
          <input name="email" type="email" value={form.email} onChange={handleChange} disabled={disabled} />
          {fieldErrors.email && <small className="field-error">{fieldErrors.email}</small>}
        </label>

        <label>
          Telefono (opcional)
          <PhoneInput
            disabled={disabled}
            error={fieldErrors.telefono}
            value={form.telefono}
            onChange={handleChange}
          />
        </label>

        <label>
          Rubro / industria *
          <input name="rubro" maxLength={120} value={form.rubro} onChange={handleChange} disabled={disabled} />
          {fieldErrors.rubro && <small className="field-error">{fieldErrors.rubro}</small>}
        </label>

        <label>
          Region (opcional)
          <select name="region" value={form.region} onChange={handleChange} disabled={disabled}>
            <option value="">Selecciona una region</option>
            {regionesChile.map((region) => (
              <option key={region} value={region}>
                {region}
              </option>
            ))}
          </select>
          {fieldErrors.region && <small className="field-error">{fieldErrors.region}</small>}
        </label>

        <VendedorSelect value={form.vendedorUid} onChange={handleChange} disabled={disabled} />

        <label>
          Estado
          <select name="estado" value={form.estado} onChange={handleChange} disabled={disabled}>
            {CLIENTE_ESTADOS.map((estado) => (
              <option key={estado} value={estado}>
                {estado}
              </option>
            ))}
          </select>
        </label>

        <div className="form-actions">
          <button className="btn-danger" type="button" onClick={handleDelete} disabled={disabled}>
            {deleting ? "Eliminando..." : "Eliminar"}
          </button>
          <button type="submit" disabled={disabled}>
            {saving ? "Guardando..." : "Guardar cambios"}
          </button>
        </div>
      </form>}

      {!loading && <section className="detail-grid">
        <article className="detail-panel">
          <h2>Oportunidades</h2>
          {historial.oportunidades.length === 0 && <p className="muted-text">Sin oportunidades registradas.</p>}
          {historial.oportunidades.map((oportunidad) => (
            <div className="timeline-item" key={oportunidad.id}>
              <Link to={`/oportunidades/${oportunidad.id}`}><strong>{oportunidad.titulo}</strong></Link>
              <span>{oportunidad.etapa} / ${Number(oportunidad.valorEstimado || 0).toLocaleString()}</span>
            </div>
          ))}
        </article>

        <article className="detail-panel">
          <h2>Propuestas</h2>
          {historial.propuestas.length === 0 && <p className="muted-text">Sin propuestas registradas.</p>}
          {historial.propuestas.map((propuesta) => (
            <div className="timeline-item" key={propuesta.id}>
              <strong>{propuesta.titulo}</strong>
              <span>{propuesta.estado} / ${Number(propuesta.montoTotal || 0).toLocaleString()}</span>
            </div>
          ))}
        </article>
      </section>}

      {!loading && <section className="detail-panel">
        <h2>Interacciones</h2>
        {historial.interacciones.length === 0 && <p className="muted-text">Sin interacciones registradas.</p>}
        <div className="timeline-list">
          {historial.interacciones.map((interaccion) => (
            <article className="timeline-item" key={interaccion.id}>
              <strong>{interaccion.tipo}</strong>
              <span>{new Date(interaccion.fecha).toLocaleString()}</span>
              <p>{interaccion.resumen}</p>
            </article>
          ))}
        </div>
      </section>}
    </main>
  );
}

export default ClienteDetalle;
