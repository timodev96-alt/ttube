import argparse
import urllib.request
import json
import re
from urllib.parse import parse_qs

HEADERS={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"
    }

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req) as response:
        return response.read()

def fetch_html(url):
    return fetch(url).decode("utf-8")

def extract_player_response(html):
    marker = "var ytInitialPlayerResponse = "
    start = html.find(marker)
    if start == -1 :
        raise ValueError("Could not find ytInitialPlayerResponse in HTML")
    start += len(marker)

    depth = 0
    end = start
    
    for i in range(start, len(html)):
        if html[i] == "{":
            depth += 1
        elif html[i] == "}":
            depth -= 1
            if depth ==0:
                end = i+1
                break

    return json.loads(html[start:end])

def get_player_js_url(html):
    match = re.search(r'"jsURL":"([^"]+)"', html)
    if not match:
        raise ValueError("Could not find player JS URL")
    js_url=match.group(1)
    if js_url.startswith("//"):
        js_url = "https:" + js_url
    elif js_url.startswith("/"):
        js_url = "https://www.youtube.com" + js_url
    return js_url

def find_cipher_function_name(js):
    match = re.search(
        r'\b([a-zA-Z0-9$]{2,4})\s*=\s*function\(\s*a\s*\)\s*\{\s*a\s*=\s*a\.split\(\s*""\s*\)',
        js,
    )
    if not match:
        raise ValueError("Could not find decipher function name")
    return match.group(1)

def get_function_body(js, func_name):
    pattern = re.compile(re.escape(func_name) + r"=function\(a\)\{(.*?)\}")
    match = pattern.search(js)
    if not match:
        raise ValueError("Could not find function body")
    return match.group(1)

def get_helper_object_name(body):
    pass

def list_formats(player_response):
    streaming_data = player_response.get("streamingData", {})
    formats = streaming_data.get("formats", [])
    adaptive_formats = player_response.get("streamingData", {}).get("adaptiveFormats", [])
    if adaptive_formats:
        print(json.dumps(adaptive_formats[0], indent=2))

    print("\n ===Full Video===")
    for f in formats:
        itag = f.get("itag")
        quality = f.get("qualityLabel", f.get("quality", "?"))
        mime = f.get("mimeType", "?")
        has_url = "url" in f
        has_cipher = "signatureCipher" in f or "cipher" in f
        print(f'itag={itag} quality={quality} mime={mime[:30]} url={has_url} cipher={has_cipher}')
    print("\n ===Video Only / Audio Only===")
    for f in adaptive_formats:
        itag = f.get(itag)
        quality = f.get("qualityLabel", f.get("quality", "?"))
        mime = f.get("mimeType", "?")
        has_url = "url" in f
        has_cipher = "signatureCipher" in f or "cipher" in f
        print(f'itag={itag} quality={quality} mime={mime[:30]} url={has_url} cipher={has_cipher}')

def main():
    parser = argparse.ArgumentParser(description="Download youtube videos")
    parser.add_argument("url", help="Youtube Video URL")
    args = parser.parse_args()

    print(f'Fetching: {args.url}')
    html = fetch_html(args.url)
    print(f'Got {len(html)} Characters of HTML')

    player_response = extract_player_response(html)
    title = player_response.get("videoDetails", {}).get("title", "UNKNOWN")
    length_seconds = player_response.get("videoDetails", {}).get("lengthSeconds", "?")

    print(f'Title: {title}')
    print(f'Length: {length_seconds} Seconds')
    list_formats(player_response)

if __name__=="__main__":
    main()