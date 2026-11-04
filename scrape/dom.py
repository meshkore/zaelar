"""scrape/dom.py — a small DOM over the standard library's `html.parser`, and the one selector syntax `scrape/` keeps
as data (V2-846 F5).

A selector is `tag.class1.class2` steps separated by spaces (descendant), each step optional in tag or classes:
`article.item`, `a.item-link`, `span.price`, `.price`, `img`. That is the whole language: it is what a kept field map
says for a page whose listings live only in its markup, and it is interpreted here — no code is generated or run.
Pure; tolerant of broken markup (a stray close tag is ignored, an unclosed one closes with its parent).
"""
from __future__ import annotations

from html.parser import HTMLParser

_VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
_SKIP = frozenset({"script", "style", "noscript", "template", "svg"})


class Node:
    __slots__ = ("tag", "attrs", "children", "parent", "text")

    def __init__(self, tag: str, attrs: dict | None = None, parent: "Node | None" = None):
        self.tag, self.attrs, self.parent = tag, attrs or {}, parent
        self.children: list[Node] = []
        self.text: list[str] = []

    @property
    def classes(self) -> frozenset:
        return frozenset((self.attrs.get("class") or "").split())

    def iter(self):
        yield self
        for c in self.children:
            yield from c.iter()

    def all_text(self) -> str:
        parts: list[str] = []

        def walk(n):
            parts.extend(n.text)
            for c in n.children:
                walk(c)
        walk(self)
        return " ".join(" ".join(parts).split())

    def sig(self) -> str:
        """`tag.class1.class2` — the step that names this element (classes sorted)."""
        cls = sorted(c for c in self.classes if len(c) < 40)
        return self.tag + "".join(f".{c}" for c in cls[:4])

    def select(self, selector: str) -> list["Node"]:
        steps = [_step(s) for s in (selector or "").split()]
        found = [self]
        for tag, cls in steps:
            nxt = []
            for base in found:
                for n in base.iter():
                    if n is not base and (not tag or n.tag == tag) and cls <= n.classes and n not in nxt:
                        nxt.append(n)
            found = nxt
        return found if steps else []

    def first(self, selector: str) -> "Node | None":
        got = self.select(selector)
        return got[0] if got else None


def _step(s: str) -> tuple[str, frozenset]:
    tag, *cls = s.split(".")
    return tag.lower(), frozenset(c for c in cls if c)


class _Builder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root")
        self.cur = self.root
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if self.skip:
            if tag in _SKIP:
                self.skip += 1
            return
        if tag in _SKIP:
            self.skip = 1
            return
        node = Node(tag, {k: (v or "") for k, v in attrs}, self.cur)
        self.cur.children.append(node)
        if tag not in _VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        if not self.skip and tag not in _SKIP:
            self.cur.children.append(Node(tag, {k: (v or "") for k, v in attrs}, self.cur))

    def handle_endtag(self, tag):
        if self.skip:
            if tag in _SKIP:
                self.skip -= 1
            return
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:
            self.cur = n.parent

    def handle_data(self, data):
        if not self.skip and data.strip():
            self.cur.text.append(data.strip())


def parse(html: str) -> Node:
    b = _Builder()
    try:
        b.feed(html or "")
        b.close()
    except Exception as e:  # noqa: BLE001 — html.parser raises on very broken input; what was built is kept
        b.root.attrs["_broken"] = type(e).__name__
    return b.root
