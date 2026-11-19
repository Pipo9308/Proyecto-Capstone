import { useEffect, useState } from "react";
import { api } from "../services/api";

type Rol = "administrador" | "comercial" | "gerencia" | "pendiente";

type Usuario = {
  id: string;
  email: string;
  rol: Rol;
  estado: string;
};

function AdminUsuarios() {
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [loading, setLoading] = useState(true);
  const [mensaje, setMensaje] = useState("");
  const [nuevo, setNuevo] = useState<{ email: string; password: string; rol: Rol }>({ email: "", password: "", rol: "comercial" });
  const [creando, setCreando] = useState(false);

  useEffect(() => {
    const cargarUsuarios = async () => {
      try {
        const response = await api.get("/admin/users/");
        if (response.data.success) {
          setUsuarios(response.data.data);
        } else {
          setMensaje("No se pudieron cargar los usuarios.");
        }
      } catch (error) {
        console.error("Error al cargar usuarios:", error);
        setMensaje("No se pudieron cargar los usuarios.");
      } finally {
        setLoading(false);
      }
    };
    cargarUsuarios();
  }, []);

  const cambiarRol = async (usuarioId: string, email: string, nuevoRol: Rol) => {
    try {
      const usuarioActualStr = localStorage.getItem("enci_user");
      const usuarioActual = usuarioActualStr ? JSON.parse(usuarioActualStr) : null;

      if (!usuarioActual) {
        setMensaje("Debes iniciar sesión para cambiar roles.");
        return;
      }

      const esMiPropioUsuario = usuarioId === usuarioActual.id;

      if (esMiPropioUsuario && nuevoRol !== "administrador") {
        setMensaje("No puedes quitarte tu propio rol de administrador.");
        return;
      }

      await api.patch("/admin/users/role", {
        email: email,
        role: nuevoRol,
      });

      setUsuarios((usuariosActuales) =>
        usuariosActuales.map((usuario) =>
          usuario.id === usuarioId ? { ...usuario, rol: nuevoRol } : usuario
        )
      );

      setMensaje("Rol actualizado correctamente.");
    } catch (error) {
      console.error("Error al cambiar rol:", error);
      setMensaje("No se pudo actualizar el rol.");
    }
  };

  const crearUsuario = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreando(true);
    try {
      const response = await api.post("/admin/users/", { email: nuevo.email, password: nuevo.password, role: nuevo.rol });
      setUsuarios((actuales) => [...actuales, response.data.data]);
      setNuevo({ email: "", password: "", rol: "comercial" });
      setMensaje(`Usuario ${response.data.data.email} creado como ${response.data.data.rol}.`);
    } catch (error) {
      const detalle = (error as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setMensaje(detalle ?? "No se pudo crear el usuario.");
    } finally {
      setCreando(false);
    }
  };

  if (loading) {
    return <p>Cargando usuarios...</p>;
  }

  return (
    <section className="admin-users-page">
      <div className="admin-users-header">
        <div>
          <h1>Administración de Usuarios</h1>
          <p>Gestiona los roles y estados de acceso dentro de ENCI-INTEL.</p>
        </div>

        <span className="admin-users-badge">Solo Administrador</span>
      </div>

      {mensaje && <div className="admin-users-message">{mensaje}</div>}

      <form className="admin-users-card admin-users-create" onSubmit={crearUsuario}>
        <h2>Agregar usuario</h2>
        <input
          type="email"
          required
          placeholder="Correo"
          value={nuevo.email}
          onChange={(e) => setNuevo({ ...nuevo, email: e.target.value })}
        />
        <input
          type="password"
          required
          minLength={8}
          autoComplete="new-password"
          placeholder="Contraseña (mínimo 8)"
          value={nuevo.password}
          onChange={(e) => setNuevo({ ...nuevo, password: e.target.value })}
        />
        <select value={nuevo.rol} onChange={(e) => setNuevo({ ...nuevo, rol: e.target.value as Rol })}>
          <option value="administrador">Administrador</option>
          <option value="gerencia">Gerencia</option>
          <option value="comercial">Comercial</option>
          <option value="pendiente">Pendiente</option>
        </select>
        <button className="btn-main" type="submit" disabled={creando}>Crear usuario</button>
      </form>

      <div className="admin-users-card">
        <table className="admin-users-table">
          <thead>
            <tr>
              <th>Correo</th>
              <th>Rol actual</th>
              <th>Estado</th>
              <th>Cambiar rol</th>
            </tr>
          </thead>

          <tbody>
            {usuarios.map((usuario) => {
              const usuarioActualStr = localStorage.getItem("enci_user");
              const usuarioActual = usuarioActualStr ? JSON.parse(usuarioActualStr) : null;
              const esMiPropioUsuario = usuarioActual && usuario.id === usuarioActual.id;

              return (
                <tr key={usuario.id}>
                  <td>{usuario.email}</td>

                  <td>
                    <span className={`role-pill role-${usuario.rol}`}>
                      {usuario.rol}
                    </span>
                  </td>

                  <td>
                    <span className="status-pill">{usuario.estado}</span>
                  </td>

                  <td>
                    <select
                      value={usuario.rol}
                      onChange={(e) =>
                        cambiarRol(usuario.id, usuario.email, e.target.value as Rol)
                      }
                    >
                      <option value="administrador">Administrador</option>

                      {!esMiPropioUsuario && (
                        <>
                          <option value="gerencia">Gerencia</option>
                          <option value="comercial">Comercial</option>
                          <option value="pendiente">Pendiente</option>
                        </>
                      )}
                    </select>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}

export default AdminUsuarios;