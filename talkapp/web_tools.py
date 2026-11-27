"""Bounded, model-selected web search for the current chat turn."""
from .app_tools import TEXT, function
from .reading import fetch_page
from urllib.parse import parse_qs, urlparse

import httpx
from bs4 import BeautifulSoup

NAME = 'search_public_web'
TOOL = function(NAME, '搜索公开互联网。用户需要近期新闻、实时信息、外部事实核实、查找网站或明确要求上网时使用。仅提交搜索所需的公开关键词。',
                {'query': TEXT}, ['query'])
MAX_CALLS = 2
# Experimental keyless search is not part of the current mobile release.
ENABLED = False
READ_NAME = 'read_public_web_page'
READ_TOOL = function(READ_NAME, '读取本轮用户给出或本轮搜索返回的公开网页；用来核实标题、日期和内容。',
                     {'url': TEXT}, ['url'])


def search(arguments):
    query = arguments.get('query') if isinstance(arguments, dict) else None
    if not isinstance(query, str) or not query.strip() or len(query) > 400:
        raise ValueError('搜索词需为 1–400 字符')
    with httpx.Client(timeout=12, follow_redirects=False) as client:
        response = client.post('https://html.duckduckgo.com/html/', data={'q': query.strip()},
                               headers={'User-Agent': 'Mozilla/5.0 (compatible; TalkApp/0.2)'})
        response.raise_for_status()
    soup = BeautifulSoup(response.text, 'html.parser')
    results = []
    for row in soup.select('.result'):
        link = row.select_one('.result__a[href]')
        if not link:
            continue
        url = link['href']
        if url.startswith('//'):
            url = 'https:' + url
        parsed = urlparse(url)
        if parsed.hostname in ('duckduckgo.com', 'www.duckduckgo.com') and parsed.path == '/l/':
            url = parse_qs(parsed.query).get('uddg', [''])[0]
        parsed = urlparse(url)
        if parsed.scheme not in ('http', 'https') or not parsed.hostname or parsed.username or parsed.password or len(url) > 2000:
            continue
        snippet = row.select_one('.result__snippet')
        results.append({'title': link.get_text(' ', strip=True)[:160], 'url': url,
                        'text': snippet.get_text(' ', strip=True)[:500] if snippet else ''})
        if len(results) == 3:
            break
    if not results and not soup.select_one('.no-results'):
        raise ValueError('免密钥搜索暂不可用或被限流，未取得可核实的结果。')
    return results


def read(arguments, allowed):
    url = arguments.get('url') if isinstance(arguments, dict) else None
    if not isinstance(url, str) or url not in allowed:
        raise ValueError('只能读取本轮用户给出或搜索返回的链接')
    page = fetch_page(url)
    return {**page, 'text': page['text'][:1300]}
