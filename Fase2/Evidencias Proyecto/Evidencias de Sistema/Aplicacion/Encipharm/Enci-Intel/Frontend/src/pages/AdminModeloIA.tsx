import { useEffect, useState } from "react";
import {
  getLlmSettings, getRagSettings, listAnthropicModels, saveLlmSettings, saveRagSettings, testLlmSettings,
  type RagAjustes,
} from "../services/api";

type Proveedor = "" | "anthropic";
type Ajustes = {
  proveedor: Proveedor; base_url: string; model: string; competencia_model: string;
  competidores_model: string; sag_model: string; api_key: string;
  agentes_proveedor: Proveedor; anthropic_api_key: string;
};
type Vigente = { source: string; api_key_set: boolean; api_key_hint: string; anthropic_key_set: boolean; anthropic_key_hint: string };
type Modelo = { id: string; nombre: string };
type Rag = { vigente: RagAjustes; por_defecto: RagAjustes; reglas: string; source: string };

const ANTHROPIC = "Anthropic (Claude)";

const PROVEEDORES = [
  { nombre: "Gemini (Google)", base_url: "https://generativelanguage.googleapis.com/v1beta/openai", model: "gemini-2.5-flash" },
  { nombre: "NVIDIA NIM", base_url: "https://integrate.api.nvidia.com/v1", model: "meta/llama-3.2-11b-vision-instruct" },
  { nombre: "DeepSeek", base_url: "https://api.deepseek.com", model: "deepseek-chat" },
  { nombre: "OpenAI", base_url: "https://api.openai.com/v1", model: "gpt-4o-mini" },
];

const MODELOS_SUGERIDOS = [
  "gemini-2.5-flash", "gemini-2.5-pro", "deepseek-chat", "gpt-4o-mini", "meta/llama-3.2-11b-vision-instruct",
];

const AGENTES = [["competidores_model", "Agente Competidores"], ["sag_model", "Agente SAG"]] as const;
type CampoModelo = "model" | "competencia_model" | (typeof AGENTES)[number][0];

const errorDe = (e: unknown) => (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "No se pudo completar la acción.";

function AdminModeloIA() {
  const [form, setForm] = useState<Ajustes>({
    proveedor: "", base_url: "", model: "", competencia_model: "", competidores_model: "", sag_model: "", api_key: "",
    agentes_proveedor: "", anthropic_api_key: "",
  });
  const [vigente, setVigente] = useState<Vigente | null>(null);
  const [modelos, setModelos] = useState<Modelo[]>([]);
  const [rag, setRag] = useState<Rag | null>(null);
  const [ragForm, setRagForm] = useState<RagAjustes | null>(null);
  const [mensaje, setMensaje] = useState("");
  const [ocupado, setOcupado] = useState(false);

  const aplicar = (d: Ajustes & Vigente) => {
    setForm({
      proveedor: d.proveedor, base_url: d.base_url, model: d.model, competencia_model: d.competencia_model,
      competidores_model: d.competidores_model, sag_model: d.sag_model, api_key: "",
      agentes_proveedor: d.agentes_proveedor, anthropic_api_key: "",
    });
    setVigente({
      source: d.source, api_key_set: d.api_key_set, api_key_hint: d.api_key_hint,
      anthropic_key_set: d.anthropic_key_set, anthropic_key_hint: d.anthropic_key_hint,
    });
  };

  const aplicarRag = (d: Rag) => {
    setRag(d);
    setRagForm(d.vigente);
  };

  // Conecta con Anthropic usando la key escrita (o la guardada) y trae sus modelos.
  const conectar = async (key: string, silencioso = false) => {
    setOcupado(true);
    if (!silencioso) setMensaje("Conectando con Anthropic...");
    try {
      const r = await listAnthropicModels(key);
      setModelos(r.modelos ?? []);
      if (!silencioso || !r.ok) {
        setMensaje(r.ok ? `Conectado: ${r.modelos?.length ?? 0} modelos disponibles.` : `Anthropic no respondió: ${r.detail}`);
      }
    } catch (e) {
      setMensaje(errorDe(e));
    } finally {
      setOcupado(false);
    }
  };

  useEffect(() => {
    getLlmSettings()
      .then((d) => {
        aplicar(d);
        if ((d.proveedor === "anthropic" || d.agentes_proveedor === "anthropic") && d.anthropic_key_set) conectar("", true);
      })
      .catch((e) => setMensaje(errorDe(e)));
    getRagSettings().then(aplicarRag).catch((e) => setMensaje(errorDe(e)));
  }, []);

  const cambiar = (campo: keyof Ajustes, valor: string) => setForm((f) => ({ ...f, [campo]: valor }));

  // Los nombres de modelo no sirven entre proveedores: al cambiar de proveedor se vacían los que dependen de él.
  const elegirProveedor = (nombre: string) => {
    if (nombre === ANTHROPIC) {
      setForm((f) => ({
        ...f, proveedor: "anthropic", model: "", competencia_model: "",
        ...(f.agentes_proveedor === "" ? { competidores_model: "", sag_model: "" } : {}),
        agentes_proveedor: "",  // con Claude arriba, "el mismo de arriba" ya es Claude
      }));
      if (!modelos.length && vigente?.anthropic_key_set) conectar("", true);
      return;
    }
    const p = PROVEEDORES.find((x) => x.nombre === nombre);
    if (!p) return;
    setForm((f) => ({
      ...f, proveedor: "", base_url: p.base_url, model: p.model,
      ...(f.proveedor === "anthropic" ? { competencia_model: "" } : {}),
      ...(f.proveedor === "anthropic" && f.agentes_proveedor === "" ? { competidores_model: "", sag_model: "" } : {}),
    }));
  };

  const cambiarProveedorAgentes = (valor: Proveedor) => {
    setForm((f) => ({ ...f, agentes_proveedor: valor, competidores_model: "", sag_model: "" }));
    if (valor === "anthropic" && !modelos.length && vigente?.anthropic_key_set) conectar("", true);
  };

  // Prueba un modelo con el proveedor y la key del formulario (vacio = el modelo general).
  const probar = async (modelo?: string, conClaude?: boolean) => {
    const probado = modelo || form.model;
    setOcupado(true);
    setMensaje(`Probando ${probado}...`);
    try {
      const r = await testLlmSettings({ ...form, model: probado, ...(conClaude ? { proveedor: "anthropic" as const } : {}) });
      setMensaje(r.ok ? `${probado} respondió correctamente (${r.ms} ms).` : `${probado} no respondió: ${r.detail}`);
    } catch (e) {
      setMensaje(errorDe(e));
    } finally {
      setOcupado(false);
    }
  };

  const guardar = async () => {
    setOcupado(true);
    try {
      aplicar(await saveLlmSettings(form));
      setMensaje("Guardado. Los chats usan el nuevo modelo desde ahora (el asistente de Ventas puede tardar hasta 1 minuto).");
    } catch (e) {
      setMensaje(errorDe(e));
    } finally {
      setOcupado(false);
    }
  };

  const guardarRag = async () => {
    if (!ragForm) return;
    setOcupado(true);
    try {
      aplicarRag(await saveRagSettings(ragForm));
      setMensaje("Comportamiento del Consultor Vet guardado. Se aplica desde la próxima pregunta.");
    } catch (e) {
      setMensaje(errorDe(e));
    } finally {
      setOcupado(false);
    }
  };

  const cambiarRag = (campo: keyof RagAjustes, valor: string) =>
    setRagForm((r) => (r ? { ...r, [campo]: campo === "instrucciones" ? valor : Number(valor) } : r));

  const generalClaude = form.proveedor === "anthropic";
  const agentesClaude = generalClaude || form.agentes_proveedor === "anthropic";
  const tieneClave = Boolean(form.anthropic_api_key.trim() || vigente?.anthropic_key_set);
  const anthropicListo = !agentesClaude || tieneClave;
  const completo = generalClaude ? form.model.trim() : form.base_url.trim() && form.model.trim();

  // Con la lista de Anthropic cargada, el modelo se elige de ella; sin conectar, se escribe a mano.
  const campoModelo = (campo: CampoModelo, vacio: string | null) =>
    modelos.length > 0 ? (
      <select value={form[campo]} onChange={(e) => cambiar(campo, e.target.value)}>
        <option value="" disabled={vacio === null}>{vacio ?? "Elige un modelo..."}</option>
        {form[campo] && !modelos.some((m) => m.id === form[campo]) && <option value={form[campo]}>{form[campo]}</option>}
        {modelos.map((m) => <option key={m.id} value={m.id}>{m.nombre} ({m.id})</option>)}
      </select>
    ) : (
      <input value={form[campo]} placeholder="Conecta para elegir de la lista" onChange={(e) => cambiar(campo, e.target.value)} />
    );

  const claveAnthropic = (
    <div className="llm-fila">
      <label>
        API key de Anthropic {vigente?.anthropic_key_set ? `(configurada, termina en ${vigente.anthropic_key_hint || "····"})` : "(sin configurar)"}
        <input
          type="password"
          autoComplete="new-password"
          placeholder={vigente?.anthropic_key_set ? "Déjala vacía para conservar la actual" : "sk-ant-..."}
          value={form.anthropic_api_key}
          onChange={(e) => cambiar("anthropic_api_key", e.target.value)}
        />
      </label>
      <button className="btn-light" disabled={ocupado || !tieneClave} onClick={() => conectar(form.anthropic_api_key.trim())}>
        Conectar
      </button>
    </div>
  );

  return (
    <section className="admin-users-page">
      <div className="admin-users-header">
        <div>
          <h1>Modelo de IA</h1>
          <p>Proveedor, modelo y API key del Consultor Vet, el asistente de Ventas, el chat de competencia y los agentes.</p>
        </div>
        <span className="admin-users-badge">Solo Administrador</span>
      </div>

      {mensaje && <div className="admin-users-message" role="status">{mensaje}</div>}

      <div className="admin-users-card llm-form">
        <label>
          Proveedor predefinido
          <select value={generalClaude ? ANTHROPIC : ""} onChange={(e) => elegirProveedor(e.target.value)}>
            <option value="">{generalClaude ? "Cambiar a un proveedor compatible con OpenAI..." : "Elegir para rellenar la URL y el modelo..."}</option>
            {PROVEEDORES.map((p) => <option key={p.nombre}>{p.nombre}</option>)}
            <option>{ANTHROPIC}</option>
          </select>
        </label>

        {generalClaude ? (
          <>
            {claveAnthropic}
            <label>
              Modelo (Consultor Vet y asistente de Ventas)
              {campoModelo("model", null)}
            </label>
            <label>
              Modelo del chat de competencia (opcional)
              {campoModelo("competencia_model", "El mismo de arriba")}
            </label>
          </>
        ) : (
          <>
            <label>
              URL del proveedor (compatible con OpenAI)
              <input value={form.base_url} onChange={(e) => cambiar("base_url", e.target.value)} />
            </label>
            <label>
              Modelo
              <input value={form.model} onChange={(e) => cambiar("model", e.target.value)} />
            </label>
            <label>
              Modelo del chat de competencia (opcional; si está vacío usa el de arriba)
              <input value={form.competencia_model} onChange={(e) => cambiar("competencia_model", e.target.value)} />
            </label>
            <label>
              API key {vigente?.api_key_set ? `(configurada, termina en ${vigente.api_key_hint || "····"})` : "(sin configurar)"}
              <input
                type="password"
                autoComplete="new-password"
                placeholder="Déjala vacía para conservar la actual"
                value={form.api_key}
                onChange={(e) => cambiar("api_key", e.target.value)}
              />
            </label>
          </>
        )}

        <fieldset className="llm-agentes">
          <legend>Agentes (Competidores y SAG)</legend>
          <label>
            Proveedor de los agentes
            <select value={form.agentes_proveedor} onChange={(e) => cambiarProveedorAgentes(e.target.value as Proveedor)}>
              <option value="">El mismo de arriba</option>
              {(!generalClaude || form.agentes_proveedor === "anthropic") && <option value="anthropic">{ANTHROPIC}</option>}
            </select>
          </label>
          {agentesClaude && !generalClaude && claveAnthropic}
          {AGENTES.map(([campo, nombre]) => (
            <div key={campo} className="llm-fila">
              <label>
                {nombre} {agentesClaude ? "" : "(opcional; vacío = usa el modelo de arriba)"}
                {agentesClaude ? (
                  campoModelo(campo, generalClaude ? "El modelo de arriba" : "Claude Opus 5.5 (por defecto)")
                ) : (
                  <input list="llm-modelos" value={form[campo]} onChange={(e) => cambiar(campo, e.target.value)} />
                )}
              </label>
              <button
                className="btn-light"
                disabled={ocupado || !form[campo].trim() || (agentesClaude ? !tieneClave : !completo)}
                onClick={() => probar(form[campo].trim(), agentesClaude)}
              >
                Probar
              </button>
            </div>
          ))}
          <datalist id="llm-modelos">
            {MODELOS_SUGERIDOS.map((m) => <option key={m} value={m} />)}
          </datalist>
          {form.agentes_proveedor === "anthropic" && !generalClaude && (
            <p className="llm-note">Solo los agentes usan Anthropic; los chats siguen con el proveedor de arriba.</p>
          )}
        </fieldset>

        <p className="llm-note">
          Origen actual: {vigente?.source === "guardado" ? "guardado en esta pantalla" : "variables de entorno del servidor"}.
          Los embeddings del Consultor Vet no cambian (siguen con la key del servidor): cambiarlos invalidaría los documentos ya indexados.
        </p>
        <div className="llm-actions">
          <button className="btn-light" disabled={ocupado || !completo || !anthropicListo} onClick={() => probar()}>Probar</button>
          <button className="btn-main" disabled={ocupado || !completo || !anthropicListo} onClick={guardar}>Guardar</button>
        </div>
      </div>

      {rag && ragForm && (
        <div className="admin-users-card llm-form">
          <h2>Comportamiento del Consultor Vet (RAG)</h2>
          <p className="llm-note">
            Origen: {rag.source === "guardado" ? "guardado en esta pantalla" : "valores por defecto"}.
          </p>
          <label>
            Instrucciones del asistente
            <textarea rows={12} value={ragForm.instrucciones} onChange={(e) => cambiarRag("instrucciones", e.target.value)} />
          </label>
          <div className="llm-numeros">
            <label>
              Temperatura (0 a 1)
              <input type="number" min={0} max={1} step={0.05} value={ragForm.temperatura} onChange={(e) => cambiarRag("temperatura", e.target.value)} />
            </label>
            <label>
              Largo máximo (tokens)
              <input type="number" min={256} max={4096} step={64} value={ragForm.max_tokens} onChange={(e) => cambiarRag("max_tokens", e.target.value)} />
            </label>
            <label>
              Documentos por respuesta
              <input type="number" min={1} max={10} value={ragForm.documentos} onChange={(e) => cambiarRag("documentos", e.target.value)} />
            </label>
            <label>
              Similitud mínima (0 a 0,95)
              <input type="number" min={0} max={0.95} step={0.05} value={ragForm.umbral} onChange={(e) => cambiarRag("umbral", e.target.value)} />
            </label>
          </div>
          <details>
            <summary className="llm-note">Reglas fijas que siempre se agregan (no se pueden editar)</summary>
            <p className="llm-reglas">{rag.reglas}</p>
          </details>
          <p className="llm-note">
            Temperatura baja = respuestas más precisas y repetibles. Similitud mínima alta = usa solo documentos muy parecidos a la pregunta.
            {generalClaude && " Con Claude, la temperatura y el largo máximo no se aplican: el largo de la respuesta se controla desde las instrucciones."}
          </p>
          <div className="llm-actions">
            <button className="btn-light" disabled={ocupado} onClick={() => setRagForm(rag.por_defecto)}>Valores por defecto</button>
            <button className="btn-main" disabled={ocupado || ragForm.instrucciones.trim().length < 20} onClick={guardarRag}>Guardar comportamiento</button>
          </div>
        </div>
      )}
    </section>
  );
}

export default AdminModeloIA;
