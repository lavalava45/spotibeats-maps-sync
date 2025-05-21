import os, time, json, urllib.parse, requests, logging, re, zipfile
from pathlib import Path
from random import uniform
from rapidfuzz import fuzz
from tqdm import tqdm
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type
import spotipy
from spotipy.oauth2 import SpotifyOAuth

# Configuration constants
TRACK_FILE = "tracklist.json"        # cache file for tracks [{artist, track}, ...]
OUT_DIR    = "maps"                  # directory for ZIP files and extracted content
PAUSE_SEC  = 0.25                     # base pause between requests
MIN_RATE   = 0.5                      # minimum required score to accept a map
HEAD = {"User-Agent": "spotify2bs/2025.05"}

logging.basicConfig(level=logging.INFO, format="%(message)s")

# Load saved tracks from cache or Spotify API
def load_tracks():
    if os.path.exists(TRACK_FILE):
        logging.info("✓ %s found - using cache.", TRACK_FILE)
        with open(TRACK_FILE, encoding="utf-8") as f:
            return json.load(f)

    # Spotify OAuth setup
    client_id     = os.getenv("SPOTI_ID")
    client_secret = os.getenv("SPOTI_SECRET")
    redirect_uri  = os.getenv("SPOTI_REDIRECT_URI", "http://127.0.0.1:8888/callback")

    oauth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope="user-library-read",
        open_browser=False)

    # Prompt user to authorize
    auth_url = oauth.get_authorize_url()
    print("\n1) Open the link, sign in, and click Agree:\n", auth_url, "\n")
    redirect_resp = input("2) Paste the full redirect URL from your browser here:\n> ").strip()

    # Extract code from URL
    code = oauth.parse_response_code(redirect_resp)
    if not code:
        raise SystemExit("✗ Failed to parse code from URL. Please try again.")

    # Obtain token and create Spotify client
    oauth.get_access_token(code, check_cache=False)
    sp = spotipy.Spotify(auth_manager=oauth)
    print("✓ Authorization successful, loading saved tracks...")

    # Fetch saved tracks
    tracks, offset = [], 0
    while True:
        page = sp.current_user_saved_tracks(limit=50, offset=offset)
        for item in page['items']:
            t = item['track']
            tracks.append({
                "artist": t['artists'][0]['name'],
                "track": t['name']
            })
        if page['next'] is None:
            break
        offset += 50

    # Save to cache file
    with open(TRACK_FILE, "w", encoding="utf-8") as f:
        json.dump(tracks, f, ensure_ascii=False, indent=2)
    print(f"✓ Saved {len(tracks)} tracks to {TRACK_FILE}")
    return tracks

# BeatSaver search logic: exact, text, advanced
@retry(
    retry=retry_if_exception_type(requests.HTTPError),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    stop=stop_after_attempt(3))
def beat_search(q: str):
    enc = urllib.parse.quote(q, safe="")
    enc_q = urllib.parse.quote(f'"{q}"', safe="")

    # 1) exact-phrase search
    url_quote = f"https://api.beatsaver.com/search/text/0?sortOrder=Relevance&q={enc_q}"
    r = requests.get(url_quote, headers=HEAD, timeout=15)
    if r.status_code == 404:
        docs = []
    elif r.status_code >= 500:
        raise requests.HTTPError()
    else:
        r.raise_for_status()
        docs = r.json().get("docs", [])
    logging.info("🔍 quoted '%s' -> returned %d docs (status %d)", q, len(docs), r.status_code)
    if docs:
        return docs

    # 2) regular text search
    url_text = f"https://api.beatsaver.com/search/text/0?sortOrder=Relevance&q={enc}"
    r2 = requests.get(url_text, headers=HEAD, timeout=15)
    if r2.status_code == 404:
        docs = []
    elif r2.status_code >= 500:
        raise requests.HTTPError()
    else:
        r2.raise_for_status()
        docs = r2.json().get("docs", [])
    logging.info("🔍 '%s' -> text returned %d docs (status %d)", q, len(docs), r2.status_code)
    if docs:
        return docs

    # 3) advanced search fallback
    url_adv = f"https://api.beatsaver.com/search/advanced?sortOrder=Relevance&q={enc}&page=0"
    r3 = requests.get(url_adv, headers=HEAD, timeout=15)
    if r3.status_code == 404:
        docs = []
    elif r3.status_code >= 500:
        raise requests.HTTPError()
    else:
        r3.raise_for_status()
        docs = r3.json().get("docs", [])
    logging.info("   ↳ advanced returned %d docs (status %d)", len(docs), r3.status_code)
    return docs

# Select best map matching exact title and artist
def best_map(track_name: str, artist_name: str = None):
    docs = beat_search(track_name)
    filtered = []
    for d in docs:
        name = d.get('metadata', {}).get('songName', d.get('name', ''))
        if name.lower() == track_name.lower():
            if artist_name:
                author = d.get('metadata', {}).get('songAuthorName', '')
                if fuzz.partial_ratio(artist_name.lower(), author.lower()) < 80:
                    continue
            filtered.append(d)
    if not filtered:
        logging.info("   ↳ no exact title/artist matches - skipping")
        return None

    # choose highest-score map among exact matches
    filtered.sort(key=lambda d: d.get('stats', {}).get('score', 0), reverse=True)
    top = filtered[0]
    rate = top.get('stats', {}).get('score', 0)
    if rate >= MIN_RATE:
        logging.info("   ✓ selected map %s (%.2f rate)", top['id'], rate)
        return top
    logging.info("   ↳ map did not pass score threshold (%.2f < %.2f)", rate, MIN_RATE)
    return None

# Download ZIP and extract into artist-track subfolder
def download_and_extract(bs_id: str, artist: str, track: str):
    zip_url = f"https://beatsaver.com/api/download/key/{bs_id}"
    r = requests.get(zip_url, headers=HEAD, timeout=30)
    if r.status_code != 200:
        logging.error("Failed to download map %s: HTTP %d", bs_id, r.status_code)
        return False
    r.raise_for_status()

    artist_clean = re.sub(r"[^A-Za-z0-9- ]", "", artist).strip().replace(" ", "_")
    track_clean  = re.sub(r"[^A-Za-z0-9- ]", "", track).strip().replace(" ", "_")
    dest_dir = Path(OUT_DIR) / f"{artist_clean}-{track_clean}"
    dest_dir.mkdir(parents=True, exist_ok=True)

    zip_path = dest_dir / f"{bs_id}.zip"
    with open(zip_path, "wb") as f:
        f.write(r.content)

    # extract and remove archive
    with zipfile.ZipFile(zip_path, 'r') as z:
        z.extractall(dest_dir)
    zip_path.unlink()
    return True


# Main loop: search and download maps
def main():
    tracks = load_tracks()
    not_found, downloaded = [], []
    print("\nStarting map search...\n")
    for item in tqdm(tracks, desc="Searching maps"):
        track_name = item['track']
        artist_name = item.get('artist')
        try:
            hit = best_map(track_name, artist_name)
            if hit:
                ok = download_and_extract(hit['id'], artist_name, track_name)
                if ok:
                    downloaded.append(f"{artist_name} - {track_name}")
                else:
                    not_found.append(f"{artist_name} - {track_name}")
            else:
                not_found.append(f"{artist_name} - {track_name}")
        except Exception as e:
            logging.info("• Skipping: %s — %s", track_name, e.__class__.__name__)
            not_found.append(f"{artist_name} - {track_name}")
        time.sleep(PAUSE_SEC + uniform(0, 0.15))

    if downloaded:
        with open("downloaded.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(downloaded))
        print(f"\n✓ Downloaded maps: {len(downloaded)} -> downloaded.txt")
    if not_found:
        with open("not_found.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(not_found))
        print(f"✗ No maps found for {len(not_found)} tracks -> not_found.txt")

if __name__ == "__main__":
    main()
