import asyncio
import requests
import logging
import os
import time
from collections import defaultdict

REDDIT_SUBREDDITS = ["darkjokes", "jokes", "dadjokes"]
REDDIT_MAX_LENGTH = 350
REDDIT_HEADERS = {"User-Agent": "Mozilla/5.0"}
REDDIT_BLOCK_COOLDOWN_SECONDS = int(os.environ.get("REDDIT_BLOCK_COOLDOWN_SECONDS", "900"))
_jokes_lock = asyncio.Lock()
_reddit_jokes_by_sub = defaultdict(list)
_reddit_blocked_until = defaultdict(float)

def _is_blocked(subreddit: str) -> bool:
    return time.time() < _reddit_blocked_until.get(subreddit, 0)

def _set_blocked(subreddit: str) -> None:
    _reddit_blocked_until[subreddit] = time.time() + REDDIT_BLOCK_COOLDOWN_SECONDS

async def fetch_reddit_top(subreddit, headers, max_posts=1000):
    url = f"https://www.reddit.com/r/{subreddit}/top.json?t=year&limit=100"
    loop = asyncio.get_event_loop()
    def fetch():
        posts, after = [], None
        while len(posts) < max_posts:
            page_url = url + (f"&after={after}" if after else "")
            try:
                r = requests.get(page_url, headers=headers, timeout=10)
                if r.status_code == 403:
                    return posts[:max_posts], True
                r.raise_for_status()
                data = r.json()["data"]
                children = data.get("children", [])
                if not children: break
                posts.extend(children)
                after = data.get("after")
                if not after or len(children) < 100: break
            except Exception as ex:
                logging.warning(f"Reddit fetch error: {ex}")
                break
        return posts[:max_posts], False
    return await loop.run_in_executor(None, fetch)

async def load_reddit_jokes():
    if os.environ.get("LOAD_REDDIT", "false").lower() != "true":
        logging.info("[Reddit] Skipping Reddit joke loading due to LOAD_REDDIT env variable.")
        return
    global _reddit_jokes_by_sub
    async with _jokes_lock:
        unique = defaultdict(list)
        seen = set()
        for sub in REDDIT_SUBREDDITS:
            if _is_blocked(sub):
                retry_in = int(_reddit_blocked_until[sub] - time.time())
                logging.info(f"[Reddit] Skipping r/{sub}; blocked recently. Retry in {max(retry_in, 0)}s.")
                continue
            posts, blocked = await fetch_reddit_top(sub, REDDIT_HEADERS, max_posts=1000)
            if blocked:
                _set_blocked(sub)
                logging.warning(
                    f"[Reddit] 403 for r/{sub}; pausing requests for {REDDIT_BLOCK_COOLDOWN_SECONDS}s."
                )
                continue
            for post in posts:
                d = post["data"]
                joke_text = f"{d.get('title','')}. {d.get('selftext','')}".strip()
                k = joke_text.lower()
                if 0 < len(joke_text) <= REDDIT_MAX_LENGTH and k not in seen:
                    unique[d.get('subreddit', sub).lower()].append(post)
                    seen.add(k)
        _reddit_jokes_by_sub = unique
        logging.info(f"[Reddit] Loaded {sum(len(x) for x in unique.values())} unique jokes.")

def get_reddit_jokes():
    return _reddit_jokes_by_sub