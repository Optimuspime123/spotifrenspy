import time
import requests
import pyotp
import base64
import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for

# --- FLASK APP CONFIGURATION ---
app = Flask(__name__)
COOKIE_FILE = 'spotify_cookie.txt'

# --- CORE SPOTIFY LOGIC (Mostly from your script) ---

def format_spotify_uri_as_url(uri: str) -> str:
    """Converts any Spotify URI to a clickable web URL."""
    if not isinstance(uri, str) or not uri.startswith('spotify:'):
        return uri
    path_part = uri.split(':', 1)[1]
    url_path = path_part.replace(':', '/')
    return f"https://open.spotify.com/{url_path}"

def generate_spotify_totp(timestamp_seconds: int) -> str:
    """Replicates the TOTP generation logic. DO NOT CHANGE THIS FUNCTION."""
    secret_cipher = [12, 56, 76, 33, 88, 44, 88, 33, 78, 78, 11, 66, 22, 22, 55, 69, 54]
    processed = [byte ^ ((i % 33) + 9) for i, byte in enumerate(secret_cipher)]
    processed_str = "".join(map(str, processed))
    utf8_bytes = processed_str.encode('utf-8')
    hex_str = utf8_bytes.hex()
    secret_bytes = bytes.fromhex(hex_str)
    b32_secret = base64.b32encode(secret_bytes).decode('utf-8')
    totp = pyotp.TOTP(b32_secret)
    return totp.at(timestamp_seconds)

def get_spotify_access_token(sp_dc_cookie: str) -> tuple[str | None, str | None]:
    """Gets the Spotify access token. Returns (token, error_message)."""
    session = requests.Session()
    jar = requests.cookies.RequestsCookieJar()
    jar.set('sp_dc', sp_dc_cookie, domain='.spotify.com', path='/')
    session.cookies = jar
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'App-Platform': 'WebPlayer'
    })

    now_ts_seconds = int(time.time())
    code = generate_spotify_totp(now_ts_seconds)

    params = {
        'reason': 'init', 'productType': 'web-player', 'totp': code, 'totpServerTime': now_ts_seconds,
        'totpVer': '5', 'sTime': now_ts_seconds, 'cTime': now_ts_seconds * 1000,
        'buildVer': 'web-player_2024-06-12_1749598284688_68a7f1a', 'buildDate': '2024-06-12'
    }
    url = 'https://open.spotify.com/api/token'

    try:
        resp = session.get(url, params=params, allow_redirects=False)
        resp.raise_for_status() # Raises HTTPError for bad responses (4xx or 5xx)
        token_data = resp.json()
        access_token = token_data.get('accessToken')
        if access_token:
            return access_token, None
        else:
            return None, "Token request succeeded, but no 'accessToken' in response."
    except requests.exceptions.HTTPError as e:
        error_detail = f"Failed to get token: {e.response.status_code}. This might mean your sp_dc cookie is invalid or expired."
        return None, error_detail
    except requests.exceptions.RequestException as e:
        return None, f"A network error occurred: {e}"

def get_friend_activity(web_access_token: str) -> tuple[dict | None, str | None]:
    """Fetches friend activity. Returns (activity_data, error_message)."""
    url = 'https://guc-spclient.spotify.com/presence-view/v1/buddylist'
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Authorization': f'Bearer {web_access_token}'
    }
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.HTTPError as e:
        return None, f"HTTP error fetching friend activity: {e}"
    except requests.exceptions.RequestException as e:
        return None, f"A network error occurred: {e}"


# --- WEB ADAPTED FUNCTIONS ---

def read_cookie_from_file() -> str | None:
    """Reads the sp_dc cookie from the local file."""
    if os.path.exists(COOKIE_FILE) and os.path.getsize(COOKIE_FILE) > 0:
        with open(COOKIE_FILE, 'r') as f:
            return f.read().strip()
    return None

def save_cookie_to_file(cookie: str):
    """Saves the sp_dc cookie to the local file."""
    with open(COOKIE_FILE, 'w') as f:
        f.write(cookie)

def clear_cookie_file():
    """Deletes the cookie file."""
    if os.path.exists(COOKIE_FILE):
        os.remove(COOKIE_FILE)

def process_friend_activity(activity_data: dict) -> list:
    """Parses API data and returns a list of friend dicts for the template."""
    processed_friends = []
    friends = activity_data.get('friends', [])
    for friend in friends:
        timestamp_ms = friend.get('timestamp')
        last_seen_str = "Timestamp not available"
        if timestamp_ms:
            dt_object = datetime.fromtimestamp(int(timestamp_ms) / 1000)
            last_seen_str = dt_object.strftime("%Y-%m-%d %I:%M:%S %p")

        user = friend.get('user', {})
        track = friend.get('track', {})
        context = track.get('context', {})
        
        processed_friends.append({
            'user_name': user.get('name', 'Unknown User'),
            'user_url': format_spotify_uri_as_url(user.get('uri', '#')),
            'image_url': user.get('imageUrl', 'https://i.scdn.co/image/ab6761610000e5eb1020c22n9ce49719111p685a'), # Placeholder
            'last_seen': last_seen_str,
            'track_name': track.get('name', 'Unknown Track'),
            'track_url': format_spotify_uri_as_url(track.get('uri', '#')),
            'artist_name': track.get('artist', {}).get('name', 'Unknown Artist'),
            'album_name': track.get('album', {}).get('name', 'Unknown Album'),
            'context_name': context.get('name', 'N/A'),
            'context_url': format_spotify_uri_as_url(context.get('uri', '#')),
        })
    return processed_friends


# --- FLASK ROUTES ---

@app.route('/', methods=['GET', 'POST'])
def index():
    error_message = None
    sp_dc_cookie = read_cookie_from_file()

    if request.method == 'POST':
        # User is submitting a new cookie
        new_cookie = request.form.get('sp_dc_cookie')
        if new_cookie:
            save_cookie_to_file(new_cookie)
            return redirect(url_for('index'))
        else:
            error_message = "Cookie field cannot be empty."
    
    if not sp_dc_cookie:
        # No cookie saved, show the form
        return render_template('index.html', show_form=True, error=error_message)

    # Cookie exists, try to fetch activity
    access_token, error_message = get_spotify_access_token(sp_dc_cookie)
    if not access_token:
        # Token failed, clear the bad cookie and show form with error
        clear_cookie_file()
        return render_template('index.html', show_form=True, error=error_message)

    friend_activity_data, error_message = get_friend_activity(access_token)
    if not friend_activity_data:
        # Friend activity fetch failed
        return render_template('index.html', error=error_message, sp_dc_cookie=sp_dc_cookie)

    # All successful, process and display data
    friends = process_friend_activity(friend_activity_data)
    return render_template('index.html', friends=friends, sp_dc_cookie=sp_dc_cookie)

@app.route('/clear')
def clear_cookie():
    """Route to clear the stored cookie and start over."""
    clear_cookie_file()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, port=5001)