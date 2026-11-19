import { useEffect, useState } from "react";
import { useAuth } from "../auth/authContext";
import { hasMinimumRole } from "../auth/roles";
import { getUsers } from "../services/api";

/**
 * Selector de vendedor para supervisor y admin (RF-06.07). Para un vendedor no se muestra:
 * el cliente queda asignado a quien lo crea.
 */
function VendedorSelect({ value, onChange, disabled }) {
  const { backendUser, idToken } = useAuth();
  const canAssign = hasMinimumRole(backendUser?.rol, "supervisor");
  const [users, setUsers] = useState([]);

  useEffect(() => {
    if (!canAssign || !idToken) return undefined;
    let cancelled = false;
    getUsers(idToken, { activo: true, limit: 500 })
      .then((list) => {
        if (!cancelled) setUsers(list.filter((user) => user.rol !== "sin_acceso"));
      })
      .catch(() => {
        // Sin la lista el cliente queda asignado a quien lo crea: no se bloquea el formulario.
      });
    return () => {
      cancelled = true;
    };
  }, [canAssign, idToken]);

  if (!canAssign) return null;

  return (
    <label>
      Vendedor asignado
      <select name="vendedorUid" value={value || ""} onChange={onChange} disabled={disabled}>
        <option value="">{`Yo (${backendUser?.nombre || "usuario actual"})`}</option>
        {users.map((user) => (
          <option key={user.uid} value={user.uid}>
            {user.nombre || user.email}
          </option>
        ))}
      </select>
    </label>
  );
}

export default VendedorSelect;
