#!/usr/bin/env python3
import json
import requests

def test_proxy(proxy: str) -> bool:
    try:
        r = requests.get(
            "http://httpbin.org/ip",
            proxies={"http": f"http://{proxy}", "https": f"http://{proxy}"},
            timeout=8
        )
        if r.status_code == 200:
            print(f"✅ Working: {proxy} -> {r.json()}")
            return True
    except Exception as e:
        print(f"❌ Failed: {proxy} ({e.__class__.__name__})")
    return False

def main():
    # JSON file load karo
    with open("active_proxies.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    proxies = [item["proxy"] for item in data.get("proxies", [])]

    print(f"🔍 Total {len(proxies)} proxies found in JSON. Testing now...\n")

    working = []
    for p in proxies[:50]:  # pehle 50 test kare (bahut zyada ho toh slow hoga)
        if test_proxy(p):
            working.append(p)

    print("\n📊 Testing finished.")
    print(f"✅ {len(working)} working proxies out of {len(proxies)}")

if __name__ == "__main__":
    main()
