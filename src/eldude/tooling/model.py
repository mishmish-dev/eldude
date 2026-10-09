"""Declarative project manifests, workspace selection, and authored source paths."""
from dataclasses import dataclass
from importlib.metadata import version
import os
from pathlib import Path
import re
import tomllib
from urllib.parse import urlsplit

from eldude.source.syntax import Diagnostic, Span


TOOLCHAIN_VERSION = version('eldude')
IDENTIFIER = r'[A-Za-z_][A-Za-z_0-9]*'
QUALIFIED = rf'{IDENTIFIER}(?:::{IDENTIFIER})+'
EXCLUDED = {'build', '.git', '.eldude', '.cache', '.venv', '__pycache__'}
SEMVER = re.compile(r'(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)'
                    r'(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?\Z')


def version_key(value):
    match = SEMVER.fullmatch(value) if isinstance(value, str) else None
    if not match:
        raise ValueError('expected a full semantic version')
    prerelease = match[4]
    parts = []
    for part in prerelease.split('.') if prerelease else ():
        if part.isdigit() and len(part) > 1 and part.startswith('0'):
            raise ValueError('numeric prerelease identifiers cannot start with zero')
        parts.append((0, int(part)) if part.isdigit() else (1, part))
    return (*map(int, match.group(1, 2, 3)), prerelease is None, tuple(parts))


def comparisons(constraint):
    if not isinstance(constraint, str):
        raise ValueError('expected a version constraint string')
    result = []
    for part in constraint.split(','):
        match = re.fullmatch(r'\s*(>=|<=|>|<|=)?\s*([^\s]+)\s*', part)
        if not match:
            raise ValueError('expected comma-separated version comparisons')
        result.append((match[1] or '=', version_key(match[2])))
    return result


def satisfies(version, constraint):
    actual, requirements = version_key(version), comparisons(constraint)
    if not actual[3] and all(required[3] for _, required in requirements):
        return False
    return all({'=': actual == value, '>': actual > value, '<': actual < value,
                '>=': actual >= value, '<=': actual <= value}[operator]
               for operator, value in requirements)


@dataclass
class Manifest:
    path: Path
    text: str
    data: dict

    @property
    def name(self):
        return self.data.get('package', {}).get('name')

    def fail(self, field, message, code='configuration'):
        parts = field.split('.')
        table, offset, start, end = '', 0, 0, 0
        for line in self.text.splitlines(keepends=True):
            heading = re.match(r'[ \t]*\[\[?([^\]]+)\]\]?', line)
            if heading:
                table = heading[1].strip()
                if field == table or field.startswith(table + '.'):
                    start, end = offset + heading.start(), offset + heading.end()
            key = re.match(r'[ \t]*([A-Za-z_][A-Za-z_0-9-]*)[ \t]*=', line)
            if key and (table + '.' + key[1]).strip('.') in (field, '.'.join(parts[:2])):
                start, end = offset + key.start(1), offset + key.end(1)
                break
            offset += len(line)
        raise Diagnostic(code, f'{field}: {message}', Span(str(self.path), start, end,
                         self.text.count('\n', 0, start) + 1, start - self.text.rfind('\n', 0, start)))

    def directory(self, kind):
        default = 'src' if kind == 'source-dir' else 'tests'
        return (self.path.parent / self.data['package'].get(kind, default)).resolve()


def read_manifest(path):
    path = Path(path).resolve()
    text = path.read_text(encoding='utf-8')
    try:
        data = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        offset = getattr(error, 'pos', 0)
        raise Diagnostic('configuration', str(error), Span(str(path), offset, offset,
                         getattr(error, 'lineno', 1), getattr(error, 'colno', 1))) from error
    manifest = Manifest(path, text, data)

    def table(value, allowed, field, required=()):
        if not isinstance(value, dict):
            manifest.fail(field, 'expected a table')
        for key in value.keys() - set(allowed):
            manifest.fail(f'{field}.{key}'.strip('.'), 'unknown field')
        for key in set(required) - value.keys():
            manifest.fail(field, f'missing required field {key}')

    def string(value, field, pattern=None):
        if not isinstance(value, str) or not value or (pattern and not re.fullmatch(pattern, value)):
            manifest.fail(field, 'invalid string value')

    def version(value, field, constraint=False):
        try:
            (comparisons if constraint else version_key)(value)
        except ValueError as error:
            manifest.fail(field, str(error))

    table(data, ('manifest-version', 'package', 'workspace', 'toolchain', 'app', 'embed', 'test',
                 'dependencies', 'dev-dependencies'), '', ('manifest-version',))
    if type(data['manifest-version']) is not int or data['manifest-version'] != 1:
        manifest.fail('manifest-version', 'supported manifest version is 1')
    if not ('package' in data or 'workspace' in data):
        manifest.fail('package', 'a package or workspace is required')
    if 'toolchain' in data:
        table(data['toolchain'], ('version',), 'toolchain', ('version',))
        version(data['toolchain']['version'], 'toolchain.version')
    if 'package' in data:
        package = data['package']
        table(package, ('name', 'version', 'eldude', 'source-dir', 'test-dir'), 'package', ('name', 'version'))
        string(package['name'], 'package.name', IDENTIFIER)
        version(package['version'], 'package.version')
        if 'eldude' in package:
            version(package['eldude'], 'package.eldude', True)
        for kind in ('source-dir', 'test-dir'):
            string(package.get(kind, 'src' if kind == 'source-dir' else 'tests'), 'package.' + kind)
            root = manifest.directory(kind)
            declared = path.parent / package.get(kind, 'src' if kind == 'source-dir' else 'tests')
            if any(p.is_symlink() for p in (declared, *declared.parents) if p != path.parent and p.is_relative_to(path.parent)):
                manifest.fail('package.' + kind, 'cannot traverse a symlinked directory')
            if not root.is_relative_to(path.parent) or root == path.parent or 'build' in root.relative_to(path.parent).parts:
                manifest.fail('package.' + kind, 'must stay inside the package, outside build/')
            for ancestor in (root, *root.parents):
                if ancestor == path.parent:
                    break
                if (ancestor / 'eldude.toml').exists():
                    manifest.fail('package.' + kind, 'cannot be inside a nested package')
        source, tests = manifest.directory('source-dir'), manifest.directory('test-dir')
        if source.is_relative_to(tests) or tests.is_relative_to(source):
            manifest.fail('package.test-dir', 'source and test roots must not overlap')
    if 'workspace' in data:
        table(data['workspace'], ('members',), 'workspace', ('members',))
        members = data['workspace']['members']
        if not isinstance(members, list):
            manifest.fail('workspace.members', 'expected a list of paths')
        seen = set()
        for member in members:
            string(member, 'workspace.members')
            location = (path.parent / member).resolve()
            if not location.is_relative_to(path.parent) or location == path.parent or location in seen:
                manifest.fail('workspace.members', 'members must be unique directories inside the workspace')
            seen.add(location)
    names = set()
    for kind in ('app', 'embed', 'test'):
        targets = data.get(kind, [])
        if not isinstance(targets, list) or (kind in data and 'package' not in data):
            manifest.fail(kind, 'target arrays require a package')
        for target in targets:
            entries = 'exports' if kind == 'embed' else 'entry'
            table(target, ('name', entries, 'host'), kind, ('name', entries, 'host'))
            string(target['name'], kind + '.name', IDENTIFIER)
            string(target['host'], kind + '.host', QUALIFIED)
            if target['name'] in names:
                manifest.fail(kind + '.name', 'target names must be unique across target kinds')
            names.add(target['name'])
            roots = target[entries] if kind == 'embed' else [target[entries]]
            if not isinstance(roots, list) or not roots:
                manifest.fail(kind + '.' + entries, 'expected a nonempty list of exported functions')
            for entry in roots:
                string(entry, kind + '.' + entries, QUALIFIED)
    for kind in ('dependencies', 'dev-dependencies'):
        dependencies = data.get(kind, {})
        if not isinstance(dependencies, dict) or (kind in data and 'package' not in data):
            manifest.fail(kind, 'dependency tables require a package')
        for name, dependency in dependencies.items():
            field = kind + '.' + name
            string(name, field, IDENTIFIER)
            table(dependency, ('path', 'version', 'registry', 'git', 'rev'), field)
            if sum(key in dependency for key in ('path', 'registry', 'git')) != 1:
                manifest.fail(field, 'select exactly one dependency source')
            for key, value in dependency.items():
                string(value, field + '.' + key)
            if 'version' in dependency:
                version(dependency['version'], field + '.version', True)
            if 'registry' in dependency and 'version' not in dependency:
                manifest.fail(field, 'registry source requires version')
            if 'git' in dependency:
                if not re.fullmatch(r'(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})', dependency.get('rev', '')):
                    manifest.fail(field + '.rev', 'Git source requires a full immutable commit')
                if 'version' in dependency:
                    manifest.fail(field, 'Git source cannot specify version')
            elif 'rev' in dependency:
                manifest.fail(field, 'rev requires a Git source')
            for key in ('registry', 'git'):
                if key in dependency:
                    url = urlsplit(dependency[key])
                    if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment:
                        manifest.fail(field + '.' + key, 'expected an HTTPS origin without credentials, query, or fragment')
    overlap = data.get('dependencies', {}).keys() & data.get('dev-dependencies', {}).keys()
    if overlap:
        manifest.fail('dev-dependencies', 'also declared in dependencies: ' + ', '.join(sorted(overlap)))
    return manifest


def nearest_manifest(start):
    start = Path(start).resolve()
    if start.is_file():
        start = start.parent
    return next((p / 'eldude.toml' for p in (start, *start.parents) if (p / 'eldude.toml').is_file()), None)


def workspace_owner(package):
    owners = []
    for parent in package.path.parent.parents:
        candidate = parent / 'eldude.toml'
        if candidate.is_file():
            outer = read_manifest(candidate)
            if package.path.parent in {(parent / p).resolve() for p in outer.data.get('workspace', {}).get('members', [])}:
                owners.append(outer)
    if len(owners) > 1:
        package.fail('workspace', 'package is owned by multiple workspaces: ' + ', '.join(str(p.path) for p in owners))
    if owners and 'workspace' in package.data:
        package.fail('workspace', 'nested workspace ownership is not supported')
    return owners[0] if owners else None


@dataclass
class Selection:
    owner: Manifest
    members: tuple[Manifest, ...]
    packages: tuple[Manifest, ...]

    @property
    def root(self):
        return self.owner.path.parent


def select_project(start, *, manifest_path=None, workspace=False, package=None):
    if workspace and package:
        raise ValueError('--workspace and --package cannot be combined')
    path = Path(manifest_path) if manifest_path else nearest_manifest(start)
    if path is None:
        raise ValueError('No eldude.toml found; use eldude init or an explicit source path')
    initial = read_manifest(path)
    owner = workspace_owner(initial) or initial
    workspace_owner(owner)
    members = [owner] if owner.name else []
    for member in owner.data.get('workspace', {}).get('members', []):
        child = read_manifest(owner.path.parent / member / 'eldude.toml')
        if child.path.parent != (owner.path.parent / member).resolve():
            owner.fail('workspace.members', 'a member manifest cannot redirect to another package')
        workspace_owner(child)
        if not child.name or 'workspace' in child.data:
            child.fail('workspace', 'workspace members must be packages without nested workspaces')
        if 'toolchain' in child.data:
            child.fail('toolchain', 'the workspace root owns the toolchain pin')
        if (child.path.parent / 'eldude.lock').exists():
            child.fail('workspace', 'the workspace root owns eldude.lock; remove the member lockfile')
        members.append(child)
    if len({m.name for m in members}) != len(members):
        owner.fail('workspace.members', 'duplicate package names')
    members.sort(key=lambda m: m.name)
    selected = members if workspace or initial.path == owner.path else [initial]
    if package:
        selected = [m for m in members if m.name == package]
        if not selected:
            owner.fail('workspace.members', f'unknown package {package!r}')
    return Selection(owner, tuple(members), tuple(selected))


def check_toolchain(selection):
    pin = selection.owner.data.get('toolchain', {}).get('version')
    if pin is not None and pin != TOOLCHAIN_VERSION:
        selection.owner.fail('toolchain.version', f'pin {pin} does not match running toolchain {TOOLCHAIN_VERSION}')
    for package in selection.members:
        check_compatibility(package)


def check_compatibility(package):
    constraint = package.data['package'].get('eldude')
    if constraint and not satisfies(TOOLCHAIN_VERSION, constraint):
        package.fail('package.eldude', f'running compiler {TOOLCHAIN_VERSION} does not satisfy {constraint}')


def discover_files(root):
    """Stable authored-file walk; nested manifests and symlink directories stop it."""
    root = Path(root)
    if root.is_symlink():
        raise ValueError(f'{root}: refusing to traverse a symlinked directory')
    for ancestor in (root, *root.parents):
        if (ancestor / 'eldude.toml').is_file():
            break
        if ancestor.name in EXCLUDED:
            return []
    result = []
    for directory, dirs, files in os.walk(root):
        current = Path(directory)
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED and not (current / d).is_symlink()
                         and not (current / d / 'eldude.toml').exists())
        result.extend(current / name for name in sorted(files) if name.endswith('.eld'))
    return sorted(result)


def source_files(package, tests=False):
    result = []
    for kind in ('source-dir', 'test-dir') if tests else ('source-dir',):
        root = package.directory(kind)
        if not root.is_dir():
            if kind == 'test-dir' and not root.exists():
                continue
            package.fail('package.' + kind, 'source root must be an existing directory')
        for path in discover_files(root):
            resolved = path.resolve()
            if not resolved.is_relative_to(root):
                package.fail('package.' + kind, f'source file escapes its declared root: {path}')
            for ancestor in resolved.parents:
                if ancestor == package.path.parent:
                    break
                if (ancestor / 'eldude.toml').exists():
                    package.fail('package.' + kind, f'source file crosses a nested package: {path}')
            result.append(path)
    return sorted(result)
