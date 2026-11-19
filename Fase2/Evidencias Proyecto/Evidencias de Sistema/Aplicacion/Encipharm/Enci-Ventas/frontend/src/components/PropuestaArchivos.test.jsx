import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PropuestaArchivos from "./PropuestaArchivos";
import * as api from "../services/api";

vi.mock("../auth/authContext", () => ({ useAuth: () => ({ idToken: "jwt-token" }) }));
vi.mock("../services/api", () => ({
  buildApiUrl: (path) => `http://api.test${path}`,
  deletePropuestaArchivo: vi.fn(),
  getPropuestaArchivoLink: vi.fn(),
  getPropuestaArchivos: vi.fn(),
  uploadPropuestaArchivo: vi.fn(),
}));

const existing = { id: "a-1", nombre: "oferta.pdf", tamanoBytes: 2048, subidoPorNombre: "Ana", createdAt: "2026-10-01T10:00:00" };
const pdf = (name = "nuevo.pdf", size = 1000) => {
  const file = new File(["%PDF"], name, { type: "application/pdf" });
  Object.defineProperty(file, "size", { value: size });
  return file;
};

async function openPanel() {
  render(<PropuestaArchivos propuestaId="p-1" />);
  fireEvent.click(screen.getByRole("button", { name: /archivos/i }));
  await waitFor(() => expect(api.getPropuestaArchivos).toHaveBeenCalled());
}

describe("PropuestaArchivos", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getPropuestaArchivos.mockResolvedValue([existing]);
  });

  it("al abrir lista los archivos con tamano y autor", async () => {
    await openPanel();

    expect(await screen.findByText("oferta.pdf")).toBeInTheDocument();
    expect(screen.getByText(/2 KB · Ana/)).toBeInTheDocument();
    expect(api.getPropuestaArchivos).toHaveBeenCalledWith("jwt-token", "p-1");
  });

  it("sin archivos lo dice", async () => {
    api.getPropuestaArchivos.mockResolvedValue([]);
    await openPanel();

    expect(await screen.findByText("Sin archivos adjuntos.")).toBeInTheDocument();
  });

  it("sube un PDF mostrando el avance y el archivo aparece sin recargar", async () => {
    let finish;
    api.uploadPropuestaArchivo.mockImplementation((token, id, file, onProgress) => {
      onProgress(40);
      return new Promise((resolve) => {
        finish = () => resolve({ id: "a-2", nombre: file.name, tamanoBytes: 1000, subidoPorNombre: "Ana" });
      });
    });
    await openPanel();
    await screen.findByText("oferta.pdf");

    fireEvent.change(screen.getByLabelText(/adjuntar pdf/i), { target: { files: [pdf("nuevo.pdf")] } });

    expect(await screen.findByText(/Subiendo... 40%/)).toBeInTheDocument();
    expect(screen.getByLabelText("Progreso de subida")).toHaveValue(40);
    finish();
    expect(await screen.findByText("nuevo.pdf")).toBeInTheDocument();
    expect(screen.queryByText(/Subiendo/)).not.toBeInTheDocument();
  });

  it("rechaza en el navegador lo que no es PDF o pasa los 20 MB, sin llamar al servidor", async () => {
    await openPanel();
    await screen.findByText("oferta.pdf");
    const input = screen.getByLabelText(/adjuntar pdf/i);

    fireEvent.change(input, { target: { files: [pdf("hoja.xlsx")] } });
    expect(await screen.findByText("Solo se permiten archivos PDF.")).toBeInTheDocument();

    fireEvent.change(input, { target: { files: [pdf("grande.pdf", 21 * 1024 * 1024)] } });
    expect(await screen.findByText(/supera el maximo de 20 MB/)).toBeInTheDocument();
    expect(api.uploadPropuestaArchivo).not.toHaveBeenCalled();
  });

  it("muestra el motivo que da el backend cuando la subida falla", async () => {
    api.uploadPropuestaArchivo.mockRejectedValue({ details: { body: { error: "Una propuesta admite hasta 10 archivos" } } });
    await openPanel();
    await screen.findByText("oferta.pdf");

    fireEvent.change(screen.getByLabelText(/adjuntar pdf/i), { target: { files: [pdf()] } });

    expect(await screen.findByText("Una propuesta admite hasta 10 archivos")).toBeInTheDocument();
  });

  it("descargar pide un enlace firmado y navega a el", async () => {
    api.getPropuestaArchivoLink.mockResolvedValue({ url: "/propuestas/archivos/descarga?token=abc" });
    const assign = vi.fn();
    vi.stubGlobal("location", { ...window.location, assign });
    await openPanel();
    await screen.findByText("oferta.pdf");

    fireEvent.click(screen.getByRole("button", { name: "Descargar" }));

    await waitFor(() => expect(assign).toHaveBeenCalledWith("http://api.test/propuestas/archivos/descarga?token=abc"));
    expect(api.getPropuestaArchivoLink).toHaveBeenCalledWith("jwt-token", "p-1", "a-1");
    vi.unstubAllGlobals();
  });

  it("eliminar pide confirmacion y quita el archivo de la lista", async () => {
    api.deletePropuestaArchivo.mockResolvedValue(null);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    await openPanel();
    await screen.findByText("oferta.pdf");

    fireEvent.click(screen.getByRole("button", { name: "Eliminar" }));

    await waitFor(() => expect(screen.queryByText("oferta.pdf")).not.toBeInTheDocument());
    expect(api.deletePropuestaArchivo).toHaveBeenCalledWith("jwt-token", "p-1", "a-1");
  });

  it("si se cancela la confirmacion no se borra nada", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    await openPanel();
    await screen.findByText("oferta.pdf");

    fireEvent.click(screen.getByRole("button", { name: "Eliminar" }));

    expect(api.deletePropuestaArchivo).not.toHaveBeenCalled();
    expect(screen.getByText("oferta.pdf")).toBeInTheDocument();
  });
});
