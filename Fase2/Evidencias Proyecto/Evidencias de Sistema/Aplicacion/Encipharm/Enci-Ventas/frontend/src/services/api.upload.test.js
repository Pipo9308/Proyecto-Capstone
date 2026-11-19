import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, uploadFileWithProgress } from "./api";

class FakeXhr {
  static instances = [];

  constructor() {
    FakeXhr.instances.push(this);
    this.headers = {};
    this.upload = {};
    this.status = 0;
    this.responseText = "";
    this.statusText = "";
  }

  open(method, url) {
    this.method = method;
    this.url = url;
  }

  setRequestHeader(name, value) {
    this.headers[name] = value;
  }

  send(body) {
    this.body = body;
  }

  respond(status, body) {
    this.status = status;
    this.responseText = typeof body === "string" ? body : JSON.stringify(body);
    this.onload();
  }
}

const pdf = () => new File(["%PDF-1.4"], "oferta.pdf", { type: "application/pdf" });

describe("uploadFileWithProgress", () => {
  beforeEach(() => {
    FakeXhr.instances = [];
    vi.stubGlobal("XMLHttpRequest", FakeXhr);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("envia el archivo con la sesion y la plataforma, y resuelve con el cuerpo", async () => {
    const promise = uploadFileWithProgress("/propuestas/p-1/archivos", { token: "jwt", file: pdf() });
    const xhr = FakeXhr.instances[0];

    xhr.respond(201, { id: "a-1", nombre: "oferta.pdf" });

    await expect(promise).resolves.toEqual({ id: "a-1", nombre: "oferta.pdf" });
    expect(xhr.method).toBe("POST");
    expect(xhr.url).toBe("http://localhost:8000/propuestas/p-1/archivos");
    expect(xhr.headers.Authorization).toBe("Bearer jwt");
    expect(xhr.headers["X-Enci-Client"]).toBe("web");
    expect(xhr.body.get("file").name).toBe("oferta.pdf");
  });

  it("informa el avance en porcentaje", async () => {
    const progress = [];
    const promise = uploadFileWithProgress("/x", { token: "t", file: pdf(), onProgress: (value) => progress.push(value) });
    const xhr = FakeXhr.instances[0];

    xhr.upload.onprogress({ lengthComputable: true, loaded: 25, total: 100 });
    xhr.upload.onprogress({ lengthComputable: true, loaded: 100, total: 100 });
    xhr.upload.onprogress({ lengthComputable: false, loaded: 5, total: 0 });
    xhr.respond(201, {});
    await promise;

    expect(progress).toEqual([25, 100]);
  });

  it("un error del backend rechaza con ApiError y deja el cuerpo en details.body", async () => {
    const promise = uploadFileWithProgress("/x", { token: "t", file: pdf() });
    FakeXhr.instances[0].respond(409, { error: "Una propuesta admite hasta 10 archivos", codigo: "ERR_LIMITE_ADJUNTOS" });

    const error = await promise.catch((e) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(409);
    expect(error.code).toBe("ERR_LIMITE_ADJUNTOS");
    expect(error.details.body.error).toBe("Una propuesta admite hasta 10 archivos");
  });

  it("un 401 avisa que la sesion vencio", async () => {
    const expired = vi.fn();
    window.addEventListener("enci:auth-expired", expired);
    const promise = uploadFileWithProgress("/x", { token: "t", file: pdf() });
    FakeXhr.instances[0].respond(401, { error: "Token invalido" });

    await promise.catch(() => {});
    window.removeEventListener("enci:auth-expired", expired);

    expect(expired).toHaveBeenCalledTimes(1);
  });

  it("una subida exitosa avisa que los datos cambiaron", async () => {
    const mutated = vi.fn();
    window.addEventListener("enci:data-mutated", mutated);
    const promise = uploadFileWithProgress("/x", { token: "t", file: pdf() });
    FakeXhr.instances[0].respond(201, {});

    await promise;
    window.removeEventListener("enci:data-mutated", mutated);

    expect(mutated).toHaveBeenCalledTimes(1);
  });

  it("un fallo de red rechaza con un error de conexion", async () => {
    const promise = uploadFileWithProgress("/x", { token: "t", file: pdf() });

    FakeXhr.instances[0].onerror();

    const error = await promise.catch((e) => e);
    expect(error.status).toBe(0);
    expect(error.code).toBe("API_NETWORK_FETCH_FAILED");
  });

  it("una respuesta de error que no es JSON no rompe", async () => {
    const promise = uploadFileWithProgress("/x", { token: "t", file: pdf() });
    FakeXhr.instances[0].respond(502, "<html>Bad gateway</html>");

    const error = await promise.catch((e) => e);

    expect(error.status).toBe(502);
  });
});
