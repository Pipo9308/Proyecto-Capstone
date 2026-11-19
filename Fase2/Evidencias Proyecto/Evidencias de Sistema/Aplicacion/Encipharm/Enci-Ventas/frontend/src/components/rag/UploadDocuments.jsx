import { useEffect, useRef, useState } from "react";
import { deleteRagDocument, getRagDocuments, reindexRagDocuments, uploadRagDocument } from "../../services/api";
import { formatFileSize } from "../../utils/archivos";

const ESTADOS = {
  subido: "Subido",
  procesando: "Procesando...",
  listo: "Listo",
  error: "Error",
};
const POLL_MS = 3000;
// Tope de seguridad: si algo queda "procesando" para siempre no se consulta eternamente.
const MAX_POLL_MS = 10 * 60 * 1000;

function backendMessage(error, fallback) {
  return error?.details?.body?.error || error?.message || fallback;
}

function UploadDocuments({ token }) {
  const [documents, setDocuments] = useState([]);
  const [file, setFile] = useState(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const pollStartedAt = useRef(null);

  const pending = documents.some((doc) => doc.estado === "subido" || doc.estado === "procesando");

  async function refreshDocuments({ quiet = false } = {}) {
    if (!quiet) setLoading(true);
    try {
      setDocuments(await getRagDocuments(token));
      if (!quiet) setError("");
    } catch (loadError) {
      if (!quiet) setError(backendMessage(loadError, "No se pudieron cargar los documentos."));
    } finally {
      if (!quiet) setLoading(false);
    }
  }

  // Carga inicial: el estado se actualiza despues de esperar a la API.
  useEffect(() => {
    let cancelled = false;
    getRagDocuments(token)
      .then((docs) => {
        if (!cancelled) setDocuments(docs);
      })
      .catch((loadError) => {
        if (!cancelled) setError(backendMessage(loadError, "No se pudieron cargar los documentos."));
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  // Mientras haya documentos en proceso, la lista se actualiza sola (RF-07.03).
  useEffect(() => {
    if (!pending) {
      pollStartedAt.current = null;
      return undefined;
    }
    pollStartedAt.current = pollStartedAt.current ?? Date.now();
    const timer = window.setInterval(() => {
      if (Date.now() - pollStartedAt.current > MAX_POLL_MS) {
        window.clearInterval(timer);
        return;
      }
      refreshDocuments({ quiet: true });
    }, POLL_MS);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pending, token]);

  async function handleUpload(event) {
    event.preventDefault();
    if (!file) return;
    // currentTarget es null despues de un await: se captura antes.
    const form = event.currentTarget;
    setUploading(true);
    setError("");
    setStatus("");
    try {
      const result = await uploadRagDocument(token, file);
      setStatus(result?.mensaje || "Documento recibido.");
      setFile(null);
      form.reset();
      await refreshDocuments({ quiet: true });
    } catch (uploadError) {
      // 409: el archivo ya estaba subido (mismo contenido o nombre); el mensaje dice cual.
      setError(backendMessage(uploadError, "No se pudo subir el documento."));
    } finally {
      setUploading(false);
    }
  }

  async function handleDelete(doc) {
    if (!window.confirm(`Eliminar "${doc.nombre}"? El asistente dejara de citarlo.`)) return;
    setError("");
    setStatus("");
    try {
      await deleteRagDocument(token, doc.id);
      setDocuments((current) => current.filter((item) => item.id !== doc.id));
      setStatus(`"${doc.nombre}" eliminado.`);
    } catch (deleteError) {
      setError(backendMessage(deleteError, "No se pudo eliminar el documento."));
    }
  }

  async function handleReindex() {
    setLoading(true);
    setError("");
    setStatus("");
    try {
      const result = await reindexRagDocuments(token);
      setStatus(`${result.chunks_indexados} fragmentos reindexados`);
      await refreshDocuments({ quiet: true });
    } catch (reindexError) {
      setError(backendMessage(reindexError, "No se pudo reindexar."));
    } finally {
      setLoading(false);
    }
  }

  const busy = loading || uploading;

  return (
    <section className="rag-admin-panel">
      <div className="rag-panel-header">
        <div>
          <h2>Corpus documental</h2>
          <p>Gestion de archivos internos disponibles para consulta (PDF, DOCX o TXT, hasta 25 MB).</p>
        </div>
        <div className="rag-admin-actions">
          <button className="btn-secondary compact" disabled={busy} onClick={() => refreshDocuments()} type="button">
            Actualizar
          </button>
          <button className="btn-secondary compact" disabled={busy} onClick={handleReindex} type="button">
            Reindexar
          </button>
        </div>
      </div>

      <form className="rag-upload-form" onSubmit={handleUpload}>
        <input
          accept=".pdf,.docx,.txt"
          disabled={busy}
          onChange={(event) => setFile(event.target.files?.[0] || null)}
          type="file"
        />
        <button className="btn-primary" disabled={!file || busy} type="submit">
          {uploading ? "Subiendo..." : "Subir documento"}
        </button>
      </form>

      {status && <p className="rag-status success">{status}</p>}
      {error && <p className="rag-status error" role="alert">{error}</p>}

      <div className="rag-document-list">
        {documents.map((doc) => (
          <article className="rag-document-item" key={doc.id}>
            <div>
              <strong>{doc.nombre}</strong>
              <br />
              <span className={`doc-estado ${doc.estado}`}>{ESTADOS[doc.estado] || doc.estado}</span>
              {doc.estado === "listo" && <span> {doc.chunks_count} fragmentos · {formatFileSize(doc.tamano_bytes)}</span>}
              {doc.estado === "error" && doc.error && <small className="field-error"> {doc.error}</small>}
            </div>
            <button className="btn-secondary compact" onClick={() => handleDelete(doc)} type="button">
              Eliminar
            </button>
          </article>
        ))}
        {!documents.length && <p className="muted-text">Sin documentos indexados.</p>}
      </div>
    </section>
  );
}

export default UploadDocuments;
