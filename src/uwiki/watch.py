"""Rebuilds on change: watches filesystem events in the folders of the vault, its config and uwiki's code.

Events only wake it up: what changed is told by mtimes and sizes of the files the vault takes, as scanned then.
Restarts on change of uwiki's own code, as when editing it or upgrading,
and on change of options the config gives the command, which it takes on start only.
"""

import os
import shutil
import subprocess
import sys
import time

from watchfiles._rust_notify import RustNotify  # what watchfiles.watch runs: watching starts on creating it

from .config import Config
from .vault import Scanner

CODE = os.path.dirname(os.path.abspath(__file__))
RESTARTED = "UWIKI_RESTARTED"  # port of serve in the environment of the restarted one
IN_VAULT, IN_CODE, IN_CONFIG = "vault", "code", "config"  # what a folder is watched for


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


def code_files(folders=None):
    """Files of uwiki code, its folders added to folders."""
    for folder, subfolders, files in os.walk(CODE):
        subfolders[:] = [f for f in subfolders if f != "__pycache__"]
        if folders is not None:
            folders.add(os.path.realpath(folder))
        yield from (os.path.join(folder, f) for f in files)


def real(file):
    """Real path of the folder of file, joined with its name: the path events tell about it, existing or not."""
    folder, name = os.path.split(os.path.abspath(file))
    return os.path.join(os.path.realpath(folder), name)


def restart_command():
    """This command again: the same python and arguments, or uwiki from PATH when an upgrade removed them."""
    if os.path.exists(sys.executable) and os.path.exists(sys.argv[0]):
        return [sys.executable, *sys.orig_argv[1:]]
    uwiki = shutil.which("uwiki")
    return uwiki and [uwiki, *sys.argv[1:]]


def broken(command):
    """Last line of the error of importing the changed code by the python of command, None when it imports."""
    if command[0] != sys.executable:
        return None
    res = subprocess.run([sys.executable, "-c", "import uwiki.cli"], capture_output=True, text=True, check=False)
    return res.returncode and (res.stderr.strip().splitlines() or ["import failed"])[-1] or None


def restart(environ):
    """Replaces this process with its command run again, environ added to the environment."""
    command = restart_command()
    if not command:
        sys.exit("uwiki code changed, no uwiki to restart")
    sys.stdout.flush()
    os.execve(command[0], command, {**os.environ, **environ})


class Watcher:
    """Builds once, then again on change of any file the vault takes: pages and attachments,
    or of its config: `uwiki.toml` or `pyproject.toml` wherever `Config.load` looks, ones not there yet too.

    Watches filesystem events in the folders the vault scan enters, symlinked ones too, the config folders
    and uwiki code folders, one by one, each by its real path; anew when they change, as a folder is added.
    Events within `DEBOUNCE` seconds of each other, `LONGEST` at most, make one look at what changed:
    a scan as of then, compared with the one before; a change makes one build,
    a failed build keeps the last good output and watching goes on.
    A change of uwiki code raises `Restart`, so does a change of what options gives:
    the option defaults the config gives the command, which it takes on start only; None watches no options.
    The restart is left out when the code fails to import, a config that fails to load builds nothing,
    watching goes on either way.
    """

    DEBOUNCE = 0.3
    LONGEST = 2

    def __init__(self, build, quiet=False, out=None, options=None):
        self.build = build
        self.options = options
        self.given = options and options()  # option defaults the command started with
        self.quiet = quiet
        self.out = out or sys.stdout
        self.outputs = {os.path.abspath(f) for f in build.outputs.values()}
        written = [os.path.realpath(f) for f in build.outputs.values()]  # write_atomic writes through symlinks
        self.written = {
            *written,
            *(os.path.join(os.path.dirname(f), f".{os.path.basename(f)}.{os.getpid()}.tmp") for f in written),
        }
        self.root = None
        self.configs = set()  # real paths of the config files, existing or not
        self.folders = {}  # real path of a folder to watch: what for, IN_VAULT, IN_CODE or IN_CONFIG, the first that fits
        self.notify = None
        self.watched = None  # folders the notify watches

    def snapshot(self):
        """Mtime and size of every file the vault takes, outputs left out, of the uwiki code and of the config;
        the folders to watch for them as of now."""
        if self.root is None:
            self.root = (self.build.selection or self.build.scan()).root
        scanner = Scanner(self.root, self.build.filter)
        scanner.scan(links=False)
        vault = stats(f for f in scanner.file_paths() if f not in self.outputs)
        code_folders = set()
        code = stats(code_files(code_folders))
        configs = Config.files(self.root)
        self.configs = {real(f) for f in configs}
        folders = dict.fromkeys((os.path.dirname(f) for f in self.configs), IN_CONFIG)
        folders.update(dict.fromkeys(code_folders, IN_CODE))
        folders.update(dict.fromkeys((os.path.realpath(f) for f in scanner.folders), IN_VAULT))
        self.folders = folders
        return vault, code, stats(configs)

    def relevant(self, path):
        """Whether an event about path may change a snapshot: a file in a vault folder but not an output,
        a vault folder, a config file or a file in a code folder."""
        if path in self.configs or self.folders.get(path) == IN_VAULT:
            return True
        kind = self.folders.get(os.path.dirname(path))
        if kind == IN_VAULT:
            return path not in self.written
        return kind == IN_CODE and not path.endswith(".pyc")

    def listen(self):
        """Watches the folders of the last snapshot, anew when they differ from the ones watched; True when anew."""
        if self.folders.keys() == self.watched:
            return False
        self.close()
        watched = set(self.folders)
        folders = sorted(f for f in watched if os.path.isdir(f))
        # paths, debug, force_polling, poll_delay_ms, recursive, ignore_permission_denied
        self.notify = RustNotify(folders, False, False, 0, False, True)
        self.watched = watched
        return True

    def close(self):
        if self.notify:
            self.notify.close()
        self.notify = self.watched = None

    def changes(self, last):
        """Waits for events until the snapshot differs from last, returns the new one.
        Watching anew looks at once, for what changed while not watching, a build or the scan before it."""
        while True:
            try:
                anew = self.listen()
            except FileNotFoundError:  # a folder went since the scan
                self.snapshot()
                continue
            if not anew:
                events = self.notify.watch(int(self.LONGEST * 1000), int(self.DEBOUNCE * 1000), 0, None)
                if events == "signal":
                    raise KeyboardInterrupt
                if not any(self.relevant(path) for _, path in events):
                    continue
            current = self.snapshot()
            if current != last:
                return current

    def print(self, text, error=False):
        if error or not self.quiet:
            print(text, file=self.out, flush=True)

    def run_build(self):
        """Builds, prints time, pages and outputs or the problems; True when built."""
        start = time.monotonic()
        stamp = time.strftime("%H:%M:%S")
        try:
            problems = self.build.run()
        except (OSError, ValueError) as e:
            problems = [f"error: {e}"]
        for warning in self.build.warnings:
            self.print(f"warning: {warning}")
        for problem in problems:
            self.print(problem, error=True)
        if problems:
            self.print(f"{stamp} build failed, last good output stays")
            return False
        pages = len(self.build.selection.shown)
        outputs = ", ".join(self.build.outputs.values())
        self.print(f"{stamp} built {pages} pages: {outputs} ({time.monotonic() - start:.2f}s)")
        return True

    def restart(self, what):
        """Raises `Restart` unless the code fails to import, then tells so and goes on."""
        stamp = time.strftime("%H:%M:%S")
        command = restart_command()
        error = command and broken(command)
        if not error:
            self.print(f"{stamp} {what} changed, restarting")
            raise Restart({})
        self.print(f"{stamp} uwiki code fails to import, not restarting: {error}", error=True)

    def config_changed(self):
        """Raises `Restart` when the options the config gives change, False when it fails to load."""
        try:
            options = self.options and self.options()
            _ = Config.load(self.root).schema  # the property validates it
        except ValueError as e:
            self.print(f"error: {e}", error=True)
            self.print(f"{time.strftime('%H:%M:%S')} config fails to load, last good output stays")
            return False
        if options != self.given:
            self.restart("config options")
        return True

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
                    self.restart("uwiki code")
                vault_changed = current[0] != last[0]
                if current[2] != last[2]:
                    vault_changed = self.config_changed()
                last = current
        except KeyboardInterrupt:
            pass
        finally:
            self.close()
