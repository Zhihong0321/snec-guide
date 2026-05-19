import urllib.request
import re

JS_URL = "https://pv.snec.org.cn/js/exhibitionHallIndex.b4578086.js"
LOCAL_JS = "exhibitionHallIndex.js"

def download_and_analyze():
    print("[*] Downloading official SNEC Vue JS chunk...")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(JS_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            content = response.read().decode('utf-8', errors='ignore')
            
        with open(LOCAL_JS, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"[+] Download complete: {len(content)} characters.")
        
        # Search for paths like '/api/...' or 'url:' or 'path:'
        print("[*] Searching for request endpoints and APIs in JS...")
        endpoints = set(re.findall(r'"(/[a-zA-Z0-9_\-\/]+)"', content))
        endpoints_filtered = [e for e in endpoints if "api" in e or "exh" in e or "hall" in e or "list" in e or "search" in e or "user" in e]
        
        print(f"\n[+] Found {len(endpoints_filtered)} potential API paths:")
        for ep in sorted(endpoints_filtered):
            print(f" -> {ep}")
            
    except Exception as e:
        print(f"[-] Error: {e}")

if __name__ == "__main__":
    download_and_analyze()
