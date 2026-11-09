"""Git commit a vault is built from, as the help of the built page tells it."""

import re
import subprocess
from dataclasses import dataclass

@dataclass
class Source:
    commit: str  # short hash
    branch: str = ''  # empty on a detached HEAD
    dirty: bool = False  # the vault folder has changes, untracked files too
    repo: str = ''  # owner/name of the origin remote, e.g. hiqsol/uwiki
    url: str = ''  # web page of the origin remote

    @classmethod
    def of(cls, folder):
        """Source of the vault at folder, None out of git or without git."""
        commit = git(folder, 'rev-parse', '--short', 'HEAD')
        if not commit:
            return None
        repo, url = web(git(folder, 'remote', 'get-url', 'origin') or '')
        return cls(commit, git(folder, 'branch', '--show-current') or '',
                   bool(git(folder, 'status', '--porcelain', '--', '.')), repo, url)

    @property
    def commit_url(self):
        return f'{self.url}/commit/{self.commit}' if self.url else ''

def git(folder, *args):
    """Output of git command in folder, None when it fails."""
    try:
        res = subprocess.run(['git', '-C', folder, *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    return res.stdout.strip() if res.returncode == 0 else None

SSH = re.compile(r'(?:ssh://)?[^@/:]+@([^:/]+)(?::\d+)?[:/](.+?)(?:\.git)?/?')  # git@github.com:owner/name.git
WEB = re.compile(r'(?:https?|git)://(?:[^@/]+@)?([^/]+)/(.+?)(?:\.git)?/?')  # credentials dropped

def web(remote):
    """Repo path and https URL of a remote URL, empty for a local one."""
    m = SSH.fullmatch(remote) or WEB.fullmatch(remote)
    return (m[2], f'https://{m[1]}/{m[2]}') if m else ('', '')
