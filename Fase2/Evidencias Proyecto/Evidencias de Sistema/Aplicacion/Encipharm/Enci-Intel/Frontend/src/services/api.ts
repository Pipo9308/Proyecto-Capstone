import axios from "axios";
import { handleSessionExpired, shouldExpireSession } from "./session";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

export const api = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    "Content-Type": "application/json",
  },
});

// Inyecta el token JWT en cada request si el usuario está autenticado
api.interceptors.request.use((config) => {
  const token = localStorage.getItem("enci_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Cierra sesión automáticamente si el token es inválido o expiró
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (shouldExpireSession(error.response?.status, error.config?.url)) {
      handleSessionExpired();
    }
    return Promise.reject(error);
  }
);

// ==========================================
// 📊 DASHBOARD
// ==========================================
export async function getDashboardSummary() {
  const response = await api.get("/dashboard/summary");
  return response.data;
}

// ==========================================
// 🚨 ALERTS
// ==========================================
// La API pagina (max 200 por pedido): se piden todas las paginas para no dejar alertas fuera.
export async function getAlerts() {
  const data: unknown[] = [];
  let page;
  do {
    page = (await api.get("/alerts/", { params: { limit: 200, offset: data.length } })).data;
    data.push(...page.data);
  } while (page.has_more && page.data.length);
  return { ...page, data };
}

// ==========================================
// 👥 AGENTS
// ==========================================
export async function getAgents() {
  const response = await api.get("/agents/");
  return response.data;
}

// ==========================================
// 📦 PRODUCTS
// ==========================================
export async function getProducts() {
  const response = await api.get("/products/");
  return response.data;
}

// ==========================================
// 📈 MARKET
// ==========================================
export async function getMarketShare() {
  const response = await api.get("/market/share");
  return response.data;
}

export async function getImportTrends() {
  const response = await api.get("/market/import-trends");
  return response.data;
}

export async function getPositioningMatrix() {
  const response = await api.get("/market/positioning-matrix");
  return response.data;
}

// ==========================================
// 💬 CHAT
// ==========================================
export async function sendChatQuestion(question: string, species: string) {
  const response = await api.post("/chat/query", { question, species });
  return response.data;
}

export function getChatStreamUrl(): string {
  return `${API_BASE_URL}/chat/stream`;
}

export async function getDocsCount() {
  const response = await api.get("/chat/docs-count");
  return response.data;
}

export async function getChatStats() {
  const response = await api.get("/chat/docs-count");
  return response.data;
}

export async function getAuthToken(): Promise<string | null> {
  return localStorage.getItem("enci_token");
}

export async function getProductRecommendations(question: string, species?: string) {
  const response = await api.post("/products/recommendations", { question, species });
  return response.data;
}

export async function triggerAgent(agentId: string) {
  const response = await api.post(`/agents/${agentId}/run`);
  return response.data;
}

// ==========================================
// 📄 ADMIN — DOCUMENTOS RAG
// ==========================================
export async function getAdminDocuments() {
  const response = await api.get("/admin/documents/");
  return response.data;
}

export async function uploadDocument(file: File, title: string, category: string) {
  const form = new FormData();
  form.append("file", file);
  form.append("title", title);
  form.append("category", category);
  const response = await api.post("/admin/documents/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return response.data;
}

export async function deleteDocument(filename: string) {
  const response = await api.delete(`/admin/documents/${encodeURIComponent(filename)}`);
  return response.data;
}


// ==========================================
// MODELO DE IA (solo admin)
// ==========================================
type LlmForm = {
  proveedor: "" | "anthropic"; base_url: string; model: string; competencia_model: string;
  competidores_model: string; sag_model: string; api_key: string;
  agentes_proveedor: "" | "anthropic"; anthropic_api_key: string;
};

export type RagAjustes = {
  instrucciones: string; temperatura: number; max_tokens: number; documentos: number; umbral: number;
};

export async function getLlmSettings() {
  const response = await api.get("/admin/llm/");
  return response.data.data;
}

export async function saveLlmSettings(form: LlmForm) {
  const response = await api.put("/admin/llm/", form);
  return response.data.data;
}

export async function testLlmSettings(form: LlmForm) {
  const response = await api.post("/admin/llm/test", form);
  return response.data.data as { ok: boolean; ms?: number; detail?: string };
}

// Conecta con Anthropic (key vacía = la guardada) y trae los modelos disponibles.
export async function listAnthropicModels(api_key: string) {
  const response = await api.post("/admin/llm/anthropic/modelos", { api_key });
  return response.data.data as { ok: boolean; modelos?: { id: string; nombre: string }[]; detail?: string };
}

export async function getRagSettings() {
  const response = await api.get("/admin/llm/rag");
  return response.data.data as { vigente: RagAjustes; por_defecto: RagAjustes; reglas: string; source: string };
}

export async function saveRagSettings(ajustes: RagAjustes) {
  const response = await api.put("/admin/llm/rag", ajustes);
  return response.data.data as { vigente: RagAjustes; por_defecto: RagAjustes; reglas: string; source: string };
}
