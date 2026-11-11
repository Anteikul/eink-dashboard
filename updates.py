"""Install immutable dashboard releases and keep device data in the installation directory."""
import fcntl
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import time
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from threading import Lock, Thread
from urllib.request import Request, urlopen

from device_settings import write_private

REPOSITORY = 'Anteikul/eink-dashboard'
GITHUB_API = f'https://api.github.com/repos/{REPOSITORY}'
REVISION = re.compile(r'[0-9a-f]{40}')
RESTART_EXIT = 75
BUSY = ('checking', 'downloading', 'restarting')


def read_revision(path):
    try:
        value = path.read_text(encoding='utf-8').strip()
    except (FileNotFoundError, UnicodeError):
        return None
    return value if REVISION.fullmatch(value) else None


def installed_version(source):
    version = read_revision(source / 'VERSION')
    if version is not None:
        return version
    try:
        root, head = subprocess.check_output(
            ['git', '-C', str(source), 'rev-parse', '--show-toplevel', 'HEAD'],
            text=True, stderr=subprocess.DEVNULL, timeout=3,
        ).splitlines()
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    return head if Path(root).resolve() == source and REVISION.fullmatch(head) else None


def github_json(path):
    request = Request(GITHUB_API + path, headers={
        'Accept': 'application/vnd.github+json', 'User-Agent': 'eink-dashboard',
    })
    with urlopen(request, timeout=8) as response:
        return json.load(response)


def latest_version():
    version = github_json('/git/ref/heads/main')['object']['sha']
    if not isinstance(version, str) or not REVISION.fullmatch(version):
        raise ValueError('Invalid GitHub revision')
    return version


def is_ahead(current, target):
    return github_json(f'/compare/{current}...{target}?per_page=1')['status'] == 'ahead'


def extract_release(response, directory, version):
    root = f'eink-dashboard-{version}'
    total = 0
    with tarfile.open(fileobj=response, mode='r|gz') as bundle:
        for count, item in enumerate(bundle, 1):
            path = PurePosixPath(item.name)
            if (not path.parts or path.parts[0] != root or '..' in path.parts
                    or not (item.isdir() or item.isreg())):
                raise ValueError('Unsafe release archive')
            total += item.size
            if count > 512 or total > 24 * 1024 * 1024:
                raise ValueError('Release archive is too large')
            if item.isdir():
                continue
            if len(path.parts) == 1:
                raise ValueError('Invalid release archive')
            destination = directory.joinpath(*path.parts[1:])
            destination.parent.mkdir(parents=True, exist_ok=True)
            with bundle.extractfile(item) as contents, destination.open('xb') as output:
                shutil.copyfileobj(contents, output)
    if read_revision(directory / 'VERSION') != version:
        raise ValueError('Release version did not match GitHub')


class UpdateStore:
    def __init__(self, data):
        self.data = data
        self.root = data / '.updates'
        self.releases = self.root / 'releases'
        self.releases.mkdir(parents=True, exist_ok=True)
        self.active = self.root / 'active'
        self.pending = self.root / 'pending'
        self.failed = self.root / 'failed'


def prepare_release(store, version):
    release = store.releases / version
    if read_revision(release / 'VERSION') == version:
        return
    with TemporaryDirectory(dir=store.root) as folder:
        candidate = Path(folder)
        request = Request(f'https://codeload.github.com/{REPOSITORY}/tar.gz/{version}',
                          headers={'User-Agent': 'eink-dashboard'})
        with urlopen(request, timeout=15) as response:
            extract_release(response, candidate, version)
        subprocess.run([sys.executable, '-B', '-c',
                        "import dashboard, panel, updates; dashboard.render_layout_preview('dashboard', None, 'light', 'en', 'celsius')"],
                       cwd=candidate, env={**os.environ, 'EINK_DATA_DIR': str(store.data)}, check=True, timeout=25)
        candidate.rename(release)


class Updater:
    def __init__(self, store, version, restart):
        self.store = store
        self.version = version
        self.restart = restart
        self.lock = Lock()
        self.state = 'idle'

    def status(self):
        with self.lock:
            state = self.state
            if read_revision(self.store.pending):
                state = 'restarting'
            elif state == 'idle' and read_revision(self.store.failed):
                state = 'rolled_back'
            return {'state': state, 'version': self.version}

    def set_state(self, state):
        with self.lock:
            self.state = state

    def check(self, retry=False):
        with self.lock:
            if self.state not in BUSY and not read_revision(self.store.pending):
                self.state = 'checking'
                Thread(target=self.check_and_prepare, args=(retry,), daemon=True).start()
        return self.status()

    def check_and_prepare(self, retry):
        try:
            version = latest_version()
            if version == self.version or (self.version is not None and not is_ahead(self.version, version)):
                self.set_state('current')
                return
            if not retry and read_revision(self.store.failed) == version:
                self.set_state('rolled_back')
                return
            self.set_state('downloading')
            prepare_release(self.store, version)
            write_private(self.store.pending, version + '\n')
            self.set_state('restarting')
            self.restart()
        except Exception as error:
            print(f'Update failed ({type(error).__name__}): {error}', flush=True)
            self.set_state('failed')


def supervise(store, args):
    data = store.data
    child = None
    stopping = False

    def stop(signum, _frame):
        nonlocal stopping
        stopping = True
        if child is not None:
            child.send_signal(signum)

    def start(source, ready=None):
        env = {**os.environ, 'EINK_DATA_DIR': str(data), 'EINK_SUPERVISED': '1'}
        env.pop('EINK_UPDATE_READY', None)
        if ready is not None:
            env['EINK_UPDATE_READY'] = str(ready)
        return subprocess.Popen([sys.executable, '-u', str(source / 'dashboard.py'), *args], cwd=data, env=env)

    previous_handlers = {signum: signal.signal(signum, stop) for signum in (signal.SIGINT, signal.SIGTERM)}
    try:
        while not stopping:
            candidate = read_revision(store.pending)
            active = read_revision(store.active)
            source = store.releases / active if active else data
            if active and read_revision(source / 'VERSION') != active:
                source = data
            elif candidate and candidate == active:
                store.pending.unlink(missing_ok=True)
                candidate = None
            if candidate:
                with TemporaryDirectory(dir=store.root) as folder:
                    ready = Path(folder) / 'ready'
                    child = start(store.releases / candidate, ready)
                    deadline = time.monotonic() + 40
                    while not stopping and not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                        time.sleep(.1)
                    if stopping:
                        return child.wait()
                    if ready.exists() and child.poll() in (None, 0):
                        write_private(store.active, candidate + '\n')
                        store.pending.unlink(missing_ok=True)
                        store.failed.unlink(missing_ok=True)
                        for release in store.releases.iterdir():
                            if release.name not in (active, candidate) and REVISION.fullmatch(release.name):
                                shutil.rmtree(release, ignore_errors=True)
                        print(f'Update installed: {candidate[:7]}', flush=True)
                    else:
                        child.terminate()
                        try:
                            child.wait(timeout=15)
                        except subprocess.TimeoutExpired:
                            child.kill()
                            child.wait()
                        write_private(store.failed, candidate + '\n')
                        store.pending.unlink(missing_ok=True)
                        print(f'Update rolled back: {candidate[:7]}', flush=True)
                        continue
            else:
                child = start(source)
            result = child.wait()
            if stopping or result != RESTART_EXIT:
                return result
        return 0
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)


def launch(data, args):
    store = UpdateStore(data)
    with (store.root / 'launcher.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Dashboard already running.', file=sys.stderr)
            return 1
        return supervise(store, args)


if __name__ == '__main__':
    sys.exit(launch(Path(__file__).resolve().parent, sys.argv[1:]))
