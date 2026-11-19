import { useCallback, useEffect, useState } from "react";
import { useAuth } from "../auth/authContext";
import { askCompetenciaChat, getAlertas } from "../services/api";
import { apiMessage } from "../utils/apiErrors";
import { buildAlertFilters, filterAlerts, formatAlertDate, priorityLabel } from "../utils/alertas";

const SAMPLE_QUESTIONS = [
  "¿Qué productos nuevos registró la competencia en el SAG este mes?",
  "¿Qué precios conocemos de los antiparasitarios de la competencia?",
  "¿Hubo cancelaciones de registros que nos favorezcan?",
];

const updatedLabel = (date) => `Actualizado ${date.toLocaleTimeString("es-CL", { hour: "2-digit", minute: "2-digit" })}`;

function InteligenciaMercado() {
  const { idToken: token } = useAuth();
  const [alerts, setAlerts] = useState({ items: [], loading: true, error: null, updatedAt: null });
  const [filter, setFilter] = useState("Todas");
  const [messages, setMessages] = useState([]);
  const [conversationId, setConversationId] = useState(null);
  const [input, setInput] = useState("");
  const [asking, setAsking] = useState(false);

  const loadAlerts = useCallback(async () => {
    setAlerts((current) => ({ ...current, loading: true, error: null }));
    try {
      const result = await getAlertas(token, { limit: 100 });
      setAlerts({ items: result.data || [], loading: false, error: null, updatedAt: new Date() });
    } catch (error) {
      setAlerts({ items: [], loading: false, error: apiMessage(error), updatedAt: null });
    }
  }, [token]);

  useEffect(() => {
    loadAlerts();
  }, [loadAlerts]);

  async function ask(question) {
    const text = question.trim();
    if (!text || asking) return;
    setMessages((prev) => [...prev, { role: "user", content: text }]);
    setInput("");
    setAsking(true);
    try {
      const res = await askCompetenciaChat(token, { pregunta: text, conversacion_id: conversationId });
      setConversationId(res.conversacion_id || conversationId);
      setMessages((prev) => [...prev, { role: "assistant", content: res.respuesta, sources: res.fuentes || [] }]);
    } catch (error) {
      setMessages((prev) => [...prev, { role: "assistant", content: apiMessage(error), failed: true }]);
    } finally {
      setAsking(false);
    }
  }

  const filters = buildAlertFilters(alerts.items);
  const visible = filterAlerts(alerts.items, filter);

  return (
    <main className="page inteligencia-content">
      <section className="chat-panel">
        <article className="card command-card">
          <div className="card-header">
            <div className="card-title"><span className="card-title-icon">IA</span>Asistente de Inteligencia</div>
          </div>

          <div className="static-chat-body" style={{ flexGrow: 1, overflowY: "auto", padding: "1rem" }}>
            <div className="static-ai-row">
              <span className="static-ai-avatar">IA</span>
              <div className="static-ai-message">
                <p>Hola. Respondo sobre competencia, registros SAG, alertas y precios reportados por el equipo. Si no tengo el dato, te lo digo.</p>
              </div>
            </div>
            {messages.length === 0 && (
              <div className="chat-samples">
                {SAMPLE_QUESTIONS.map((question) => (
                  <button type="button" key={question} onClick={() => ask(question)} disabled={asking}>{question}</button>
                ))}
              </div>
            )}

            {messages.map((msg, idx) => (
              <div key={idx} className={msg.role === "user" ? "user-message-row" : "static-ai-row"} style={msg.role === "user" ? { textAlign: "right", margin: "1rem 0" } : {}}>
                {msg.role === "assistant" && <span className="static-ai-avatar">IA</span>}
                <div
                  className={msg.role === "user" ? "user-message" : "static-ai-message"}
                  role={msg.failed ? "alert" : undefined}
                  style={msg.role === "user" ? { background: "var(--color-bg-alt)", padding: "0.75rem", borderRadius: "8px", display: "inline-block" } : {}}
                >
                  <p>{msg.content}</p>
                  {(msg.sources || []).map((source, i) => (
                    <div className="static-source-pill" key={i}>
                      {source.url ? <a href={source.url} target="_blank" rel="noopener noreferrer">{source.titulo || source.origen}</a> : (source.titulo || source.origen)}
                      {" · "}{source.origen}{source.fecha ? ` · ${source.fecha}` : ""}
                    </div>
                  ))}
                </div>
              </div>
            ))}
            {asking && <div role="status" style={{ padding: "1rem", color: "var(--color-text-muted)" }}>Pensando...</div>}
          </div>

          <form className="static-chat-input" onSubmit={(event) => { event.preventDefault(); ask(input); }}>
            <input
              type="text"
              aria-label="Pregunta"
              placeholder="Pregunta sobre la competencia, el SAG o precios..."
              value={input}
              maxLength={1000}
              onChange={(event) => setInput(event.target.value)}
              disabled={asking}
              style={{ flexGrow: 1, background: "transparent", border: "none", color: "inherit", outline: "none" }}
            />
            <button type="submit" aria-label="Enviar" disabled={!input.trim() || asking}>→</button>
          </form>
        </article>
      </section>

      <section className="news-panel">
        <article className="card command-card">
          <div className="card-header">
            <div className="card-title"><span className="card-title-icon">▣</span>Alertas de la competencia</div>
            {alerts.updatedAt && <small className="comp-updated">{updatedLabel(alerts.updatedAt)}</small>}
          </div>
          <div className="static-news-filters">
            {filters.map((name) => (
              <button
                type="button"
                className={filter === name ? "active" : ""}
                key={name}
                aria-pressed={filter === name}
                onClick={() => setFilter(name)}
              >
                {name}
              </button>
            ))}
          </div>
          <div className="static-news-feed">
            {alerts.loading ? (
              <p role="status" style={{ padding: "1rem" }}>Cargando alertas...</p>
            ) : alerts.error ? (
              <p role="alert" className="comp-error" style={{ padding: "1rem" }}>
                {alerts.error} <button type="button" onClick={loadAlerts}>Reintentar</button>
              </p>
            ) : visible.length === 0 ? (
              <p style={{ padding: "1rem" }}>No hay alertas para este filtro.</p>
            ) : (
              visible.map((item) => (
                <article className={`static-news-item ${["critical", "high"].includes(item.priority) ? "peor" : "similar"}`} key={item.id}>
                  <div className="static-news-content">
                    <div className="static-news-meta"><span>{item.competitor || "Sin competidor"}</span><small>{formatAlertDate(item.created_at)}</small></div>
                    <strong>{item.title}</strong>
                    {(item.description || item.body) && <p>{item.description || item.body}</p>}
                    <div className="static-news-tags"><span>{priorityLabel(item.priority)}</span></div>
                  </div>
                </article>
              ))
            )}
          </div>
        </article>
      </section>
    </main>
  );
}

export default InteligenciaMercado;
