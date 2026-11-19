import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth/authContext";
import { hasMinimumRole } from "../auth/roles";
import EventoForm from "../components/calendario/EventoForm";
import { getEventos, getUsers, updateEvento } from "../services/api";
import { parseUtc } from "../utils/alertas";
import { apiMessage } from "../utils/apiErrors";
import {
  dayKey, ESTADO_LABEL, eventsByDay, formatTime, moveToDay, rangeFor, startOfDay, stepAnchor, TIPO_LABEL, titleFor, VIEWS,
} from "../utils/calendario";

const WEEKDAYS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"];
const MAX_CHIPS = 3;

function EventChip({ event, onOpen, compact }) {
  const draggable = event.estado === "planificada";
  return (
    <button
      type="button"
      className={`cal-chip ${event.estado}`}
      draggable={draggable}
      onDragStart={(dragEvent) => dragEvent.dataTransfer.setData("text/plain", event.id)}
      onClick={() => onOpen(event)}
      title={`${event.clienteNombre} · ${TIPO_LABEL[event.tipo]}`}
    >
      <b>{formatTime(event.inicio)}</b> {event.clienteNombre}
      {!compact && event.lugar ? <small> · {event.lugar}</small> : null}
    </button>
  );
}

function Calendario() {
  const { backendUser, idToken: token } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const isSupervisor = hasMinimumRole(backendUser?.rol, "supervisor");
  const [view, setView] = useState("mes");
  const [anchor, setAnchor] = useState(() => new Date());
  const [vendedor, setVendedor] = useState("");
  const [users, setUsers] = useState([]);
  const [state, setState] = useState({ events: [], loading: true, error: null });
  const [reload, setReload] = useState(0);
  const [form, setForm] = useState(() => (params.get("clienteId") ? { event: null, clienteId: params.get("clienteId") } : null));
  const [selected, setSelected] = useState(null);
  const [notice, setNotice] = useState(null);

  const { days, desde, hasta } = useMemo(() => rangeFor(view, anchor), [view, anchor]);
  const byDay = useMemo(() => eventsByDay(state.events), [state.events]);

  useEffect(() => {
    if (!isSupervisor) return undefined;
    let cancelled = false;
    getUsers(token, { activo: true, limit: 500 })
      .then((list) => !cancelled && setUsers(list.filter((u) => u.rol !== "sin_acceso")))
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [isSupervisor, token]);

  useEffect(() => {
    let cancelled = false;
    getEventos(token, { desde: desde.toISOString(), hasta: hasta.toISOString(), vendedorUid: vendedor || undefined })
      .then((events) => !cancelled && setState({ events, loading: false, error: null }))
      .catch((err) => !cancelled && setState({ events: [], loading: false, error: apiMessage(err) }));
    return () => {
      cancelled = true;
    };
  }, [token, desde, hasta, vendedor, reload]);

  const refresh = () => setReload((n) => n + 1);
  const go = (next) => {
    setState((current) => ({ ...current, loading: true }));
    next();
  };

  async function change(event, changes, success) {
    setNotice(null);
    try {
      await updateEvento(token, event.id, changes);
      setSelected(null);
      setNotice({ ok: true, text: success });
      refresh();
    } catch (err) {
      setNotice({ ok: false, text: apiMessage(err) });
    }
  }

  function drop(dropEvent, day) {
    dropEvent.preventDefault();
    const event = state.events.find((e) => e.id === dropEvent.dataTransfer.getData("text/plain"));
    if (event && dayKey(day) !== dayKey(parseUtc(event.inicio))) {
      change(event, moveToDay(event, day), "Evento movido.");
    }
  }

  const today = dayKey(new Date());

  return (
    <main className="page calendario-content">
      <section className="competencia-section">
        <article className="card command-card">
          <div className="card-header">
            <div>
              <h3 className="cal-title">{titleFor(view, anchor)}</h3>
              <p className="competition-card-sub">Visitas, reuniones y llamadas con clientes.</p>
            </div>
            <div className="cal-toolbar">
              <button type="button" onClick={() => go(() => setAnchor(stepAnchor(view, anchor, -1)))} aria-label="Anterior">‹</button>
              <button type="button" onClick={() => go(() => setAnchor(new Date()))}>Hoy</button>
              <button type="button" onClick={() => go(() => setAnchor(stepAnchor(view, anchor, 1)))} aria-label="Siguiente">›</button>
              {Object.entries(VIEWS).map(([key, label]) => (
                <button type="button" key={key} className={view === key ? "active" : ""} aria-pressed={view === key} onClick={() => go(() => setView(key))}>
                  {label}
                </button>
              ))}
              {isSupervisor && (
                <select aria-label="Filtrar por vendedor" value={vendedor} onChange={(e) => go(() => setVendedor(e.target.value))}>
                  <option value="">Todo el equipo</option>
                  {users.map((u) => <option key={u.uid} value={u.uid}>{u.nombre || u.email}</option>)}
                </select>
              )}
              <button type="button" className="btn-primary" onClick={() => setForm({ event: null })}>Nuevo evento</button>
            </div>
          </div>

          <div className="card-body competition-card-body">
            {notice && <p role={notice.ok ? "status" : "alert"} className={notice.ok ? "comp-ok" : "comp-error"}>{notice.text}</p>}
            {state.error && (
              <p role="alert" className="comp-error">{state.error} <button type="button" onClick={() => go(refresh)}>Reintentar</button></p>
            )}
            {state.loading && <p role="status">Cargando…</p>}
            {!state.loading && !state.error && state.events.length === 0 && <p>No hay eventos en este período.</p>}

            <div className={`cal-grid ${view}`}>
              {view !== "dia" && WEEKDAYS.map((name) => <div className="cal-weekday" key={name}>{name}</div>)}
              {days.map((day) => {
                const events = byDay.get(dayKey(day)) || [];
                const outside = view === "mes" && day.getMonth() !== anchor.getMonth();
                return (
                  <div
                    key={dayKey(day)}
                    className={`cal-day${outside ? " outside" : ""}${dayKey(day) === today ? " today" : ""}`}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={(e) => drop(e, startOfDay(day))}
                    aria-label={day.toLocaleDateString("es-CL", { weekday: "long", day: "numeric", month: "long" })}
                  >
                    <button type="button" className="cal-daynum" onClick={() => go(() => { setAnchor(day); setView("dia"); })}>
                      {day.getDate()}
                    </button>
                    {(view === "mes" ? events.slice(0, MAX_CHIPS) : events).map((event) => (
                      <EventChip key={event.id} event={event} onOpen={setSelected} compact={view === "mes"} />
                    ))}
                    {view === "mes" && events.length > MAX_CHIPS && (
                      <button type="button" className="cal-more" onClick={() => go(() => { setAnchor(day); setView("dia"); })}>
                        +{events.length - MAX_CHIPS} más
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </article>
      </section>

      {selected && (
        <div className="opportunity-modal-backdrop" onMouseDown={(e) => e.target === e.currentTarget && setSelected(null)}>
          <section className="opportunity-modal" role="dialog" aria-modal="true" aria-label="Detalle del evento">
            <button className="opportunity-modal-close" type="button" onClick={() => setSelected(null)} aria-label="Cerrar">×</button>
            <header className="opportunity-modal-header">
              <h2>{selected.clienteNombre}</h2>
              <p>{TIPO_LABEL[selected.tipo]} · {ESTADO_LABEL[selected.estado]}</p>
            </header>
            <div className="opportunity-modal-body">
              <p>{formatTime(selected.inicio)} – {formatTime(selected.fin)}{selected.lugar ? ` · ${selected.lugar}` : ""}</p>
              {isSupervisor && <p>Vendedor: {selected.vendedorNombre}</p>}
              {selected.notas && <p>{selected.notas}</p>}
              <div className="comp-form-actions">
                <button type="button" onClick={() => { setForm({ event: selected }); setSelected(null); }}>Editar</button>
                {selected.estado === "planificada" && (
                  <>
                    <button type="button" className="btn-primary" onClick={() => change(selected, { estado: "realizada" }, "Visita registrada en el historial del cliente.")}>
                      Marcar como realizada
                    </button>
                    <button type="button" onClick={() => change(selected, { estado: "cancelada" }, "Evento cancelado.")}>Cancelar evento</button>
                  </>
                )}
                <button type="button" onClick={() => navigate(`/clientes/${selected.clienteId}`)}>Ver cliente</button>
              </div>
            </div>
          </section>
        </div>
      )}

      {form && (
        <EventoForm
          event={form.event}
          defaults={{ start: new Date(new Date().setMinutes(0, 0, 0) + 60 * 60 * 1000), clienteId: form.clienteId }}
          onClose={() => setForm(null)}
          onSaved={() => {
            setForm(null);
            setNotice({ ok: true, text: "Evento guardado." });
            refresh();
          }}
        />
      )}
    </main>
  );
}

export default Calendario;
