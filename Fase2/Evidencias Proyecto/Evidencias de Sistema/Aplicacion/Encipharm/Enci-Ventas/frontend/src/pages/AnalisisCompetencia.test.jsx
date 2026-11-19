import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import AnalisisCompetencia from "./AnalisisCompetencia";
import * as api from "../services/api";

let currentRole = "vendedor";
vi.mock("../auth/authContext", () => ({
  useAuth: () => ({ idToken: "jwt", backendUser: { rol: currentRole, nombre: "Ana" } }),
}));
vi.mock("../services/api", () => ({
  createCatalogoProducto: vi.fn(),
  createCompetenciaProducto: vi.fn(),
  getCompetenciaCatalogo: vi.fn(),
  getCompetenciaComparativa: vi.fn(),
  getCompetenciaProductos: vi.fn(),
  getCompetenciaResumen: vi.fn(),
  getPreciosCompetencia: vi.fn(),
  reportarPrecioCompetencia: vi.fn(),
  revisarPrecioCompetencia: vi.fn(),
  setCompetenciaEquivalentes: vi.fn(),
}));

const enci = {
  id: "e-1", nombre: "Ivermax 1%", principiosActivos: ["ivermectina"], concentracion: "1%", unidadMedida: "ml",
  cantidadPresentacion: 500, precioLista: 40000, precioPorUnidad: 80, moneda: "CLP",
};
const comparativa = {
  productoEncipharm: enci,
  equivalentes: [
    {
      productoCompetenciaId: "c-1", competidor: "Zoetis", nombre: "Ivomec 1%", presentacion: "Frasco 500 ml",
      principiosActivos: ["ivermectina"], concentracion: "1%", registroSag: "1001", precioPorUnidad: 100, moneda: "CLP",
      fechaPrecio: "2026-10-01", fuente: "Cotizacion", diferenciaPct: -20, motivoSinDiferencia: null,
    },
    {
      productoCompetenciaId: "c-2", competidor: "Agrovet", nombre: "Sin precio", presentacion: null, principiosActivos: [],
      concentracion: null, registroSag: null, precioPorUnidad: null, moneda: null, fechaPrecio: null, fuente: null,
      diferenciaPct: null, motivoSinDiferencia: "Sin precio aprobado de la competencia",
    },
  ],
};
const resumen = {
  porCategoria: [{ clave: "Antiparasitario", unidadMedida: "ml", moneda: "CLP", productos: 1, precioPromedioPorUnidad: 100, diferenciaPromedioPct: -20 }],
  porCompetidor: [{ clave: "Zoetis", unidadMedida: "ml", moneda: "CLP", productos: 1, precioPromedioPorUnidad: 100, diferenciaPromedioPct: -20 }],
  productosSinPrecio: 1,
};

describe("AnalisisCompetencia", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    currentRole = "vendedor";
    api.getCompetenciaCatalogo.mockResolvedValue([enci]);
    api.getCompetenciaComparativa.mockResolvedValue(comparativa);
    api.getCompetenciaResumen.mockResolvedValue(resumen);
    api.getCompetenciaProductos.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 100 });
    api.getPreciosCompetencia.mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 50 });
  });

  it("compara el precio por unidad de Encipharm contra cada equivalente", async () => {
    render(<AnalisisCompetencia />);

    expect(await screen.findByText("Ivomec 1% · Frasco 500 ml")).toBeInTheDocument();
    const row = screen.getByText("Ivomec 1% · Frasco 500 ml").closest("tr");
    expect(within(row).getByText("$100 / ml")).toBeInTheDocument();
    expect(within(row).getByText("-20%")).toHaveClass("mejor");
    expect(api.getCompetenciaComparativa).toHaveBeenCalledWith("jwt", "e-1");
  });

  it("un equivalente sin precio explica por que no hay diferencia", async () => {
    render(<AnalisisCompetencia />);

    const row = (await screen.findAllByText("Sin precio"))[0].closest("tr");
    expect(within(row).getByText("Sin precio aprobado")).toBeInTheDocument();
    expect(within(row).getByText("Sin precio aprobado de la competencia")).toBeInTheDocument();
  });

  it("muestra la composicion de Encipharm y de cada equivalente", async () => {
    render(<AnalisisCompetencia />);

    expect(await screen.findByText("Registro SAG 1001")).toBeInTheDocument();
    expect(screen.getByText("Sin principios activos registrados")).toBeInTheDocument();
  });

  it("sin catalogo lo dice, sin inventar datos de ejemplo", async () => {
    api.getCompetenciaCatalogo.mockResolvedValue([]);
    render(<AnalisisCompetencia />);

    expect(await screen.findByText(/Aún no hay productos Encipharm en el catálogo/)).toBeInTheDocument();
    expect(screen.queryByText(/Oxitetraciclina/)).not.toBeInTheDocument();
  });

  it("si el resumen falla muestra el error y permite reintentar", async () => {
    api.getCompetenciaResumen.mockRejectedValueOnce({ details: { body: { error: "Base no disponible" } } });
    render(<AnalisisCompetencia />);

    expect(await screen.findByText(/Base no disponible/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByText("Antiparasitario")).toBeInTheDocument();
  });

  it("el vendedor no ve la cola de aprobacion ni la gestion del catalogo", async () => {
    render(<AnalisisCompetencia />);
    await screen.findByText("Ivomec 1% · Frasco 500 ml");

    expect(screen.queryByText("Reportes pendientes de aprobación")).not.toBeInTheDocument();
    expect(api.getPreciosCompetencia).not.toHaveBeenCalled();
  });

  it("el supervisor aprueba un reporte y las comparaciones se recargan", async () => {
    currentRole = "supervisor";
    api.getPreciosCompetencia
      .mockResolvedValueOnce({
        items: [{ id: "p-1", competidor: "Zoetis", productoNombre: "Ivomec 1%", precio: 50000, moneda: "CLP", precioPorUnidad: 100, unidadMedida: "ml", fuente: "Visita", fechaPrecio: "2026-10-01", reportadoPorNombre: "Ana" }],
        total: 1, page: 1, pageSize: 50,
      })
      .mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 50 });
    api.revisarPrecioCompetencia.mockResolvedValue({});
    render(<AnalisisCompetencia />);
    await screen.findByText("Zoetis · Ivomec 1%");
    const before = api.getCompetenciaComparativa.mock.calls.length;

    fireEvent.click(screen.getByRole("button", { name: "Aprobar" }));

    await waitFor(() => expect(api.revisarPrecioCompetencia).toHaveBeenCalledWith("jwt", "p-1", true));
    expect(await screen.findByText("No hay reportes pendientes.")).toBeInTheDocument();
    await waitFor(() => expect(api.getCompetenciaComparativa.mock.calls.length).toBeGreaterThan(before));
  });

  it("el vendedor reporta un precio de un producto nuevo y queda pendiente", async () => {
    api.createCompetenciaProducto.mockResolvedValue({ id: "c-9", competidor: "Biogénesis", nombre: "Nuevo", presentacion: null });
    api.reportarPrecioCompetencia.mockResolvedValue({});
    render(<AnalisisCompetencia />);
    await screen.findByText("Ivomec 1% · Frasco 500 ml");
    const form = screen.getByRole("form", { name: "Reportar precio" });

    fireEvent.change(within(form).getByLabelText("Producto de la competencia"), { target: { value: "__nuevo__" } });
    fireEvent.change(within(form).getByLabelText("Competidor"), { target: { value: "Biogénesis" } });
    fireEvent.change(within(form).getByLabelText("Nombre comercial"), { target: { value: "Nuevo" } });
    fireEvent.change(within(form).getByLabelText("Cantidad por envase"), { target: { value: "100" } });
    fireEvent.change(within(form).getByLabelText("Principios activos (separados por coma)"), { target: { value: "a, b" } });
    fireEvent.change(within(form).getByLabelText("Precio (CLP)"), { target: { value: "9990" } });
    fireEvent.click(within(form).getByRole("button", { name: "Reportar precio" }));

    expect(await screen.findByText(/pendiente de aprobación/)).toBeInTheDocument();
    expect(api.createCompetenciaProducto).toHaveBeenCalledWith("jwt", expect.objectContaining({
      competidor: "Biogénesis", cantidadPresentacion: 100, principiosActivos: ["a", "b"],
    }));
    expect(api.reportarPrecioCompetencia).toHaveBeenCalledWith("jwt", "c-9", expect.objectContaining({ precio: 9990 }));
  });

  it("muestra el motivo del backend si el reporte falla", async () => {
    api.getCompetenciaProductos.mockResolvedValue({
      items: [{ id: "c-1", competidor: "Zoetis", nombre: "Ivomec", presentacion: null }], total: 1, page: 1, pageSize: 100,
    });
    api.reportarPrecioCompetencia.mockRejectedValue({ details: { body: { error: "Producto no encontrado" } } });
    render(<AnalisisCompetencia />);
    await screen.findByText("Ivomec 1% · Frasco 500 ml");
    const form = screen.getByRole("form", { name: "Reportar precio" });
    await within(form).findByRole("option", { name: "Zoetis · Ivomec" });

    fireEvent.change(within(form).getByLabelText("Producto de la competencia"), { target: { value: "c-1" } });
    fireEvent.change(within(form).getByLabelText("Precio (CLP)"), { target: { value: "100" } });
    fireEvent.click(within(form).getByRole("button", { name: "Reportar precio" }));

    expect(await within(form).findByRole("alert")).toHaveTextContent("Producto no encontrado");
  });
});
