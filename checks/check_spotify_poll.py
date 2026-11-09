from io import BytesIO
from unittest.mock import patch
from urllib.error import HTTPError

from spotify_playback import Playback, SpotifyPlayback, Track, queue_tracks

first = Track('01Txvu3dNthhldq8oR0Pae', 'First', 'Artist')
second = Track('629DixmZGHc7ILtEntuiWE', 'Second', 'Artist')


def observed_waits(responses, queue_requests=None):
    count = len(responses)
    responses = iter(responses)
    waits = []
    now = 10.0
    spotify = SpotifyPlayback.__new__(SpotifyPlayback)
    spotify.latest = (None, 0)

    class Stop:
        def is_set(self):
            return len(waits) == count

        def wait(self, delay):
            nonlocal now
            waits.append(delay)
            now += delay

    def read():
        response = next(responses)
        if isinstance(response, HTTPError):
            raise response
        if response is not None:
            return Playback(*response, sampled_at=now)
        return None

    spotify.read = read

    def read_next(track):
        if queue_requests is not None:
            queue_requests.append((track.id, now))
        return None

    spotify.read_next = read_next
    with patch('spotify_playback.time.monotonic', side_effect=lambda: now):
        spotify.poll(Stop(), lambda _: None)
    return waits


assert observed_waits([
    (first, 100_000, 97_000), (first, 100_000, 100_000), (first, 100_000, 100_000),
    (second, 200_000, 4_000), None,
]) == [3, 1, 5, 5, 8]
assert observed_waits([
    (first, 100_000, 97_000),
    HTTPError('https://api.spotify.com', 429, '', {'Retry-After': '41'}, BytesIO()),
]) == [3, 41]
assert observed_waits([
    (first, 3_000, 2_500), (first, 3_000, 0), None,
]) == [0.5, 3, 8]
queue_requests = []
assert observed_waits([
    (first, 100_000, 70_000), (first, 100_000, 75_000), (first, 100_000, 80_000),
    (first, 100_000, 98_000), (second, 100_000, 76_000),
], queue_requests) == [5, 5, 5, 2, 5]
assert queue_requests == [(first.id, 10), (second.id, 27)]
queued_item = {'id': second.id, 'type': 'track', 'name': second.title,
               'artists': [{'name': second.artist}]}
assert queue_tracks({'currently_playing': {'id': first.id}, 'queue': [queued_item] * 3}, first) == (second, second)
assert queue_tracks({'currently_playing': {'id': second.id}, 'queue': [queued_item]}, first) == ()
print('End-of-track, stale responses, repeat and Spotify backoff passed.')
