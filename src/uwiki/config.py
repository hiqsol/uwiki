"""Vault config: `uwiki.toml`, or `[tool.uwiki]` in `pyproject.toml`, in the vault root or the nearest
folder above it, up to the git work tree root, so a vault inside a project takes the project's config.

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
    def __init__(self, data=None, path=None, prefix=''):
        self.data = data or {}
        self.path = path
        self.prefix = prefix  # vault root relative to the config folder, schema globs match from there
        self._schema = None

    @classmethod
    def load(cls, root):
        """Config of the vault at given root, empty when there is none."""
        folder = os.path.abspath(root)
        while True:
            config = cls.find(folder)
            if config:
                data, file = config
                prefix = os.path.relpath(os.path.abspath(root), folder).replace(os.sep, '/')
                return cls(data, file, '' if prefix == '.' else prefix)
            parent = os.path.dirname(folder)
            if parent == folder or os.path.exists(os.path.join(folder, '.git')):
                return cls()
            folder = parent

    @classmethod
    def find(cls, folder):
        """Config data and its file in folder, None if there is none."""
        file = os.path.join(folder, 'uwiki.toml')
        if os.path.isfile(file):
            return cls.read(file), file
        file = os.path.join(folder, 'pyproject.toml')
        if os.path.isfile(file):
            data = cls.read(file).get('tool', {}).get('uwiki')
            if data is not None:
                return data, file
        return None

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
    def layers(self):
        """Front matter keys with their values in layer order, `[check] layers.KEY = [values]`."""
        table = self.data.get('check', {})
        layers = table.get('layers', {}) if isinstance(table, dict) else {}
        if not isinstance(layers, dict) or not all(
                isinstance(v, list) and all(isinstance(x, str) for x in v) for v in layers.values()):
            raise ConfigError(f'{self.path}: check.layers should be a table of keys with lists of values')
        return layers

    @property
    def schema(self):
        if self._schema is None:
            self._schema = Schema(self.data.get('schema', {}), self.path, self.prefix)
        return self._schema

class Schema:
    """Front matter keys allowed, value is allowed values or a type, `_required` lists required keys.

    ```
    [schema]
    _required = ["status", "generated.at"]
    status = ["stub", "draft", "stable"]
    aliases = "list"
    generated.at = "datetime"                # nested key, of a map or of every map of a list
    [schema."docs/**"]
    _required = ["owner"]
    owner = "string"
    [schema."**/index.md"]
    _inherit = false                         # this rule only, not the ones before it
    ```
    Folder tables add to the rules before them, matching glob as `--exclude` does from the config folder,
    later ones win. Keys go in schema order, build shows front matter so.
    """

    TYPES = ('string', 'number', 'bool', 'date', 'datetime', 'list', 'any')
    NUMBER = re.compile(r'[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?')
    DATE = re.compile(r'\d{4}-\d\d-\d\d(?:[T ]\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|[-+]\d\d:?\d\d)?)?')
    DATETIME = re.compile(r'\d{4}-\d\d-\d\d[T ]\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|[-+]\d\d:?\d\d)')

    def __init__(self, table, path=None, prefix=''):
        self.path = path
        self.prefix = prefix
        self.rules = []  # (glob regex or None, {key: spec}, required keys, inherit)
        if not isinstance(table, dict):
            raise ConfigError(f'{path}: schema should be a table')
        top = self.flat({key: value for key, value in table.items() if not self.folder_rule(key, value)})
        self.rules.append((None, *self.parse(top, 'schema'), True))
        for key, value in table.items():
            if self.folder_rule(key, value):
                inherit = value.get('_inherit', True)
                if not isinstance(inherit, bool):
                    raise ConfigError(f'{path}: schema."{key}"._inherit should be true or false')
                known = self.rules[0][1] if inherit else ()
                specs = self.flat({k: v for k, v in value.items() if k != '_inherit'})
                self.rules.append((Filter.compile(key), *self.parse(specs, f'schema."{key}"', known), inherit))
        self.empty = not table

    @staticmethod
    def folder_rule(key, value):
        """Table of folder rules: key is a glob, a table of other keys gives nested keys."""
        return isinstance(value, dict) and any(c in key for c in '/*?.')

    @classmethod
    def flat(cls, table, prefix=''):
        """Table with nested key tables, `generated.at = ...` too, as dotted keys."""
        res = {}
        for key, value in table.items():
            if isinstance(value, dict):
                res.update(cls.flat(value, f'{prefix}{key}.'))
            else:
                res[prefix + key] = value
        return res

    def parse(self, table, where, known=()):
        """Specs of keys of table and its required keys, ones of known specs too."""
        specs = {}
        for key, spec in table.items():
            if key == '_required':
                continue
            if key.endswith('!'):
                raise ConfigError(f'{self.path}: {where}."{key}": list required keys in _required instead of !')
            if not isinstance(spec, list) and spec not in self.TYPES:
                raise ConfigError(f'{self.path}: {where}.{key}: {spec!r} is no list of values '
                                  f'nor type: {", ".join(self.TYPES)}')
            specs[key] = spec
        required = table.get('_required', [])
        if not isinstance(required, list) or not all(isinstance(key, str) for key in required):
            raise ConfigError(f'{self.path}: {where}._required should be a list of keys')
        for key in required:
            if not any(k == key or k.startswith(key + '.') for k in (*specs, *known)):
                raise ConfigError(f'{self.path}: {where}._required: {key} is not in schema')
        return specs, set(required)

    def keys(self, path):
        """Rules for page at vault relative path in schema order: key: (required, spec)."""
        specs, required = {}, set()
        path = f'{self.prefix}/{path}' if self.prefix else path
        for glob, rules, keys, inherit in self.rules:
            if glob is None or glob.fullmatch(path):
                if not inherit:
                    specs, required = {}, set()
                specs.update(rules)
                required |= keys
        return {key: (key in required, spec) for key, spec in specs.items()}

    def facets(self):
        """Keys listing their values, with the values, in schema order, folder rules adding to them."""
        res = {}
        for _, rules, _, _ in self.rules:
            for key, spec in rules.items():
                if isinstance(spec, list):
                    res[key] = list(dict.fromkeys(res.get(key, []) + [str(v) for v in spec]))
        return res

    def sort(self, items, path):
        """Front matter items of page at path in schema order, keys out of schema after them as they come."""
        order = {key: n for n, key in enumerate(self.keys(path))}
        return sorted(items, key=lambda item: order.get(item[0], len(order)))

    def problems(self, tree, path):
        """(key, message) for front matter of page at path, as front_matter_tree gives it,
        key is the top level key the problem is at, None for missing ones."""
        if self.empty:
            return []
        res = []
        self.check_map(tree, '', self.keys(path), res, None)
        return res

    def check_map(self, values, prefix, rules, res, at):
        """Problems of map of front matter values whose keys start with prefix, at top level key or None."""
        for key, value in values.items():
            full = prefix + key
            top = at or key
            nested = any(k.startswith(full + '.') for k in rules)
            if nested and isinstance(value, dict):
                self.check_map(value, full + '.', rules, res, top)
                continue
            if nested and isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
                for item in value:
                    self.check_map(item, full + '.', rules, res, top)
                continue
            if full not in rules:
                res.append((top, f'unknown front matter key: {full}'))
                continue
            required, spec = rules[full]
            if value in ('', [], {}):
                if required:
                    res.append((top, f'front matter {full}: empty, required'))
                continue
            bad = self.mismatch(spec, value)
            if bad:
                res.append((top, f'front matter {full}: {bad}'))
        for key, (required, _) in rules.items():
            if required and key.startswith(prefix) and key[len(prefix):].split('.')[0] not in values:
                res.append((at, f'missing front matter key: {key}'))

    @classmethod
    def mismatch(cls, spec, value):
        """What is wrong with the value, None if it fits."""
        if isinstance(value, dict):
            return None if spec == 'any' else f'map, expected {spec if isinstance(spec, str) else "one of values"}'
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
                or spec == 'date' and not cls.DATE.fullmatch(value) \
                or spec == 'datetime' and not cls.DATETIME.fullmatch(value):
            return f'{value}, expected {spec}'
        return None

    @staticmethod
    def text(value):
        return ('true' if value else 'false') if isinstance(value, bool) else str(value)
