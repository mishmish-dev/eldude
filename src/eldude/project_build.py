"""Experimental Python host: checked IR bundles and isolated zipapp execution."""
import hashlib
import io
import json
from pathlib import Path
import platform
import subprocess
import sys
import zipfile

from eldude.ir_artifact import encode_program
from eldude.project_model import TOOLCHAIN_VERSION, source_files
from eldude.project_resolver import atomic_write, lock_data
from eldude.source_elaboration import SourceElaborator
from eldude.source_modules import load_modules
from eldude.source_syntax import Diagnostic, parse_source


RUNTIME_FILES = ('ir_artifact.py', 'source_pipeline.py', 'source_syntax.py', 'check_grammar.py',
                 'source_features.py', 'source_declarations.py', 'inference.py', 'handlers.py',
                 'effect_rows.py', 'capture_rows.py', 'trait_constraints.py', 'task_runtime.py',
                 'source_modules.py', '__init__.py')


def machine_target(requested=None):
    current = f'python-{platform.machine().lower()}-{sys.platform}'
    if requested not in (None, current):
        from eldude.source_syntax import Span
        raise Diagnostic('unsupported', f'Implementation limit: Python host supports only {current}, not {requested}',
                         Span('<command>', 0, 0, 1, 1))
    return current


def check_root(package, kind, target, path, function, sources, allowed):
    if target['host'] != 'python::experimental' or kind == 'embed':
        package.fail(kind + '.host', f'Implementation limit: {target["host"]} {kind} host is unavailable; '
                     'Python applications/tests use python::experimental', 'unsupported')
    ast = parse_source(path.read_text(encoding='utf-8', newline=''), str(path))
    graph = load_modules(ast, sources=sources, import_allowed=allowed)
    declaration = graph.exports[ast.items[0].items[0]].get(function)
    if declaration is None or declaration.kind != 'function':
        raise Diagnostic('entry', f'Entry {function!r} must be an exported function', ast.span)
    return SourceElaborator(ast, graph).compile(entry=function, fixture=False)


def json_bytes(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')


def archive_bytes(program, record, root):
    buffer = io.BytesIO()
    files = {'eldude/' + name: (Path(__file__).parent / name).read_bytes() for name in RUNTIME_FILES}
    files['__main__.py'] = b'from eldude.ir_artifact import main\nraise SystemExit(main())\n'
    files['program.json'] = json_bytes(encode_program(program, root=root))
    files['build.json'] = json_bytes(record)
    with zipfile.ZipFile(buffer, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name, contents in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, contents)
    return buffer.getvalue()


def build_and_execute(graph, args, reporter, checked, roots, application_args):
    if application_args:
        graph.selection.owner.fail('run', 'Implementation limit: Python host has no Eldude argument API', 'unsupported')
    profile = 'release' if args.release else 'dev'
    machine = machine_target(args.target)
    build = graph.selection.root / 'build'
    directory = build / machine / profile
    compiler_files = sorted(Path(__file__).parent.glob('*.py'))
    compiler = hashlib.sha256(b''.join(p.name.encode() + p.read_bytes() for p in compiler_files if not p.name.startswith('test_'))).hexdigest()
    base = {'schema_version': 1, 'backend': 'python-ir-experimental', 'toolchain': TOOLCHAIN_VERSION,
            'compiler': compiler, 'python': platform.python_version(), 'machine_target': machine,
            'profile': profile, 'graph': lock_data(graph), 'native_inputs': []}
    pending = []
    if args.command == 'build':
        owners = {path: package for package in graph.selection.packages for path in source_files(package)}
        for path, source in checked.items():
            package = owners[path]
            module = source.ast.items[0].items[0]
            record = base | {'package': package.name, 'module': module, 'artifact_kind': 'checked-ir'}
            content = json_bytes({'build': record, 'program': encode_program(source.program, root=package.path.parent)})
            # Hex identities stay distinct on case-insensitive filesystems.
            module_path = Path(*(part.encode().hex() for part in module.split('::'))).with_suffix('.eldir.json')
            pending.append((package, None, 'checked-ir', directory / package.name.encode().hex() / 'modules' / module_path, content))
    for package, kind, target, source in roots:
        if args.command == 'test' and kind != 'test':
            continue
        record = base | {'package': package.name, 'target': target['name'], 'host': target['host'], 'entry': target['entry']}
        content = archive_bytes(source.program, record, package.path.parent)
        # Immutable content names let concurrent invocations launch their own exact build.
        digest = hashlib.sha256(content).hexdigest()
        path = directory / package.name.encode().hex() / target['name'].encode().hex() / (digest + '.pyz')
        pending.append((package, target, kind, path, content))
    artifacts = []
    for package, target, kind, path, content in pending:
        for parent in (path, *path.parents):
            if parent.is_symlink():
                raise ValueError(f'{parent}: refusing symlinked build output')
            if parent == graph.selection.root:
                break
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_bytes() != content:
            atomic_write(path, content)
        artifact_kind = 'application' if kind == 'app' else kind
        reporter.event('artifact', path=str(path), artifact_kind=artifact_kind, package=package.name,
                       target=target['name'] if target else None, profile=profile, backend='python-ir-experimental')
        if not reporter.machine:
            print(f'Built experimental Python {artifact_kind}: {path}', file=sys.stderr)
        if target:
            artifacts.append((package, target, path))
    if args.command == 'build':
        reporter.summary('success', f'Built {len(pending)} experimental Python IR artifacts', artifacts=len(pending))
        return 0
    if args.command == 'run':
        package, _, path = artifacts[0]
        result = subprocess.run([sys.executable, str(path)], cwd=package.path.parent)
        return result.returncode if result.returncode >= 0 else 128 - result.returncode
    failures = 0
    for package, target, path in artifacts:
        result = subprocess.run([sys.executable, str(path)], cwd=package.path.parent,
                                capture_output=reporter.machine)
        if reporter.machine:
            for stream in ('stdout', 'stderr'):
                text = getattr(result, stream).decode('utf-8', errors='replace')
                if text:
                    reporter.event('output', package=package.name, target=target['name'], stream=stream, text=text)
        failures += result.returncode != 0
        reporter.event('test-result', package=package.name, target=target['name'],
                       status='passed' if result.returncode == 0 else 'failed', exit_status=result.returncode)
    message = f'{len(artifacts)} tests executed; {failures} failed' if artifacts else 'No test targets selected; 0 tests executed'
    reporter.summary('failure' if failures else 'success', message, executed=len(artifacts), failed=failures)
    return int(bool(failures))
