# Enci Ventas Frontend

Frontend web del MVP comercial Enci Ventas. La app usa React, Vite y consume la API FastAPI mediante tokens JWT.

## Desarrollo local

```bash
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

## Variables

Crear `frontend/.env` desde `.env.example`:

```env
VITE_APP_NAME=Enci Ventas
VITE_API_BASE_URL=http://localhost:8000
```

## QA tecnica

```bash
npm run lint
npm run build
```
