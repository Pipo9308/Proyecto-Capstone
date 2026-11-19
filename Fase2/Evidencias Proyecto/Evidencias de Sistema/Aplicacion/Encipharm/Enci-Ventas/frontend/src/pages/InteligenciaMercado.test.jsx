import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import InteligenciaMercado from "./InteligenciaMercado";
import * as api from "../services/api";

vi.mock("../auth/authContext", () => ({ useAuth: () => ({ idToken: "jwt" }) }));
vi.mock("../services/api", () => ({ askCompetenciaChat: vi.fn(), getAlertas: vi.fn() }));

const alerts = [
  { id: "a-1", title: "Zoetis lanza X", competitor: "Zoetis", type: "LAUNCH", priority: "high", created_at: "2026-10-01T10:00:00Z", description: "Detalle X" },
  { id: "a-2", title: "Registro SAG nuevo", competitor: "Agrovet", type: "REGULATORY", priority: "medium", created_at: "2026-10-02T10:00:00Z" },
];

describe("InteligenciaMercado", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getAlertas.mockResolvedValue({ data: alerts, total: 2 });
  });

  it("lista alertas reales con filtros por competidor y regulación", async () => {
    render(<InteligenciaMercado />);

    expect(await screen.findByText("Zoetis lanza X")).toBeInTheDocument();
    expect(screen.getByText(/Actualizado/)).toBeInTheDocument();
    expect(screen.queryByText("VetPharma")).not.toBeInTheDocument(); // sin competidores de ejemplo

    fireEvent.click(screen.getByRole("button", { name: "Agrovet" }));
    expect(screen.queryByText("Zoetis lanza X")).not.toBeInTheDocument();
    expect(screen.getByText("Registro SAG nuevo")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Regulación" }));
    expect(screen.getByText("Registro SAG nuevo")).toBeInTheDocument();
  });

  it("si no hay alertas para el filtro lo dice", async () => {
    api.getAlertas.mockResolvedValue({ data: [], total: 0 });
    render(<InteligenciaMercado />);

    expect(await screen.findByText("No hay alertas para este filtro.")).toBeInTheDocument();
  });

  it("si Intel falla muestra el error y permite reintentar", async () => {
    api.getAlertas.mockRejectedValueOnce({ details: { body: { error: "Enci-Intel no responde" } } });
    render(<InteligenciaMercado />);

    expect(await screen.findByText(/Enci-Intel no responde/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByText("Zoetis lanza X")).toBeInTheDocument();
  });

  it("el chat responde con fuentes y mantiene la conversación", async () => {
    api.askCompetenciaChat
      .mockResolvedValueOnce({ respuesta: "Zoetis lanzó X.", fuentes: [{ origen: "enci-intel", titulo: "Zoetis lanza X", fecha: "2026-10-01" }], conversacion_id: "conv-1" })
      .mockResolvedValueOnce({ respuesta: "Segunda respuesta.", fuentes: [] });
    render(<InteligenciaMercado />);
    await screen.findByText("Zoetis lanza X");

    fireEvent.change(screen.getByLabelText("Pregunta"), { target: { value: "¿Qué lanzó Zoetis?" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));

    expect(await screen.findByText("Zoetis lanzó X.")).toBeInTheDocument();
    expect(screen.getByText(/enci-intel · 2026-10-01/)).toBeInTheDocument();
    expect(api.askCompetenciaChat).toHaveBeenCalledWith("jwt", { pregunta: "¿Qué lanzó Zoetis?", conversacion_id: null });

    fireEvent.change(screen.getByLabelText("Pregunta"), { target: { value: "¿Y precios?" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));
    expect(await screen.findByText("Segunda respuesta.")).toBeInTheDocument();
    expect(api.askCompetenciaChat).toHaveBeenLastCalledWith("jwt", { pregunta: "¿Y precios?", conversacion_id: "conv-1" });
  });

  it("una pregunta de ejemplo se envía al hacer clic", async () => {
    api.askCompetenciaChat.mockResolvedValue({ respuesta: "ok", fuentes: [] });
    render(<InteligenciaMercado />);
    await screen.findByText("Zoetis lanza X");

    fireEvent.click(screen.getByRole("button", { name: /precios conocemos/ }));

    expect(await screen.findByText("ok")).toBeInTheDocument();
    expect(api.askCompetenciaChat.mock.calls[0][1].pregunta).toMatch(/precios/);
  });

  it("el error del chat (por ejemplo, tope diario) se muestra como alerta", async () => {
    api.askCompetenciaChat.mockRejectedValue({ details: { body: { error: "Llegaste al tope diario de preguntas" } } });
    render(<InteligenciaMercado />);
    await screen.findByText("Zoetis lanza X");

    fireEvent.change(screen.getByLabelText("Pregunta"), { target: { value: "hola" } });
    fireEvent.click(screen.getByRole("button", { name: "Enviar" }));

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText("Llegaste al tope diario de preguntas")).toBeInTheDocument();
  });
});
