"""Coalesce progress updates so a fast producer cannot flood the GUI queue."""

from threading import Lock


class ProgressBuffer:
    def __init__(self):
        self._lock = Lock()
        self._latest = {}

    def put(self, filename, downloaded, total):
        with self._lock:
            self._latest[filename] = (downloaded, total)

    def take(self):
        with self._lock:
            latest, self._latest = self._latest, {}
        return latest
