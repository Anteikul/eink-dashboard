"""Read Spotify playback and refresh the read-only PKCE session on the Pi."""
import json
import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass, replace
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen

TOKEN_URL = 'https://accounts.spotify.com/api/token'
PLAYBACK_URL = 'https://api.spotify.com/v1/me/player/currently-playing'
QUEUE_URL = 'https://api.spotify.com/v1/me/player/queue'
SPOTIFY_ID = re.compile(r'[A-Za-z0-9]{22}')
PLAYING_INTERVAL, IDLE_INTERVAL = 5, 8


@dataclass(frozen=True)
class Track:
    id: str
    title: str
    artist: str
    album_id: str = ''
    artwork: str = ''

    @property
    def url(self):
        return f'https://open.spotify.com/track/{self.id}'


@dataclass(frozen=True)
class Playback:
    track: Track
    duration_ms: int
    position_ms: int | None
    sampled_at: float

    def position_at(self, now):
        elapsed_ms = int(max(0, now - self.sampled_at) * 1000)
        return min(self.duration_ms, (self.position_ms or 0) + elapsed_ms)

    def progress_at(self, now):
        return self.position_at(now) / self.duration_ms if self.duration_ms else 0

    def with_estimate(self, previous):
        if self.position_ms is not None or previous is None or previous.track.id != self.track.id:
            return self
        return replace(self, position_ms=previous.position_at(self.sampled_at))


def album_artwork(images):
    choices = []
    for image in images:
        url = image.get('url') or ''
        parts = urlsplit(url)
        if parts.scheme == 'https' and (parts.hostname or '').endswith(('.scdn.co', '.spotifycdn.com')):
            choices.append((abs((image.get('width') or 300) - 300), url))
    return min(choices)[1] if choices else ''


def parse_track(item):
    track_id = item.get('id') or ''
    if item.get('type') != 'track' or not SPOTIFY_ID.fullmatch(track_id):
        return None
    artist = ', '.join(value['name'] for value in item.get('artists', []) if value.get('name'))
    album = item.get('album') or {}
    album_id = album.get('id') or ''
    return Track(track_id, item['name'], artist, album_id if SPOTIFY_ID.fullmatch(album_id) else '',
                 album_artwork(album.get('images') or []))


def playing_track(payload, *, sampled_at=None):
    if not payload.get('is_playing'):
        return None
    item = payload.get('item') or {}
    track = parse_track(item)
    if track is None:
        return None
    duration = max(0, item.get('duration_ms') or 0)
    position = payload.get('progress_ms')
    if position is not None:
        position = max(0, min(duration, position))
    return Playback(track, duration, position, time.monotonic() if sampled_at is None else sampled_at)


def queue_tracks(payload, current):
    active = payload.get('currently_playing') or {}
    if active.get('id') != current.id:
        return ()
    queued = (payload.get('queue') or [])[:2]
    return tuple(track for item in queued if (track := parse_track(item)) is not None)


def prefetch_covers(tracks, prepare_cover):
    started = time.monotonic()
    count = sum(prepare_cover(track) is not None for track in tracks)
    if count:
        print(f'Spotify: {count} queue covers ready in {time.monotonic() - started:.2f}s', flush=True)


class SpotifyPlayback:
    def __init__(self, credentials_path, credentials_lock=None):
        self.credentials_path = credentials_path
        self.credentials_lock = credentials_lock or threading.Lock()
        self.request_lock = threading.Lock()
        self.credentials = json.loads(credentials_path.read_text(encoding='utf-8'))
        self.access_token = ''
        self.expires = 0
        self.latest = (None, 0)
        self.maximum_age = 40

    @property
    def current(self):
        prepared, timestamp = self.latest
        return prepared if time.monotonic() - timestamp < self.maximum_age else None

    def renew(self):
        request = Request(
            TOKEN_URL, data=urlencode({'grant_type': 'refresh_token', **self.credentials}).encode(),
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
        )
        with urlopen(request, timeout=8) as response:
            payload = json.load(response)
        new_refresh = payload.get('refresh_token')
        if new_refresh and new_refresh != self.credentials['refresh_token']:
            updated = {**self.credentials, 'refresh_token': new_refresh}
            with self.credentials_lock:
                if (self.credentials_path.is_file()
                        and json.loads(self.credentials_path.read_text()) == self.credentials):
                    with tempfile.NamedTemporaryFile(mode='w', dir=self.credentials_path.parent, delete=False) as staged:
                        path = Path(staged.name)
                        try:
                            json.dump(updated, staged)
                            staged.flush()
                            os.replace(path, self.credentials_path)
                        finally:
                            path.unlink(missing_ok=True)
                    self.credentials = updated
        self.access_token = payload['access_token']
        self.expires = time.monotonic() + int(payload['expires_in']) - 45

    def request_json(self, url, timeout):
        with self.request_lock:
            for attempt in range(2):
                if time.monotonic() >= self.expires:
                    self.renew()
                request = Request(url, headers={'Authorization': f'Bearer {self.access_token}'})
                try:
                    with urlopen(request, timeout=timeout) as response:
                        return {} if response.status == 204 else json.load(response)
                except HTTPError as error:
                    if error.code != 401 or attempt:
                        raise
                    self.expires = 0

    def read(self):
        return playing_track(self.request_json(PLAYBACK_URL, 8))

    def read_next(self, current):
        return queue_tracks(self.request_json(QUEUE_URL, 2), current)

    def poll(self, stop, prepare_cover, *, playing_interval=PLAYING_INTERVAL, idle_interval=IDLE_INTERVAL,
             prefetch=True, enabled=None):
        self.maximum_age = max(40, playing_interval + 20)
        known = False
        previous_playback = None
        end_checks = 0
        queue_allowed = prefetch
        queue_checked = False
        cover_worker = None
        while not stop.is_set():
            if enabled is not None and not enabled():
                self.latest = None, 0
                known = False
                previous_playback = None
                stop.wait(1)
                continue
            try:
                playback = self.read()
                track = playback.track if playback else None
                delay = playing_interval if track else idle_interval
                previous_track = previous_playback.track if previous_playback else None
                changed = not known or track != previous_track
                if changed:
                    print('Spotify: playing track' if track else 'Spotify: idle', flush=True)
                    end_checks = 0
                    queue_checked = False
                known = True
                if (end_checks and playback and previous_playback
                        and playback.position_ms is not None and previous_playback.position_ms is not None
                        and playback.position_ms + 1000 < previous_playback.position_ms):
                    end_checks = 0  # Seek back or repeat of the same track.
                    queue_checked = False
                if playback:
                    playback = playback.with_estimate(previous_playback)
                previous_playback = playback
                cover_started = time.monotonic()
                cover = prepare_cover(track) if playback else None
                now = time.monotonic()
                if changed and cover is not None:
                    print(f'Spotify: current cover ready in {now - cover_started:.2f}s', flush=True)
                self.latest = ((playback, cover) if playback else None, now)
                remaining = None
                if playback and playback.duration_ms:
                    remaining = (playback.duration_ms - playback.position_at(now)) / 1000
                    if remaining > delay:
                        end_checks = 0
                    elif end_checks < 2:
                        # Probe at the estimated end, then allow one retry for Spotify to catch up.
                        delay = max(remaining, 1 if end_checks else 0.2)
                        end_checks += 1
                        print(f'Spotify: end-of-track check in {delay:.2f}s', flush=True)
                if (playback and queue_allowed and not queue_checked and (remaining is None or remaining > 5)
                        and (cover_worker is None or not cover_worker.is_alive())):
                    queue_checked = True
                    try:
                        upcoming = self.read_next(track)
                    except HTTPError as error:
                        if error.code == 429:
                            raise
                        queue_allowed = error.code not in (403, 404)
                        print(f'Spotify queue: HTTP {error.code}', flush=True)
                    except (OSError, KeyError, TypeError, ValueError):
                        print('Spotify queue unavailable', flush=True)
                    else:
                        if upcoming:
                            cover_worker = threading.Thread(
                                    target=prefetch_covers, args=(upcoming, prepare_cover), daemon=True)
                            cover_worker.start()
                    delay = max(0, now + delay - time.monotonic())
            except HTTPError as error:
                print(f'Spotify API: HTTP {error.code}', flush=True)
                delay = 60 if error.code in (400, 401, 403) else 16
                if error.code == 429:
                    retry = error.headers.get('Retry-After', '')
                    delay = max(delay, int(retry)) if retry.isdigit() else 30
            except (OSError, KeyError, TypeError, ValueError) as error:
                print(f'Spotify API unavailable ({type(error).__name__})', flush=True)
                delay = 16
            stop.wait(delay)
