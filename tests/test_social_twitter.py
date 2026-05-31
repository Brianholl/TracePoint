"""
Tests del parser de Nitter (modules/social_twitter.py).

_scrape_nitter_tweets recibe el client por parámetro → se inyecta un client
mockeado con HTML de Nitter congelado. Cero red real.
"""
import pytest

from modules.social_twitter import _scrape_nitter_tweets
from tests._helpers import static_client

NITTER_HTML = """
<html><body>
<div class="timeline-item">
  <a class="tweet-link" href="/jdoe/status/123#m"></a>
  <div class="tweet-content">Hello world #osint @someone</div>
  <span class="tweet-date"><a title="May 1, 2024 · 10:00 UTC" href="#"></a></span>
  <span class="tweet-stat"><span class="icon-comment"></span><span>5</span></span>
  <span class="tweet-stat"><span class="icon-retweet"></span><span>10</span></span>
  <span class="tweet-stat"><span class="icon-heart"></span><span>20</span></span>
</div>
</body></html>
"""


async def test_parses_tweet_fields():
    client = static_client(200, text=NITTER_HTML)
    tweets = await _scrape_nitter_tweets(client, "jdoe")
    assert len(tweets) == 1
    t = tweets[0]
    assert t["id"] == "123"
    assert t["url"] == "https://twitter.com/jdoe/status/123"
    assert "Hello world" in t["content"]
    assert t["date"] == "May 1, 2024 · 10:00 UTC"
    assert t["replies"] == 5
    assert t["retweets"] == 10
    assert t["likes"] == 20
    assert t["hashtags"] == ["osint"]
    assert t["mentioned_users"] == ["someone"]


async def test_all_instances_failing_returns_empty():
    client = static_client(404, text="not found")
    tweets = await _scrape_nitter_tweets(client, "jdoe")
    assert tweets == []
