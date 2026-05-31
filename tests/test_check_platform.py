"""
Tests del clasificador `check_platform` (modules/search_usernames.py).

Es un árbol de decisión puro sobre (status_code, body, url final). Estabilizar
estos veredictos estabiliza toda la UI de resultados y el KPI de detección.
Cada caso inyecta un client mockeado — cero red real.
"""
import httpx
import pytest

from modules.search_usernames import check_platform
from tests._helpers import (
    static_client,
    redirect_client,
    raising_client,
    platform,
)

USERNAME = "jdoe"


async def _status(client, plat):
    """Corre check_platform y devuelve el 'status' (o None si retornó None)."""
    result = await check_platform(client, USERNAME, plat)
    return result["status"] if result is not None else None


# ─── Cortocircuitos por status code (válidos para todos los tipos) ──────────

@pytest.mark.parametrize("code,expected", [
    (429, "rate_limited"),
    (403, "blocked"),
    (404, "not_found"),
])
async def test_status_code_shortcuts(code, expected):
    client = static_client(code)
    assert await _status(client, platform(ptype="text")) == expected


# ─── type '404' ─────────────────────────────────────────────────────────────

async def test_type_404_ok_is_found():
    assert await _status(static_client(200), platform(ptype="404")) == "found"

async def test_type_404_other_status_is_none():
    # 500 no cae en los cortocircuitos → la rama '404' devuelve None
    assert await _status(static_client(500), platform(ptype="404")) is None


# ─── type 'api' (GitHub API) ────────────────────────────────────────────────

async def test_type_api_login_field_is_found():
    client = static_client(200, text='{"login": "jdoe"}')
    assert await _status(client, platform(ptype="api")) == "found"

async def test_type_api_message_not_found():
    client = static_client(200, text='{"message": "Not Found"}')
    assert await _status(client, platform(ptype="api")) == "not_found"

async def test_type_api_non_200_is_not_found():
    assert await _status(static_client(500), platform(ptype="api")) == "not_found"


# ─── type 'facebook' ────────────────────────────────────────────────────────

async def test_facebook_redirect_to_login():
    client = redirect_client("https://facebook.test/login")
    assert await _status(client, platform(name="Facebook", ptype="facebook")) == "redirect_login"

async def test_facebook_ok_is_found():
    assert await _status(static_client(200), platform(name="Facebook", ptype="facebook")) == "found"


# ─── type 'linkedin' ────────────────────────────────────────────────────────

async def test_linkedin_redirect_to_login():
    client = redirect_client("https://linkedin.test/login")
    assert await _status(client, platform(name="LinkedIn", ptype="linkedin")) == "redirect_login"

async def test_linkedin_search_redirect_is_not_found():
    client = redirect_client("https://linkedin.test/search/results")
    assert await _status(client, platform(name="LinkedIn", ptype="linkedin")) == "not_found"

async def test_linkedin_ok_is_found():
    assert await _status(static_client(200), platform(name="LinkedIn", ptype="linkedin")) == "found"


# ─── type 'telegram' ────────────────────────────────────────────────────────

async def test_telegram_view_marker_is_found():
    client = static_client(200, text="Telegram: View @jdoe")
    assert await _status(client, platform(name="Telegram", ptype="telegram")) == "found"

async def test_telegram_contact_marker_is_not_found():
    client = static_client(200, text="Contact @jdoe on Telegram")
    assert await _status(client, platform(name="Telegram", ptype="telegram")) == "not_found"

async def test_telegram_ambiguous_is_unverified():
    client = static_client(200, text="<html>algo neutro</html>")
    assert await _status(client, platform(name="Telegram", ptype="telegram")) == "unverified"


# ─── type 'medium' ──────────────────────────────────────────────────────────

async def test_medium_username_in_title_is_found():
    client = static_client(200, text="<title>jdoe – Medium</title>")
    assert await _status(client, platform(name="Medium", ptype="medium")) == "found"

async def test_medium_username_absent_is_not_found():
    client = static_client(200, text="<title>Medium</title>")
    assert await _status(client, platform(name="Medium", ptype="medium")) == "not_found"


# ─── type 'pinterest' ───────────────────────────────────────────────────────

async def test_pinterest_profile_title_is_found():
    client = static_client(200, text="<title>jdoe profile</title>")
    assert await _status(client, platform(name="Pinterest", ptype="pinterest")) == "found"

async def test_pinterest_not_found_indicator():
    client = static_client(200, text="Sorry, couldn't find that page")
    assert await _status(client, platform(name="Pinterest", ptype="pinterest")) == "not_found"

async def test_pinterest_redirect_away():
    client = redirect_client("https://other.test/home", final_status=200)
    assert await _status(client, platform(name="Pinterest", ptype="pinterest")) == "redirect_away"

async def test_pinterest_ambiguous_is_unverified():
    client = static_client(200, text="<title>algo</title>")
    assert await _status(client, platform(name="Pinterest", ptype="pinterest")) == "unverified"


# ─── type 'reddit' ──────────────────────────────────────────────────────────

async def test_reddit_rate_limit_in_body():
    client = static_client(200, text="please wait for verification")
    assert await _status(client, platform(name="Reddit", ptype="reddit")) == "rate_limited"

async def test_reddit_not_found_indicator():
    client = static_client(200, text="Sorry, nobody on Reddit goes by that name")
    assert await _status(client, platform(name="Reddit", ptype="reddit")) == "not_found"

async def test_reddit_default_is_unverified():
    client = static_client(200, text="<html>u/jdoe</html>")
    assert await _status(client, platform(name="Reddit", ptype="reddit")) == "unverified"


# ─── type 'twitter' (página x.com) ──────────────────────────────────────────

async def test_twitter_account_does_not_exist():
    client = static_client(200, text="This account doesn't exist")
    assert await _status(client, platform(name="X", ptype="twitter")) == "not_found"

async def test_twitter_redirect_to_login():
    client = redirect_client("https://x.test/i/flow/login")
    assert await _status(client, platform(name="X", ptype="twitter")) == "redirect_login"

async def test_twitter_default_is_unverified():
    client = static_client(200, text="<html>tweets</html>")
    assert await _status(client, platform(name="X", ptype="twitter")) == "unverified"


# ─── type 'spa' (no verificable por GET simple) ─────────────────────────────

async def test_spa_always_unverified():
    assert await _status(static_client(200), platform(name="TikTok", ptype="spa")) == "unverified"


# ─── type 'text' (default) ──────────────────────────────────────────────────

async def test_text_clean_200_is_found():
    client = static_client(200, text="<title>jdoe</title> welcome")
    assert await _status(client, platform(ptype="text", not_found=["Not Found"])) == "found"

async def test_text_not_found_indicator():
    client = static_client(200, text="<title>Not Found</title>")
    assert await _status(client, platform(ptype="text", not_found=["Not Found"])) == "not_found"

async def test_text_cloudflare_challenge_is_blocked():
    client = static_client(200, text="<title>Just a moment...</title>")
    assert await _status(client, platform(ptype="text", not_found=[])) == "blocked"

async def test_text_redirect_to_login():
    client = redirect_client("https://testsite.test/auth/login")
    assert await _status(client, platform(ptype="text", not_found=[])) == "redirect_login"

async def test_text_redirect_away_without_username():
    client = redirect_client("https://other.test/home", final_status=200)
    assert await _status(client, platform(ptype="text", not_found=[])) == "redirect_away"

async def test_text_error_status_is_not_found():
    client = static_client(500, text="<title>boom</title>")
    assert await _status(client, platform(ptype="text", not_found=[])) == "not_found"


# ─── Ramas de borde adicionales del árbol de decisión ───────────────────────

async def test_facebook_server_error_is_not_found():
    assert await _status(static_client(500), platform(name="Facebook", ptype="facebook")) == "not_found"

async def test_linkedin_server_error_is_not_found():
    assert await _status(static_client(500), platform(name="LinkedIn", ptype="linkedin")) == "not_found"

async def test_telegram_does_not_appear_to_exist():
    client = static_client(200, text="If you have Telegram, you can contact ... doesn't appear to exist")
    assert await _status(client, platform(name="Telegram", ptype="telegram")) == "not_found"

async def test_telegram_non_200_is_not_found():
    assert await _status(static_client(500), platform(name="Telegram", ptype="telegram")) == "not_found"

async def test_medium_non_200_is_not_found():
    assert await _status(static_client(500), platform(name="Medium", ptype="medium")) == "not_found"

async def test_pinterest_non_200_is_none():
    assert await _status(static_client(500), platform(name="Pinterest", ptype="pinterest")) is None

async def test_reddit_redirect_away():
    client = redirect_client("https://other.test/home", final_status=200)
    assert await _status(client, platform(name="Reddit", ptype="reddit")) == "redirect_away"

async def test_text_error_in_title_is_not_found():
    client = static_client(200, text="<title>Error 500 internal</title>")
    assert await _status(client, platform(ptype="text", not_found=[])) == "not_found"


# ─── Manejo de fallos de red ────────────────────────────────────────────────

async def test_timeout_is_classified():
    client = raising_client(httpx.TimeoutException("slow"))
    assert await _status(client, platform(ptype="text")) == "timeout"

async def test_request_error_is_classified():
    client = raising_client(httpx.ConnectError("no route"))
    assert await _status(client, platform(ptype="text")) == "error"

async def test_unexpected_exception_is_classified():
    # Cualquier excepción no-httpx también se degrada a 'error', no propaga
    client = raising_client(ValueError("kaboom"))
    assert await _status(client, platform(ptype="text")) == "error"
