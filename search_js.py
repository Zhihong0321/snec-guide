with open("exhibitionHallIndex.js", "r", encoding="utf-8") as f:
    js_content = f.read()

import re

# Find occurrences of 'companyList'
matches = [m.start() for m in re.finditer("companyList", js_content)]
print(f"[+] Found {len(matches)} occurrences of 'companyList':")

for idx, pos in enumerate(matches):
    start = max(0, pos - 150)
    end = min(len(js_content), pos + 150)
    print(f"\nMatch #{idx+1} (around position {pos}):")
    print(js_content[start:end])
    
print("\n" + "="*50 + "\n")

# Find other occurrences of 'axios' or 'request' or 'get' or 'post'
axios_matches = [m.start() for m in re.finditer("axios|request|get|post", js_content, re.IGNORECASE)]
print(f"[+] Found {len(axios_matches)} occurrences of axios/request/get/post:")
for idx, pos in enumerate(axios_matches[:10]):  # print first 10
    start = max(0, pos - 50)
    end = min(len(js_content), pos + 50)
    print(f" -> {js_content[start:end]}")
