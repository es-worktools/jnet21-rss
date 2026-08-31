import requests

URL = "https://www.yorozu-ibaraki.go.jp/seminar"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
}

response = requests.get(
    URL,
    headers=HEADERS,
    timeout=60,
)

response.raise_for_status()
response.encoding = response.apparent_encoding

print("status:", response.status_code)
print("length:", len(response.text))
print("contains セミナー:", "セミナー" in response.text)

with open(
    "yorozu-ibaraki-debug.html",
    "w",
    encoding="utf-8",
) as f:
    f.write(response.text)

print("yorozu-ibaraki-debug.html を保存しました")
