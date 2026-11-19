import { useEffect, useState } from "react";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { useAuth } from "../auth/authContext";
import { getInvitationPreview, setPasswordWithToken } from "../services/api";
import { PASSWORD_HINT, passwordPolicyError } from "../utils/passwordPolicy";

const inputStyle = { padding: "0.75rem", width: "100%", borderRadius: "4px", border: "1px solid #ccc" };

/**
 * Pantalla publica a la que llega el usuario con el enlace de invitacion o de restablecimiento.
 * Muestra para quien es el enlace, pide la contraseña nueva y abre la sesion.
 */
function Activar() {
  const [params] = useSearchParams();
  const token = params.get("token") || "";
  const { isAuthenticated, login } = useAuth();
  const navigate = useNavigate();
  const [preview, setPreview] = useState(null);
  const [linkError, setLinkError] = useState("");
  const [password, setPassword] = useState("");
  const [repeat, setRepeat] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    if (!token) return undefined;
    getInvitationPreview(token)
      .then((data) => {
        if (!cancelled) setPreview(data);
      })
      .catch((previewError) => {
        if (!cancelled) {
          setLinkError(previewError?.details?.body?.error || "El enlace no es valido o ya vencio. Pide uno nuevo a tu administrador.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (isAuthenticated && !saving) {
    return <Navigate to="/dashboard" replace />;
  }

  const handleSubmit = async (event) => {
    event.preventDefault();
    setError("");
    const policy = passwordPolicyError(password);
    if (policy) {
      setError(policy);
      return;
    }
    if (password !== repeat) {
      setError("Las contraseñas no coinciden.");
      return;
    }
    try {
      setSaving(true);
      await setPasswordWithToken(token, password);
      // La contraseña ya quedo guardada: se inicia sesion con ella.
      await login(preview.email, password);
      navigate("/dashboard", { replace: true });
    } catch (saveError) {
      setSaving(false);
      setError(saveError?.details?.body?.error || "No se pudo guardar la contraseña. Intenta de nuevo.");
    }
  };

  const missingToken = !token;
  const failed = missingToken || linkError;

  return (
    <main className="login-page">
      <section className="login-panel">
        <p className="eyebrow">Enci Ventas</p>
        {failed ? (
          <>
            <h1>Enlace no disponible</h1>
            <p className="status-message error">{missingToken ? "Falta el enlace de invitacion." : linkError}</p>
            <p><Link to="/login">Ir al inicio de sesión</Link></p>
          </>
        ) : !preview ? (
          <p className="status-message">Validando enlace...</p>
        ) : (
          <>
            <h1>{preview.tipo === "invitacion" ? "Crea tu contraseña" : "Nueva contraseña"}</h1>
            <p>
              Hola <strong>{preview.nombre}</strong>. Estás creando la contraseña de <strong>{preview.email}</strong>.
            </p>

            <form onSubmit={handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem", marginTop: "1.5rem" }}>
              <input
                type="password"
                autoComplete="new-password"
                placeholder="Contraseña nueva"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                style={inputStyle}
              />
              <input
                type="password"
                autoComplete="new-password"
                placeholder="Repite la contraseña"
                value={repeat}
                onChange={(e) => setRepeat(e.target.value)}
                required
                style={inputStyle}
              />
              <small>{PASSWORD_HINT}</small>
              <button className="login-button" disabled={saving || !password || !repeat} type="submit">
                {saving ? "Guardando..." : "Guardar y entrar"}
              </button>
            </form>
            {error && <p className="status-message error" role="alert">{error}</p>}
          </>
        )}
      </section>
    </main>
  );
}

export default Activar;
