"""Bounded durable streaming buffers shared by CLI and desktop runs."""

import threading


class StreamBuffer:
    def __init__(self, store, session_id, run_id):
        self.store, self.session_id, self.run_id = store, session_id, run_id
        self.pending = {}
        self.size = 0
        self.lock = threading.RLock()
        self.timer = None
        self.error = None

    def append(self, kind, text):
        with self.lock:
            if self.error:
                raise self.error
            raw = text.encode('utf-8')
            offset = 0
            while offset < len(raw):
                piece = raw[offset:offset+16*1024-self.size].decode('utf-8',errors='ignore')
                if not piece:
                    self.flush()
                    continue
                length = len(piece.encode('utf-8'))
                self.pending.setdefault(kind, []).append(piece)
                self.size += length
                offset += length
                if self.size == 16*1024:
                    self.flush()
            if self.size and self.timer is None:
                self.timer = threading.Timer(0.25, self._timed_flush)
                self.timer.daemon = True
                self.timer.start()

    def _timed_flush(self):
        try:
            self.flush()
        except Exception as error:
            self.error = error

    def flush(self):
        with self.lock:
            if self.timer:
                self.timer.cancel()
                self.timer = None
            if self.error:
                raise self.error
            for kind in list(self.pending):
                try:
                    self.store.write_stream(self.session_id,self.run_id,kind,''.join(self.pending[kind]))
                except Exception as error:
                    self.error = error
                    raise
                del self.pending[kind]
            self.size = 0
