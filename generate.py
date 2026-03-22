import requests
import json
import time
from datetime import datetime

BASE_URL = "https://streamed.pk/api"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://streamed.pk/",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://streamed.pk",
}

# Ad domains block list
AD_DOMAINS = [
    "doubleclick", "googlesyndication", "adservice", "analytics",
    "tracking", "pixel", "banner", "popup", "ads.", "/ads/",
    "adserver", "adnetwork", "advertisement",
]

def is_ad_url(url):
    """Check if URL is an ad"""
    url_lower = url.lower()
    return any(ad in url_lower for ad in AD_DOMAINS)

def get_poster_url(poster):
    """Poster URL fix করো"""
    if not poster:
        return "https://streamed.pk/favicon.ico"
    if poster.startswith('http'):
        return poster
    if poster.startswith('/api/'):
        return f"https://streamed.pk{poster}"
    return f"https://streamed.pk/api/images/proxy/{poster}"

def get_streams(source, match_id, retry=2):
    """একটা match এর stream URLs বের করো"""
    for attempt in range(retry):
        try:
            url = f"{BASE_URL}/stream/{source}/{match_id}"
            res = requests.get(url, headers=HEADERS, timeout=10)
            if res.status_code == 200:
                data = res.json()
                return data if isinstance(data, list) else [data]
        except Exception as e:
            if attempt < retry - 1:
                time.sleep(1)
    return []

def extract_hls_url(stream):
    """Stream object থেকে HLS URL বের করো"""
    if not isinstance(stream, dict):
        return None

    # সব possible field names check করো
    fields = [
        'hls', 'url', 'streamUrl', 'stream_url', 'link',
        'hlsUrl', 'hls_url', 'playbackUrl', 'playback_url',
        'm3u8', 'source', 'stream', 'live_url', 'liveUrl',
    ]

    for field in fields:
        val = stream.get(field, '')
        if isinstance(val, str) and val and '.m3u8' in val:
            if not is_ad_url(val):
                return val

    # Nested check
    for key, val in stream.items():
        if isinstance(val, str) and '.m3u8' in val and not is_ad_url(val):
            return val
        if isinstance(val, dict):
            result = extract_hls_url(val)
            if result:
                return result

    return None

def get_matches(endpoint):
    """Matches fetch করো"""
    try:
        url = f"{BASE_URL}/matches/{endpoint}"
        res = requests.get(url, headers=HEADERS, timeout=15)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        print(f"  Error fetching {endpoint}: {e}")
    return []

def generate_playlist():
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    playlist = f"""#EXTM3U
#PLAYLIST: Streamed Sports Live
# Auto-generated: {now}
# Source: streamed.pk
# Ad-free playlist

"""
    seen_urls = set()
    total_channels = 0
    total_matches = 0

    print(f"🚀 Starting playlist generation at {now}")
    print("=" * 50)

    # Endpoints priority order
    endpoints = [
        ("live", "🔴 LIVE"),
        ("all-today", "📅 TODAY"),
    ]

    # Sport categories
    sports_endpoints = [
        "cricket", "football", "basketball", "tennis",
        "hockey", "baseball", "motor-sports", "fight",
        "rugby", "golf", "other"
    ]

    all_matches = []

    # Live + Today matches
    for ep, label in endpoints:
        matches = get_matches(ep)
        print(f"{label}: {len(matches)} matches found")
        all_matches.extend(matches)

    # Sport specific
    for sport in sports_endpoints:
        matches = get_matches(sport)
        if matches:
            all_matches.extend(matches)

    # Duplicate remove
    seen_ids = set()
    unique_matches = []
    for m in all_matches:
        mid = m.get('id', '')
        if mid and mid not in seen_ids:
            seen_ids.add(mid)
            unique_matches.append(m)

    print(f"\n📊 Total unique matches: {len(unique_matches)}")
    print("=" * 50)
    print("Fetching streams...")

    for match in unique_matches:
        title    = match.get('title', 'Live Match')
        category = match.get('category', 'sports').upper()
        poster   = get_poster_url(match.get('poster', ''))
        sources  = match.get('sources', [])
        date_ms  = match.get('date', 0)

        # Time format
        try:
            match_time = datetime.utcfromtimestamp(date_ms / 1000).strftime("%H:%M UTC")
        except:
            match_time = ""

        match_channels = 0

        for src_idx, src in enumerate(sources):
            source   = src.get('source', '')
            match_id = src.get('id', '')

            if not source or not match_id:
                continue

            streams = get_streams(source, match_id)

            # Small delay to avoid rate limit
            time.sleep(0.3)

            for stream_idx, stream in enumerate(streams):
                hls_url = extract_hls_url(stream)

                if not hls_url:
                    continue

                # Skip ads
                if is_ad_url(hls_url):
                    continue

                if hls_url in seen_urls:
                    continue

                seen_urls.add(hls_url)

                # Server name
                server_name = (
                    stream.get('name') or
                    stream.get('server') or
                    f"{source.capitalize()} {stream_idx + 1}"
                )

                # User agent
                user_agent = (
                    stream.get('userAgent') or
                    stream.get('user_agent') or
                    "Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36"
                )

                # Referer
                referer = (
                    stream.get('referer') or
                    stream.get('Referer') or
                    "https://streamed.pk/"
                )

                channel_name = f"{title}"
                if len(sources) > 1 or len(streams) > 1:
                    channel_name = f"{title} [{server_name}]"

                playlist += f'#EXTINF:-1 tvg-logo="{poster}" group-title="{category}", {channel_name}\n'

                if user_agent:
                    playlist += f'#EXTVLCOPT:http-user-agent={user_agent}\n'

                if referer:
                    playlist += f'#EXTVLCOPT:http-referrer={referer}\n'

                playlist += f'{hls_url}\n\n'

                match_channels += 1
                total_channels += 1

        if match_channels > 0:
            total_matches += 1
            print(f"  ✅ {title} ({category}) — {match_channels} streams")
        else:
            print(f"  ❌ {title} — no streams found")

    # Save playlist
    with open("playlist.m3u", "w", encoding="utf-8") as f:
        f.write(playlist)

    print("\n" + "=" * 50)
    print(f"✅ DONE!")
    print(f"   Matches: {total_matches}")
    print(f"   Channels: {total_channels}")
    print(f"   Saved: playlist.m3u")
    print("=" * 50)

    return total_channels

if __name__ == "__main__":
    generate_playlist()
