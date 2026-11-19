import { useState } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../auth/authContext";
import { forgotPassword } from "../services/api";

const inputStyle = { padding: "0.75rem", width: "100%", borderRadius: "4px", border: "1px solid #ccc" };

function Login() {
  const { error, isAuthenticated, loading, login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [forgotOpen, setForgotOpen] = useState(false);
  const [forgotMessage, setForgotMessage] = useState("");
  const [forgotError, setForgotError] = useState("");
  const [sending, setSending] = useState(false);

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }

  const handleSubmit = async (e) => {
    e.preventDefault();
    await login(email, password);
  };

  // Todavia no hay envio de correos: la solicitud queda visible para el administrador,
  // que le entrega un enlace para crear una contraseña nueva.
  const handleForgot = async (e) => {
    e.preventDefault();
    setForgotError("");
    setForgotMessage("");
    try {
      setSending(true);
      const result = await forgotPassword(email);
      setForgotMessage(result?.mensaje || "Solicitud enviada a tu administrador.");
    } catch {
      setForgotError("No se pudo enviar la solicitud. Intenta de nuevo en unos minutos.");
    } finally {
      setSending(false);
    }
  };

  return (
    <main className="login-page">
      <section className="login-panel">
        <p className="eyebrow">Enci Ventas</p>
        <h1>Acceso seguro al CRM comercial</h1>
        <p>
          Ingresa con tu correo y contraseña. Si aun no tienes cuenta, pide a un administrador que te invite.
        </p>

        <form onSubmit={forgotOpen ? handleForgot : handleSubmit} style={{ display: "flex", flexDirection: "column", gap: "1rem", marginTop: "1.5rem" }}>
          <div>
            <input
              type="email"
              placeholder="Correo electrónico"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              style={inputStyle}
            />
          </div>
          {!forgotOpen && (
            <div>
              <input
                type="password"
                placeholder="Contraseña"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                style={inputStyle}
              />
            </div>
          )}

          {forgotOpen ? (
            <button className="login-button" disabled={sending || !email} type="submit">
              {sending ? "Enviando..." : "Solicitar nueva contraseña"}
            </button>
          ) : (
            <button className="login-button" disabled={loading || !email || !password} type="submit">
              {loading ? "Validando sesion..." : "Login"}
            </button>
          )}
        </form>

        <p style={{ marginTop: "1rem", textAlign: "center" }}>
          <button
            type="button"
            onClick={() => {
              setForgotOpen(!forgotOpen);
              setForgotMessage("");
              setForgotError("");
            }}
            style={{ background: "none", border: "none", color: "var(--color-primary, #007bff)", cursor: "pointer", textDecoration: "underline" }}
          >
            {forgotOpen ? "Volver a iniciar sesión" : "¿Olvidaste tu contraseña?"}
          </button>
        </p>

        {forgotMessage && <p className="status-message" role="status">{forgotMessage}</p>}
        {forgotError && <p className="status-message error">{forgotError}</p>}
        {error && !forgotOpen && <p className="status-message error">{error}</p>}
      </section>
    </main>
  );
}

export default Login;
