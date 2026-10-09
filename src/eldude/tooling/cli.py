"""The experimental Eldude project CLI, using the Python IR frontend."""
import argparse
from dataclasses import asdict
import difflib
import json
from pathlib import Path
import re
import shutil
import sys
import tomllib

from eldude.tooling.format import format_source, write_file
from eldude.tooling.model import (TOOLCHAIN_VERSION, IDENTIFIER, select_project, check_toolchain,
                           source_files, discover_files, nearest_manifest)
from eldude.tooling.resolver import resolve, reconcile_lock, module_sources
from eldude.source.modules import _header, load_modules
from eldude.source.pipeline import check_file
from eldude.source.syntax import Diagnostic, Span, parse_source


class Reporter:
    def __init__(self, machine=False):
        self.machine = machine
        self.scope = {}

    def event(self, kind, **fields):
        if self.machine:
            print(json.dumps({'schema_version': 1, 'kind': kind, **fields}, ensure_ascii=False))

    def diagnostic(self, error):
        if self.machine:
            self.event('diagnostic', category=error.code, code=error.code, severity='error', message=error.message,
                       primary=asdict(error.span), related=[{'message': m, 'span': asdict(s)} for m, s in error.related],
                       notes=[], suggested_edits=[])
        else:
            print(error, file=sys.stderr)

    def summary(self, status, message, **fields):
        self.event('summary', status=status, selection=self.scope, message=message, **fields)
        if not self.machine:
            print(message, file=sys.stderr)


def parser():
    result = argparse.ArgumentParser(prog='eldude', description=__doc__)
    result.add_argument('--version', action='version', version='eldude ' + TOOLCHAIN_VERSION + ' (experimental Python IR)')
    commands = result.add_subparsers(dest='command', required=True)
    for command in ('new', 'init'):
        sub = commands.add_parser(command)
        if command == 'new':
            sub.add_argument('path')
        sub.add_argument('--lib', action='store_true')
    for command in ('check', 'build', 'run', 'test', 'fmt', 'metadata', 'lock', 'update', 'clean', 'interface'):
        sub = commands.add_parser(command)
        sub.add_argument('--manifest-path')
        if command != 'clean':
            selection = sub.add_mutually_exclusive_group()
            selection.add_argument('--workspace', action='store_true')
            selection.add_argument('--package')
        if command in ('check', 'build', 'run', 'test', 'interface', 'lock', 'update'):
            sub.add_argument('--locked', action='store_true')
            sub.add_argument('--offline', action='store_true')
        if command in ('check', 'build', 'test'):
            sub.add_argument('--message-format', choices=('human', 'json'), default='human')
        if command in ('build', 'run', 'test', 'check'):
            sub.add_argument('--target')
            if command != 'check':
                sub.add_argument('--release', action='store_true')
            roots = sub.add_mutually_exclusive_group()
            if command in ('check', 'build', 'run'):
                roots.add_argument('--app')
            if command in ('check', 'build'):
                roots.add_argument('--embed')
            if command in ('check', 'test'):
                roots.add_argument('--test')
        if command == 'check':
            sub.add_argument('file', nargs='?')
        elif command == 'interface':
            sub.add_argument('module')
        elif command == 'update':
            sub.add_argument('dependency', nargs='?')
        elif command == 'fmt':
            sub.add_argument('paths', nargs='*')
            modes = sub.add_mutually_exclusive_group()
            modes.add_argument('--check', action='store_true')
            modes.add_argument('--diff', action='store_true')
    return result


def project(args, start=None):
    return select_project(start or Path.cwd(), manifest_path=args.manifest_path,
                          workspace=getattr(args, 'workspace', False), package=getattr(args, 'package', None))


def create_project(args):
    root = Path(args.path).absolute() if args.command == 'new' else Path.cwd()
    name = root.name
    if not re.fullmatch(IDENTIFIER, name):
        raise ValueError('destination name must be an ASCII package identifier')
    if root.is_symlink() or (args.command == 'new' and root.exists()):
        raise ValueError(f'{root}: destination already exists or is a symlink')
    manifest = root / 'eldude.toml'
    if manifest.exists() or manifest.is_symlink():
        raise ValueError(f'{manifest}: refusing to overwrite an existing manifest')
    source = root / 'src' / ('lib.eld' if args.lib else 'main.eld')
    if (root / 'src').is_symlink() or ((root / 'src').exists() and not (root / 'src').is_dir()):
        raise ValueError('src must be a real directory')
    if source.is_symlink() or (source.exists() and not source.is_file()):
        raise ValueError(f'{source}: invalid starter path')
    text = (f'manifest-version = 1\n\n[package]\nname = "{name}"\nversion = "0.1.0"\n'
            f'\n[toolchain]\nversion = "{TOOLCHAIN_VERSION}"\n')
    if not args.lib:
        text += f'\n[[app]]\nname = "{name}"\nentry = "{name}::main"\nhost = "cli::standard"\n'
    starter = f'module {name};\n' + ('' if args.lib else '\npub fn main() -> Int {\n    0\n}\n')
    files = [(manifest, text)]
    if not source.exists():
        files.append((source, starter))
    if not (root / '.gitignore').exists() and not (root / '.gitignore').is_symlink():
        files.append((root / '.gitignore', '/build/\n'))
    created = []
    try:
        for path, contents in files:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open('x', encoding='utf-8', newline='\n') as stream:
                created.append(path)
                stream.write(contents)
    except OSError:
        for path in reversed(created):
            path.unlink()
        raise
    print(f'Created {"library" if args.lib else "application"} {name} at {root}', file=sys.stderr)
    return 0


def format_paths(args):
    if args.paths and (args.workspace or args.package or args.manifest_path):
        raise ValueError('explicit format paths cannot be combined with project selectors')
    if '-' in args.paths and args.paths != ['-']:
        raise ValueError('stdin must be the sole input')
    if args.paths == ['-']:
        if nearest_manifest(Path.cwd()):
            check_toolchain(project(args))
        original = sys.stdin.buffer.read()
        pending = [(None, original, format_source(original.decode('utf-8'), '<stdin>').encode('utf-8'), 0)]
    else:
        if args.paths:
            paths = []
            for name in args.paths:
                path = Path(name).absolute()
                if not path.exists():
                    raise ValueError(f'{path}: input does not exist')
                paths.extend(discover_files(path) if path.is_dir() else [path])
            # Even an empty directory belongs to its project's formatter pin.
            for name in args.paths:
                if nearest_manifest(name):
                    check_toolchain(select_project(name))
        else:
            selection = project(args)
            check_toolchain(selection)
            paths = [path for package in selection.packages for path in source_files(package, tests=True)]
        pending, seen = [], set()
        for path in sorted(paths):
            if not (args.check or args.diff) and path.is_symlink():
                raise ValueError(f'{path}: refusing to replace a symlink')
            if args.paths and nearest_manifest(path):
                check_toolchain(select_project(path))
            stat = path.stat()
            identity = path.resolve()
            if identity in seen:
                continue
            seen.add(identity)
            original = path.read_bytes()
            formatted = format_source(original.decode('utf-8'), str(path)).encode('utf-8')
            pending.append((path, original, formatted, stat.st_mode))
    changed = False
    for path, original, formatted, mode in pending:
        name = str(path) if path else '<stdin>'
        if path is None and not (args.check or args.diff):
            sys.stdout.buffer.write(formatted)
        elif original != formatted:
            changed = True
            if args.diff:
                sys.stdout.writelines(difflib.unified_diff(original.decode('utf-8').splitlines(keepends=True),
                    formatted.decode('utf-8').splitlines(keepends=True), fromfile=name, tofile=name + ' (formatted)'))
            else:
                if not args.check:
                    write_file(path, original, formatted, mode)
                print(name)
    return int(changed and (args.check or args.diff))


def metadata(selection):
    graph = resolve(selection, inspect=True)
    packages = []
    for package in graph.packages.values():
        modules = []
        for path in source_files(package, tests=package in selection.members):
            header = _header(path.read_text(encoding='utf-8'), path)
            modules.append({'path': str(path), 'module': header[0] if header else None})
        packages.append({'name': package.name, 'version': package.data['package']['version'],
                         'manifest': str(package.path), 'modules': modules,
                         'targets': {kind: package.data.get(kind, []) for kind in ('app', 'embed', 'test')}})
    lock = selection.root / 'eldude.lock'
    existing = tomllib.loads(lock.read_text(encoding='utf-8')) if lock.exists() else None
    pin = selection.owner.data.get('toolchain', {}).get('version')
    return {'schema_version': 1, 'root': str(selection.root), 'selection': [p.name for p in selection.packages],
            'packages': packages, 'dependencies': graph.edges, 'graph_complete': not graph.unresolved,
            'unresolved': graph.unresolved, 'lock': existing,
            'toolchain': {'running': TOOLCHAIN_VERSION, 'pin': pin, 'matches_pin': pin is None or pin == TOOLCHAIN_VERSION},
            'hosts': [{'identity': 'python::experimental', 'status': 'experimental'},
                      {'identity': 'cli::standard', 'status': 'unsupported'}],
            'artifacts': [str(p) for p in sorted((selection.root / 'build').rglob('*'))
                          if p.is_file() and (p.suffix == '.pyz' or p.name.endswith('.eldir.json'))]
                         if not (selection.root / 'build').is_symlink() else []}


def selected_targets(selection, args):
    selector = next(((kind, getattr(args, kind, None)) for kind in ('app', 'embed', 'test')
                     if getattr(args, kind, None)), None)
    if selector and len(selection.packages) != 1:
        raise ValueError('a root selector requires exactly one selected package')
    kinds = {'run': ('app',), 'build': ('app', 'embed')}.get(args.command, ('app', 'embed', 'test'))
    targets = [(p, kind, target) for p in selection.packages for kind in kinds for target in p.data.get(kind, [])
               if selector is None or (kind, target['name']) == selector]
    if selector and not targets:
        raise ValueError(f'unknown {selector[0]} target {selector[1]!r}')
    if args.command == 'run' and len(targets) != 1:
        if not targets:
            raise ValueError('no applications selected; declare an [[app]] target in eldude.toml')
        names = '\n'.join('  ' + p.name + ':' + t['name'] for p, _, t in targets)
        package_flag = '--package PACKAGE ' if len(selection.packages) > 1 else ''
        raise ValueError(f'run requires exactly one application; selected {len(targets)}\n'
                         f'Choose one with: eldude run {package_flag}--app NAME\n\n'
                         f'Available applications (package:name):\n{names}')
    return targets, selector


def check_project(graph, args, reporter):
    selection = graph.selection
    targets, selector = selected_targets(selection, args)
    tests = args.command in ('check', 'test') and (not selector or selector[0] == 'test')
    paths, allowed = module_sources(graph, selection.packages, tests=tests)
    reporter.scope = {'packages': [p.name for p in selection.packages], 'root': list(selector) if selector else None}
    entries = []
    for package, kind, target in targets:
        for entry in target.get('exports', [target.get('entry')]):
            module, function = entry.rsplit('::', 1)
            own = source_files(package, tests=kind == 'test')
            matches = [p for p in own if (header := _header(p.read_text(encoding='utf-8'), p)) and header[0] == module]
            if len(matches) != 1:
                field = 'exports' if kind == 'embed' else 'entry'
                package.fail(kind + '.' + field, f'entry module {module!r} must be provided by this package',
                             occurrence=package.data[kind].index(target))
            entries.append((package, kind, target, matches[0], function))
    selected_paths = sorted({item[3] for item in entries}) if selector or args.command == 'run' else sorted({
        path for package in selection.packages for path in source_files(package, tests=tests)})
    checked = {path: check_file(path, sources=paths, import_allowed=allowed) for path in selected_paths}
    roots = []
    from eldude.tooling.build import check_root, machine_target
    machine_target(getattr(args, 'target', None))
    for package, kind, target, path, function in entries:
        roots.append((package, kind, target, check_root(package, kind, target, path, function, paths, allowed)))
    return checked, roots


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    application_args = []
    if arguments and arguments[0] == 'run' and '--' in arguments:
        marker = arguments.index('--')
        application_args, arguments = arguments[marker + 1:], arguments[:marker]
    args = parser().parse_args(arguments)
    reporter = Reporter(getattr(args, 'message_format', None) == 'json')
    try:
        if args.command in ('new', 'init'):
            return create_project(args)
        if args.command == 'fmt':
            return format_paths(args)
        if args.command == 'check' and args.file:
            if args.workspace or args.package or args.app or args.embed or args.test:
                raise ValueError('file selection cannot be combined with package, workspace, or root selectors')
            path = Path(args.file).resolve()
            reporter.scope = {'file': str(path)}
            if nearest_manifest(path) or args.manifest_path:
                selection = project(args, path)
                check_toolchain(selection)
                graph = resolve(selection)
                reconcile_lock(graph, locked=args.locked)
                paths, allowed = module_sources(graph, selection.packages, tests=True)
                if path not in paths:
                    raise ValueError('selected file is outside the package source/test roots')
                check_file(path, sources=paths, import_allowed=allowed)
            else:
                check_file(path)
            reporter.summary('success', f'Checked module {path}; no application host validated', checked=1)
            return 0
        selection = project(args)
        reporter.scope = {'packages': [p.name for p in selection.packages]}
        if args.command == 'metadata':
            print(json.dumps(metadata(selection), indent=2, ensure_ascii=False))
            return 0
        if args.command == 'clean':
            build = selection.root / 'build'
            if build.is_symlink():
                raise ValueError(f'{build}: refusing to clean a symlinked build root')
            if build.exists():
                shutil.rmtree(build)
            reporter.summary('success', f'Cleaned owning project build directory {build}')
            return 0
        check_toolchain(selection)
        graph = resolve(selection)
        if args.command == 'update' and args.dependency and args.dependency not in {e['to'] for e in graph.edges}:
            raise ValueError(f'unknown dependency {args.dependency!r}')
        changed = reconcile_lock(graph, locked=args.locked)
        if args.command in ('lock', 'update'):
            reporter.summary('success', f'{"Updated" if changed else "Unchanged"} {selection.root / "eldude.lock"} (path dependencies)')
            return 0
        if args.command == 'interface':
            selection.owner.fail('interface', 'Implementation limit: complete canonical interface rendering is not available', 'unsupported')
        checked, roots = check_project(graph, args, reporter)
        if args.command == 'check':
            reporter.summary('success', f'Checked {len(checked)} selected modules in {", ".join(reporter.scope["packages"])}'
                             + (f'; target {reporter.scope["root"]}' if reporter.scope['root'] else ''), checked=len(checked))
            return 0
        from eldude.tooling.build import build_and_execute
        return build_and_execute(graph, args, reporter, checked, roots, application_args)
    except Diagnostic as caught:
        error = caught
        status = 2 if args.command == 'fmt' or error.code in ('configuration', 'unsupported', 'internal-error') else 1
    except (OSError, UnicodeError, ValueError) as caught:
        error = Diagnostic('configuration' if isinstance(caught, ValueError) else 'input', str(caught), Span('<command>', 0, 0, 1, 1))
        status = 2
    except KeyboardInterrupt:
        print('eldude: interrupted', file=sys.stderr)
        return 130
    except Exception as caught:
        error = Diagnostic('internal-error', f'{type(caught).__name__}: {caught}', Span('<command>', 0, 0, 1, 1))
        status = 2
    reporter.diagnostic(error)
    if args.command in ('check', 'build', 'test'):
        reporter.summary('failure', 'Selected operation failed')
    return status


if __name__ == '__main__':
    sys.exit(main())
