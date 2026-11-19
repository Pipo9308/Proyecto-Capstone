import { useCallback, useEffect, useMemo, useState } from "react";
import { translateStaticDom } from "../i18n/useI18n";
import { 
  clearApiGetCache, 
  loginWithCredentials, 
  registerWithCredentials, 
  updateCurrentUserPreferences,
  getCurrentUser
} from "../services/api";
import { AuthContext } from "./authContext";

function friendlyAuthError(error) {
  return error?.details?.message || error?.message || "No se pudo iniciar sesion.";
}

function ensureWebAccess(user) {
  if (user?.rol === "sin_acceso") {
    throw new Error("Tu cuenta no tiene un rol habilitado en el sistema web.");
  }

  if (user?.webApp === false) {
    throw new Error("Tu cuenta no tiene acceso habilitado al sistema web.");
  }
}

export function AuthProvider({ children }) {
  const [backendUser, setBackendUser] = useState(null);
  const [idToken, setIdToken] = useState(() => localStorage.getItem("enci_token") || null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let isMounted = true;
    async function initAuth() {
      if (!idToken) {
        if (isMounted) setLoading(false);
        return;
      }
      try {
        const user = await getCurrentUser(idToken);
        if (!isMounted) return;
        ensureWebAccess(user);
        setBackendUser(user);
        localStorage.setItem("enci_user", JSON.stringify(user));
      } catch (err) {
        if (!isMounted) return;
        console.error("Auth init failed", err);
        localStorage.removeItem("enci_token");
        localStorage.removeItem("enci_user");
        setIdToken(null);
        setBackendUser(null);
      } finally {
        if (isMounted) setLoading(false);
      }
    }
    initAuth();
    return () => { isMounted = false; };
  }, [idToken]);


  const handleAuthSuccess = (response) => {
    const { access_token, user } = response;
    ensureWebAccess(user);
    localStorage.setItem("enci_token", access_token);
    localStorage.setItem("enci_user", JSON.stringify(user));
    setIdToken(access_token);
    setBackendUser(user);
    setError("");
  };

  useEffect(() => {
    const language = backendUser?.language || "es";
    let animationFrameId = 0;

    document.documentElement.dataset.theme = backendUser?.theme || "dark";
    document.documentElement.lang = language;

    const translateCurrentView = () => {
      window.cancelAnimationFrame(animationFrameId);
      animationFrameId = window.requestAnimationFrame(() => translateStaticDom(language));
    };

    translateCurrentView();

    const observer = new MutationObserver(translateCurrentView);
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ["placeholder", "title", "aria-label"],
    });

    return () => {
      window.cancelAnimationFrame(animationFrameId);
      observer.disconnect();
    };
  }, [backendUser?.theme, backendUser?.language]);

  const logout = useCallback(() => {
    clearApiGetCache();
    localStorage.removeItem("enci_token");
    localStorage.removeItem("enci_user");
    setIdToken(null);
    setBackendUser(null);
  }, []);

  useEffect(() => {
    async function handleAuthExpired() {
      setError("Tu sesion expiro. Ingresa nuevamente.");
      logout();
    }

    window.addEventListener("enci:auth-expired", handleAuthExpired);
    return () => window.removeEventListener("enci:auth-expired", handleAuthExpired);
  }, [logout]);

  const login = useCallback(async (email, password) => {
    setLoading(true);
    setError("");
    try {
      const res = await loginWithCredentials(email, password);
      handleAuthSuccess(res);
    } catch (loginError) {
      setError(friendlyAuthError(loginError));
    } finally {
      setLoading(false);
    }
  }, []);

  const register = useCallback(async (email, password) => {
    setLoading(true);
    setError("");
    try {
      const res = await registerWithCredentials(email, password);
      handleAuthSuccess(res);
    } catch (regError) {
      setError(friendlyAuthError(regError));
    } finally {
      setLoading(false);
    }
  }, []);

  const updatePreferences = useCallback(async (preferences) => {
    if (!idToken) {
      throw new Error("No hay sesion activa para actualizar preferencias.");
    }

    const previousUser = backendUser;
    const optimisticUser = { ...backendUser, ...preferences };
    setBackendUser(optimisticUser);
    document.documentElement.dataset.theme = optimisticUser.theme || "dark";
    document.documentElement.lang = optimisticUser.language || "es";
    translateStaticDom(optimisticUser.language || "es");

    try {
      const updatedUser = await updateCurrentUserPreferences(idToken, preferences);
      setBackendUser(updatedUser);
      return updatedUser;
    } catch (preferenceError) {
      setBackendUser(previousUser);
      document.documentElement.dataset.theme = previousUser?.theme || "dark";
      document.documentElement.lang = previousUser?.language || "es";
      translateStaticDom(previousUser?.language || "es");
      throw preferenceError;
    }
  }, [backendUser, idToken]);

  const value = useMemo(
    () => ({
      backendUser,
      error,
      idToken,
      isAuthenticated: Boolean(backendUser && idToken),
      loading,
      login,
      register,
      logout,
      updatePreferences,
    }),
    [backendUser, error, idToken, loading, login, register, logout, updatePreferences],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
