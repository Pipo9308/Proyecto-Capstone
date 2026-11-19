"""Filtros para que el chat responda solo sobre animales y productos veterinarios, nunca sobre personas.

Son una capa mas, junto a la regla del prompt: ninguna basta sola. Entrada: se corta antes de llamar al modelo.
Salida: se revisa la respuesta ya generada. Los patrones buscan medicina para PERSONAS, no las advertencias
al operador de las fichas ("no usar en personas"), que se permiten.
shortcut: palabras clave; da falsos positivos/negativos raros, medirlos con preguntas reales y ajustar los patrones.
Misma logica en Enci-Ventas (app/services/solo_animales.py): si cambia una, cambiar la otra."""
import logging
import re
import unicodedata

logger = logging.getLogger(__name__)

FRASE_FIJA = (
    "Solo respondo consultas sobre animales y productos veterinarios. No puedo dar información médica, dosis ni "
    "recomendaciones para personas; consulta a un profesional de la salud."
)
FRASE_FIJA_EN = (
    "I only answer questions about animals and veterinary products. I can't give medical information, doses or "
    "recommendations for people; please consult a healthcare professional."
)


def frase_fija(idioma: str | None = "es") -> str:
    return FRASE_FIJA_EN if idioma == "en" else FRASE_FIJA


def _norm(texto: str) -> str:
    sin_tildes = unicodedata.normalize("NFKD", texto.lower())
    return "".join(c for c in sin_tildes if not unicodedata.combining(c))


_PERSONA = (
    r"(?:personas?|humanos?|seres humanos|adultos?|ninos?|ninas?|bebes?|embarazadas?|"
    r"mi (?:hij[oa]s?|espos[ao]|madre|padre|mama|papa|abuel[oa]|hermano|hermana|bebe|pareja)|"
    r"people|humans?|adults?|child(?:ren)?|kids?|my (?:son|daughter|baby|wife|husband|mother|father|kid))"
)
_ACCION = (
    r"(?:dosis|dosificacion|tratamiento|tomar|tomaria|inyectar|administrar|recetar|medicar|curar|ponerse|darle|ingerir|"
    r"dose|dosage|treatment|treat|take|inject|give)"
)
_ACCION_DOSIS = r"(?:dosis|tomar|tomaria|ponerse|inyectarse|ingerir|darle|dose|take)"
_ANIMAL = re.compile(
    r"\b(?:perros?|gatos?|caninos?|felinos?|bovinos?|vacas?|terneros?|caballos?|equinos?|cerdos?|porcinos?|"
    r"ovejas?|ovinos?|cabras?|caprinos?|aves?|pollos?|gallinas?|animal(?:es)?|mascotas?|ganado|"
    r"dogs?|cats?|cows?|horses?|pigs?|sheep|pets?|livestock|cattle)\b"
)

# Dosis/tratamiento para una persona. No se corta si la frase habla de un animal (ej. "dosis para el perro de mi hijo").
_DOSIS_PERSONA = [
    re.compile(rf"\b{_ACCION}\b.{{0,60}}\b{_PERSONA}\b"),
    re.compile(rf"\b{_PERSONA}\b.{{0,60}}\b{_ACCION_DOSIS}\b"),
    re.compile(r"\b(?:paciente humano|human patient|medicina humana|human medicine|uso humano|human use)\b"),
]
# Exposicion o consumo propio: se corta aunque mencione un animal (ej. "me inyecte la ivermectina del perro").
_EXPOSICION_PROPIA = re.compile(
    r"\b(?:yo|me)\s+(?:me\s+)?(?:tome|tomo|inyecte|inyecto|pique|trague|mordio|clave|i\s+(?:took|injected|swallowed))\b"
    r"|\bi\s+(?:took|injected|swallowed|got\s+(?:bitten|pricked))\b"
)


def consulta_humana(pregunta: str) -> bool:
    """True si la pregunta pide medicina o dosis para una persona."""
    texto = _norm(pregunta)
    if _EXPOSICION_PROPIA.search(texto):
        return True
    if _ANIMAL.search(texto):
        return False
    return any(p.search(texto) for p in _DOSIS_PERSONA)


_SALIDA = [
    re.compile(r"\b(?:dosis|dosificacion|tratamiento|uso)\b[^.\n]{0,50}\b(?:en|para)\s+(?:humanos|personas|adultos|ninos|seres humanos)\b"),
    re.compile(r"\b(?:dose|dosage|treatment)\b[^.\n]{0,50}\b(?:in|for)\s+(?:humans|people|adults|children)\b"),
    re.compile(r"\b(?:paciente humano|human patient)\b"),
    re.compile(r"\bconsult[ae]\s+(?:a|con)\s+(?:su|un)\s+medico\b(?!\s+veterinari)"),
]
_NEGACION_PREVIA = re.compile(r"\b(?:no|nunca|evit\w*|prohibid\w*|contraindicad\w*|not|never)\b")
_NEGACION_POSTERIOR = re.compile(r"^[^.\n]{0,25}\b(?:no (?:esta|se|debe|puede|recomend\w*)|contraindicad\w*|prohibid\w*|not (?:recommended|for))")


def respuesta_humana(respuesta: str) -> bool:
    """True si la respuesta da medicina o dosis para personas (las advertencias "no usar en personas" no cuentan)."""
    texto = _norm(respuesta)
    for patron in _SALIDA:
        for m in patron.finditer(texto):
            if not (_NEGACION_PREVIA.search(texto[max(0, m.start() - 25):m.start()]) or _NEGACION_POSTERIOR.search(texto[m.end():])):
                return True
    return False


def registrar(motivo: str, texto: str) -> None:
    logger.info("Solo animales: %s (%.80s)", motivo, texto.replace("\n", " "))
