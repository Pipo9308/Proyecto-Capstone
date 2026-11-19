import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import NotificationBell, { POLL_MS } from "./NotificationBell";
import * as api from "../services/api";
import { badgeText, timeAgo } from "../utils/notificaciones";

const navigate = vi.fn();
vi.mock("react-router-dom", () => ({ useNavigate: () => navigate }));
vi.mock("../auth/authContext", () => ({ useAuth: () => ({ idToken: "jwt" }) }));
vi.mock("../services/api", () => ({
  getNotificaciones: vi.fn(),
  marcarNotificacionLeida: vi.fn(),
  marcarTodasNotificaciones: vi.fn(),
}));

const item = (over = {}) => ({
  id: "n-1", tipo: "alerta_intel", titulo: "Cancelación SAG: X", mensaje: "ZOETIS · Prioridad crítica",
  enlace: "/inteligencia", leida: false, createdAt: new Date().toISOString(), ...over,
});

describe("NotificationBell", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getNotificaciones.mockResolvedValue({ items: [item(), item({ id: "n-2", titulo: "Leída", leida: true, enlace: null })], total: 2, noLeidas: 1 });
    api.marcarNotificacionLeida.mockResolvedValue(null);
    api.marcarTodasNotificaciones.mockResolvedValue({ marcadas: 1 });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("muestra el numero de no leidas en la campana", async () => {
    render(<NotificationBell />);

    expect(await screen.findByRole("button", { name: "Notificaciones (1 sin leer)" })).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
  });

  it("consulta cada 30 segundos, asi un aviso nuevo aparece en menos de 60 s", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    render(<NotificationBell />);
    await waitFor(() => expect(api.getNotificaciones).toHaveBeenCalledTimes(1));

    api.getNotificaciones.mockResolvedValue({ items: [item()], total: 1, noLeidas: 5 });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(POLL_MS + 100);
    });

    expect(await screen.findByRole("button", { name: "Notificaciones (5 sin leer)" })).toBeInTheDocument();
  });

  it("al abrir lista los avisos; el que lleva a otra pagina se marca leido y navega", async () => {
    render(<NotificationBell />);
    fireEvent.click(await screen.findByRole("button", { name: /Notificaciones/ }));

    fireEvent.click(await screen.findByText("Cancelación SAG: X"));

    expect(api.marcarNotificacionLeida).toHaveBeenCalledWith("jwt", "n-1");
    expect(navigate).toHaveBeenCalledWith("/inteligencia");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Notificaciones" })).toBeInTheDocument(); // contador en 0
  });

  it("un aviso ya leido no vuelve a marcarse", async () => {
    render(<NotificationBell />);
    fireEvent.click(await screen.findByRole("button", { name: /Notificaciones/ }));

    fireEvent.click(await screen.findByText("Leída"));

    expect(api.marcarNotificacionLeida).not.toHaveBeenCalled();
    expect(navigate).not.toHaveBeenCalled();
  });

  it("marcar todas deja el contador en cero", async () => {
    render(<NotificationBell />);
    fireEvent.click(await screen.findByRole("button", { name: /Notificaciones/ }));

    fireEvent.click(await screen.findByRole("button", { name: "Marcar todas como leídas" }));

    await waitFor(() => expect(api.marcarTodasNotificaciones).toHaveBeenCalledWith("jwt"));
    expect(screen.getByRole("button", { name: "Notificaciones" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Marcar todas como leídas" })).toBeDisabled();
  });

  it("sin avisos lo dice, y Escape cierra el panel", async () => {
    api.getNotificaciones.mockResolvedValue({ items: [], total: 0, noLeidas: 0 });
    render(<NotificationBell />);
    fireEvent.click(await screen.findByRole("button", { name: "Notificaciones" }));

    expect(await screen.findByText("No tienes notificaciones.")).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "Escape" });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("si la consulta falla conserva el contador y avisa dentro del panel", async () => {
    render(<NotificationBell />);
    await screen.findByRole("button", { name: "Notificaciones (1 sin leer)" });
    api.getNotificaciones.mockRejectedValue(new Error("sin red"));

    fireEvent.click(screen.getByRole("button", { name: /Notificaciones/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo actualizar");
    expect(screen.getByRole("button", { name: "Notificaciones (1 sin leer)" })).toBeInTheDocument();
  });
});

describe("utils/notificaciones", () => {
  const now = new Date("2026-10-12T12:00:00Z");

  it("tiempo relativo", () => {
    expect(timeAgo("2026-10-12T11:59:40Z", now)).toBe("ahora");
    expect(timeAgo("2026-10-12T11:30:00Z", now)).toBe("hace 30 min");
    expect(timeAgo("2026-10-12T07:00:00Z", now)).toBe("hace 5 h");
    expect(timeAgo("2026-10-09T12:00:00Z", now)).toBe("hace 3 d");
    expect(timeAgo(null, now)).toBe("");
  });

  it("el contador no pasa de 99+", () => {
    expect([badgeText(3), badgeText(99), badgeText(100)]).toEqual(["3", "99", "99+"]);
  });
});
