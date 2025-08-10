"""
Answers folder watcher that triggers inference when new audio appears.
"""

import os
import time
import threading
from typing import Callable, Optional


class AnswersWatcher:
    """Watches a directory for new/updated .wav files and invokes a callback.

    The callback signature: (path: str) -> None
    """

    def __init__(self, answers_dir: str, on_new_answer: Callable[[str], None], poll_interval: float = 0.3) -> None:
        self.answers_dir = answers_dir
        self.on_new_answer = on_new_answer
        self.poll_interval = poll_interval
        self._stop_flag = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_flag = False
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_flag = True
        if self._thread:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        print(f"[MuseTalk][Watcher] Watching answers dir: {self.answers_dir}")
        last_seen: Optional[str] = None
        last_mtime: float = 0.0
        while not self._stop_flag:
            try:
                files = [f for f in os.listdir(self.answers_dir) if f.lower().endswith('.wav')]
                if files:
                    abs_files = [os.path.join(self.answers_dir, f) for f in files]
                    abs_files.sort(key=lambda p: os.path.getmtime(p))
                    newest = abs_files[-1]
                    mtime = os.path.getmtime(newest)
                    if newest != last_seen or mtime > last_mtime:
                        last_seen = newest
                        last_mtime = mtime
                        print(f"[MuseTalk][Watcher] Detected new answer: {newest}")
                        try:
                            self.on_new_answer(newest)
                        except Exception as e:
                            print(f"[MuseTalk][Watcher] Callback error: {e}")
                time.sleep(self.poll_interval)
            except Exception as e:
                print(f"[MuseTalk][Watcher] Error: {e}")
                time.sleep(1.0)


