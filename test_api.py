import urllib.request
import json

URLS = [
    "https://pv.snec.org.cn/hallIndex/companyList",
    "https://pv.snec.org.cn/api/hallIndex/companyList",
]

def test_endpoints():
    headers = {
        'User-Agent': 'Mozilla/5.0',
        'Content-Type': 'application/json'
    }
    
    # Try different payloads: typical pagination
    payloads = [
        {}, # Empty
        {"page": 1, "pageSize": 10},
        {"pageIndex": 1, "pageSize": 10},
        {"page": 1, "limit": 10},
    ]
    
    for url in URLS:
        print(f"\n[*] Testing URL: {url}")
        for payload in payloads:
            print(f"  -> Testing payload: {payload}")
            try:
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode('utf-8'),
                    headers=headers,
                    method='POST'
                )
                with urllib.request.urlopen(req, timeout=5) as response:
                    res_body = response.read().decode('utf-8')
                    print(f"  [+] Response (first 200 chars): {res_body[:200]}")
                    if len(res_body) > 200:
                        # Save the full successful response to a file for analysis
                        with open("api_response.json", "w", encoding="utf-8") as f:
                            f.write(res_body)
                        print("[+] Saved full response to api_response.json")
                        return
            except Exception as e:
                print(f"  [-] Failed: {e}")
                
        # Also try GET request just in case
        try:
            print("  -> Testing GET request...")
            req = urllib.request.Request(url, headers=headers, method='GET')
            with urllib.request.urlopen(req, timeout=5) as response:
                res_body = response.read().decode('utf-8')
                print(f"  [+] GET Response (first 200 chars): {res_body[:200]}")
        except Exception as e:
            print(f"  [-] GET Failed: {e}")

if __name__ == "__main__":
    test_endpoints()
