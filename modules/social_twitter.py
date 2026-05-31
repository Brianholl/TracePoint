import httpx
import re
from bs4 import BeautifulSoup
from modules.accounts_config import get_platform_accounts

NITTER_INSTANCES = [
    'https://nitter.net',
    'https://nitter.privacydev.net',
    'https://nitter.unixfox.eu',
]


async def _scrape_nitter_tweets(client: httpx.AsyncClient, username: str) -> list:
    for instance in NITTER_INSTANCES:
        try:
            resp = await client.get(f'{instance}/{username}', timeout=10)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, 'html.parser')
            tweets = []

            for item in soup.select('div.timeline-item')[:20]:
                content_el = item.select_one('.tweet-content')
                content = content_el.get_text(strip=True)[:300] if content_el else ''

                link_el = item.select_one('a.tweet-link')
                href = link_el['href'] if link_el else ''
                tweet_id = href.split('/status/')[1].split('#')[0] if '/status/' in href else ''
                tweet_url = f'https://twitter.com{href.split("#")[0]}' if href else ''

                date_el = item.select_one('.tweet-date a')
                date = date_el.get('title', '') if date_el else ''

                replies = retweets = likes = 0
                for stat in item.select('.tweet-stat'):
                    icon = stat.select_one('[class]')
                    if not icon:
                        continue
                    icon_classes = ' '.join(icon.get('class', []))
                    count_el = stat.select_one('span:last-child')
                    raw = count_el.get_text(strip=True).replace(',', '') if count_el else ''
                    count = int(raw) if raw.isdigit() else 0
                    if 'comment' in icon_classes:
                        replies = count
                    elif 'retweet' in icon_classes:
                        retweets = count
                    elif 'heart' in icon_classes:
                        likes = count

                tweets.append({
                    'id': tweet_id,
                    'url': tweet_url,
                    'content': content,
                    'date': date,
                    'likes': likes,
                    'retweets': retweets,
                    'replies': replies,
                    'media': [],
                    'mentioned_users': re.findall(r'@(\w+)', content),
                    'hashtags': re.findall(r'#(\w+)', content),
                })

            if tweets:
                return tweets
        except Exception:
            continue

    return []


async def scrape_twitter(target_username: str) -> dict:
    result = {
        'target': target_username,
        'authenticated': False,
        'profile': None,
        'tweets': [],
        'mentions': [],
        'followers_count': 0,
        'following_count': 0,
        'error': None,
    }

    accounts = get_platform_accounts('twitter')
    token = None
    if accounts and accounts.get('enabled'):
        token = accounts.get('bearer_token')
        result['authenticated'] = bool(token)

    headers = {'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36'}
    if token:
        headers['Authorization'] = f'Bearer {token}'

    async with httpx.AsyncClient(headers=headers, timeout=15) as client:
        try:
            if token:
                api_url = (
                    f'https://api.twitter.com/2/users/by/username/{target_username}'
                    '?user.fields=created_at,description,public_metrics,location,'
                    'profile_image_url,verified,protected,url,name,entities'
                )
                resp = await client.get(api_url)
                if resp.status_code == 200:
                    data = resp.json().get('data', {})
                    metrics = data.get('public_metrics', {})
                    result['profile'] = {
                        'id': data.get('id'),
                        'username': data.get('username'),
                        'name': data.get('name'),
                        'description': data.get('description'),
                        'location': data.get('location'),
                        'url': data.get('url'),
                        'profile_image_url': data.get('profile_image_url'),
                        'verified': data.get('verified', False),
                        'protected': data.get('protected', False),
                        'created_at': data.get('created_at'),
                        'followers_count': metrics.get('followers_count', 0),
                        'following_count': metrics.get('following_count', 0),
                        'tweet_count': metrics.get('tweet_count', 0),
                        'listed_count': metrics.get('listed_count', 0),
                    }
                    result['followers_count'] = metrics.get('followers_count', 0)
                    result['following_count'] = metrics.get('following_count', 0)
            else:
                # Fallback: Nitter for profile card + tweets
                for instance in NITTER_INSTANCES:
                    try:
                        resp = await client.get(f'{instance}/{target_username}', timeout=10)
                        if resp.status_code == 200:
                            soup = BeautifulSoup(resp.text, 'html.parser')
                            name_el = soup.select_one('.profile-card-fullname')
                            bio_el = soup.select_one('.profile-bio')
                            result['profile'] = {
                                'username': target_username,
                                'name': name_el.get_text(strip=True) if name_el else '',
                                'description': bio_el.get_text(strip=True) if bio_el else '',
                            }
                            break
                    except Exception:
                        continue

                result['tweets'] = await _scrape_nitter_tweets(client, target_username)

        except Exception as e:
            result['error'] = str(e)[:200]

    return result
