import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth/authContext";
import { getNotificaciones, marcarNotificacionLeida, marcarTodasNotificaciones } from "../services/api";
import { badgeText, timeAgo } from "../utils/notificaciones";

// Cada cuanto se consultan los avisos: asi aparecen en menos de 60 s (RF-01.04).
export const POLL_MS = 30000;

const BELL_PATH = "M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9";

/** Campana de la barra superior: contador de no leidas y panel con la lista (RF-01.01). */
function NotificationBell() {
  const { idToken: token } = useAuth();
  const navigate = useNavigate();
  const [state, setState] = useState({ items: [], noLeidas: 0, error: false });
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const page = await getNotificaciones(token, { limit: 20 });
      setState({ items: page.items, noLeidas: page.noLeidas, error: false });
    } catch {
      // Sin red el contador queda como estaba; el panel avisa que no se pudo actualizar.
      setState((current) => ({ ...current, error: true }));
    }
  }, [token]);

  useEffect(() => {
    if (!token) return undefined;
    const first = setTimeout(load, 0);
    const timer = setInterval(load, POLL_MS);
    return () => {
      clearTimeout(first);
      clearInterval(timer);
    };
  }, [token, load]);

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (event) => !rootRef.current?.contains(event.target) && setOpen(false);
    const onKey = (event) => event.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function openItem(item) {
    setOpen(false);
    if (!item.leida) {
      setState((current) => ({
        ...current,
        noLeidas: Math.max(current.noLeidas - 1, 0),
        items: current.items.map((n) => (n.id === item.id ? { ...n, leida: true } : n)),
      }));
      marcarNotificacionLeida(token, item.id).catch(load);
    }
    if (item.enlace) navigate(item.enlace);
  }

  async function markAll() {
    setState((current) => ({ ...current, noLeidas: 0, items: current.items.map((n) => ({ ...n, leida: true })) }));
    try {
      await marcarTodasNotificaciones(token);
    } catch {
      load();
    }
  }

  return (
    <div className="notification-bell" ref={rootRef}>
      <button
        className="header-icon-btn"
        type="button"
        aria-label={state.noLeidas ? `Notificaciones (${state.noLeidas} sin leer)` : "Notificaciones"}
        aria-expanded={open}
        onClick={() => {
          setOpen((value) => !value);
          if (!open) load();
        }}
      >
        {state.noLeidas > 0 && <span className="notification-count">{badgeText(state.noLeidas)}</span>}
        <svg aria-hidden="true" fill="none" height="20" viewBox="0 0 24 24" width="20">
          <path d={BELL_PATH} stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" />
        </svg>
      </button>

      {open && (
        <div className="notification-panel" role="dialog" aria-label="Notificaciones">
          <div className="notification-panel-header">
            <strong>Notificaciones</strong>
            <button type="button" onClick={markAll} disabled={state.noLeidas === 0}>Marcar todas como leídas</button>
          </div>
          {state.error && <p role="alert" className="comp-error notification-empty">No se pudo actualizar. Reintentando…</p>}
          {state.items.length === 0 && !state.error && <p className="notification-empty">No tienes notificaciones.</p>}
          <ul>
            {state.items.map((item) => (
              <li key={item.id}>
                <button type="button" className={item.leida ? "notification-item" : "notification-item unread"} onClick={() => openItem(item)}>
                  <strong>{item.titulo}</strong>
                  {item.mensaje && <span>{item.mensaje}</span>}
                  <small>{timeAgo(item.createdAt)}</small>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

export default NotificationBell;
