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
    """Front matter keys allowed, value is allowed values or a type, `_required` lists required keys.

    ```
    [schema]
    _required = ["status"]
    status = ["stub", "draft", "stable"]
    aliases = "list"
    [schema."docs/**"]
    _required = ["owner"]
    owner = "string"
    ```
    Folder tables add to the top level rules, matching glob as `--exclude` does, later ones win.
    Keys go in schema order, build shows front matter so.
    """

    TYPES = ('string', 'number', 'bool', 'date', 'list', 'any')
    NUMBER = re.compile(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?')
    DATE = re.compile(r'\d{4}-\d\d-\d\d(?:[T ]\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|[-+]\d\d:?\d\d)?)?')

    def __init__(self, table, path=None):
        self.path = path
        self.rules = []  # (glob regex or None, {key: spec}, required keys)
        if not isinstance(table, dict):
            raise ConfigError(f'{path}: schema should be a table')
        top = {key: value for key, value in table.items() if not isinstance(value, dict)}
        self.rules.append((None, *self.parse(top, 'schema')))
        for key, value in table.items():
            if isinstance(value, dict):
                self.rules.append((Filter.compile(key), *self.parse(value, f'schema."{key}"', self.rules[0][1])))
        self.empty = not table

    def parse(self, table, where, known=()):
        """Specs of keys of table and its required keys, ones of known specs too."""
        specs = {}
        for key, spec in table.items():
            if key == '_required':
                continue
            if key.endswith('!'):
                raise ConfigError(f'{self.path}: {where}."{key}": list required keys in _required instead of !')
            if isinstance(spec, dict):
                raise ConfigError(f'{self.path}: {where}.{key}: nested tables are folder rules of schema only')
            if not isinstance(spec, list) and spec not in self.TYPES:
                raise ConfigError(f'{self.path}: {where}.{key}: {spec!r} is no list of values '
                                  f'nor type: {", ".join(self.TYPES)}')
            specs[key] = spec
        required = table.get('_required', [])
        if not isinstance(required, list) or not all(isinstance(key, str) for key in required):
            raise ConfigError(f'{self.path}: {where}._required should be a list of keys')
        for key in required:
            if key not in specs and key not in known:
                raise ConfigError(f'{self.path}: {where}._required: {key} is not in schema')
        return specs, set(required)

    def keys(self, path):
        """Rules for page at vault relative path in schema order: key: (required, spec)."""
        specs, required = {}, set()
        for glob, rules, keys in self.rules:
            if glob is None or glob.fullmatch(path):
                specs.update(rules)
                required |= keys
        return {key: (key in required, spec) for key, spec in specs.items()}

    def sort(self, items, path):
        """Front matter items of page at path in schema order, keys out of schema after them as they come."""
        order = {key: n for n, key in enumerate(self.keys(path))}
        return sorted(items, key=lambda item: order.get(item[0], len(order)))

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
