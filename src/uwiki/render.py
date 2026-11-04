"""Renders markdown to HTML as GitHub and Obsidian do: CommonMark with tables, strikethrough, task lists
and bare http links and emails linked.

Headings take ids written after them as `## Heading {#id}`, blocks take the source lines they start at.
"""

import functools
import re

from markdown_it import MarkdownIt
from markdown_it.token import Token

HEADING_ID = re.compile(r'(?:^|[ \t]+)\{#([^\s}]+)\}[ \t]*$')
TASK = re.compile(r'\[([ xX])\][ \t]+')
# blocks taking source lines: list items carry the line of their first paragraph, rows the line of their table
LINE_BLOCKS = {'paragraph_open', 'heading_open', 'list_item_open', 'blockquote_open', 'table_open',
               'fence', 'code_block', 'hr'}

@functools.cache
def renderer():
    md = MarkdownIt('commonmark', {'html': True, 'linkify': True}).enable(['table', 'strikethrough', 'linkify'])
    # links only with scheme: a bare `README.md` or `foo.com` is not a link
    md.linkify.set({'fuzzy_link': False})
    md.core.ruler.before('inline', 'heading_ids', heading_ids)
    md.core.ruler.after('inline', 'task_lists', task_lists)
    return md

def html(text, lines=None):
    """HTML of markdown text; with lines, the source line of every text line, blocks get `data-line` of theirs."""
    md = renderer()
    tokens = md.parse(text)
    if lines is not None:
        for token in tokens:
            if token.map and token.type in LINE_BLOCKS and not token.hidden and token.map[0] < len(lines):
                line = lines[token.map[0]]
                if line is not None:
                    token.attrSet('data-line', str(line))
    return md.renderer.render(tokens, md.options, {})

def inline(text):
    """HTML of markdown text as inline content, as a title is."""
    return renderer().renderInline(text)

def heading_ids(state):
    """`## Heading {#id}` is heading with id."""
    tokens = state.tokens
    for i, token in enumerate(tokens):
        if token.type == 'heading_open':
            m = HEADING_ID.search(tokens[i + 1].content)
            if m:
                token.attrSet('id', m[1])
                tokens[i + 1].content = tokens[i + 1].content[:m.start()]

def task_lists(state):
    """List item starting with `[ ]` or `[x]` is a task: a checkbox in place of its marker,
    after anchors put at its start."""
    tokens = state.tokens
    for i in range(2, len(tokens)):
        if tokens[i].type != 'inline' or tokens[i - 1].type != 'paragraph_open' \
                or tokens[i - 2].type != 'list_item_open':
            continue
        children = tokens[i].children or []
        k = 0
        while k < len(children) and children[k].type == 'html_inline':
            k += 1
        m = k < len(children) and children[k].type == 'text' and TASK.match(children[k].content)
        if not m:
            continue
        children[k].content = children[k].content[m.end():]
        box = Token('html_inline', '', 0)
        checked = ' checked' if m[1] != ' ' else ''
        box.content = f'<input type="checkbox" class="task-list-item-checkbox" disabled{checked}> '
        children.insert(k, box)
        tokens[i - 2].attrJoin('class', 'task-list-item')
