import time
import requests
import pyotp
import base64
from datetime import datetime
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

SECRETS_URL = "https://raw.githubusercontent.com/Thereallo1026/spotify-secrets/main/secrets/secrets.json"
FALLBACK_SECRET = "qR@.~y>1Wl$GEVP7^UmG )-" #v25, last known
LATEST_SPOTIFY_SECRET = "qR@.~y>1Wl$GEVP7^UmG )-"

def fetch_and_set_latest_secret():
    global LATEST_SPOTIFY_SECRET
    try:
        print("Fetching latest Spotify secrets...")
        response = requests.get(SECRETS_URL, timeout=10)
        response.raise_for_status()
        secrets_data = response.json()
        
        if not secrets_data:
            raise ValueError("Secrets data is empty.")
            
        latest_secret_obj = max(secrets_data, key=lambda x: x['version'])
        LATEST_SPOTIFY_SECRET = latest_secret_obj['secret']
        
        print(f"Successfully loaded Spotify secret version {latest_secret_obj['version']}.")

    except (requests.exceptions.RequestException, ValueError, KeyError) as e:
        print(f"!!! WARNING: Could not fetch latest Spotify secret: {e}")
        print(f"!!! Using fallback secret.")
        LATEST_SPOTIFY_SECRET = FALLBACK_SECRET

def format_spotify_uri_as_url(uri: str) -> str:
    if not isinstance(uri, str) or not uri.startswith('spotify:'): return uri
    path_part = uri.split(':', 1)[1]
    url_path = path_part.replace(':', '/')
    return f"https://open.spotify.com/{url_path}"

def generate_spotify_totp(timestamp_seconds: int) -> str:
    secret_string = LATEST_SPOTIFY_SECRET
    processed = [ord(char) ^ ((i % 33) + 9) for i, char in enumerate(secret_string)]
    processed_str = "".join(map(str, processed))
    utf8_bytes = processed_str.encode('utf-8')
    b32_secret = base64.b32encode(utf8_bytes).decode('utf-8')
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
    server_ts_seconds = now_ts_seconds
    try:
        server_time_response = session.get('https://open.spotify.com/api/server-time', timeout=5)
        if server_time_response.ok:
            server_time_data = server_time_response.json()
            server_ts_seconds = int(server_time_data.get('timestamp', now_ts_seconds * 1000)) // 1000
    except requests.exceptions.RequestException:
        pass

    totp_local = generate_spotify_totp(now_ts_seconds)
    totp_server = generate_spotify_totp(server_ts_seconds)

    params = {
        'reason': 'init',
        'productType': 'web-player',
        'totp': totp_local,
        'totpServer': totp_server,
        'totpServerTime': server_ts_seconds,
        'totpVer': '16',
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

def get_friend_activity(web_access_token: str) -> tuple[dict | None, str | None]:
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/activity', methods=['POST'])
def get_activity():
    data = request.get_json()
    if not data or 'sp_dc_cookie' not in data:
        return jsonify({"error": "sp_dc_cookie not provided."}), 400

    sp_dc_cookie = data['sp_dc_cookie']

    access_token, error = get_spotify_access_token(sp_dc_cookie)
    if error:
        return jsonify({"error": error}), 401

    friend_activity_data, error = get_friend_activity(access_token)
    if error:
        return jsonify({"error": error}), 500

    friends = process_friend_activity(friend_activity_data)
    return jsonify({"friends": friends})


if __name__ == '__main__':
    fetch_and_set_latest_secret()
    app.run(debug=True, port=5001)


