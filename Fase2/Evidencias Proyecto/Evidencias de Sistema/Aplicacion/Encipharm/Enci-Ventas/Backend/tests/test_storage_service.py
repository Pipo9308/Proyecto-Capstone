from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import storage_service


def _settings(tmp_path, **overrides):
    """Construye configuracion minima para probar storage sin servicios externos."""

    values = {
        "APP_ENV": "development",
        "AZURE_STORAGE_CONNECTION_STRING": None,
        "AZURE_STORAGE_CONTAINER": "enci-documents",
        "LOCAL_DOCUMENT_STORAGE_DIR": str(tmp_path / "documents"),
    }
    values.update(overrides)
    return SimpleNamespace(**values)





def test_production_without_bucket_keeps_configuration_error(tmp_path, monkeypatch):
    """Exige GCS en produccion aunque exista un directorio local configurado."""

    monkeypatch.setattr(
        storage_service,
        "get_settings",
        lambda: _settings(tmp_path, APP_ENV="production"),
    )

    with pytest.raises(HTTPException) as error:
        storage_service.upload_document_bytes("manual.txt", b"contenido", "text/plain")

    assert error.value.status_code == 503
    assert error.value.detail == "Storage connection string no configurada"
