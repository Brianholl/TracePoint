import httpx
import hashlib
from bs4 import BeautifulSoup
from config import config

HIBP_URL = 'https://haveibeenpwned.com/account/{}'
GOOGLE_DORK = 'https://www.google.com/search?q={}'

async def check_gravatar(email: str) -> dict | None:
    email_hash = hashlib.md5(email.lower().strip().encode()).hexdigest()
    gravatar_url = f'https://www.gravatar.com/{email_hash}.json'
    profile_url = f'https://gravatar.com/{email_hash}'

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(gravatar_url)
            if resp.status_code == 200:
                data = resp.json()
                entry = data.get('entry', [{}])[0]
                return {
                    'hash': email_hash,
                    'profile_url': profile_url,
                    'avatar': f'https://www.gravatar.com/avatar/{email_hash}?s=400',
                    'display_name': entry.get('displayName'),
                    'preferred_username': entry.get('preferredUsername'),
                    'about': entry.get('aboutMe'),
                    'current_location': entry.get('currentLocation'),
                    'urls': [u.get('value') for u in entry.get('urls', []) if u.get('value')],
                    'emails': [u.get('value') for u in entry.get('emails', []) if u.get('value')],
                    'phone_numbers': [u.get('value') for u in entry.get('phoneNumbers', []) if u.get('value')],
                    'accounts': [
                        {'domain': a.get('domain'), 'display': a.get('display'), 'url': a.get('url')}
                        for a in entry.get('accounts', [])
                    ],
                }
    except Exception:
        pass
    return None

async def check_hibp(email: str) -> dict:
    result = {'breaches': [], 'pastes': [], 'total_breaches': 0}
    if not config.HIBP_API_KEY:
        result['status'] = 'no_api_key'
        return result
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                f'https://haveibeenpwned.com/api/v3/breachedaccount/{email}',
                headers={'hibp-api-key': config.HIBP_API_KEY, 'user-agent': 'TracePoint'}
            )
            if resp.status_code == 200:
                result['breaches'] = [
                    {'name': b.get('Name'), 'domain': b.get('Domain'),
                     'date': b.get('BreachDate'), 'data_classes': b.get('DataClasses')}
                    for b in resp.json()
                ]
                result['total_breaches'] = len(result['breaches'])
            elif resp.status_code == 404:
                pass
            elif resp.status_code == 401:
                result['status'] = 'invalid_api_key'
    except Exception as e:
        result['error'] = str(e)[:200]
    return result

async def google_dork_email(email: str) -> list:
    results = []
    dork = f'"{email}"'
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.get(
                f'https://www.google.com/search?q={dork}',
                headers={'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}
            )
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                for link in soup.select('a[href^="/url?q="]')[:10]:
                    href = link.get('href', '')
                    if 'http' in href:
                        url = href.split('/url?q=')[1].split('&')[0] if '/url?q=' in href else href
                        title = link.get_text(strip=True) or url
                        results.append({'title': title, 'url': url})
    except Exception:
        pass
    return results

async def search_email(email: str) -> dict:
    results = {
        'email': email,
        'gravatar': None,
        'hibp': None,
        'web_mentions': [],
        'risk_score': 0,
    }

    gravatar_data = await check_gravatar(email)
    if gravatar_data:
        results['gravatar'] = gravatar_data

    hibp_data = await check_hibp(email)
    if hibp_data:
        results['hibp'] = hibp_data

    web_data = await google_dork_email(email)
    if web_data:
        results['web_mentions'] = web_data

    if results['hibp'] and results['hibp']['total_breaches'] > 0:
        results['risk_score'] += min(results['hibp']['total_breaches'] * 15, 60)
    if results['gravatar']:
        results['risk_score'] += 10
    if results['web_mentions']:
        results['risk_score'] += min(len(results['web_mentions']) * 5, 30)

    return results
