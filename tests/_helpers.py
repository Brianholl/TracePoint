"""
Helpers para tests: clients httpx servidos por un transporte mockeado.

Regla de oro del suite unitario: NUNCA tocar la red real. `check_platform`
recibe el `httpx.AsyncClient` por parámetro, así que basta con inyectarle un
client cuyo transporte devuelve respuestas predefinidas.
"""
from __future__ import annotations

import httpx


def client_for(handler) -> httpx.AsyncClient:
    """Client cuyo cada request lo resuelve `handler(request) -> httpx.Response`."""
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def static_client(status_code: int = 200, text: str = "", headers: dict | None = None) -> httpx.AsyncClient:
    """Devuelve siempre la misma respuesta para cualquier request (sin redirects)."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text=text, headers=headers or {})
    return client_for(handler)


def redirect_client(
    location: str,
    final_status: int = 200,
    final_text: str = "",
    final_headers: dict | None = None,
) -> httpx.AsyncClient:
    """
    302-redirige el primer salto a `location` y luego sirve la respuesta final.
    Permite que check_platform observe un `resp.url` distinto al solicitado
    (usa follow_redirects=True).
    """
    target = httpx.URL(location)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == target.host and request.url.path == target.path:
            return httpx.Response(final_status, text=final_text, headers=final_headers or {})
        return httpx.Response(302, headers={"Location": location})

    return client_for(handler)


def raising_client(exc: Exception) -> httpx.AsyncClient:
    """Client cuyo transporte levanta `exc` (para simular timeouts / errores de red)."""
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc
    return client_for(handler)


def platform(name: str = "TestSite", ptype: str = "text", not_found: list | None = None) -> dict:
    """Construye un dict de plataforma mínimo, desacoplado de la lista PLATFORMS real."""
    p = {"name": name, "url": "https://" + name.lower() + ".test/{username}", "type": ptype}
    if not_found is not None:
        p["not_found"] = not_found
    return p
