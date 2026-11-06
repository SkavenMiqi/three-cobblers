"""Download selected upstream files without the large exercise media library."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import urllib.request
import time

ROOT = Path(__file__).resolve().parents[1] / "fitness"
REV = "079b7ea0890285bd3d7200e6782a494cc0da1035"
FILES = ["README.md", "ai_chat.py", "ai_settings.py", "llm_client.py",
         "llm_config.py", "main.py", "buildozer.spec", "config/theme.py",
         "utils/platform.py", "assets/icons/icon.png"]

def fetch(name):
    url = f"https://api.github.com/repos/SkavenMiqi/fitness/contents/{name}?ref={REV}"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"Accept": "application/vnd.github.raw+json"})
            with urllib.request.urlopen(req, timeout=60) as response:
                data = response.read()
            target = ROOT / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            return f"Downloaded {name}"
        except Exception as exc:
            if attempt == 2:
                return f"Failed {name}: {type(exc).__name__}"
            time.sleep(1)

if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=4) as pool:
        for status in pool.map(fetch, FILES):
            print(status)
