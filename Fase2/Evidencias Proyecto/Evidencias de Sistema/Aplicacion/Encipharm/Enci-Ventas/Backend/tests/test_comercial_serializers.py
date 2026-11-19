from types import SimpleNamespace

from app.services.comercial import (
    _interaction_model_to_dict,
    _opportunity_model_to_dict,
    _proposal_model_to_dict,
)


def test_interaction_serializer_keeps_resultado_and_proxima_accion():
    interaction = SimpleNamespace(
        id="i-1", clienteId="c-1", tipo="llamada", fecha=None, resumen="Llamada de seguimiento",
        resultado="Interesado", proximaAccion="Enviar cotizacion", vendedorUid="u-1", createdAt=None, updatedAt=None,
    )

    data = _interaction_model_to_dict(interaction)

    assert data["resultado"] == "Interesado"
    assert data["proximaAccion"] == "Enviar cotizacion"


def test_opportunity_serializer_keeps_descripcion():
    opportunity = SimpleNamespace(
        id="o-1", clienteId="c-1", titulo="Lote vacunas", descripcion="Compra anual", etapa="nuevo",
        valorEstimado=1000.0, probabilidad=20, vendedorUid="u-1", createdAt=None, updatedAt=None,
    )

    assert _opportunity_model_to_dict(opportunity)["descripcion"] == "Compra anual"


def test_proposal_serializer_keeps_notas():
    proposal = SimpleNamespace(
        id="p-1", clienteId="c-1", oportunidadId="o-1", titulo="Propuesta", montoNeto=100.0, descuentoPct=10.0,
        estado="borrador", notas="Pago a 30 dias", vendedorUid="u-1", montoDescuento=10.0, montoTotal=90.0,
        createdAt=None, updatedAt=None,
    )

    assert _proposal_model_to_dict(proposal)["notas"] == "Pago a 30 dias"
