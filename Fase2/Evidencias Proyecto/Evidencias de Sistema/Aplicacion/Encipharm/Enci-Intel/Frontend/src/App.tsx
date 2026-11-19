import { useState } from "react";

import Sidebar from "./components/layout/sidebar";
import Navbar from "./components/layout/Navbar";
import MainContent from "./components/layout/mainContent";
import LoginScreen from "./components/auth/LoginScreen";

import { useAuth } from "./hooks/useAuth";
import { useLocalStorage } from "./hooks/useLocalStorage";
import type { Vista, Language } from "./types";

import "../src/assets/style/index.css";

function App() {
  const [vista, setVista] = useState<Vista>("dashboard");

  const [darkModeStr, setDarkModeStr] = useLocalStorage<"false" | "true">("enci_dark_mode", "false");
  const darkMode = darkModeStr === "true";
  const setDarkMode = (v: boolean) => setDarkModeStr(String(v) as "false" | "true");

  const [language, setLanguage] = useLocalStorage<Language>("enci_language", "es" as Language);

  const {
    role,
    email,
    setEmail,
    password,
    setPassword,
    loginError,
    handleLogin,
    handleLogout,
  } = useAuth(language, setVista);

  // Sesión única was removed along with Firebase.

  if (!role) {
    return (
      <LoginScreen
        darkMode={darkMode}
        setDarkMode={setDarkMode}
        language={language}
        setLanguage={setLanguage}
        email={email}
        setEmail={setEmail}
        password={password}
        setPassword={setPassword}
        loginError={loginError}
        handleLogin={handleLogin}
      />
    );
  }

  return (
    <div className={darkMode ? "app dark-mode" : "app"}>
      <Sidebar
        role={role}
        vista={vista}
        setVista={setVista}
        language={language}
        onLogout={handleLogout}
      />

      <div className="app-content">
        <Navbar
          language={language}
          setLanguage={setLanguage}
          darkMode={darkMode}
          setDarkMode={setDarkMode}
        />
        <MainContent vista={vista} role={role} language={language} setVista={setVista} />
      </div>
    </div>
  );
}

export default App;
