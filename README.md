# SpotiBeats Maps Sync

Convert your saved Spotify tracks into Beat Saber custom map downloads—automatically fetch (from https://beatsaver.com/), extract, and organize maps into artist-track folders.

## Features

- Fetch your Spotify “Liked Songs” (or any user library) via OAuth  
- Search BeatSaver API for matching custom maps  
- Exact-title search with quoted queries for precision  
- Filter by rating threshold (`MIN_RATE`)  
- Download & extract maps into `maps/Artist-Track/` folders  
- Cache track list in `tracklist.json` for faster re-runs  
- Generate `downloaded.txt` and `not_found.txt` summaries  

## Prerequisites

- **Python 3.8+**  
- **Git** (to clone the repo)  
- **Windows 10 / macOS / Linux**  

## Installation

1. **Clone the repository**  
   ```bash
   git clone https://github.com/lavalava45/spotibeats-maps-sync.git
   cd spotibeats-maps-sync
   ```

2. **Create & activate a virtual environment** (optional but recommended)  
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # macOS / Linux
   source venv/bin/activate
   ```

3. **Install required Python packages**  
   ```bash
   pip install spotipy requests rapidfuzz tqdm tenacity
   ```

## Spotify App Setup

1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and create a new app.  
2. Copy its **Client ID** and **Client Secret**.  
3. Under **Edit Settings → Redirect URIs**, add exactly:  
   ```
   http://127.0.0.1:8888/callback
   ```  
4. Save changes.

## Configuration

In your shell (for the current session):

```bash
# Windows CMD
set SPOTI_ID=your_client_id_here
set SPOTI_SECRET=your_client_secret_here
set SPOTI_REDIRECT_URI=http://127.0.0.1:8888/callback

# macOS / Linux
export SPOTI_ID=your_client_id_here
export SPOTI_SECRET=your_client_secret_here
export SPOTI_REDIRECT_URI=http://127.0.0.1:8888/callback
```

To persist these across sessions, use your OS’s permanent env-var mechanism (e.g. `setx` on Windows or add to `~/.bashrc` on Linux/macOS).

## Usage

1. **First run** prompts for Spotify authorization:  
   ```bash
   python spotify2bs.py
   ```
   - The script prints a URL—open it in your browser and click **Agree**.  
   - Copy the full redirected URL (`http://127.0.0.1:8888/callback?code=…`) back into the console.  
   - The script caches your track list in `tracklist.json` and starts downloading maps.

2. **Subsequent runs** skip login and immediately search & download:   

3. **Output**  
   - `maps/Artist-Track/…` → extracted map folders  
   - `downloaded.txt` → list of downloaded map IDs  
   - `not_found.txt` → tracks for which no map passed filters  

## Configuration Options

Inside the script you can adjust:

```python
MIN_RATE   = 0.75   # minimum BeatSaver score to accept a map
PAUSE_SEC  = 0.25   # delay between API calls (in seconds)
```

Lower `MIN_RATE` to include less-rated maps; increase `PAUSE_SEC` if you hit rate limits.

## Troubleshooting

- **Invalid Redirect URI**  
  Ensure the URI in your Spotify Dashboard exactly matches `SPOTI_REDIRECT_URI`.  
- **Network/API errors**  
  Check your internet or try a VPN if BeatSaver API returns errors.  
- **Stuck on 0%**  
  Delete `tracklist.json` and rerun to force fresh Spotify login and cache.

## License

MIT © lavalava45  
[https://github.com/lavalava45/spotibeats-maps-sync](https://github.com/lavalava45/spotibeats-maps-sync)
