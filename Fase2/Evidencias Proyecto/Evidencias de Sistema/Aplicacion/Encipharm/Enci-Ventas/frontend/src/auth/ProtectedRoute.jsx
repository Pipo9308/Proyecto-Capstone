import { Navigate } from "react-router-dom";
import AppShell from "../components/AppShell";
import AccessDenied from "../pages/AccessDenied";
import { hasIntelAccess, hasMinimumRole } from "./roles";
import { useAuth } from "./authContext";

function ProtectedRoute({ children, minimumRole = "vendedor", requireIntelAccess = false }) {
  const { backendUser, isAuthenticated, loading } = useAuth();

  if (loading) {
    return (
      <main className="page">
        <section className="card">
          <p className="status-message">Validando sesion...</p>
        </section>
      </main>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (!hasMinimumRole(backendUser?.rol, minimumRole)) {
    return <AccessDenied minimumRole={minimumRole} userRole={backendUser?.rol} />;
  }

  if (requireIntelAccess && !hasIntelAccess(backendUser)) {
    return (
      <AppShell>
        <main className="page">
          <section className="card">
            <h2>Sin acceso a Inteligencia de Mercado</h2>
            <p className="status-message">
              Tu cuenta no tiene habilitado el acceso a Inteligencia. Solicitalo a un administrador.
            </p>
          </section>
        </main>
      </AppShell>
    );
  }

  return (
    <AppShell>
      {children}
    </AppShell>
  );
}

export default ProtectedRoute;
