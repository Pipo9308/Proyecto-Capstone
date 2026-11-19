import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import UploadDocuments from "./UploadDocuments";
import * as api from "../../services/api";

vi.mock("../../services/api", () => ({
  deleteRagDocument: vi.fn(),
  getRagDocuments: vi.fn(),
  reindexRagDocuments: vi.fn(),
  uploadRagDocument: vi.fn(),
}));

const doc = (overrides = {}) => ({
  id: "d-1", nombre: "manual.txt", estado: "listo", chunks_count: 3, tamano_bytes: 2048, error: null, ...overrides,
});

describe("UploadDocuments", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.getRagDocuments.mockResolvedValue([doc()]);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("lista los documentos con su estado y detalle", async () => {
    api.getRagDocuments.mockResolvedValue([
      doc(),
      doc({ id: "d-2", nombre: "roto.pdf", estado: "error", chunks_count: 0, error: "No se pudo extraer texto" }),
    ]);

    render(<UploadDocuments token="t" />);

    expect(await screen.findByText("manual.txt")).toBeInTheDocument();
    expect(screen.getByText("Listo")).toBeInTheDocument();
    expect(screen.getByText(/3 fragmentos · 2 KB/)).toBeInTheDocument();
    expect(screen.getByText("Error")).toBeInTheDocument();
    expect(screen.getByText(/No se pudo extraer texto/)).toBeInTheDocument();
  });

  it("mientras un documento se procesa la lista se actualiza sola hasta que queda listo", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    api.getRagDocuments
      .mockResolvedValueOnce([doc({ estado: "procesando", chunks_count: 0 })])
      .mockResolvedValue([doc({ estado: "listo" })]);

    render(<UploadDocuments token="t" />);
    expect(await screen.findByText("Procesando...")).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3100);
    });

    expect(await screen.findByText("Listo")).toBeInTheDocument();
    const calls = api.getRagDocuments.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000);
    });
    expect(api.getRagDocuments.mock.calls.length).toBe(calls); // ya no hay nada pendiente: deja de consultar
  });

  it("al subir muestra el mensaje del backend y refresca la lista", async () => {
    api.uploadRagDocument.mockResolvedValue({ id: "d-9", documento: "nuevo.txt", estado: "subido", mensaje: "Documento recibido: se esta indexando." });
    render(<UploadDocuments token="t" />);
    await screen.findByText("manual.txt");

    const file = new File(["contenido"], "nuevo.txt", { type: "text/plain" });
    fireEvent.change(document.querySelector("input[type=file]"), { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "Subir documento" }));

    expect(await screen.findByText("Documento recibido: se esta indexando.")).toBeInTheDocument();
    expect(api.uploadRagDocument).toHaveBeenCalledWith("t", file);
    await waitFor(() => expect(api.getRagDocuments.mock.calls.length).toBeGreaterThan(1));
  });

  it("un archivo repetido muestra cual es el que ya existe", async () => {
    api.uploadRagDocument.mockRejectedValue({
      details: { body: { error: "Ya existe un documento con el mismo contenido: manual.txt" } },
    });
    render(<UploadDocuments token="t" />);
    await screen.findByText("manual.txt");

    fireEvent.change(document.querySelector("input[type=file]"), { target: { files: [new File(["x"], "copia.txt")] } });
    fireEvent.click(screen.getByRole("button", { name: "Subir documento" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Ya existe un documento con el mismo contenido: manual.txt");
  });

  it("eliminar pide confirmacion y saca el documento de la lista", async () => {
    api.deleteRagDocument.mockResolvedValue(null);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<UploadDocuments token="t" />);
    await screen.findByText("manual.txt");

    fireEvent.click(screen.getByRole("button", { name: "Eliminar" }));

    await waitFor(() => expect(screen.queryByText("manual.txt")).not.toBeInTheDocument());
    expect(api.deleteRagDocument).toHaveBeenCalledWith("t", "d-1");
    expect(await screen.findByText(/eliminado/)).toBeInTheDocument();
  });

  it("si se cancela la confirmacion el documento sigue ahi", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<UploadDocuments token="t" />);
    await screen.findByText("manual.txt");

    fireEvent.click(screen.getByRole("button", { name: "Eliminar" }));

    expect(api.deleteRagDocument).not.toHaveBeenCalled();
  });
});
