"""Rebuilds on change: polls mtimes and file lists of the vault, no dependency."""

import os
import sys
import time

from .vault import Scanner

class Watcher:
    """Builds once, then again on change of any file the vault takes: pages and attachments.

    Changes within `debounce` seconds of each other make one build, a failed build keeps
    the last good output and watching goes on.
    """

    def __init__(self, build, interval=0.5, debounce=0.3, quiet=False, on_build=None, out=None):
        self.build = build
        self.interval = interval
        self.debounce = debounce
        self.quiet = quiet
        self.on_build = on_build
        self.out = out or sys.stdout
        self.outputs = {os.path.abspath(f) for f in build.outputs.values()}
        self.root = None

    def snapshot(self):
        """Every file the vault takes with its mtime and size, outputs left out."""
        if self.root is None:
            self.root = self.build.scan().root
        scanner = Scanner(self.root, '', self.build.filter)
        scanner.scan()
        files = [*scanner.pages(), *(f for files in scanner.attachments.values() for f in files)]
        res = {}
        for file in files:
            if file in self.outputs:
                continue
            try:
                st = os.stat(file)
            except OSError:
                continue
            res[file] = st.st_mtime_ns, st.st_size
        return res

    def print(self, text, error=False):
        if error or not self.quiet:
            print(text, file=self.out, flush=True)

    def run_build(self):
        """Builds, prints time, pages and outputs or the problems; True when built."""
        start = time.monotonic()
        stamp = time.strftime('%H:%M:%S')
        try:
            problems = self.build.run()
        except (OSError, ValueError) as e:
            problems = [f'error: {e}']
        for warning in self.build.warnings:
            self.print(f'warning: {warning}')
        for problem in problems:
            self.print(problem, error=True)
        if problems:
            self.print(f'{stamp} build failed, last good output stays')
            return False
        pages = len(self.build.selection.shown)
        outputs = ', '.join(self.build.outputs.values())
        self.print(f'{stamp} built {pages} pages: {outputs} ({time.monotonic() - start:.2f}s)')
        if self.on_build:
            self.on_build()
        return True

    def changes(self, last):
        """Waits for a change and until files stay the same for debounce seconds, returns the new snapshot."""
        while True:
            time.sleep(self.interval)
            current = self.snapshot()
            if current != last:
                break
        while True:
            time.sleep(self.debounce)
            settled = self.snapshot()
            if settled == current:
                return current
            current = settled

    def run(self, first=None):
        """Builds now and on every change till interrupted, calls first after the first good build."""
        last = self.snapshot()
        try:
            while True:
                if self.run_build() and first:
                    first()
                    first = None
                last = self.changes(last)
        except KeyboardInterrupt:
            pass
