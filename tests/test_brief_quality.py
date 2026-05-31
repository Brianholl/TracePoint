"""
Tests de modules/brief_quality.py — contra-métrica anti-tokenmaxxing.

Scorer puro: sin red, sin estado. Todos los casos son deterministas.
Cubre las dos señales que importan:
  - unsupported_specifics (fabricación = análogo de falsa atribución)
  - filler_density (relleno por 1k palabras, NO longitud absoluta)
"""
from modules.brief_quality import score_brief

SOURCE = {
    "results": {
        "profiles": [
            {"platform": "GitHub", "url": "https://github.com/jdoe", "status": "found"},
        ],
        "email": "jdoe@example.com",
    }
}


def test_brief_with_only_supported_specifics_has_no_unsupported():
    brief = "El usuario jdoe@example.com tiene perfil en https://github.com/jdoe."
    r = score_brief(brief, SOURCE)
    assert r["unsupported_specifics"] == []
    assert r["unsupported_rate"] == 0.0
    assert r["evidence_items"] == 2  # email + url


def test_fabricated_email_is_flagged_as_unsupported():
    # @inventado y correo fantasma: NO están en los datos → fabricación
    brief = "También se halló fake@phantom.org y el handle @inventado."
    r = score_brief(brief, SOURCE)
    assert "fake@phantom.org" in r["unsupported_specifics"]
    assert "@inventado" in r["unsupported_specifics"]
    assert r["unsupported_rate"] == 1.0


def test_mixed_supported_and_fabricated():
    brief = "Perfil real https://github.com/jdoe y otro falso https://evil.test/x."
    r = score_brief(brief, SOURCE)
    assert "https://evil.test/x" in r["unsupported_specifics"]
    assert "https://github.com/jdoe" not in r["unsupported_specifics"]
    assert r["specifics_in_brief"] == 2
    assert r["unsupported_rate"] == 0.5


def test_url_trailing_slash_is_normalized():
    brief = "Ver https://github.com/jdoe/ (con slash final)."
    r = score_brief(brief, SOURCE)
    assert r["unsupported_specifics"] == []


def test_filler_density_detected():
    brief = (
        "Es importante destacar que el perfil existe. Cabe mencionar que hay datos. "
        "It is worth noting the presence online."
    )
    r = score_brief(brief, SOURCE)
    assert r["filler_hits"] == 3
    assert r["filler_density"] > 0


def test_filler_density_is_rate_not_count():
    # Mismo # de muletillas, pero diluidas en mucho texto → densidad menor.
    base = "es importante destacar que hay un dato real. "
    short = score_brief(base, SOURCE)
    long = score_brief(base + ("palabra " * 200), SOURCE)
    assert short["filler_hits"] == long["filler_hits"] == 1
    assert long["filler_density"] < short["filler_density"]


def test_clean_dense_brief_scores_well():
    brief = "jdoe@example.com activo en https://github.com/jdoe. Riesgo bajo."
    r = score_brief(brief, SOURCE)
    assert r["unsupported_rate"] == 0.0
    assert r["filler_hits"] == 0
    assert r["evidence_items"] == 2


def test_empty_brief_does_not_crash():
    r = score_brief("", SOURCE)
    assert r["word_count"] == 0
    assert r["unsupported_specifics"] == []
    assert r["unsupported_rate"] == 0.0
    assert r["filler_density"] == 0.0


def test_handles_in_emails_not_double_counted():
    # El '@example.com' de un correo NO debe contarse como handle '@example'.
    brief = "Contacto: jdoe@example.com."
    r = score_brief(brief, SOURCE)
    assert r["specifics_in_brief"] == 1  # solo el email
    assert r["unsupported_specifics"] == []


def test_none_brief_is_safe():
    r = score_brief(None, SOURCE)
    assert r["word_count"] == 0
