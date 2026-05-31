import httpx
import json
import base64
from pathlib import Path
from config import config

SYSTEM_PROMPT_TEXT = """Eres un analista de inteligencia OSINT experto. Tu trabajo es analizar toda la información 
recolectada sobre una persona y producir un perfil completo y detallado.

Debes:
1. Correlacionar toda la información encontrada
2. Identificar conexiones entre diferentes fuentes
3. Detectar posibles inconsistencias o datos falsos
4. Generar un perfil unificado de la persona
5. Estimar nivel de confianza de cada hallazgo
6. Sugerir siguientes pasos de investigación
7. Identificar riesgos de seguridad o privacidad

Sé objetivo, metódico y profesional. Cuando no tengas suficiente información, indícalo claramente.
No inventes datos. Basa todo tu análisis únicamente en la información proporcionada."""

SYSTEM_PROMPT_VISION = """Eres un analista de inteligencia OSINT con capacidades de análisis visual. 
Tu trabajo es analizar una fotografía junto con información recolectada sobre una persona.

Debes:
1. Analizar la fotografía proporcionada (personas, lugares, objetos, texto visible, metadatos visuales)
2. Correlacionar los elementos visuales con los datos OSINT recolectados
3. Identificar posibles coincidencias entre la foto y los perfiles encontrados
4. Determinar nivel de confianza de la coincidencia visual
5. Detectar posibles inconsistencias entre la foto y los datos
6. Sugerir siguientes pasos de investigación basados en pistas visuales

Sé objetivo y metódico. No inventes personas o detalles que no puedas confirmar visualmente.
Si la foto no es clara o no hay suficiente información visual, indícalo."""

_MODEL_MAP = {
    'text': config.OPENROUTER_MODEL_TEXT,
    'vision': config.OPENROUTER_MODEL_VISION,
    'extreme': config.OPENROUTER_MODEL_EXTREME,
}

_MODEL_LABELS = {
    config.OPENROUTER_MODEL_TEXT: config.MODEL_TEXT_LABEL,
    config.OPENROUTER_MODEL_VISION: config.MODEL_VISION_LABEL,
    config.OPENROUTER_MODEL_EXTREME: config.MODEL_EXTREME_LABEL,
}

def _select_model(has_image: bool = False, profile_count: int = 0) -> str:
    if has_image:
        return _MODEL_MAP['vision']
    if profile_count > 50:
        return _MODEL_MAP['extreme']
    return _MODEL_MAP['text']

def _model_label(model: str) -> str:
    return _MODEL_LABELS.get(model, model.split('/')[-1])

async def analyze_results(search_data: dict, image_path: str = None) -> str:
    if not config.OPENROUTER_API_KEY:
        return "**AI Analysis unavailable**: No OpenRouter API key configured. Set OPENROUTER_API_KEY in .env file."

    has_image = image_path is not None and Path(image_path).exists()
    results = search_data.get('results', {})
    profile_count = 0
    if isinstance(results, dict):
        for v in results.values():
            if isinstance(v, dict):
                profile_count += len(v.get('profiles', [])) if isinstance(v.get('profiles'), list) else 0
                profile_count += int(v.get('total_found', 0))
                profile_count += len(v.get('found_profiles', [])) if isinstance(v.get('found_profiles'), list) else 0

    model = _select_model(has_image=has_image, profile_count=profile_count)
    prompt = _build_prompt(search_data)

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            messages = [
                {'role': 'system', 'content': SYSTEM_PROMPT_VISION if has_image else SYSTEM_PROMPT_TEXT},
            ]

            user_content = []
            if has_image:
                with open(image_path, 'rb') as f:
                    img_b64 = base64.b64encode(f.read()).decode()
                    ext = Path(image_path).suffix.lstrip('.') or 'jpeg'
                    if ext.lower() == 'jpg':
                        ext = 'jpeg'
                    user_content.append({
                        'type': 'image_url',
                        'image_url': {'url': f'data:image/{ext};base64,{img_b64}'},
                    })
            user_content.append({'type': 'text', 'text': prompt})
            messages.append({'role': 'user', 'content': user_content})

            payload = {
                'model': model,
                'messages': messages,
                'temperature': 0.3,
                'max_tokens': 4096,
            }

            resp = await client.post(
                f'{config.OPENROUTER_BASE_URL}/chat/completions',
                headers={
                    'Authorization': f'Bearer {config.OPENROUTER_API_KEY}',
                    'Content-Type': 'application/json',
                    'HTTP-Referer': config.OPENROUTER_SITE_URL,
                    'X-Title': config.OPENROUTER_SITE_NAME,
                },
                json=payload,
            )

            if resp.status_code == 200:
                data = resp.json()
                analysis = data['choices'][0]['message']['content']
                tag = _model_label(model)
                return f'> *AI Analysis powered by **{tag}** — model: `{model}`*\n\n---\n\n{analysis}'
            elif resp.status_code == 401:
                return "**AI Error**: Invalid API key. Check your OpenRouter API key."
            else:
                return f"**AI Error**: {resp.status_code} - {resp.text[:500]}"

    except httpx.TimeoutException:
        return "**AI Error**: Request timed out. The AI model may be overloaded."
    except Exception as e:
        return f"**AI Error**: {str(e)[:500]}"

def _build_prompt(search_data: dict) -> str:
    parts = []
    parts.append(f"# OSINT Investigation Report - {search_data.get('query_type', 'Unknown')}: {search_data.get('query_value', 'Unknown')}")
    parts.append("")

    results = search_data.get('results', {})

    if search_data.get('query_type') == 'username':
        parts.append("## Username Search Results")
        profiles = results.get('profiles', [])
        found = [p for p in profiles if p.get('status') == 'found']
        parts.append(f"Total platforms checked: {len(profiles)}")
        parts.append(f"Profiles found: {len(found)}")
        for p in found[:20]:
            parts.append(f"- {p['platform']}: {p['url']}")

        social = results.get('social_analysis', {})
        if social:
            parts.append("### Social Profile Analysis")
            for prof in social.get('profiles_analyzed', []):
                if prof.get('info') or prof.get('bio'):
                    parts.append(f"**{prof['platform']}**: {json.dumps(prof['info'] or {'bio': prof.get('bio')}, indent=2)}")
            common = social.get('common_info', {})
            if common.get('locations'):
                parts.append(f"Possible locations: {', '.join(common['locations'])}")
            if common.get('possible_names'):
                parts.append(f"Possible names: {', '.join(common['possible_names'])}")

    elif search_data.get('query_type') == 'email':
        parts.append("## Email Search Results")
        parts.append(f"Email: {results.get('email', '')}")
        parts.append(f"Risk Score: {results.get('risk_score', 0)}/100")

        gravatar = results.get('gravatar')
        if gravatar:
            parts.append(f"### Gravatar Profile Found")
            for k, v in gravatar.items():
                if v and k not in ('hash',):
                    parts.append(f"- {k}: {v}")

        hibp = results.get('hibp')
        if hibp:
            parts.append(f"### Data Breaches: {hibp.get('total_breaches', 0)} found")
            for b in hibp.get('breaches', []):
                parts.append(f"- {b.get('name')} ({b.get('date')}): {', '.join(b.get('data_classes', []))}")

        mentions = results.get('web_mentions', [])
        if mentions:
            parts.append(f"### Web Mentions: {len(mentions)}")
            for m in mentions[:10]:
                parts.append(f"- {m.get('title')}: {m.get('url')}")

    elif search_data.get('query_type') == 'name':
        parts.append("## Name Search Results")
        parts.append(f"Name: {results.get('name', '')}")
        parts.append(f"Total results: {results.get('total_results', 0)}")
        if results.get('profiles'):
            parts.append(f"### Social Profiles Found: {len(results['profiles'])}")
            for p in results['profiles'][:10]:
                parts.append(f"- {p.get('title')}: {p.get('url')}")
        if results.get('web_results'):
            parts.append(f"### Web Mentions: {len(results['web_results'])}")
            for r in results['web_results'][:10]:
                parts.append(f"- {r.get('title')}: {r.get('url')}")

    elif search_data.get('query_type') == 'phone':
        parts.append("## Phone Search Results")
        parts.append(f"Phone: {results.get('phone', '')}")
        parts.append(f"Valid: {results.get('valid', False)}")
        parts.append(f"Formatted: {results.get('formatted', '')}")
        parts.append(f"Country: {results.get('country', '')}")
        parts.append(f"Carrier: {results.get('carrier', '')}")
        parts.append(f"Location: {results.get('location', '')}")
        if results.get('timezones'):
            parts.append(f"Timezones: {', '.join(results['timezones'])}")

    if isinstance(results, dict):
        image_social = results.get('image_social', {})
        if image_social and image_social.get('found_profiles'):
            parts.append("## Image Reverse Search Results")
            parts.append(f"Photo analyzed: {image_social.get('photo', 'N/A')[:100]}")
            parts.append(f"Total candidates: {image_social.get('total_candidates', 0)}")
            parts.append(f"Verified profiles: {image_social.get('total_verified', 0)}")
            for p in image_social.get('found_profiles', [])[:10]:
                parts.append(f"- {p['platform']}: {p['url']} (status: {p.get('status', 'unknown')})")

    parts.append("")
    parts.append("## Instrucciones de análisis")
    parts.append("Reglas (obligatorias):")
    parts.append("- Sé conciso y denso en información. NO repitas los datos crudos ya listados arriba ni agregues relleno.")
    parts.append("- Incluí una sección SOLO si hay evidencia para sostenerla. Si no, omitila o escribí una sola línea 'Sin datos suficientes'. Nunca infles para completar.")
    parts.append("- Toda afirmación debe poder rastrearse a un hallazgo concreto de los datos. Distinguí hecho observado de inferencia (marcá la inferencia como tal).")
    parts.append("- NO introduzcas datos específicos (nombres, correos, @usuarios, URLs, fechas, ubicaciones) que no aparezcan en los datos recolectados.")
    parts.append("- Ajustá la profundidad al volumen de datos: pocos datos → informe corto.")
    parts.append("")
    parts.append("Cubrí, solo en la medida que los datos lo permitan:")
    parts.append("1. **Resumen ejecutivo** (2-4 frases)")
    parts.append("2. **Huella digital**: qué revela la presencia online encontrada")
    parts.append("3. **Correlaciones** entre fuentes (solo si hay >1 fuente)")
    parts.append("4. **Riesgos** de privacidad/seguridad identificados")
    parts.append("5. **Nivel de confianza** (Bajo/Medio/Alto) y por qué")
    parts.append("6. **Próximos pasos** sugeridos")

    if image_social and image_social.get('found_profiles'):
        parts.append("")
        parts.append("### Visual Analysis Instructions")
        parts.append("Since a photo was also provided, please additionally:")
        parts.append("1. Describe what you can identify from the photo (visible features, setting, objects)")
        parts.append("2. Correlate visual elements with the OSINT data found")
        parts.append("3. Note any discrepancies between the photo and the digital profile")
        parts.append("4. Assess confidence level of linking the photo to the identified person")

    return '\n'.join(parts)
