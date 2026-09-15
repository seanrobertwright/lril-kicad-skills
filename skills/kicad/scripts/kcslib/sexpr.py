"""Minimal, dependency-free S-expression reader/writer for KiCad files.

Representation
--------------
* A KiCad *list* is a Python ``list``.
* A quoted string ``"like this"`` is a plain ``str``.
* A bare token (``yes``, ``hide``, ``0.254``, ``kicad_sch``) is an ``Atom``
  (a ``str`` subclass), so it round-trips without gaining quotes.

Numbers are kept as their original text so a file re-written without edits
serialises identically apart from whitespace. Use :func:`num` when emitting
numbers you computed yourself.
"""
from __future__ import annotations

import re
from typing import Iterator, Union

Node = Union["Atom", str, list]


class Atom(str):
    """A bare (unquoted) token."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Atom({str.__repr__(self)})"


def num(value: float, places: int = 6) -> Atom:
    """Format a number the way KiCad does: trim trailing zeros, no '-0'."""
    if isinstance(value, bool):
        raise TypeError("bool is not a number here")
    value = float(value)
    if abs(value - round(value)) < 1e-9:
        text = str(int(round(value)))
    else:
        text = f"{value:.{places}f}".rstrip("0").rstrip(".")
    if text in ("-0", "-0.0"):
        text = "0"
    return Atom(text)


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #
_TOKEN_RE = re.compile(
    r"""
    (?P<ws>\s+)
  | (?P<open>\()
  | (?P<close>\))
  | (?P<string>"(?:[^"\\]|\\.)*")
  | (?P<atom>[^\s()"]+)
    """,
    re.VERBOSE,
)

_UNESCAPE = {
    "n": "\n",
    "r": "\r",
    "t": "\t",
    '"': '"',
    "\\": "\\",
}


def _unescape(body: str) -> str:
    out: list[str] = []
    i = 0
    while i < len(body):
        ch = body[i]
        if ch == "\\" and i + 1 < len(body):
            nxt = body[i + 1]
            out.append(_UNESCAPE.get(nxt, nxt))
            i += 2
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def escape(text: str) -> str:
    """Escape a Python string for emission inside double quotes."""
    return (
        text.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def _tokens(text: str) -> Iterator[tuple[str, str]]:
    pos = 0
    n = len(text)
    while pos < n:
        m = _TOKEN_RE.match(text, pos)
        if m is None:
            raise ValueError(f"Unexpected character at offset {pos}: {text[pos:pos+20]!r}")
        pos = m.end()
        kind = m.lastgroup
        if kind == "ws":
            continue
        yield kind, m.group(kind)


def loads(text: str) -> list:
    """Parse one top-level S-expression."""
    stack: list[list] = [[]]
    for kind, tok in _tokens(text):
        if kind == "open":
            stack.append([])
        elif kind == "close":
            if len(stack) < 2:
                raise ValueError("Unbalanced ')' in S-expression")
            done = stack.pop()
            stack[-1].append(done)
        elif kind == "string":
            stack[-1].append(_unescape(tok[1:-1]))
        else:
            stack[-1].append(Atom(tok))
    if len(stack) != 1:
        raise ValueError("Unbalanced '(' in S-expression (truncated file?)")
    root = stack[0]
    if len(root) != 1 or not isinstance(root[0], list):
        raise ValueError("Expected exactly one top-level list")
    return root[0]


def load(path) -> list:
    with open(path, encoding="utf-8") as fh:
        return loads(fh.read())


# --------------------------------------------------------------------------- #
# Serialising
# --------------------------------------------------------------------------- #
def _fmt_leaf(node: Node) -> str:
    if isinstance(node, Atom):
        return str(node)
    if isinstance(node, str):
        return f'"{escape(node)}"'
    raise TypeError(f"not a leaf: {node!r}")


def _has_sublist(node: list) -> bool:
    return any(isinstance(c, list) for c in node)


def dumps(node: list, indent: int = 0) -> str:
    """Serialise with KiCad-like layout: leaf lists inline, others one-per-line."""
    pad = "\t" * indent
    if not _has_sublist(node):
        return pad + "(" + " ".join(_fmt_leaf(c) for c in node) + ")"
    parts: list[str] = []
    head: list[str] = []
    i = 0
    # leading leaves stay on the opening line
    while i < len(node) and not isinstance(node[i], list):
        head.append(_fmt_leaf(node[i]))
        i += 1
    parts.append(pad + "(" + " ".join(head))
    for c in node[i:]:
        if isinstance(c, list):
            parts.append(dumps(c, indent + 1))
        else:
            parts.append("\t" * (indent + 1) + _fmt_leaf(c))
    parts.append(pad + ")")
    return "\n".join(parts)


def dump(node: list, path) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(dumps(node))
        fh.write("\n")


# --------------------------------------------------------------------------- #
# Query helpers
# --------------------------------------------------------------------------- #
def is_node(node: Node, name: str) -> bool:
    return isinstance(node, list) and len(node) > 0 and isinstance(node[0], Atom) and node[0] == name


def children(node: list, name: str) -> list[list]:
    """All direct children whose head atom is ``name``."""
    return [c for c in node if is_node(c, name)]


def child(node: list, name: str) -> list | None:
    for c in node:
        if is_node(c, name):
            return c
    return None


def find_all(node: list, name: str) -> Iterator[list]:
    """Depth-first search for every list headed by ``name``."""
    for c in node:
        if isinstance(c, list):
            if is_node(c, name):
                yield c
            yield from find_all(c, name)


def values(node: list) -> list[Node]:
    """Leaf values after the head atom, e.g. ``(at 1 2 90)`` -> ['1','2','90']."""
    return [c for c in node[1:] if not isinstance(c, list)]


def floats(node: list) -> list[float]:
    return [float(v) for v in values(node)]


def set_child(node: list, new: list) -> None:
    """Replace the first child with the same head as ``new`` or append it."""
    for i, c in enumerate(node):
        if is_node(c, new[0]):
            node[i] = new
            return
    node.append(new)


def remove_children(node: list, name: str) -> None:
    node[:] = [c for c in node if not is_node(c, name)]


def get_property(node: list, key: str) -> str | None:
    """Value of ``(property "key" "value" ...)`` inside a symbol/footprint."""
    for p in children(node, "property"):
        if len(p) >= 3 and p[1] == key:
            return str(p[2])
    return None


def A(name: str, *rest: Node) -> list:
    """Build ``(name rest...)`` with the head as an Atom."""
    return [Atom(name), *rest]


def yn(flag: bool) -> Atom:
    return Atom("yes" if flag else "no")
