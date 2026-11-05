"""Serves the built HTML with http.server, rebuilding on change and reloading the page."""

import os
import signal
import sys
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, unquote, urlsplit

from .watch import Watcher

FILES = '/__uwiki/files/'
BUILD = '/__uwiki/build'

class Handler(SimpleHTTPRequestHandler):
    """Output folder files, the id of the last good build and vault attachments the build links."""

    def __init__(self, *args, server_state, **kwargs):
        self.state = server_state
        super().__init__(*args, **kwargs)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == BUILD:
            return self.text(self.state.build.build_id)
        if path == '/':
            self.send_response(302)
            self.send_header('Location', '/' + quote(os.path.basename(self.state.page)))
            self.end_headers()
            return
        return super().do_GET()

    def translate_path(self, path):
        path = urlsplit(path).path
        if path.startswith(FILES):
            file = os.path.join(self.state.root, unquote(path[len(FILES):]))
            return file if os.path.abspath(file) in self.state.attachments() else ''
        return super().translate_path(path)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()

    def text(self, text):
        body = text.encode()
        self.send_response(200)
        self.send_header('Content-Type', 'text/plain; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass

def interrupt(signum, frame):
    """Stops on SIGTERM as on Ctrl+C, so the temporary output goes away."""
    raise KeyboardInterrupt

class Server:
    """Watches as `uwiki watch` does and serves the output folder, by default on localhost only."""

    def __init__(self, build, host='127.0.0.1', port=8000, open=False, interval=0.5, quiet=False, out=None):
        self.build = build
        self.page = build.outputs['html']
        self.outdir = os.path.dirname(os.path.abspath(self.page))
        self.root = None
        self._attachments = None, set()  # selection: attachment files of its vault
        self.open = open
        self.out = out or sys.stdout
        self.watcher = Watcher(build, interval, quiet=quiet, out=self.out)
        handler = partial(Handler, server_state=self, directory=self.outdir)
        self.httpd = ThreadingHTTPServer((host, port), handler)
        self.httpd.daemon_threads = True
        host, self.port = self.httpd.server_address[:2]
        self.url = f'http://{host}:{self.port}/' + quote(os.path.basename(self.page))

    def attachments(self):
        """Attachment files of the last scan, collected once per build."""
        selection = self.build.selection
        if selection is None:
            return set()
        if self._attachments[0] is not selection:
            self._attachments = selection, {os.path.abspath(f) for f in selection.scanner.file_paths(pages=False)}
        return self._attachments[1]

    def run(self):
        signal.signal(signal.SIGTERM, interrupt)
        self.root = self.build.scan().root
        thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        thread.start()
        print(f'serving {self.url}', file=self.out, flush=True)
        try:
            self.watcher.run(first=self.opened)
        finally:
            self.httpd.shutdown()
            self.httpd.server_close()

    def opened(self):
        if self.open:
            webbrowser.open(self.url)
