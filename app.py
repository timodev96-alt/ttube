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
    match = re.search(r'"[^"]*/player_ias\.base\.js"', html) or \
            re.search(r'"[^"]*/base\.js"', html)
    if not match:
        raise ValueError("Could not find player JS URL")
    js_url = match.group(0).strip('"')
    if js_url.startswith("//"):
        js_url = "https:" + js_url
    elif js_url.startswith("/"):
        js_url = "https://www.youtube.com" + js_url
    return js_url

def find_cipher_function_name(js):
    pattern = re.compile(
        r'([a-zA-Z0-9$]{1,5})=function\(([a-zA-Z0-9$]{1,3})\)\{'
        r'\2=\2\.split\(""\)'
    )
    matches = pattern.findall(js)
    if not matches:
        raise ValueError("Could not find decipher function name")
    return matches[0][0]

def get_function_body(js, func_name):
    pattern = re.compile(re.escape(func_name) + r"=function\(a\)\{(.*?)\}")
    match = pattern.search(js)
    if not match:
        raise ValueError("Could not find function body")
    return match.group(1)

def get_helper_object(js, obj_name):
    pattern = re.compile(r"var\s+" + re.escape(obj_name) + r"\s*=\s*\{(.*?)\};" , re.DOTALL)
    match = pattern.search(js)
    if not match:
        raise ValueError("Could not find helper object")
    obj_body = match.group(1)

    methods = {}
    for m in re.finditer(r"([a-zA-Z0-9$]{2,3}):function\(([^)]*)\)\{([^}]*)\}", obj_body):
        name, code = m.group(1), m.group(3)
        if "reverse" in code:
            methods[name] = "reverse"
        elif "splice" in code:
            methods[name] = "splice"
        else:
            methods[name] = "swap"
    return methods

def get_helper_object_name(body):
    match = re.search(r"([a-zA-Z0-9$]{2,3})\.[a-zA-Z0-9$]{2,3}\(a,\d+\)", body)
    if not match:
        raise ValueError("Could not find helper object name")
    return match.group(1)

def get_operations(body, obj_name, methods):
    ops = []
    for m in re.finditer(re.escape(obj_name)+ r"\.([a-zA-Z0-9$]{2,3})\(a,(\d+)\)", body):
        methods_name , arg = m.group(1) , int(m.group(2))
        ops.append((methods.get(methods_name), arg))
    return ops

def apply_operations(signature, operations):
    a = list(signature)
    for op_type, arg in operations:
        if op_type == "reverse":
            a.reverse()
        elif op_type == "splice":
            a = a[arg:]
        elif op_type == "swap":
            arg = arg % len(a)
            a[0], a[arg] = a[arg], a[0]
    return "".join(a)

def extract_functions(js):
    for m in re.finditer(r'([a-zA-Z0-9$]{1,6})=function\(([a-zA-Z0-9$]{1,3})\)\{', js):
        name, param = m.group(1), m.group(2)
        body_start = m.end()
        depth = 1
        i = body_start
        while i < len(js) and depth > 0:
            if js[i] == '{':
                depth += 1
            elif js[i] == '}':
                depth -= 1
            i += 1
        if depth == 0:
            yield name, param, js[body_start:i-1]

def decipher_signature(js, signature):
    candidates = []
    for name, param, body in extract_functions(js):
        if len(body) > 400:
            continue
        if f'{param}=' + param + '.split(' not in body.replace('"', '').replace("'", ''):
            continue
        op_calls = re.findall(r'([a-zA-Z0-9$]{1,3})\.([a-zA-Z0-9$]{1,3})\(' + re.escape(param) + r',\d+\)', body)
        if len(op_calls) >= 2:
            candidates.append((name, param, body))

    if not candidates:
        raise ValueError("Could not find decipher function name")

    print(f"Found {len(candidates)} real candidate(s):")
    for name, param, body in candidates:
        print(f"--- {name}(param={param}) ---")
        print(body)
        print()
    name, param, body = candidates[0]
    obj_name = get_helper_object_name(body)
    methods = get_helper_object(js, obj_name)
    operations = get_operations(body, obj_name, methods)
    return apply_operations(signature, operations)

def get_download_url(format_info, js):
    cipher = format_info.get("signatureCipher") or format_info.get("cipher")
    if not cipher:
        return format_info.get("url")
    parsed = parse_qs(cipher)
    signature = parsed["s"][0]
    sp = parsed.get("sp", ["signature"])[0]
    base_url = parsed["url"][0]
    decoded_signature = decipher_signature(js, signature)
    return f'{base_url}&{sp}={decoded_signature}'

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
    player_response = extract_player_response(html)
    title = player_response.get("videoDetails", {}).get("title", "video")
    print(f"Title: {title}")

    formats = player_response.get("streamingData", {}).get("formats", [])
    target = next((f for f in formats if f.get("itag")==18), None)
    if not target:
        raise ValueError("itag 18 not found in this video's format")

    print("Fetching Player js")
    js_url = get_player_js_url(html)
    print(f"JS URL: {js_url}")
    js = fetch(js_url).decode("utf-8")
    print(f"JS length: {len(js)}")
    
    print("Decoding signature...")
    download_url = get_download_url(target, js)

    print("Downloading Video...")
    video_bytes = fetch(download_url)

    safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()
    file_name = f"{safe_title}.mp4"
    with open(file_name, "wb") as f:
        f.write(video_bytes)

    print(f"Saved as {file_name} ({len(video_bytes)} bytes)")

if __name__=="__main__":
    main()