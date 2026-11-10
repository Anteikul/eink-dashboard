"""Publish the dashboard's IPv4 address on the local network."""
import subprocess
import time

HOSTNAME = 'eink.local'


class LocalName:
    def __init__(self):
        self.address = None
        self.publisher = None
        self.retry_at = 0

    def update(self, address):
        if address != self.address:
            self.close()
            self.address = address
            self.retry_at = 0
        if not address or (self.publisher and self.publisher.poll() is None):
            return
        now = time.monotonic()
        if now < self.retry_at:
            return
        self.retry_at = now + 15
        try:
            self.publisher = subprocess.Popen(
                ['avahi-publish-address', '--no-reverse', HOSTNAME, address],
                stdin=subprocess.DEVNULL,
            )
        except OSError as error:
            print(f'Could not publish {HOSTNAME}: {error}', flush=True)

    def close(self):
        publisher, self.publisher = self.publisher, None
        if publisher and publisher.poll() is None:
            publisher.terminate()
            try:
                publisher.wait(timeout=2)
            except subprocess.TimeoutExpired:
                publisher.kill()
                publisher.wait()
