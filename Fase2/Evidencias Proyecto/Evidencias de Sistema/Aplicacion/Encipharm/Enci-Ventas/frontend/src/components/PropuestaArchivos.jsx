import { useRef, useState } from "react";
import { useAuth } from "../auth/authContext";
import {
  buildApiUrl,
  deletePropuestaArchivo,
  getPropuestaArchivoLink,
  getPropuestaArchivos,
  uploadPropuestaArchivo,
} from "../services/api";
import { formatFileSize, validatePdfFile } from "../utils/archivos";

function backendMessage(error, fallback) {
  return error?.details?.body?.error || fallback;
}

/** PDF adjuntos de una propuesta: subir con barra de progreso, descargar con enlace firmado y borrar. */
function PropuestaArchivos({ propuestaId }) {
  const { idToken } = useAuth();
  const inputRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [files, setFiles] = useState(null);
  const [loading, setLoading] = useState(false);
  const [progress, setProgress] = useState(null);
  const [error, setError] = useState("");

  const load = async () => {
    setLoading(true);
    setError("");
    try {
      setFiles(await getPropuestaArchivos(idToken, propuestaId));
    } catch (loadError) {
      setError(backendMessage(loadError, "No se pudieron cargar los archivos."));
    } finally {
      setLoading(false);
    }
  };

  const toggle = async () => {
    const next = !open;
    setOpen(next);
    if (next && files === null) await load();
  };

  const handleSelect = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setError("");
    const problem = validatePdfFile(file) || ((files?.length || 0) >= 10 ? "Una propuesta admite hasta 10 archivos." : "");
    if (problem) {
      setError(problem);
      event.target.value = "";
      return;
    }
    try {
      setProgress(0);
      const created = await uploadPropuestaArchivo(idToken, propuestaId, file, setProgress);
      // El archivo aparece en cuanto termina la subida, sin recargar la pagina.
      setFiles((current) => [...(current || []), created]);
    } catch (uploadError) {
      setError(backendMessage(uploadError, "No se pudo subir el archivo. Intenta de nuevo."));
    } finally {
      setProgress(null);
      if (inputRef.current) inputRef.current.value = "";
    }
  };

  const handleDownload = async (file) => {
    setError("");
    try {
      const { url } = await getPropuestaArchivoLink(idToken, propuestaId, file.id);
      // El enlace es firmado y vence a los pocos minutos; la respuesta fuerza la descarga.
      window.location.assign(buildApiUrl(url));
    } catch (downloadError) {
      setError(backendMessage(downloadError, "No se pudo generar el enlace de descarga."));
    }
  };

  const handleDelete = async (file) => {
    if (!window.confirm(`Eliminar "${file.nombre}"?`)) return;
    setError("");
    try {
      await deletePropuestaArchivo(idToken, propuestaId, file.id);
      setFiles((current) => (current || []).filter((item) => item.id !== file.id));
    } catch (deleteError) {
      setError(backendMessage(deleteError, "No se pudo eliminar el archivo."));
    }
  };

  const count = files?.length;

  return (
    <div className="propuesta-archivos">
      <button className="btn-secondary compact" onClick={toggle} type="button" aria-expanded={open}>
        {open ? "Ocultar archivos" : `Archivos${count != null ? ` (${count})` : ""}`}
      </button>

      {open && (
        <div>
          {loading && <p className="muted-text">Cargando archivos...</p>}
          {error && <p className="field-error" role="alert">{error}</p>}

          {(files || []).map((file) => (
            <div className="archivo-row" key={file.id}>
              <div>
                <strong>{file.nombre}</strong>
                <br />
                <small>
                  {formatFileSize(file.tamanoBytes)} · {file.subidoPorNombre || "usuario"}
                  {file.createdAt ? ` · ${new Date(`${file.createdAt}Z`).toLocaleDateString()}` : ""}
                </small>
              </div>
              <div className="archivo-actions">
                <button className="btn-secondary compact" onClick={() => handleDownload(file)} type="button">Descargar</button>
                <button className="btn-secondary compact" onClick={() => handleDelete(file)} type="button">Eliminar</button>
              </div>
            </div>
          ))}
          {files && files.length === 0 && !loading && <p className="muted-text">Sin archivos adjuntos.</p>}

          {progress !== null && (
            <div>
              <progress className="upload-progress" max="100" value={progress} aria-label="Progreso de subida" />
              <small>Subiendo... {progress}%</small>
            </div>
          )}

          <label>
            Adjuntar PDF (hasta 20 MB)
            <input
              accept="application/pdf,.pdf"
              disabled={progress !== null}
              onChange={handleSelect}
              ref={inputRef}
              type="file"
            />
          </label>
        </div>
      )}
    </div>
  );
}

export default PropuestaArchivos;
