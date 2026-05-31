"""
Contra-métrica anti-tokenmaxxing para el brief generado por la IA.

`tokenmaxxing` = inflar la salida (longitud, relleno, falsa exhaustividad) como
proxy de calidad. No medimos longitud como objetivo (eso *sería* Goodhart: un
informe corto y denso es bueno, uno largo y vacío es malo). Medimos dos señales
que un modelo no puede satisfacer inflando:

  1. **unsupported_specifics** — específicos (correos, @usuarios, URLs) que
     aparecen en el brief pero NO en los datos recolectados. Es el análogo
     generativo de la *falsa atribución*: el modelo inventó un dato. Atado al
     guardrail CARDINAL del KPI (falsa atribución ≤5%). Inflar el texto solo
     EMPEORA esta señal, nunca la mejora.

  2. **filler_density** — densidad de muletillas/relleno por cada 1000 palabras.
     Lista curada (es+en) de frases de cortesía vacía. Es densidad, no conteo
     absoluto: un brief largo legítimo no se penaliza si el relleno está diluido.

Scorer PURO: sin red, sin estado. Entra (brief_text, source_results) y sale un
dict de métricas. Testeable de forma determinista.
"""
import json
import re

# Específicos rastreables: si el brief los nombra, deben estar en los datos.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_HANDLE_RE = re.compile(r"(?<![\w@/])@[A-Za-z0-9_]{2,}")
_URL_RE = re.compile(r"https?://[^\s)\]}>\"']+")

# Muletillas de relleno (cortesía vacía / falsa exhaustividad). Curada a mano:
# frases que aportan volumen sin información. Minúsculas; match por substring.
_FILLER_PHRASES = (
    # español
    "es importante destacar",
    "es importante mencionar",
    "es importante señalar",
    "cabe destacar",
    "cabe mencionar",
    "cabe señalar",
    "en resumen",
    "en conclusión",
    "como se mencionó anteriormente",
    "como ya se mencionó",
    "vale la pena mencionar",
    "vale la pena destacar",
    "a modo de resumen",
    "dicho esto",
    "en este sentido",
    "en términos generales",
    "por lo general",
    "en última instancia",
    "es fundamental tener en cuenta",
    "no se puede pasar por alto",
    # inglés
    "it is important to note",
    "it's important to note",
    "it is worth noting",
    "it's worth noting",
    "it should be noted",
    "as mentioned above",
    "as previously mentioned",
    "in conclusion",
    "in summary",
    "needless to say",
    "at the end of the day",
    "it goes without saying",
)

_WORD_RE = re.compile(r"\S+")


def _normalize(s: str) -> str:
    """Minúsculas para comparación case-insensitive de específicos."""
    return s.lower()


def _extract_specifics(text: str) -> dict:
    """Específicos atómicos hallados en `text`, normalizados y deduplicados."""
    emails = {_normalize(m) for m in _EMAIL_RE.findall(text)}
    # La regex de URL es voraz: recortamos puntuación de cierre pegada (. , ; etc.).
    urls = {_normalize(m.rstrip(".,;:!?)\]}>\"'")) for m in _URL_RE.findall(text)}
    # Los handles no se buscan dentro de correos: removemos correos antes.
    text_no_emails = _EMAIL_RE.sub(" ", text)
    handles = {_normalize(m) for m in _HANDLE_RE.findall(text_no_emails)}
    return {"emails": emails, "handles": handles, "urls": urls}


def _flatten(source_results) -> str:
    """Aplana los datos recolectados a un único blob de texto buscable."""
    try:
        return json.dumps(source_results, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(source_results)


def score_brief(brief_text: str, source_results) -> dict:
    """
    Evalúa un brief de IA contra los datos que debió usar.

    Devuelve un dict con:
      - word_count
      - evidence_items: # de específicos del brief respaldados por los datos
      - specifics_in_brief: total de específicos nombrados en el brief
      - unsupported_specifics: específicos del brief AUSENTES en los datos
        (lista de strings) → fabricación → análogo generativo de falsa atribución
      - unsupported_rate: unsupported / specifics_in_brief (0.0 si no hay)
      - filler_hits: # de muletillas de relleno detectadas
      - filler_density: muletillas por cada 1000 palabras
    Scorer puro y determinista.
    """
    brief_text = brief_text or ""
    haystack = _normalize(_flatten(source_results))

    brief_spec = _extract_specifics(brief_text)
    all_specifics = sorted(brief_spec["emails"] | brief_spec["handles"] | brief_spec["urls"])

    supported, unsupported = [], []
    for spec in all_specifics:
        # Un específico está respaldado si aparece textualmente en los datos.
        # Para URLs normalizamos el slash final (suelen variar con/sin "/").
        needle = spec.rstrip("/") if spec.startswith("http") else spec
        if needle in haystack:
            supported.append(spec)
        else:
            unsupported.append(spec)

    words = _WORD_RE.findall(brief_text)
    word_count = len(words)

    low = _normalize(brief_text)
    filler_hits = sum(low.count(p) for p in _FILLER_PHRASES)
    filler_density = (filler_hits * 1000 / word_count) if word_count else 0.0

    specifics_in_brief = len(all_specifics)
    unsupported_rate = (len(unsupported) / specifics_in_brief) if specifics_in_brief else 0.0

    return {
        "word_count": word_count,
        "evidence_items": len(supported),
        "specifics_in_brief": specifics_in_brief,
        "unsupported_specifics": unsupported,
        "unsupported_rate": round(unsupported_rate, 4),
        "filler_hits": filler_hits,
        "filler_density": round(filler_density, 4),
    }
