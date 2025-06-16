import time
import requests
import pyotp
import base64
from datetime import datetime
from flask import Flask, render_template, request, jsonify

# --- FLASK APP CONFIGURATION ---
app = Flask(__name__)
# NO MORE COOKIE_FILE

# --- CORE SPOTIFY LOGIC (Unchanged from before) ---
def format_spotify_uri_as_url(uri: str) -> str:
    if not isinstance(uri, str) or not uri.startswith('spotify:'): return uri
    path_part = uri.split(':', 1)[1]
    url_path = path_part.replace(':', '/')
    return f"https://open.spotify.com/{url_path}"

def generate_spotify_totp(timestamp_seconds: int) -> str:
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
        resp.raise_for_status()
        token_data = resp.json()
        access_token = token_data.get('accessToken')
        if access_token:
            return access_token, None
        return None, "Token request succeeded, but no 'accessToken' in response."
    except requests.exceptions.HTTPError as e:
        return None, f"Failed to get token (Status: {e.response.status_code}). Your sp_dc cookie is likely invalid or expired."
    except requests.exceptions.RequestException as e:
        return None, f"A network error occurred: {e}"

def get_friend_activity(web_access_token: str) -> tuple[dict | None, str | None]:
    url = 'https://guc-spclient.spotify.com/presence-view/v1/buddylist'
    headers = {'Authorization': f'Bearer {web_access_token}'}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.HTTPError as e:
        return None, f"HTTP error fetching friend activity: {e}"
    except requests.exceptions.RequestException as e:
        return None, f"A network error occurred: {e}"

def process_friend_activity(activity_data: dict) -> list:
    """Parses API data and returns a list of friend dicts for the template."""
    processed_friends = []
    friends = activity_data.get('friends', [])
    for friend in friends:
        user = friend.get('user', {})
        track = friend.get('track', {})
        
        # The only change is adding 'user_image_url' here
        processed_friends.append({
            'timestamp': friend.get('timestamp'), # Send the raw timestamp
            'user_name': user.get('name', 'Unknown User'),
            'user_url': format_spotify_uri_as_url(user.get('uri', '#')),
            'user_image_url': user.get('imageUrl', 'https://i.scdn.co/image/ab6761610000e5eb1020c22n9ce49719111p685a'), # Default avatar
            'track_name': track.get('name', 'Unknown Track'),
            'track_url': format_spotify_uri_as_url(track.get('uri', '#')),
            'artist_name': track.get('artist', {}).get('name', 'Unknown Artist'),
            'context_name': track.get('context', {}).get('name', 'N/A'),
            'context_url': format_spotify_uri_as_url(track.get('context', {}).get('uri', '#')),
        })
    return processed_friends

# --- FLASK ROUTES ---

@app.route('/')
def index():
    """Serves the main HTML page which contains all the client-side logic."""
    return render_template('index.html')

@app.route('/api/activity', methods=['POST'])
def get_activity():
    """API endpoint that receives the cookie and returns activity or an error."""
    data = request.get_json()
    if not data or 'sp_dc_cookie' not in data:
        return jsonify({"error": "sp_dc_cookie not provided."}), 400

    sp_dc_cookie = data['sp_dc_cookie']
    
    # Step 1: Get Access Token
    access_token, error = get_spotify_access_token(sp_dc_cookie)
    if error:
        return jsonify({"error": error}), 401 # Unauthorized

    # Step 2: Get Friend Activity
    friend_activity_data, error = get_friend_activity(access_token)
    if error:
        return jsonify({"error": error}), 500 # Server error

    # Step 3: Process and return data
    friends = process_friend_activity(friend_activity_data)
    return jsonify({"friends": friends})


if __name__ == '__main__':
    app.run(debug=True, port=5001)
