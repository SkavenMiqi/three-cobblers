"""Read public GitHub metadata and READMEs for product research."""
import concurrent.futures
import json
import urllib.request

REPOS = ['rikkahub/rikkahub', 'CherryHQ/cherry-studio',
         'ChatGPTNextWeb/NextChat', 'open-webui/open-webui', 'lobehub/lobe-chat']
opener = urllib.request.build_opener(urllib.request.ProxyHandler({
    'https': 'http://127.0.0.1:7890', 'http': 'http://127.0.0.1:7890'}))

def fetch(repo):
    result = {'repo': repo}
    for suffix, key, accept in [('/main/README.md', 'readme', 'text/plain')]:
        try:
            req = urllib.request.Request('https://raw.githubusercontent.com/' + repo + suffix,
                                         headers={'Accept': accept, 'User-Agent': 'TalkApp-research'})
            with opener.open(req, timeout=60) as response:
                content = response.read().decode('utf-8')
            if key == 'metadata':
                data = json.loads(content)
                result[key] = {k: data.get(k) for k in ['html_url', 'description', 'language', 'license', 'archived', 'pushed_at']}
            else:
                terms = ('feature', 'support', 'memory', 'voice', 'speech', 'image', 'markdown',
                         'backup', 'sync', 'android', '功能', '支持', '语音', '记忆', '备份', '历史')
                result[key] = '\n'.join(line for line in content.splitlines()
                    if len(line) < 650 and any(term in line.lower() for term in terms))[:14000]
        except Exception as exc:
            result[key] = str(exc)
    return result

if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        for result in pool.map(fetch, REPOS):
            print(json.dumps(result, ensure_ascii=False))
