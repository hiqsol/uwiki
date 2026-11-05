"""Rebuilds on change: polls mtimes and file lists of the vault, no dependency.

Restarts on change of uwiki's own code, as when editing it or upgrading.
"""

import os
import shutil
import subprocess
import sys
import time

from .vault import Scanner

CODE = os.path.dirname(os.path.abspath(__file__))
RESTARTED = 'UWIKI_RESTARTED'  # port of serve in the environment of the restarted one

class Restart(Exception):
    """uwiki code changed: the command runs again as a new process, with the environment of args[0] added."""

    @property
    def environ(self):
        return self.args[0]

def stats(files):
    """Mtime and size of the files that exist."""
    res = {}
    for file in files:
        try:
            st = os.stat(file)
        except OSError:
            continue
        res[file] = st.st_mtime_ns, st.st_size
    return res

def code_files():
    for folder, folders, files in os.walk(CODE):
        folders[:] = [f for f in folders if f != '__pycache__']
        yield from (os.path.join(folder, f) for f in files)

def restart_command():
    """This command again: the same python and arguments, or uwiki from PATH when an upgrade removed them."""
    if os.path.exists(sys.executable) and os.path.exists(sys.argv[0]):
        return [sys.executable, *sys.orig_argv[1:]]
    uwiki = shutil.which('uwiki')
    return uwiki and [uwiki, *sys.argv[1:]]

def broken(command):
    """Last line of the error of importing the changed code by the python of command, None when it imports."""
    if command[0] != sys.executable:
        return None
    res = subprocess.run([sys.executable, '-c', 'import uwiki.cli'], capture_output=True, text=True)
    return res.returncode and (res.stderr.strip().splitlines() or ['import failed'])[-1] or None

def restart(environ):
    """Replaces this process with its command run again, environ added to the environment."""
    command = restart_command()
    if not command:
        sys.exit('uwiki code changed, no uwiki to restart')
    sys.stdout.flush()
    os.execve(command[0], command, {**os.environ, **environ})

class Watcher:
    """Builds once, then again on change of any file the vault takes: pages and attachments.

    Changes within `DEBOUNCE` seconds of each other, or the interval when shorter, make one build,
    a failed build keeps the last good output and watching goes on.
    A change of uwiki code raises `Restart`, unless the code fails to import: then watching goes on.
    """

    DEBOUNCE = 0.3

    def __init__(self, build, interval=0.5, quiet=False, out=None):
        self.build = build
        self.interval = interval
        self.quiet = quiet
        self.out = out or sys.stdout
        self.outputs = {os.path.abspath(f) for f in build.outputs.values()}
        self.root = None

    def snapshot(self):
        """Every file the vault takes with its mtime and size, outputs left out, and the uwiki code files."""
        if self.root is None:
            self.root = (self.build.selection or self.build.scan()).root
        scanner = Scanner(self.root, self.build.filter)
        scanner.scan(links=False)
        return stats(f for f in scanner.file_paths() if f not in self.outputs), stats(code_files())

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
        return True

    def changes(self, last):
        """Waits for a change and until files stay the same for debounce seconds, returns the new snapshot."""
        while True:
            time.sleep(self.interval)
            current = self.snapshot()
            if current != last:
                break
        while True:
            time.sleep(min(self.DEBOUNCE, self.interval))
            settled = self.snapshot()
            if settled == current:
                return current
            current = settled

    def code_changed(self):
        """Raises `Restart` unless the changed code fails to import, then tells so and goes on."""
        stamp = time.strftime('%H:%M:%S')
        command = restart_command()
        error = command and broken(command)
        if not error:
            self.print(f'{stamp} uwiki code changed, restarting')
            raise Restart({})
        self.print(f'{stamp} uwiki code fails to import, not restarting: {error}', error=True)

    def run(self, first=None):
        """Builds now and on every change till interrupted, calls first after the first good build."""
        last = self.snapshot()
        vault_changed = True
        try:
            while True:
                if vault_changed and self.run_build() and first:
                    first()
                    first = None
                current = self.changes(last)
                if current[1] != last[1]:
                    self.code_changed()
                vault_changed = current[0] != last[0]
                last = current
        except KeyboardInterrupt:
            pass
