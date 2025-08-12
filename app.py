import time
import threading
import requests
import pyotp
import base64
from datetime import datetime
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# -----------------------------
# Config
# -----------------------------
SECRETS_URL = "https://raw.githubusercontent.com/Thereallo1026/spotify-secrets/main/secrets/secrets.json"
FALLBACK_SECRET = "X:<1zK2J|Oq2WLE3JNG`.},sdQ.%."  # v28, last known
LATEST_SPOTIFY_SECRET = FALLBACK_SECRET

# Refresh secrets every 6 hours
SECRET_TTL_SECONDS = 6 * 60 * 60
_LAST_SECRET_FETCH = 0.0
_SECRET_LOCK = threading.Lock()


# -----------------------------
# Secrets handling
# -----------------------------
def fetch_and_set_latest_secret(force: bool = False) -> None:
    """
    Fetch latest secret JSON and cache it with a TTL.
    Safe to call frequently; will be a no-op until TTL expires unless force=True.
    """
    global LATEST_SPOTIFY_SECRET, _LAST_SECRET_FETCH

    now = time.time()
    if not force and (now - _LAST_SECRET_FETCH) < SECRET_TTL_SECONDS:
        return

    with _SECRET_LOCK:
        # Another thread might have done it while we waited
        if not force and (time.time() - _LAST_SECRET_FETCH) < SECRET_TTL_SECONDS:
            return

        try:
            print("[secrets] Fetching latest Spotify secret...")
            resp = requests.get(
                SECRETS_URL,
                headers={"Accept": "application/json"},
                timeout=10
            )
            resp.raise_for_status()
            secrets_data = resp.json()
            if not secrets_data:
                raise ValueError("Secrets data is empty.")

            latest = max(secrets_data, key=lambda x: x["version"])
            LATEST_SPOTIFY_SECRET = latest["secret"]
            _LAST_SECRET_FETCH = time.time()
            print(f"[secrets] Loaded Spotify secret version {latest['version']}.")

        except (requests.RequestException, ValueError, KeyError) as e:
            print(f"[secrets] WARNING: Could not fetch latest secret: {e}")
            print("[secrets] Using fallback secret.")
            LATEST_SPOTIFY_SECRET = FALLBACK_SECRET
            _LAST_SECRET_FETCH = time.time()


# Fetch once at import so it works on Render/Gunicorn (main guard won't run there)
fetch_and_set_latest_secret(force=True)


# -----------------------------
# Utilities
# -----------------------------
def format_spotify_uri_as_url(uri: str) -> str:
    if not isinstance(uri, str) or not uri.startswith('spotify:'):
        return uri
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


# -----------------------------
# Spotify API helpers
# -----------------------------
def get_spotify_access_token(sp_dc_cookie: str) -> tuple[str | None, str | None]:
    # Ensure we have a relatively fresh secret
    fetch_and_set_latest_secret()

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

    def _make_params(ts_local: int, ts_server: int) -> dict:
        return {
            'reason': 'init',
            'productType': 'web-player',
            'totp': generate_spotify_totp(ts_local),
            'totpServer': generate_spotify_totp(ts_server),
            'totpServerTime': ts_server,
            'totpVer': '16',
            'sTime': ts_local,
            'cTime': ts_local * 1000,
            'buildVer': 'web-player_2024-06-12_1749598284688_68a7f1a',
            'buildDate': '2024-06-12'
        }

    url = 'https://open.spotify.com/api/token'
    params = _make_params(now_ts_seconds, server_ts_seconds)

    def _try_get(params: dict):
        resp = session.get(url, params=params, allow_redirects=False, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get('accessToken')

    try:
        token = _try_get(params)
        if token:
            return token, None
        return None, "Token request succeeded, but no 'accessToken' in response. The cookie might be valid but expired for this action."
    except requests.exceptions.HTTPError as e:
        should_retry = False
        status = getattr(e.response, "status_code", None)
        try:
            err_msg = (e.response.json().get('error', {}).get('message', '') or '').lower()
            if 'invalid totp' in err_msg:
                should_retry = True
        except Exception:
            pass

        if should_retry:
            # Force refresh secrets and retry once with fresh TOTP
            fetch_and_set_latest_secret(force=True)
            params = _make_params(int(time.time()), server_ts_seconds)
            try:
                token = _try_get(params)
                if token:
                    return token, None
            except Exception as e2:
                return None, f"Retry after refreshing secrets failed: {e2}"

        error_details = f"Failed to get token (Status: {status}). Your sp_dc cookie may be invalid or expired."
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
        response = requests.get(url, headers=headers, timeout=10)
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


# -----------------------------
# Routes
# -----------------------------
@app.route('/')
def index():
    # If you don't have templates, you can just return a simple text/JSON here.
    # return "OK"
    return render_template('index.html')


@app.route('/api/activity', methods=['POST'])
def get_activity():
    data = request.get_json(silent=True) or {}
    sp_dc_cookie = data.get('sp_dc_cookie')
    if not sp_dc_cookie:
        return jsonify({"error": "sp_dc_cookie not provided."}), 400

    access_token, error = get_spotify_access_token(sp_dc_cookie)
    if error:
        return jsonify({"error": error}), 401

    friend_activity_data, error = get_friend_activity(access_token)
    if error:
        return jsonify({"error": error}), 500

    friends = process_friend_activity(friend_activity_data)
    return jsonify({"friends": friends})




# -----------------------------
# Local dev entry point
# -----------------------------
if __name__ == '__main__':
    # On Render/Gunicorn this block won't run; import-time fetch handles secrets there.
    app.run(debug=True, port=5001)

