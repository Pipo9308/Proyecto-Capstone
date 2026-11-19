import { useEffect, useState } from "react";
import { useAuth } from "../../auth/authContext";
import { hasMinimumRole } from "../../auth/roles";
import { createEvento, getClientes, getOportunidades, updateEvento } from "../../services/api";
import { apiMessage } from "../../utils/apiErrors";
import { fromLocalInput, TIPO_LABEL, toLocalInput } from "../../utils/calendario";
import { parseUtc } from "../../utils/alertas";
import ClienteSelect from "../ClienteSelect";
import VendedorSelect from "../VendedorSelect";

const MAX_HOURS = 12; // el backend rechaza duraciones mayores

function initialValues(event, defaults) {
  if (event) {
    return {
      clienteId: event.clienteId, oportunidadId: event.oportunidadId || "", tipo: event.tipo,
      inicio: toLocalInput(parseUtc(event.inicio)), fin: toLocalInput(parseUtc(event.fin)),
      lugar: event.lugar || "", notas: event.notas || "", vendedorUid: "",
    };
  }
  const start = defaults.start;
  return {
    clienteId: defaults.clienteId || "", oportunidadId: "", tipo: "presencial", inicio: toLocalInput(start),
    fin: toLocalInput(new Date(start.getTime() + 60 * 60 * 1000)), lugar: "", notas: "", vendedorUid: "",
  };
}

/** Crear o editar un evento del calendario. `event` null = crear. */
function EventoForm({ event, defaults, onClose, onSaved }) {
  const { backendUser, idToken: token } = useAuth();
  const [values, setValues] = useState(() => initialValues(event, defaults));
  const [clientes, setClientes] = useState([]);
  const [oportunidades, setOportunidades] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const canAssign = hasMinimumRole(backendUser?.rol, "supervisor");

  useEffect(() => {
    let cancelled = false;
    Promise.all([getClientes(token), getOportunidades(token)])
      .then(([clientesList, oportunidadesList]) => {
        if (cancelled) return;
        setClientes(clientesList);
        setOportunidades(oportunidadesList);
      })
      .catch((err) => !cancelled && setError(apiMessage(err)));
    return () => {
      cancelled = true;
    };
  }, [token]);

  useEffect(() => {
    const onKey = (keyEvent) => keyEvent.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const set = (key) => (changeEvent) => setValues((current) => ({ ...current, [key]: changeEvent.target.value }));
  // Al mover el inicio, el fin se desplaza igual (como en cualquier calendario): se conserva la duracion.
  const setStart = (changeEvent) => {
    const inicio = changeEvent.target.value;
    setValues((current) => {
      const duration = new Date(current.fin) - new Date(current.inicio);
      const moved = new Date(new Date(inicio).getTime() + duration);
      const valid = inicio && duration > 0 && !Number.isNaN(moved.getTime());
      return { ...current, inicio, fin: valid ? toLocalInput(moved) : current.fin };
    });
  };
  const opportunitiesOfClient = oportunidades.filter((o) => o.clienteId === values.clienteId);

  async function submit(submitEvent) {
    submitEvent.preventDefault();
    setError(null);
    const duration = new Date(values.fin) - new Date(values.inicio);
    if (!(duration > 0)) {
      setError("El fin debe ser posterior al inicio.");
      return;
    }
    if (duration > MAX_HOURS * 3600 * 1000) {
      setError(`Un evento no puede durar más de ${MAX_HOURS} horas. Ajusta el fin.`);
      return;
    }
    setBusy(true);
    try {
      const body = {
        tipo: values.tipo, inicio: fromLocalInput(values.inicio), fin: fromLocalInput(values.fin),
        lugar: values.lugar || null, notas: values.notas || null, oportunidadId: values.oportunidadId || null,
      };
      const saved = event
        ? await updateEvento(token, event.id, body)
        : await createEvento(token, { ...body, clienteId: values.clienteId, vendedorUid: values.vendedorUid || null });
      onSaved(saved);
    } catch (err) {
      setError(apiMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="opportunity-modal-backdrop" onMouseDown={(mouseEvent) => mouseEvent.target === mouseEvent.currentTarget && onClose()}>
      <section className="opportunity-modal cal-modal" role="dialog" aria-modal="true" aria-label={event ? "Editar evento" : "Nuevo evento"}>
        <button className="opportunity-modal-close" type="button" onClick={onClose} aria-label="Cerrar">×</button>
        <form className="comp-form" onSubmit={submit}>
          <h3>{event ? "Editar evento" : "Nuevo evento"}</h3>
          <label>
            Cliente
            <ClienteSelect clientes={clientes} value={values.clienteId} onChange={set("clienteId")} disabled={Boolean(event)} />
          </label>
          <label>
            Oportunidad (opcional)
            <select value={values.oportunidadId} onChange={set("oportunidadId")} disabled={!values.clienteId}>
              <option value="">Sin oportunidad</option>
              {opportunitiesOfClient.map((o) => <option key={o.id} value={o.id}>{o.titulo}</option>)}
            </select>
          </label>
          <div className="comp-form-grid">
            <label>
              Tipo
              <select value={values.tipo} onChange={set("tipo")}>
                {Object.entries(TIPO_LABEL).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
              </select>
            </label>
            <label>Inicio<input type="datetime-local" value={values.inicio} onChange={setStart} required /></label>
            <label>Fin<input type="datetime-local" value={values.fin} onChange={set("fin")} required /></label>
          </div>
          <label>Lugar<input value={values.lugar} onChange={set("lugar")} maxLength={200} /></label>
          <label>Notas<textarea value={values.notas} onChange={set("notas")} maxLength={2000} rows={3} /></label>
          {!event && canAssign && <VendedorSelect value={values.vendedorUid} onChange={set("vendedorUid")} disabled={busy} />}
          {error && <p role="alert" className="comp-error">{error}</p>}
          <div className="comp-form-actions">
            <button type="submit" className="btn-primary" disabled={busy || !values.clienteId}>{busy ? "Guardando…" : "Guardar"}</button>
            <button type="button" className="btn-secondary" onClick={onClose}>Cancelar</button>
          </div>
        </form>
      </section>
    </div>
  );
}

export default EventoForm;
