from PIL import Image

from dashboard import WIDTH, changed_regions, needs_full_refresh, pack
from music_screen import progress_pixels, render_music
from spotify_playback import playing_track

payload = {
    'is_playing': True,
    'progress_ms': 95_000,
    'item': {
        'id': '01Txvu3dNthhldq8oR0Pae', 'type': 'track', 'name': 'Money For Nothing',
        'artists': [{'name': 'Dire Straits'}], 'duration_ms': 240_000,
        'album': {'images': [
            {'url': 'https://i.scdn.co/image/large', 'width': 640},
            {'url': 'https://i.scdn.co/image/medium', 'width': 300},
        ]},
    },
}
playing = playing_track(payload, sampled_at=10.0)
assert playing.track.artwork == 'https://i.scdn.co/image/medium'
assert playing.position_at(10.0) == 95_000
assert playing.position_at(12.0) == 97_000
assert playing.progress_at(12.0) == 97_000 / 240_000
assert playing.progress_at(1000.0) == 1
assert playing_track({**payload, 'is_playing': False}) is None
unknown = playing_track({**payload, 'progress_ms': None}, sampled_at=15.0)
assert unknown.with_estimate(playing).position_at(16.0) == 101_000
assert unknown.with_estimate(None).position_at(16.0) == 1_000
seek = playing_track({**payload, 'progress_ms': 12_000}, sampled_at=15.0)
assert seek.with_estimate(playing).position_at(16.0) == 13_000
assert not needs_full_refresh('light', 'light', 5, advancing=True)
assert needs_full_refresh('light', 'dark', 5, advancing=True)
assert needs_full_refresh('light', 'light', 5)

cover = Image.new('1', (96, 96), 0)
for theme in ('light', 'dark'):
    earlier = render_music(playing.track, theme, cover, progress_pixels(.25, cover))
    later = render_music(playing.track, theme, cover, progress_pixels(.5, cover))
    differences = [index for index, (old, new) in enumerate(zip(earlier, later)) if old != new]
    assert differences
    assert all(index // WIDTH in (105, 106) and index % WIDTH > 118 for index in differences)
    assert all(later[y * WIDTH + 10] == 0 for y in range(13, 109))
    assert changed_regions(pack(earlier, 180), pack(later, 180))
print('Spotify art and progress parse correctly. Only the line pixels change as playback advances.')
