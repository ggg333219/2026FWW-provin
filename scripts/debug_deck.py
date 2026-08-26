#!/usr/bin/env python
import urllib.request, json, sys

data = {
    "intent": {
        "title": "Python基础",
        "description": "介绍Python基本语法",
        "key_points": ["变量", "数据类型"]
    },
    "palette": "klein-blue"
}

req = urllib.request.Request(
    "http://localhost:8000/api/v1/skill/deck",
    data=json.dumps(data).encode(),
    headers={"Content-Type": "application/json"}
)

try:
    r = urllib.request.urlopen(req, timeout=25)
    result = json.loads(r.read())
except Exception as e:
    print(f"Request failed: {e}")
    sys.exit(1)

print("=== Response ===")
print(json.dumps(result, ensure_ascii=False, indent=2))

slides = result.get("slides", [])
html_url = result.get("html_url", "")
html_path = result.get("html_path", "")

print(f"\nslides count: {len(slides)}")
print(f"page_count: {result.get('page_count')}")
print(f"html_url: {html_url}")
print(f"html_path: {html_path}")

# Try to fetch HTML content
if html_url:
    target = html_url
elif html_path:
    target = f"http://localhost:8000/previews/{html_path}"
else:
    print("No html_url or html_path found!")
    sys.exit(1)

print(f"\nFetching HTML from: {target}")
try:
    r2 = urllib.request.urlopen(target, timeout=5)
    content = r2.read().decode("utf-8", errors="replace")
    print(f"HTML size: {len(content)} bytes")
    print(f"First 500 chars:\n{content[:500]}")
except Exception as e:
    print(f"Failed to fetch HTML: {e}")
