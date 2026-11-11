import io
import tarfile
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest.mock import patch

from updates import UpdateStore, Updater, extract_release, launch

old = 'a' * 40
new = 'b' * 40


def archive(entries):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode='w:gz') as bundle:
        for name, content in entries.items():
            item = tarfile.TarInfo(f'eink-dashboard-{new}/{name}')
            item.size = len(content)
            bundle.addfile(item, io.BytesIO(content))
    data.seek(0)
    return data


def stage(store, version, script):
    release = store.releases / version
    release.mkdir(parents=True)
    (release / 'VERSION').write_text(version)
    (release / 'dashboard.py').write_text(script)


with TemporaryDirectory() as directory:
    root = Path(directory)
    output = root / 'archive'
    output.mkdir()
    extract_release(archive({'VERSION': new.encode(), 'web/settings.html': b'example'}), output, new)
    assert (output / 'web/settings.html').read_bytes() == b'example'
    try:
        extract_release(archive({'../escape': b'bad'}), output, new)
    except ValueError:
        assert not (root / 'escape').exists()
    else:
        raise AssertionError('Unsafe archive path was accepted')

with TemporaryDirectory() as directory:
    root = Path(directory)
    store = UpdateStore(root)
    restarted = Event()
    updater = Updater(store, old, restarted.set)
    with patch('updates.latest_version', return_value=new), patch('updates.is_ahead', return_value=True), \
            patch('updates.prepare_release') as prepare:
        updater.check()
        assert restarted.wait(5)
    assert store.pending.read_text().strip() == new and prepare.call_count == 1
    assert updater.status() == {'state': 'restarting', 'version': old}

with TemporaryDirectory() as directory:
    root = Path(directory)
    store = UpdateStore(root)
    root.joinpath('dashboard.py').write_text('from pathlib import Path\nPath("old-started").touch()\n')
    root.joinpath('.settings.json').write_text('{"theme": "dark"}')
    stage(store, new, 'import os\nfrom pathlib import Path\nPath(os.environ["EINK_UPDATE_READY"]).touch()\n')
    store.pending.write_text(new)
    assert launch(root, []) == 0
    assert store.active.read_text().strip() == new and not store.pending.exists()
    assert root.joinpath('.settings.json').read_text() == '{"theme": "dark"}'
    assert not root.joinpath('old-started').exists()

with TemporaryDirectory() as directory:
    root = Path(directory)
    store = UpdateStore(root)
    stage(store, old, 'from pathlib import Path\nPath("old-started").touch()\n')
    store.active.write_text(old)
    stage(store, new, 'raise SystemExit(1)\n')
    store.pending.write_text(new)
    assert launch(root, []) == 0
    assert root.joinpath('old-started').exists() and store.active.read_text().strip() == old
    assert store.failed.read_text().strip() == new and not store.pending.exists()
    updater = Updater(store, old, lambda: None)
    with patch('updates.latest_version', return_value=new), patch('updates.is_ahead', return_value=True), \
            patch('updates.prepare_release') as prepare:
        updater.check_and_prepare(False)
        assert updater.status()['state'] == 'rolled_back' and not prepare.called
        updater.check_and_prepare(True)
        assert store.pending.read_text().strip() == new and prepare.call_count == 1

with TemporaryDirectory() as directory:
    root = Path(directory)
    root.joinpath('dashboard.py').write_text(
        'from pathlib import Path\nmarker = Path("restarted")\n'
        'if not marker.exists():\n    marker.touch()\n    raise SystemExit(75)\n')
    assert launch(root, []) == 0 and root.joinpath('restarted').exists()

print('Update download, staging, activation and recovery passed.')
