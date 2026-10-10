"""Resolve local source identities and order their static import closure.

Discovery reads module headers only. Full parsing is restricted to dependencies;
neither discovery nor loading evaluates a declaration or mutates the root AST.
"""
from dataclasses import dataclass
from graphlib import TopologicalSorter
from heapq import heappop, heappush
from pathlib import Path
import re

from eldude.source.syntax import Diagnostic, Node, Span, parse_source


STDLIB = Path(__file__).resolve().parents[1] / 'stdlib'
if not STDLIB.exists():
    STDLIB = Path(__file__).resolve().parents[3] / 'stdlib'
HOST_MODULE = 'eldude::fixture'
_TRIVIA = r'(?:\s|//[^\n]*(?:\n|$)|/\*[\s\S]*?\*/)*'
_IDENT = r'[A-Za-z_][A-Za-z_0-9]*'
_HEADER = re.compile(rf'\A{_TRIVIA}module\b{_TRIVIA}(?P<path>{_IDENT}(?:{_TRIVIA}::{_TRIVIA}{_IDENT})*){_TRIVIA};')
_COMMENTS = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/')


@dataclass(frozen=True)
class ModuleGraph:
    modules: dict[str, Node]
    order: tuple[str, ...]
    exports: dict[str, dict[str, Node]]
    dependencies: dict[str, tuple[str, ...]]


def _header(text, filename):
    match = _HEADER.match(text)
    if match is None:
        return None
    start, end = match.span('path')
    path = ''.join(_COMMENTS.sub('', match['path']).split())
    span = Span(str(filename), start, end, text.count('\n', 0, start) + 1,
                start - text.rfind('\n', 0, start))
    return path, span


def _module_order(dependencies):
    """Tarjan components, then the specification's lexical ready-component rule."""
    indices, low, stack, active, components = {}, {}, [], set(), []

    def visit(module):
        indices[module] = low[module] = len(indices)
        stack.append(module)
        active.add(module)
        for dependency in dependencies[module]:
            if dependency not in indices:
                visit(dependency)
                low[module] = min(low[module], low[dependency])
            elif dependency in active:
                low[module] = min(low[module], indices[dependency])
        if low[module] == indices[module]:
            component = []
            while True:
                member = stack.pop()
                active.remove(member)
                component.append(member)
                if member == module:
                    break
            components.append(tuple(sorted(component)))

    for module in sorted(dependencies):
        if module not in indices:
            visit(module)
    component_of = {member: component for component in components for member in component}
    sorter = TopologicalSorter()
    for component in components:
        sorter.add(component, *(component_of[dependency]
                               for member in component for dependency in dependencies[member]
                               if component_of[dependency] != component))
    sorter.prepare()
    ready, order = [], []
    while sorter.is_active():
        for component in sorter.get_ready():
            heappush(ready, component)
        component = heappop(ready)
        order.extend(component)
        sorter.done(component)
    return tuple(order)


def load_modules(root_ast, search_roots=(), *, sources=None, import_allowed=None):
    """Load root, adjacent sources, explicit search roots, and bundled stdlib.

    ``modules`` retains the supplied root object. ``exports[module][name]`` is
    the defining declaration (also for aliases/re-exports). ``dependencies``
    excludes host fixture imports. ``order`` includes the root and preserves
    cyclic imports by visiting each SCC's members in canonical path order.
    Nested projects and checkouts require an explicit root or source selection.
    """
    root_name = root_ast.items[0].items[0]
    root_file = Path(root_ast.span.filename).resolve()
    roots = [Path(path).resolve() for path in search_roots] + [STDLIB]
    if sources is None and not root_ast.span.filename.startswith('<'):
        roots.append(root_file.parent)
    candidates = set()
    for root in roots:
        for directory, subdirectories, filenames in root.walk():
            subdirectories[:] = [name for name in subdirectories if name != '.venv'
                                 and not (directory / name / 'eldude.toml').is_file()
                                 and not (directory / name / '.git').exists()]
            candidates.update((directory / name).resolve() for name in filenames if name.endswith('.eld'))
    candidates.update(Path(path).resolve() for path in sources or ())
    candidates = sorted(candidates)
    index = {}
    for path in candidates:
        if path == root_file:
            continue
        try:
            text = path.read_text(encoding='utf-8', errors='replace', newline='')
        except OSError as error:
            raise Diagnostic('module', f'Cannot read source: {error}', Span(str(path), 0, 0, 1, 1)) from error
        header = _header(text, path)
        if header:
            name, span = header
            index.setdefault(name, []).append((path, span))

    modules, dependencies = {root_name: root_ast}, {}

    def check_duplicates(name, span):
        entries = index.get(name, [])
        if len(entries) > (0 if name == root_name else 1):
            locations = [('Module declared here', location) for _, location in entries]
            if name == root_name:
                locations.insert(0, ('Root module declared here', root_ast.items[0].span))
            raise Diagnostic('module', f'Duplicate module identity {name!r}', span, locations)

    check_duplicates(root_name, root_ast.items[0].span)
    if sources is not None:
        for name, entries in sorted(index.items()):
            check_duplicates(name, entries[0][1])

    def visit(name):
        module = modules[name]
        imports = [node for node in module.items[1] if node.kind == 'import']
        dependencies[name] = tuple(sorted({node.items[1].items[0] for node in imports
                                           if node.items[1].items[0] != HOST_MODULE}))
        for node in imports:
            path = node.items[1]
            imported = path.items[0]
            if import_allowed is not None and not import_allowed(name, imported):
                raise Diagnostic('module', f'Module {imported!r} is not provided by a direct dependency of {name!r}',
                                 path.span)
            if imported == HOST_MODULE:
                continue
            check_duplicates(imported, path.span)
            if imported not in modules:
                if imported not in index:
                    raise Diagnostic('module', f'Cannot find module {imported!r}', path.span)
                filename = index[imported][0][0]
                try:
                    text = filename.read_text(encoding='utf-8', newline='')
                except (OSError, UnicodeError) as error:
                    raise Diagnostic('syntax', f'Cannot read source: {error}',
                                     Span(str(filename), 0, 0, 1, 1)) from error
                modules[imported] = parse_source(text, str(filename))
                visit(imported)

    visit(root_name)
    exports = {name: {} for name in modules}
    declared = {name: set() for name in modules}
    imports = []
    for name, module in modules.items():
        for node in module.items[1]:
            if node.kind == 'import':
                public, path, names = node.items
                declared[name].update(alias.items[0] for _, alias in names)
                if path.items[0] != HOST_MODULE:
                    imports.append((name, public, path.items[0], names))
            elif node.kind in ('function', 'struct', 'enum', 'effect', 'trait', 'type_alias', 'let', 'public_let'):
                if node.kind in ('let', 'public_let'):
                    public, binding = node.kind == 'public_let', node.items[0]
                else:
                    public, binding = node.items[:2]
                pending = [binding]
                while pending:
                    binding = pending.pop()
                    if binding.kind == 'tuple_pattern':
                        pending.extend(binding.items[0])
                    elif binding.kind in ('name', 'generic_name'):
                        symbol = binding.items[0]
                        declared[name].add(symbol)
                        if public:
                            exports[name][symbol] = node

    # Resolve public aliases to a fixed point so cycles with real definitions
    # preserve those identities; a cycle of aliases alone has no definition.
    changed = True
    while changed:
        changed = False
        for name, public, imported, names in imports:
            if public:
                for source, alias in names:
                    if source.items[0] in exports[imported] and alias.items[0] not in exports[name]:
                        exports[name][alias.items[0]] = exports[imported][source.items[0]]
                        changed = True
    for _, _, imported, names in imports:
        for source, _ in names:
            symbol = source.items[0]
            if symbol not in exports[imported]:
                private = symbol in declared[imported]
                raise Diagnostic('visibility' if private else 'name',
                                 f'{"Private" if private else "Unknown"} name {symbol!r} in module {imported!r}',
                                 source.span)
    return ModuleGraph(modules, _module_order(dependencies), exports, dependencies)
