"""Bounded text extraction and search with explicit sources."""
import ipaddress
import re
import socket
from pathlib import Path
from urllib.parse import urlparse, urljoin
import httpx
from bs4 import BeautifulSoup

MAX_BYTES = 12 * 1024 * 1024


def read_document(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('文件需小于12MB')
    suffix = path.suffix.lower()
    if suffix == '.pdf':
        from pypdf import PdfReader
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise ValueError('请先解密PDF')
        parts = []
        size = 0
        for index, page in enumerate(reader.pages):
            value = f'[第{index + 1}页]\n' + (page.extract_text() or '')
            parts.append(value)
            size += len(value)
            if size >= 120000:
                parts.append('[文件超过提取上限，仅包含前面的页面]')
                break
        text = '\n\n'.join(parts)
        if not any(page.strip() for page in re.sub(r'\[第\d+页\]', '', text).splitlines()):
            raise ValueError('PDF没有可提取文字，扫描件暂需OCR')
    elif suffix == '.docx':
        from docx import Document
        doc = Document(str(path))
        text = '\n'.join(p.text for p in doc.paragraphs)
        text += '\n' + '\n'.join(' | '.join(cell.text for cell in row.cells) for table in doc.tables for row in table.rows)
    elif suffix in ('.txt', '.md', '.csv', '.json', '.py', '.log'):
        raw = path.read_bytes()
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError:
            text = raw.decode('gb18030')
    else:
        raise ValueError('支持PDF、DOCX、TXT、Markdown及文本文件')
    if not text.strip():
        raise ValueError('未提取到文字')
    return {'name': path.name, 'content': text[:120000]}


def public_url(url):
    parsed = urlparse(url)
    if parsed.scheme not in ('https', 'http') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('网页地址无效')
    addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == 'https' else 80), type=socket.SOCK_STREAM)
    if any(not ipaddress.ip_address(row[4][0]).is_global for row in addresses):
        raise ValueError('网页读取仅支持公网地址')
    return url


def fetch_page(url):
    with httpx.Client(timeout=20, follow_redirects=False) as client:
        for _ in range(5):
            public_url(url)
            with client.stream('GET', url, headers={'User-Agent': 'TalkApp/0.1 reader'}) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers['location'])
                    continue
                response.raise_for_status()
                if not any(kind in response.headers.get('content-type', '') for kind in ('text/', 'html', 'xml')):
                    raise ValueError('链接不是可读取的网页')
                data = bytearray()
                for chunk in response.iter_bytes():
                    data.extend(chunk)
                    if len(data) > 2 * 1024 * 1024:
                        raise ValueError('网页过大')
                soup = BeautifulSoup(bytes(data), 'html.parser')
                title = soup.title.get_text(' ', strip=True) if soup.title else url
                for element in soup(['script', 'style', 'nav', 'footer', 'header', 'noscript']):
                    element.decompose()
                text = soup.get_text('\n', strip=True)
                return {'title': title[:200], 'url': url, 'text': text[:18000]}
    raise ValueError('网页重定向过多')


def search_web(query, endpoint='', key=''):
    if not key:
        raise ValueError('联网搜索尚未配置Tavily密钥；直接粘贴网页链接可免搜索密钥阅读')
    with httpx.Client(timeout=25) as client:
        response = client.post(endpoint or 'https://api.tavily.com/search',
            headers={'Authorization': 'Bearer ' + key},
            json={'query': query[:1000], 'max_results': 4, 'search_depth': 'basic'})
        response.raise_for_status()
        return [{'title': row.get('title', ''), 'url': row['url'], 'text': row.get('content', '')[:3500]}
                for row in response.json().get('results', []) if row.get('url', '').startswith(('https://', 'http://'))][:4]


def needs_search(text, mode):
    if mode == 'off':
        return False
    return mode == 'on' or any(word in text.lower() for word in ('搜索', '查一下', '联网', '最新', '新闻', '今天的', '股价', '天气', '实时', 'search'))


def select_passages(text, query, limit=5000):
    from .memory import terms
    if len(text) <= limit:
        return text
    paragraphs = [text[i:i + 1000] for i in range(0, len(text), 1000)]
    tokens = set(terms(query))
    ranked = sorted(range(len(paragraphs)), key=lambda i: len(tokens & set(terms(paragraphs[i]))), reverse=True)
    selected = sorted(set([0] + ranked[:max(1, limit // 1000 - 1)]))
    return '[以下为相关节选，不是全文]\n' + '\n…\n'.join(paragraphs[i] for i in selected)[:limit]
