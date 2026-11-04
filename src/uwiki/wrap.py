"""Rewraps markdown lines longer than width (tab counts as 4).

Only paragraphs and list items containing an overlong line are rewrapped,
together with their continuation lines. Frontmatter, code blocks, tables
and headings are left as is. Wiki links and inline code are not split.
A line rewrapping leaves as is, e.g. a long URL, is not reported.
"""

import re

from .convert import Converter
from .vault import FRONT_MATTER

WIDTH = 70
TOKEN = re.compile(r'(?:\[\[[^\]]*\]\]|`[^`]*`|[^\s`\[]+|\[)+')
ITEM = re.compile(r'^(\t*)((?:[-*+]|\d+[.)]|>) +|[a-z]\) +)?')
BLOCK = re.compile(r'^\s*(?:[-*+>#|]|\d+[.)])(?:\s|$)')


def columns(s):
    return len(s.expandtabs(4))


def is_plain(line):
    return line.strip() and not line.lstrip().startswith(('#', '|'))


def wrap(head, cont, words, width):
    # Glue a word that would start a list or heading to the previous one
    glued = []
    for w in words:
        if glued and BLOCK.match(w + ' '):
            glued[-1] += ' ' + w
        else:
            glued.append(w)
    lines, cur = [], head
    for w in glued:
        sep = '' if cur in (head, cont) else ' '
        nxt = cur + sep + w
        if columns(nxt) > width and cur not in (head, cont):
            lines.append(cur)
            cur = cont + w
        else:
            cur = nxt
    lines.append(cur)
    return lines


def rewrap(text, width=WIDTH):
    """Returns rewrapped text and numbers of the overlong lines it rewrapped."""
    m = FRONT_MATTER.match(text)
    if not m and text.startswith('---\n'):
        return text, []  # unclosed front matter: all of the page may be it
    src = text.split('\n')
    i = m[0].count('\n') if m else 0
    out, long = src[:i], []
    code = [False] * i + [c for _, c in Converter.fenced(src[i:])]
    while i < len(src):
        line = src[i]
        if code[i] or not is_plain(line):
            out.append(line)
            i += 1
            continue
        m = ITEM.match(line)
        head = line[:m.end()]
        cont = m.group(1) + (' ' * len(m.group(2)) if m.group(2) else '')
        if m.group(2) and m.group(2).startswith('>'):
            cont = m.group(1) + m.group(2)
        group = [line]
        j = i + 1
        while j < len(src) and not code[j] and is_plain(src[j]) and not ITEM.match(src[j]).group(2):
            nl = src[j]
            if cont and nl.startswith(cont) and not nl[len(cont):].startswith((' ', '\t')):
                group.append(nl)
            elif not cont and nl[:1].islower():
                group.append(nl)
            else:
                break
            j += 1
        wrapped = group
        if any(columns(g) > width for g in group):
            words = TOKEN.findall(' '.join([line[m.end():]] + [g.strip() for g in group[1:]]))
            wrapped = wrap(head, cont, words, width)
        if wrapped != group:
            long += [i + 1 + k for k, g in enumerate(group) if columns(g) > width]
        out.extend(wrapped)
        i = j
    return '\n'.join(out), long


def wrap_files(paths, width=WIDTH, check=False):
    """Rewraps files in place, with check only reports overlong lines as `path:line: message`."""
    problems = []
    for path in paths:
        with open(path, encoding='utf-8') as f:
            text = f.read()
        new, long = rewrap(text, width)
        if check:
            problems += [f'{path}:{n}: longer than {width} columns' for n in long]
        elif new != text:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(new)
    return problems
