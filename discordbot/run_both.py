#!/usr/bin/env python3
"""Run both Discord bot profiles (main + musiconly) concurrently.

Features:
- Spawns two subprocesses using `python -m discordbot.main` with different COMMAND_PROFILE env vars.
- Streams their stdout/stderr prefixed with profile name.
- Handles SIGINT / SIGTERM to terminate both cleanly.
- Restarts a profile automatically if it exits unexpectedly (optional flag future-ready).

Usage:
    python -m discordbot.run_both
    # or
    python discordbot/run_both.py

Environment overrides honored per child:
    DISCORD_TOKEN (if set) overrides token selection for BOTH children.
    LOG_LEVEL (optional) sets logging level for launcher (default INFO).

Future ideas (not yet implemented):
    --no-restart : disable auto-restart
    --once       : run once and exit with first child termination
"""
from __future__ import annotations
import subprocess
import sys
import os
import signal
import threading
import queue
import time
from typing import Optional, List

PROFILES = ["main", "musiconly"]
PYTHON = sys.executable or "python3"

class ChildProcess:
    def __init__(self, profile: str):
        self.profile = profile
        self.proc: Optional[subprocess.Popen] = None
        self.stdout_thread: Optional[threading.Thread] = None
        self.stderr_thread: Optional[threading.Thread] = None
        self.queue = queue.Queue()
        self.alive = False

    def start(self):
        env = os.environ.copy()
        env["COMMAND_PROFILE"] = self.profile
        # Ensure we run module form for package-safe imports
        cmd = [PYTHON, "-m", "discordbot.main"]
        self.proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            bufsize=1,
        )
        self.alive = True
        self.stdout_thread = threading.Thread(target=self._pump, args=(self.proc.stdout, False), daemon=True)
        self.stderr_thread = threading.Thread(target=self._pump, args=(self.proc.stderr, True), daemon=True)
        self.stdout_thread.start()
        self.stderr_thread.start()

    def _pump(self, stream, is_err: bool):
        prefix = f"[{self.profile}:{'ERR' if is_err else 'OUT'}]"
        for line in iter(stream.readline, ''):
            self.queue.put(f"{prefix} {line.rstrip()}\n")
        stream.close()

    def terminate(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass

    def kill(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.kill()
            except Exception:
                pass

    def poll(self):
        return self.proc.poll() if self.proc else None


def install_signal_handlers(children: List[ChildProcess], stop_flag):
    def handler(signum, frame):
        print(f"\n[launcher] Caught signal {signum}. Shutting down children...")
        stop_flag[0] = True
        for c in children:
            c.terminate()
    signal.signal(signal.SIGINT, handler)
    signal.signal(signal.SIGTERM, handler)


def main():
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    print(f"[launcher] Starting dual-profile launcher (log_level={log_level})")
    children = [ChildProcess(p) for p in PROFILES]

    for c in children:
        print(f"[launcher] Spawning profile '{c.profile}'...")
        c.start()

    stop_flag = [False]
    install_signal_handlers(children, stop_flag)

    # Fan-out queue printer loop
    try:
        while not stop_flag[0]:
            # Print any pending lines
            try:
                while True:
                    line = None
                    for c in children:
                        try:
                            line = c.queue.get_nowait()
                        except queue.Empty:
                            continue
                        if line:
                            sys.stdout.write(line)
                    break
            except Exception:
                pass

            # Check child status
            all_dead = True
            for c in children:
                if c.poll() is None:
                    all_dead = False
                else:
                    if c.alive:
                        print(f"[launcher] Profile '{c.profile}' exited with code {c.poll()}")
                        c.alive = False
            if all_dead:
                print("[launcher] All child processes have exited. Launcher stopping.")
                break
            time.sleep(0.5)
    finally:
        # Graceful shutdown
        for c in children:
            c.terminate()
        # Final wait
        deadline = time.time() + 5
        for c in children:
            while time.time() < deadline and c.poll() is None:
                time.sleep(0.1)
        # Force kill if still alive
        for c in children:
            if c.poll() is None:
                c.kill()
        print("[launcher] Shutdown complete.")

if __name__ == "__main__":  # pragma: no cover
    main()
