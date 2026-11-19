import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Calendario from "./Calendario";
import * as api from "../services/api";

let currentRole = "vendedor";
vi.mock("../auth/authContext", () => ({
  useAuth: () => ({ idToken: "jwt", backendUser: { rol: currentRole, nombre: "Ana" } }),
}));
vi.mock("../services/api", () => ({
  createEvento: vi.fn(),
  getClientes: vi.fn(),
  getEventos: vi.fn(),
  getOportunidades: vi.fn(),
  getUsers: vi.fn(),
  updateEvento: vi.fn(),
}));

const today = new Date();
const at = (day, hour) => new Date(today.getFullYear(), today.getMonth(), day, hour).toISOString();
const event = (over = {}) => ({
  id: "e-1", clienteId: "c-1", clienteNombre: "Avicola Pinos", vendedorUid: "u-1", vendedorNombre: "Ana",
  tipo: "presencial", inicio: at(10, 9), fin: at(10, 10), lugar: "Plantel norte", notas: null, estado: "planificada",
  interaccionId: null, oportunidadId: null, ...over,
});

function renderPage(url = "/calendario") {
  return render(<MemoryRouter initialEntries={[url]}><Calendario /></MemoryRouter>);
}

describe("Calendario", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    currentRole = "vendedor";
    api.getEventos.mockResolvedValue([event()]);
    api.getClientes.mockResolvedValue([{ id: "c-1", empresa: "Avicola Pinos" }]);
    api.getOportunidades.mockResolvedValue([{ id: "o-1", clienteId: "c-1", titulo: "Venta anual" }]);
    api.getUsers.mockResolvedValue([{ uid: "u-1", nombre: "Ana", rol: "vendedor" }, { uid: "u-2", nombre: "Beto", rol: "vendedor" }]);
    api.updateEvento.mockResolvedValue({});
  });

  it("muestra el mes con los eventos del usuario y pide el rango visible al backend", async () => {
    renderPage();

    expect(await screen.findByText(/Avicola Pinos/)).toBeInTheDocument();
    const params = api.getEventos.mock.calls[0][1];
    expect(new Date(params.hasta) - new Date(params.desde)).toBe(42 * 24 * 3600 * 1000);
    expect(params.vendedorUid).toBeUndefined();
    expect(screen.queryByLabelText("Filtrar por vendedor")).not.toBeInTheDocument(); // solo supervisor
  });

  it("sin eventos lo dice", async () => {
    api.getEventos.mockResolvedValue([]);
    renderPage();

    expect(await screen.findByText("No hay eventos en este período.")).toBeInTheDocument();
  });

  it("si falla la carga muestra el error y permite reintentar", async () => {
    api.getEventos.mockRejectedValueOnce({ details: { body: { error: "Base no disponible" } } });
    renderPage();

    expect(await screen.findByText(/Base no disponible/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByText(/Avicola Pinos/)).toBeInTheDocument();
  });

  it("el supervisor filtra por vendedor", async () => {
    currentRole = "supervisor";
    renderPage();
    await screen.findByText(/Avicola Pinos/);

    fireEvent.change(await screen.findByLabelText("Filtrar por vendedor"), { target: { value: "u-2" } });

    await waitFor(() => expect(api.getEventos.mock.calls.at(-1)[1].vendedorUid).toBe("u-2"));
  });

  it("cambiar a la vista de dia pide solo ese dia", async () => {
    renderPage();
    await screen.findByText(/Avicola Pinos/);

    fireEvent.click(screen.getByRole("button", { name: "Día" }));

    await waitFor(() => {
      const params = api.getEventos.mock.calls.at(-1)[1];
      expect(new Date(params.hasta) - new Date(params.desde)).toBe(24 * 3600 * 1000);
    });
  });

  it("arrastrar un evento a otro dia lo mueve conservando la hora", async () => {
    renderPage();
    const chip = (await screen.findByText(/Avicola Pinos/)).closest("button");
    const target = screen.getAllByLabelText(/\d+ de /).find((cell) => within(cell).queryByRole("button", { name: "20" }));
    const dataTransfer = { getData: () => "e-1", setData: vi.fn() };

    fireEvent.dragStart(chip, { dataTransfer });
    fireEvent.drop(target, { dataTransfer });

    await waitFor(() => expect(api.updateEvento).toHaveBeenCalledTimes(1));
    const [, id, changes] = api.updateEvento.mock.calls[0];
    expect(id).toBe("e-1");
    expect(new Date(changes.inicio)).toEqual(new Date(today.getFullYear(), today.getMonth(), 20, 9));
    expect(new Date(changes.fin)).toEqual(new Date(today.getFullYear(), today.getMonth(), 20, 10));
    expect(await screen.findByText("Evento movido.")).toBeInTheDocument();
  });

  it("un evento ya realizado no se puede arrastrar", async () => {
    api.getEventos.mockResolvedValue([event({ estado: "realizada" })]);
    renderPage();

    const chip = (await screen.findByText(/Avicola Pinos/)).closest("button");

    expect(chip).toHaveAttribute("draggable", "false");
  });

  it("marcar como realizada avisa que quedo en el historial del cliente", async () => {
    renderPage();
    fireEvent.click((await screen.findByText(/Avicola Pinos/)).closest("button"));

    fireEvent.click(await screen.findByRole("button", { name: "Marcar como realizada" }));

    await waitFor(() => expect(api.updateEvento).toHaveBeenCalledWith("jwt", "e-1", { estado: "realizada" }));
    expect(await screen.findByText(/historial del cliente/)).toBeInTheDocument();
  });

  it("si el backend rechaza el cambio muestra el motivo", async () => {
    api.updateEvento.mockRejectedValue({ details: { body: { error: "Un evento cancelada ya no se puede mover" } } });
    renderPage();
    fireEvent.click((await screen.findByText(/Avicola Pinos/)).closest("button"));

    fireEvent.click(await screen.findByRole("button", { name: "Cancelar evento" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("ya no se puede mover");
  });

  it("crear un evento envia la hora en UTC y refresca el calendario", async () => {
    api.createEvento.mockResolvedValue({});
    renderPage();
    await screen.findByText(/Avicola Pinos/);

    fireEvent.click(screen.getByRole("button", { name: "Nuevo evento" }));
    const dialog = await screen.findByRole("dialog", { name: "Nuevo evento" });
    await waitFor(() => expect(within(dialog).getByRole("option", { name: "Avicola Pinos" })).toBeInTheDocument());
    fireEvent.change(within(dialog).getByRole("combobox", { name: "Cliente" }), { target: { value: "c-1" } });
    fireEvent.change(within(dialog).getByLabelText("Inicio"), { target: { value: "2026-10-20T09:00" } });
    fireEvent.change(within(dialog).getByLabelText("Fin"), { target: { value: "2026-10-20T10:30" } });
    fireEvent.change(within(dialog).getByLabelText("Lugar"), { target: { value: "Oficina" } });
    const before = api.getEventos.mock.calls.length;
    fireEvent.click(within(dialog).getByRole("button", { name: "Guardar" }));

    await waitFor(() => expect(api.createEvento).toHaveBeenCalledTimes(1));
    const body = api.createEvento.mock.calls[0][1];
    expect(body).toMatchObject({ clienteId: "c-1", tipo: "presencial", lugar: "Oficina", oportunidadId: null });
    expect(new Date(body.inicio)).toEqual(new Date(2026, 9, 20, 9, 0));
    expect(new Date(body.fin)).toEqual(new Date(2026, 9, 20, 10, 30));
    await waitFor(() => expect(api.getEventos.mock.calls.length).toBeGreaterThan(before));
  });

  it("no deja guardar un fin anterior al inicio", async () => {
    renderPage();
    await screen.findByText(/Avicola Pinos/);
    fireEvent.click(screen.getByRole("button", { name: "Nuevo evento" }));
    const dialog = await screen.findByRole("dialog", { name: "Nuevo evento" });
    await waitFor(() => expect(within(dialog).getByRole("option", { name: "Avicola Pinos" })).toBeInTheDocument());
    fireEvent.change(within(dialog).getByRole("combobox", { name: "Cliente" }), { target: { value: "c-1" } });
    fireEvent.change(within(dialog).getByLabelText("Inicio"), { target: { value: "2026-10-20T10:00" } });
    fireEvent.change(within(dialog).getByLabelText("Fin"), { target: { value: "2026-10-20T09:00" } });

    fireEvent.click(within(dialog).getByRole("button", { name: "Guardar" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("El fin debe ser posterior al inicio");
    expect(api.createEvento).not.toHaveBeenCalled();
  });

  it("desde la ficha del cliente abre el formulario con el cliente elegido", async () => {
    renderPage("/calendario?clienteId=c-1");

    const dialog = await screen.findByRole("dialog", { name: "Nuevo evento" });
    await waitFor(() => expect(within(dialog).getByRole("combobox", { name: "Cliente" })).toHaveValue("c-1"));
  });

  async function openForm() {
    renderPage();
    await screen.findByText(/Avicola Pinos/);
    fireEvent.click(screen.getByRole("button", { name: "Nuevo evento" }));
    const dialog = await screen.findByRole("dialog", { name: "Nuevo evento" });
    await waitFor(() => expect(within(dialog).getByRole("option", { name: "Avicola Pinos" })).toBeInTheDocument());
    fireEvent.change(within(dialog).getByRole("combobox", { name: "Cliente" }), { target: { value: "c-1" } });
    return dialog;
  }

  it("al mover el inicio el fin se desplaza igual y conserva la duracion", async () => {
    const dialog = await openForm();
    fireEvent.change(within(dialog).getByLabelText("Inicio"), { target: { value: "2026-10-20T09:00" } });
    fireEvent.change(within(dialog).getByLabelText("Fin"), { target: { value: "2026-10-20T10:30" } });

    fireEvent.change(within(dialog).getByLabelText("Inicio"), { target: { value: "2026-10-21T15:00" } });

    expect(within(dialog).getByLabelText("Fin")).toHaveValue("2026-10-21T16:30");
  });

  it("un evento de mas de 12 horas se explica antes de enviar", async () => {
    const dialog = await openForm();
    fireEvent.change(within(dialog).getByLabelText("Inicio"), { target: { value: "2026-10-13T22:00" } });
    fireEvent.change(within(dialog).getByLabelText("Fin"), { target: { value: "2026-10-14T11:00" } });

    fireEvent.click(within(dialog).getByRole("button", { name: "Guardar" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("no puede durar más de 12 horas");
    expect(api.createEvento).not.toHaveBeenCalled();
  });

  it("si el backend rechaza por validacion se muestra el motivo, no el mensaje generico", async () => {
    api.createEvento.mockRejectedValue({
      details: { body: { error: "Datos de entrada invalidos", detalles: [{ loc: ["body"], msg: "Value error, El fin debe ser posterior al inicio" }] } },
    });
    const dialog = await openForm();

    fireEvent.click(within(dialog).getByRole("button", { name: "Guardar" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent("El fin debe ser posterior al inicio");
  });
});
