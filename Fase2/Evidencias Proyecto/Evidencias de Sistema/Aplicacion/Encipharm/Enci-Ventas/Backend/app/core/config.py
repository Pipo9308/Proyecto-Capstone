import json
from functools import lru_cache
from typing import Optional

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )

    APP_NAME: str = "Enci API"
    # Por defecto produccion: si falta la variable en un despliegue no se abren /docs ni los errores detallados.
    # En local se declara APP_ENV=development (docker-compose y .env.example ya lo hacen).
    APP_ENV: str = "production"
    APP_VERSION: str = "1.0.0"
    LOG_LEVEL: str = "INFO"
    LOG_FORMAT: str = "json"  # json (hosting) o text (local)
    ENABLE_TEMPORARY_ROLE_SWITCHER: bool = False

    # CORS
    CORS_ORIGINS: str = (
        "http://localhost:3000,"
        "http://localhost:5173,"
        "http://localhost:5174,"
        "http://localhost:5175,"
        "http://127.0.0.1:5173,"
        "http://127.0.0.1:5174,"
        "http://127.0.0.1:5175"
    )
    CORS_ORIGIN_REGEX: Optional[str] = None



    # Custom Auth & DB
    # Cloud Firestore (unica base de datos). Credenciales: FIREBASE_CREDENTIALS_JSON o FIREBASE_CREDENTIALS_PATH;
    # con FIRESTORE_EMULATOR_HOST se usa el emulador local.
    FIREBASE_PROJECT_ID: str = Field(..., description="ID del proyecto de Firebase")
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis URL for rate limiting")
    JWT_SECRET: str = Field(..., description="Secret for signing JWTs")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7 # 1 semana

    # Cuentas: enlaces de invitacion y registro
    FRONTEND_URL: str = "http://localhost:5173"
    INVITATION_TTL_HOURS: int = 72
    # El registro publico esta cerrado: las cuentas se crean por invitacion (RF-05.07).
    ALLOW_SELF_REGISTER: bool = False

    # Notificaciones (RQ-01): cada cuantos segundos, como maximo, se consulta Enci-Intel por alertas
    # criticas/altas (0 lo apaga) y cuantas horas hacia atras se mira.
    NOTIFICATIONS_INTEL_POLL_SECONDS: int = 120
    NOTIFICATIONS_INTEL_LOOKBACK_HOURS: int = 72

    # Enci Inteligencia
    ENCI_INTEL_API_URL: Optional[str] = None
    ENCI_INTEL_API_KEY: Optional[str] = None

    # Azure Blob Storage (Azurite fallback)
    AZURE_STORAGE_CONNECTION_STRING: Optional[str] = "DefaultEndpointsProtocol=http;AccountName=devstoreaccount1;AccountKey=Eby8vdM02xNOcqFlqUwJPLlmEtlCDXJ1OUzFT50uSRZ6IFsuFq2UVErCz4I6tq/K1SZFPTOtr/KBHBeksoGMGw==;BlobEndpoint=http://127.0.0.1:10000/devstoreaccount1;"
    AZURE_STORAGE_CONTAINER: str = "enci-documents"

    # RAG assistant
    DEEPSEEK_API_KEY: Optional[str] = None
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com"
    DEEPSEEK_MODEL: str = "deepseek-chat"
    # "anthropic": los chats usan Claude con ANTHROPIC_API_KEY y DEEPSEEK_MODEL/COMPETENCIA_MODEL como modelo de Claude.
    LLM_PROVIDER: str = ""
    ANTHROPIC_API_KEY: Optional[str] = None
    MAX_TOKENS_RESPONSE: int = 1024
    MAX_CONTEXT_CHUNKS: int = 5
    SIMILARITY_THRESHOLD: float = 0.30
    GCS_BUCKET_DOCUMENTS: Optional[str] = None
    LOCAL_DOCUMENT_STORAGE_DIR: str = "./document_storage"
    RAG_CHAT_RATE_LIMIT_PER_MINUTE: int = 30
    RAG_MAX_UPLOAD_BYTES: int = 25 * 1024 * 1024

    # Adjuntos de propuestas (RQ-07): PDF de hasta 20 MB, con un maximo por propuesta, y
    # enlaces de descarga firmados que vencen.
    PROPUESTA_MAX_ARCHIVO_BYTES: int = 20 * 1024 * 1024
    PROPUESTA_MAX_ARCHIVOS: int = 10
    DOWNLOAD_LINK_MINUTES: int = 10

    # Chat de competencia (RQ-08). El modelo se cambia por variable de entorno (RF-08.11);
    # si no se define, usa el mismo del asistente RAG.
    COMPETENCIA_MODEL: Optional[str] = None
    COMPETENCIA_CHAT_DAILY_LIMIT: int = 50
    COMPETENCIA_MAX_TOOL_ROUNDS: int = 4
    COMPETENCIA_MAX_TOKENS: int = 900
    # Costo aproximado por 1000 tokens (USD) para el reporte de uso; 0 = no se calcula.
    COMPETENCIA_PRICE_PER_1K_INPUT: float = 0.0
    COMPETENCIA_PRICE_PER_1K_OUTPUT: float = 0.0
    # Busqueda web en vivo: apagada por defecto (costo variable y contenido no confiable).
    WEB_SEARCH_ENABLED: bool = False
    TAVILY_API_KEY: Optional[str] = None
    WEB_SEARCH_MAX_RESULTS: int = 5

    @property
    def cors_origins_list(self) -> list[str]:
        """Accept JSON arrays or comma-separated values from hosting panels."""
        raw_value = self.CORS_ORIGINS.strip()
        if not raw_value:
            return []

        if raw_value.startswith("["):
            value = json.loads(raw_value)
        else:
            value = raw_value.split(",")

        return [
            origin.strip().rstrip("/")
            for origin in value
            if isinstance(origin, str) and origin.strip()
        ]

    @model_validator(mode="after")
    def validate_security_settings(self):
        if self.APP_ENV == "production" and "*" in self.cors_origins_list:
            raise ValueError("CORS_ORIGINS no puede incluir '*' en produccion")
        if self.APP_ENV == "production" and self.CORS_ORIGIN_REGEX in {".*", "^.*$"}:
            raise ValueError("CORS_ORIGIN_REGEX no puede permitir todos los origenes en produccion")
        if self.APP_ENV == "production" and self.ENABLE_TEMPORARY_ROLE_SWITCHER:
            raise ValueError("ENABLE_TEMPORARY_ROLE_SWITCHER debe estar deshabilitado en produccion")
        return self

@lru_cache()
def get_settings() -> Settings:
    return Settings()
