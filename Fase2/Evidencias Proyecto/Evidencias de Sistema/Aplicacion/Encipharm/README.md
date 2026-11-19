# Encipharm — Enci-Intel + Enci-Ventas

Código fuente del proyecto APT122 · Grupo 1 (Felipe Ramos, Benjamín Pumarino, Elías Sánchez).

Monorepo con dos productos que comparten una base de datos Cloud Firestore:

- **Enci-Ventas**: CRM comercial (web React, app móvil Flutter y API FastAPI).
- **Enci-Intel**: plataforma de inteligencia de mercado (dashboard React, API FastAPI, agentes de scraping SAG y
  Competidores, asistente RAG).

## Estructura

```text
Encipharm/
├── Enci-Ventas/
│   ├── Backend/               # API FastAPI (app/, tests/, scripts/)
│   ├── frontend/              # CRM web React + Vite
│   ├── vendedor_app_flutter/  # App móvil del vendedor
│   ├── e2e/                   # Pruebas de punta a punta (Playwright)
│   └── docs/                  # Documentación técnica de Ventas
├── Enci-Intel/
│   ├── Backend/               # API FastAPI, agentes (agents/), RAG (app/rag/), tests/, scripts/
│   └── Frontend/              # Dashboard React + Vite
├── docs/                      # Revisiones y planes técnicos
├── .github/workflows/         # CI (ci.yml) y disparador diario de agentes (agentes.yml)
├── docker-compose.yml         # Levanta todo el proyecto
└── .env.example               # Plantilla de variables de entorno
```

## Cómo levantarlo

```bash
cp .env.example .env      # completar los valores
docker compose up -d --build
```

- Enci-Ventas web: http://localhost:5173 · API: http://localhost:8000/health
- Enci-Intel web: http://localhost:5174 · API: http://localhost:8080/docs

Más detalle en `ONBOARDING.md` y `Enci-Ventas/docs/setup.md`.

La planificación, el avance y la distribución del trabajo del equipo están documentados en los informes de la
asignatura (carpetas de cada fase del repositorio).
