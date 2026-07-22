import argparse
import urllib.request
import json

def fetch_html(url):
    headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36"
    }
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req) as response:
        html = response.read().decode("utf-8")
    return html

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
    
    json_str = html[start:end]
    return json.loads(json_str)


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

if __name__=="__main__":
    main()