import time
import requests
import pyotp
import base64
from datetime import datetime
from flask import Flask, render_template, request, jsonify

# --- FLASK APP CONFIGURATION ---
app = Flask(__name__)



def format_spotify_uri_as_url(uri: str) -> str:
    """Converts any Spotify URI (e.g., spotify:user:xyz) to a clickable web URL."""
    if not isinstance(uri, str) or not uri.startswith('spotify:'): return uri
    path_part = uri.split(':', 1)[1]
    url_path = path_part.replace(':', '/')
    return f"https://open.spotify.com/{url_path}"


def generate_spotify_totp(timestamp_seconds: int) -> str:
    """Replicates the TOTP generation logic for version 10."""
    secret_string = "=n:b#OuEfH\\fE])e*K"
    processed = [ord(char) ^ ((i % 33) + 9) for i, char in enumerate(secret_string)]
    processed_str = "".join(map(str, processed))
    utf8_bytes = processed_str.encode('utf-8')
    b32_secret = base64.b32encode(utf8_bytes).decode('utf-8')
    totp = pyotp.TOTP(b32_secret)
    return totp.at(timestamp_seconds)


def get_spotify_access_token(sp_dc_cookie: str) -> tuple[str | None, str | None]:
    """Gets a Spotify web access token using the sp_dc cookie and v10 TOTP logic."""
    session = requests.Session()
    jar = requests.cookies.RequestsCookieJar()
    jar.set('sp_dc', sp_dc_cookie, domain='.spotify.com', path='/')
    session.cookies = jar
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'App-Platform': 'WebPlayer'
    })

    
    now_ts_seconds = int(time.time())
    server_ts_seconds = now_ts_seconds
    try:
        server_time_response = session.get('https://open.spotify.com/api/server-time', timeout=5)
        if server_time_response.ok:
            server_time_data = server_time_response.json()
            # Convert milliseconds to seconds, with fallback to local time
            server_ts_seconds = int(server_time_data.get('timestamp', now_ts_seconds * 1000)) // 1000
    except requests.exceptions.RequestException:
        # Fallback: if server time fails, use local time for both (see librespot issue #1475) 
        pass

    # Generate TOTPs
    totp_local = generate_spotify_totp(now_ts_seconds)
    totp_server = generate_spotify_totp(server_ts_seconds)

   
    params = {
        'reason': 'init',
        'productType': 'web-player',
        'totp': totp_local,
        'totpServer': totp_server,
        'totpServerTime': server_ts_seconds,
        'totpVer': '10',
        'sTime': now_ts_seconds,
        'cTime': now_ts_seconds * 1000,
        'buildVer': 'web-player_2024-06-12_1749598284688_68a7f1a',
        'buildDate': '2024-06-12'
    }
    url = 'https://open.spotify.com/api/token'

    try:
        resp = session.get(url, params=params, allow_redirects=False)
        resp.raise_for_status()
        token_data = resp.json()
        access_token = token_data.get('accessToken')
        if access_token:
            return access_token, None
        return None, "Token request succeeded, but no 'accessToken' in response. The cookie might be valid but expired for this action."
    except requests.exceptions.HTTPError as e:
        error_details = f"Failed to get token (Status: {e.response.status_code}). Your sp_dc cookie is likely invalid or expired."
        try: 
            error_details += f" Details: {e.response.json().get('error', {}).get('message', '')}"
        except requests.exceptions.JSONDecodeError:
            pass
        return None, error_details
    except requests.exceptions.RequestException as e:
        return None, f"A network error occurred while getting the token: {e}"

# --- UNCHANGED FUNCTIONS ---
def get_friend_activity(web_access_token: str) -> tuple[dict | None, str | None]:
    """Fetches the friend activity feed using a web access token."""
    url = 'https://guc-spclient.spotify.com/presence-view/v1/buddylist'
    headers = {'Authorization': f'Bearer {web_access_token}'}
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        return response.json(), None
    except requests.exceptions.HTTPError as e:
        return None, f"HTTP error fetching friend activity (Status: {e.response.status_code}). The access token may have expired or is invalid."
    except requests.exceptions.RequestException as e:
        return None, f"A network error occurred while fetching activity: {e}"

def process_friend_activity(activity_data: dict) -> list:
    """Parses API data and returns a list of friend dicts for the template."""
    processed_friends = []
    friends = activity_data.get('friends', [])
    for friend in friends:
        user = friend.get('user', {})
        track = friend.get('track', {})
        processed_friends.append({
            'timestamp': friend.get('timestamp'),
            'user_name': user.get('name', 'Unknown User'),
            'user_url': format_spotify_uri_as_url(user.get('uri', '#')),
            'user_image_url': user.get('imageUrl', 'https://i.scdn.co/image/ab6761610000e5eb1020c22n9ce49719111p685a'),
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
