"""Vault config: `uwiki.toml` in the vault root, or `[tool.uwiki]` in its `pyproject.toml`.

Top level keys are defaults of options of every command taking them, e.g. `exclude = ["drafts"]`,
`[build]`, `[check]` and other command tables of that command only, `[build]` also of watch and serve.
`[schema]` declares front matter keys, see Schema.
"""

import os
import re
import tomllib

from .vault import Filter

class ConfigError(ValueError):
    """Config that cannot be read or does not fit the commands."""

class Config:
    def __init__(self, data=None, path=None):
        self.data = data or {}
        self.path = path
        self._schema = None

    @classmethod
    def load(cls, root):
        """Config of the vault at given root, empty when there is none."""
        file = os.path.join(root, 'uwiki.toml')
        if os.path.isfile(file):
            return cls(cls.read(file), file)
        file = os.path.join(root, 'pyproject.toml')
        if os.path.isfile(file):
            data = cls.read(file).get('tool', {}).get('uwiki')
            if data is not None:
                return cls(data, file)
        return cls()

    @staticmethod
    def read(file):
        try:
            with open(file, 'rb') as f:
                return tomllib.load(f)
        except (OSError, tomllib.TOMLDecodeError) as e:
            raise ConfigError(f'{file}: {e}') from e

    def options(self, command, takes=('build',)):
        """Option defaults for command: top level ones, then of its own table and of tables it takes."""
        res = {k: v for k, v in self.data.items() if not isinstance(v, dict)}
        for table in (*takes, command):
            value = self.data.get(table, {})
            if not isinstance(value, dict):
                raise ConfigError(f'{self.path}: {table} should be a table')
            res.update(value)
        return res

    @property
    def schema(self):
        if self._schema is None:
            self._schema = Schema(self.data.get('schema', {}), self.path)
        return self._schema

class Schema:
    """Front matter keys allowed, `!` after a key makes it required, value is allowed values or a type.

    ```
    [schema]
    "status!" = ["stub", "draft", "stable"]
    date = "date"
    aliases = "list"
    [schema."docs/**"]
    "owner!" = "string"
    ```
    Folder tables add to the top level rules, matching glob as `--exclude` does, later ones win.
    """

    TYPES = ('string', 'number', 'bool', 'date', 'list', 'any')
    NUMBER = re.compile(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?')
    DATE = re.compile(r'\d{4}-\d\d-\d\d(?:[T ]\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|[-+]\d\d:?\d\d)?)?')

    def __init__(self, table, path=None):
        self.path = path
        self.rules = []  # (glob regex or None, {key: (required, spec)})
        if not isinstance(table, dict):
            raise ConfigError(f'{path}: schema should be a table')
        top = {}
        for key, value in table.items():
            if isinstance(value, dict):
                self.rules.append((Filter.compile(key), self.parse(value, f'schema."{key}"')))
            else:
                top[key] = value
        self.rules.insert(0, (None, self.parse(top, 'schema')))
        self.empty = not table

    def parse(self, table, where):
        res = {}
        for key, spec in table.items():
            required = key.endswith('!')
            key = key[:-1] if required else key
            if isinstance(spec, dict):
                raise ConfigError(f'{self.path}: {where}.{key}: nested tables are folder rules of schema only')
            if not isinstance(spec, list) and spec not in self.TYPES:
                raise ConfigError(f'{self.path}: {where}.{key}: {spec!r} is no list of values '
                                  f'nor type: {", ".join(self.TYPES)}')
            res[key] = required, spec
        return res

    def keys(self, path):
        """Rules for page at vault relative path: key: (required, spec)."""
        res = {}
        for glob, rules in self.rules:
            if glob is None or glob.fullmatch(path):
                res.update(rules)
        return res

    def problems(self, items, path):
        """(key, message) for front matter items of page at path, key None for missing ones."""
        if self.empty:
            return []
        rules = self.keys(path)
        res = []
        given = dict(items)
        for key, value in items:
            if key not in rules:
                res.append((key, f'unknown front matter key: {key}'))
                continue
            required, spec = rules[key]
            if value in ('', []):
                if required:
                    res.append((key, f'front matter {key}: empty, required'))
                continue
            bad = self.mismatch(spec, value)
            if bad:
                res.append((key, f'front matter {key}: {bad}'))
        for key, (required, _) in rules.items():
            if required and key not in given:
                res.append((None, f'missing front matter key: {key}'))
        return res

    @classmethod
    def mismatch(cls, spec, value):
        """What is wrong with the value, None if it fits."""
        if isinstance(spec, list):
            allowed = [cls.text(v) for v in spec]
            bad = [v for v in (value if isinstance(value, list) else [value]) if v not in allowed]
            return f'{", ".join(bad)}, expected one of {", ".join(allowed)}' if bad else None
        if spec == 'any':
            return None
        if spec == 'list':
            return None if isinstance(value, list) else f'{value}, expected list'
        if isinstance(value, list):
            return f'list, expected {spec}'
        if spec == 'number' and not cls.NUMBER.fullmatch(value) \
                or spec == 'bool' and value not in ('true', 'false') \
                or spec == 'date' and not cls.DATE.fullmatch(value):
            return f'{value}, expected {spec}'
        return None

    @staticmethod
    def text(value):
        return ('true' if value else 'false') if isinstance(value, bool) else str(value)
