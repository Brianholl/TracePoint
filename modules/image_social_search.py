import httpx
import asyncio
import re
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urlparse

SOCIAL_PLATFORM_PATTERNS = [
    (r'(?:https?://)?(?:www\.)?instagram\.com/([a-zA-Z0-9_.]+)', 'Instagram'),
    (r'(?:https?://)?(?:www\.)?facebook\.com/([a-zA-Z0-9.]+)', 'Facebook'),
    (r'(?:https?://)?(?:www\.)?x\.com/([a-zA-Z0-9_]+)', 'X (Twitter)'),
    (r'(?:https?://)?(?:www\.)?twitter\.com/([a-zA-Z0-9_]+)', 'Twitter'),
    (r'(?:https?://)?(?:www\.)?tiktok\.com/@([a-zA-Z0-9_.]+)', 'TikTok'),
    (r'(?:https?://)?(?:www\.)?linkedin\.com/in/([a-zA-Z0-9-]+)', 'LinkedIn'),
    (r'(?:https?://)?(?:www\.)?youtube\.com/@([a-zA-Z0-9_.-]+)', 'YouTube'),
    (r'(?:https?://)?(?:www\.)?github\.com/([a-zA-Z0-9-]+)', 'GitHub'),
    (r'(?:https?://)?(?:www\.)?reddit\.com/user/([a-zA-Z0-9_-]+)', 'Reddit'),
    (r'(?:https?://)?(?:www\.)?pinterest\.com/([a-zA-Z0-9_-]+)', 'Pinterest'),
    (r'(?:https?://)?(?:www\.)?tumblr\.com/([a-zA-Z0-9_-]+)', 'Tumblr'),
    (r'(?:https?://)?(?:www\.)?twitch\.tv/([a-zA-Z0-9_]+)', 'Twitch'),
    (r'(?:https?://)?(?:www\.)?snapchat\.com/add/([a-zA-Z0-9_.]+)', 'Snapchat'),
    (r'(?:https?://)?(?:www\.)?telegram\.me/([a-zA-Z0-9_]+)', 'Telegram'),
    (r'(?:https?://)?(?:t\.me)/([a-zA-Z0-9_]+)', 'Telegram'),
    (r'(?:https?://)?(?:www\.)?whatsapp\.com/(?:send/?\?phone=)?([0-9]+)', 'WhatsApp'),
    (r'(?:https?://)?(?:www\.)?threads\.net/@([a-zA-Z0-9_.]+)', 'Threads'),
    (r'(?:https?://)?(?:www\.)?vk\.com/([a-zA-Z0-9_.]+)', 'VK'),
    (r'(?:https?://)?(?:www\.)?steamcommunity\.com/id/([a-zA-Z0-9_-]+)', 'Steam'),
    (r'(?:https?://)?(?:www\.)?medium\.com/@([a-zA-Z0-9_.-]+)', 'Medium'),
    (r'(?:https?://)?(?:www\.)?flickr\.com/people/([a-zA-Z0-9@_/-]+)', 'Flickr'),
    (r'(?:https?://)?(?:www\.)?deviantart\.com/([a-zA-Z0-9_-]+)', 'DeviantArt'),
    (r'(?:https?://)?(?:www\.)?behance\.net/([a-zA-Z0-9_-]+)', 'Behance'),
    (r'(?:https?://)?(?:www\.)?dribbble\.com/([a-zA-Z0-9_-]+)', 'Dribbble'),
    (r'(?:https?://)?(?:www\.)?soundcloud\.com/([a-zA-Z0-9_-]+)', 'SoundCloud'),
    (r'(?:https?://)?(?:www\.)?spotify\.com/user/([a-zA-Z0-9_-]+)', 'Spotify'),
    (r'(?:https?://)?(?:www\.)?patreon\.com/([a-zA-Z0-9_-]+)', 'Patreon'),
    (r'(?:https?://)?(?:www\.)?onlyfans\.com/([a-zA-Z0-9_-]+)', 'OnlyFans'),
    (r'(?:https?://)?(?:www\.)?discord\.com/users/([0-9]+)', 'Discord'),
]

SEARCH_ENGINES = {
    'google_lens': 'https://lens.google.com/uploadbyurl?url={image_url}',
    'yandex': 'https://yandex.com/images/search?url={image_url}&rpt=imageview',
    'bing': 'https://www.bing.com/images/search?view=detailv2&iss=sbi&FORM=IRSBIQ&q=imgurl:{image_url}',
    'tineye': 'https://tineye.com/search/?url={image_url}',
}

async def search_social_by_image(image_path: str = None, image_url: str = None) -> dict:
    result = {
        'photo': image_url or image_path,
        'found_profiles': [],
        'total_candidates': 0,
        'total_verified': 0,
        'engines_used': [],
        'error': None,
        'thumbnail': image_url or '',
    }

    if not image_path and not image_url:
        result['error'] = 'No image provided'
        return result

    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    }

    async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=25) as client:
        tasks = []
        engine_configs = []

        # Local URLs (e.g. /uploads/...) are not reachable by external search engines
        if image_url and image_url.startswith('/'):
            result['error'] = 'reverse_image_unavailable_local'
            return result

        if image_url:
            for engine_name, url_tpl in SEARCH_ENGINES.items():
                search_url = url_tpl.format(image_url=quote_plus(image_url))
                tasks.append(_scrape_engine(client, engine_name, search_url))
                engine_configs.append(engine_name)

            responses = await asyncio.gather(*tasks, return_exceptions=True)

            all_links = []
            for engine_name, resp in zip(engine_configs, responses):
                if isinstance(resp, list):
                    result['engines_used'].append(engine_name)
                    all_links.extend(resp)

            seen = set()
            unique_links = []
            for link in all_links:
                normalized = link.rstrip('/').lower()
                if normalized not in seen:
                    seen.add(normalized)
                    unique_links.append(link)

            candidates_by_platform = {}
            for link in unique_links:
                for pattern, platform in SOCIAL_PLATFORM_PATTERNS:
                    m = re.search(pattern, link, re.IGNORECASE)
                    if m:
                        username = m.group(1)
                        if platform not in candidates_by_platform:
                            candidates_by_platform[platform] = set()
                        candidates_by_platform[platform].add((username, link))
                        break

            result['total_candidates'] = sum(len(v) for v in candidates_by_platform.values())

            verify_tasks = []
            verify_configs = []
            from modules.search_usernames import check_platform, PLATFORMS as PLATFORMS_DICT

            for platform_name, entries in candidates_by_platform.items():
                for username, full_url in entries:
                    platform_cfg = None
                    for p in PLATFORMS_DICT:
                        if p['name'].lower() == platform_name.lower() or platform_name.lower() in p['name'].lower():
                            platform_cfg = p
                            break
                    if not platform_cfg:
                        platform_cfg = {'name': platform_name, 'url': full_url, 'type': 'text', 'not_found': ['Page not found', 'Not Found', 'doesn\'t exist']}

                    verify_tasks.append(check_platform(client, username, platform_cfg))
                    verify_configs.append((platform_name, username, full_url))

            verify_responses = await asyncio.gather(*verify_tasks, return_exceptions=True)

            for vcfg, vresp in zip(verify_configs, verify_responses):
                platform_name, username, full_url = vcfg
                status = 'unverified'
                if isinstance(vresp, dict):
                    status = vresp.get('status', 'unverified')

                result['found_profiles'].append({
                    'platform': platform_name,
                    'username': username,
                    'url': full_url,
                    'status': status,
                    'match_type': 'reverse_image',
                })
                if status == 'found':
                    result['total_verified'] += 1

            result['found_profiles'].sort(key=lambda x: (0 if x['status'] == 'found' else 1, x['platform']))

    return result

async def _scrape_engine(client: httpx.AsyncClient, engine: str, url: str) -> list:
    links = []
    try:
        resp = await client.get(url, timeout=20)
        if resp.status_code != 200:
            return links

        soup = BeautifulSoup(resp.text, 'html.parser')

        if engine == 'google_lens':
            for a in soup.find_all('a', href=True):
                href = a['href']
                if any(s in href for s in ['http://', 'https://']) and not any(
                    s in href for s in ['google.com', 'policies.google', 'accounts.google']
                ):
                    links.append(href)
            for script in soup.find_all('script'):
                if script.string:
                    found_urls = re.findall(r'https?://[^\s"\'<>]+', script.string)
                    for u in found_urls[:20]:
                        if 'google.com' not in u:
                            links.append(u)

        elif engine == 'yandex':
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith('//') and 'yandex' not in href:
                    href = 'https:' + href
                if href.startswith('http') and 'yandex' not in href and 'yastatic' not in href:
                    links.append(href)
            for img in soup.find_all('img', src=True):
                src = img['src']
                if src.startswith('//'):
                    src = 'https:' + src
                if src.startswith('http') and 'yandex' not in src:
                    links.append(src)

        elif engine == 'bing':
            for a in soup.find_all('a', href=True):
                href = a['href']
                if 'bing.com' not in href and href.startswith('http'):
                    links.append(href)

        elif engine == 'tineye':
            for a in soup.find_all('a', href=True):
                href = a['href']
                if href.startswith('/'):
                    href = 'https://tineye.com' + href
                if 'tineye.com' not in href and href.startswith('http'):
                    links.append(href)

    except Exception:
        pass

    return links[:50]

async def search_social_by_url(image_url: str) -> dict:
    return await search_social_by_image(image_url=image_url)
