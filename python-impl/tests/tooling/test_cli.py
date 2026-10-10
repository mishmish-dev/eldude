"""End-to-end CLI behavior in temporary projects, including filesystem safety."""
import json
from contextlib import redirect_stdout
from io import StringIO
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch



class EldudeCLITests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()

    def cli(self, *args, cwd=None, input=None):
        return subprocess.run([sys.executable, '-m', 'eldude', *args], cwd=cwd or self.root,
                              input=input, text=True, capture_output=True)

    def package(self, source='module app; pub fn main()->Int { 0 }', targets='', dependencies=''):
        (self.root / 'src').mkdir(exist_ok=True)
        (self.root / 'src/main.eld').write_text(source)
        (self.root / 'eldude.toml').write_text(
            'manifest-version=1\n[package]\nname="app"\nversion="0.1.0"\n' + targets + dependencies)

    def test_new_library_and_application_templates_and_existing_files(self):
        self.assertEqual(self.cli('new', 'hello').returncode, 0)
        manifest = (self.root / 'hello/eldude.toml').read_text()
        self.assertIn('host = "cli::standard"', manifest)
        self.assertEqual(self.cli('check', 'src/main.eld', cwd=self.root / 'hello').returncode, 0)
        old = (self.root / 'hello/src/main.eld').read_bytes()
        self.assertEqual(self.cli('new', 'hello').returncode, 2)
        self.assertEqual((self.root / 'hello/src/main.eld').read_bytes(), old)
        self.assertEqual(self.cli('new', 'library', '--lib').returncode, 0)
        self.assertEqual(self.cli('check', cwd=self.root / 'library').returncode, 0)

    def test_static_check_json_and_no_initialization(self):
        self.package('module app; let value: Int = 1 / 0; pub fn valueOf()->Int { value }')
        result = self.cli('check', '--message-format=json')
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        events = [json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual(events[-1]['kind'], 'summary')
        self.assertEqual(events[-1]['status'], 'success')
        (self.root / 'src/main.eld').write_text('module app;\nfn bad()->Int { true }')
        result = self.cli('check', '--message-format=json')
        self.assertEqual(result.returncode, 1)
        event = json.loads(result.stdout.splitlines()[0])
        self.assertEqual(event['kind'], 'diagnostic')
        self.assertEqual(event['primary']['line'], 2)

    def test_run_with_inherited_package_host_and_explicit_override(self):
        self.package(targets=(
            'host="python::experimental"\n'
            '[[app]]\nname="inherited"\nentry="app::main"\n'
            '[[app]]\nname="override"\nentry="app::main"\nhost="cli::standard"\n'))
        result = self.cli('metadata')
        self.assertEqual(result.returncode, 0, result.stderr)
        targets = json.loads(result.stdout)['packages'][0]['targets']['app']
        self.assertEqual([target['host'] for target in targets],
                         ['python::experimental', 'cli::standard'])
        result = self.cli('run', '--app', 'inherited')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = self.cli('run', '--app', 'override')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('cli::standard', result.stderr)

    def test_tests_inherit_package_host_and_can_override_it(self):
        self.package(targets=(
            'host="python::experimental"\n'
            '[[test]]\nname="inherited"\nentry="app::main"\n'
            '[[test]]\nname="override"\nentry="app::main"\nhost="cli::standard"\n'))
        result = self.cli('metadata')
        self.assertEqual(result.returncode, 0, result.stderr)
        targets = json.loads(result.stdout)['packages'][0]['targets']['test']
        self.assertEqual([target['host'] for target in targets],
                         ['python::experimental', 'cli::standard'])
        result = self.cli('test', '--test', 'inherited')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('1 tests executed; 0 failed', result.stderr)
        result = self.cli('test', '--test', 'override')
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn('cli::standard', result.stderr)

    def test_json_spans_count_unicode_scalars_and_preserve_crlf(self):
        self.package()
        source = 'module app;\r\n// π 🚀\r\nfn bad()->Int { true }\r\n'
        (self.root / 'src/main.eld').write_bytes(source.encode('utf-8'))
        result = self.cli('check', 'src/main.eld', '--message-format=json')
        self.assertEqual(result.returncode, 1)
        events = [json.loads(line) for line in result.stdout.splitlines()]
        span = events[0]['primary']
        self.assertEqual(source[span['start']:span['end']], 'true')
        self.assertEqual((span['line'], span['column']), (3, 17))
        self.assertEqual(events[-1]['selection']['file'], str(self.root / 'src/main.eld'))

    def test_targeted_check_skips_unrelated_errors_but_bare_check_finds_them(self):
        self.package(targets='[[app]]\nname="app"\nentry="app::main"\nhost="python::experimental"\n')
        (self.root / 'src/broken.eld').write_text('module broken; fn bad()->Int { true }')
        result = self.cli('check', '--app', 'app')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('app', result.stderr)
        self.assertEqual(self.cli('check').returncode, 1)

    def test_format_diff_check_preflight_and_no_lock(self):
        self.package('module app; pub fn main()->Int{0}')
        path = self.root / 'src/main.eld'
        original = path.read_bytes()
        self.assertEqual(self.cli('fmt', '--check').returncode, 1)
        diff = self.cli('fmt', '--diff')
        self.assertEqual(diff.returncode, 1)
        self.assertIn('---', diff.stdout)
        self.assertEqual(path.read_bytes(), original)
        bad = self.root / 'src/bad.eld'
        bad.write_text('module bad; fn')
        self.assertEqual(self.cli('fmt').returncode, 2)
        self.assertEqual(path.read_bytes(), original)
        bad.unlink()
        self.assertEqual(self.cli('fmt').returncode, 0)
        self.assertEqual(self.cli('fmt', '--check').returncode, 0)
        self.assertFalse((self.root / 'eldude.lock').exists())
        self.assertEqual(self.cli('fmt', '-','--check', input='module m;').returncode, 1)

    def test_project_format_reads_the_manifest_once(self):
        from eldude.tooling.cli import format_paths, parser
        from eldude.tooling.model import read_manifest
        self.package()
        for index in range(19):
            (self.root / f'src/extra_{index}.eld').write_text(f'module extra_{index};')
        with patch('pathlib.Path.cwd', return_value=self.root), redirect_stdout(StringIO()), \
                patch('eldude.tooling.model.read_manifest', wraps=read_manifest) as read:
            self.assertEqual(format_paths(parser().parse_args(['fmt', '--check'])), 1)
        self.assertEqual(read.call_count, 1)

    def test_second_target_json_diagnostic_points_to_its_host_or_entry(self):
        for kind, flag in (('app', '--app'), ('test', '--test')):
            for field, value in (('host', 'cli::standard'), ('entry', 'missing::main')):
                with self.subTest(kind=kind, field=field):
                    second = {'host': 'python::experimental', 'entry': 'app::main'} | {field: value}
                    self.package(targets=(
                        f'[[{kind}]]\nname="good"\nentry="app::main"\nhost="python::experimental"\n'
                        f'[[{kind}]]\nname="broken"\nentry="{second["entry"]}"\nhost="{second["host"]}"\n'))
                    result = self.cli('check', flag, 'broken', '--message-format=json')
                    self.assertEqual(result.returncode, 2, result.stderr + result.stdout)
                    diagnostic = json.loads(result.stdout.splitlines()[0])
                    self.assertEqual(diagnostic['kind'], 'diagnostic')
                    self.assertEqual(diagnostic['primary']['line'], 12 if field == 'host' else 11)

    def test_metadata_does_not_resolve_or_reject_a_pin_mismatch(self):
        self.package(dependencies='[toolchain]\nversion="99.0.0"\n[dependencies]\nmissing={path="../missing"}')
        result = self.cli('metadata')
        self.assertEqual(result.returncode, 0, result.stderr)
        metadata = json.loads(result.stdout)
        self.assertFalse(metadata['graph_complete'])
        self.assertFalse(metadata['toolchain']['matches_pin'])
        self.assertFalse((self.root / 'eldude.lock').exists())
        self.assertEqual(self.cli('fmt').returncode, 2)

    def test_clean_refuses_symlink_and_preserves_lock_and_source(self):
        self.package()
        (self.root / 'build').symlink_to(self.root / 'src', target_is_directory=True)
        self.assertEqual(self.cli('clean').returncode, 2)
        self.assertTrue((self.root / 'src/main.eld').exists())
        (self.root / 'build').unlink()
        (self.root / 'build').mkdir()
        (self.root / 'build/output').write_text('generated')
        (self.root / 'eldude.lock').write_text('lock')
        self.assertEqual(self.cli('clean').returncode, 0)
        self.assertFalse((self.root / 'build').exists())
        self.assertEqual((self.root / 'eldude.lock').read_text(), 'lock')

    def test_empty_tests_and_unsupported_capabilities_are_honest(self):
        self.package()
        result = self.cli('test')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('No test targets selected', result.stderr)
        self.assertEqual(self.cli('interface', 'app').returncode, 2)
        self.assertEqual(self.cli('run').returncode, 2)

    def test_run_lists_ambiguous_applications_on_separate_lines(self):
        names = [f'example_{index}' for index in range(84)]
        self.package(targets=''.join(
            f'[[app]]\nname="{name}"\nentry="app::main"\nhost="python::experimental"\n'
            for name in names))
        result = self.cli('run')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertIn('selected 84', result.stderr.splitlines()[0])
        self.assertIn('eldude run --app NAME', result.stderr)
        self.assertIn('Available applications:\n  Package app:\n', result.stderr)
        self.assertEqual([line for line in result.stderr.splitlines() if line.startswith('    ')],
                         [f'    {name}' for name in names])
        self.assertEqual(self.cli('run', '--app', names[0]).returncode, 0)

    def test_run_workspace_selection_explains_package_and_application_flags(self):
        self.package(targets='[[app]]\nname="hello"\nentry="app::main"\nhost="python::experimental"\n')
        manifest = self.root / 'eldude.toml'
        manifest.write_text(manifest.read_text() + '\n[workspace]\nmembers=["member"]\n')
        member = self.root / 'member'
        (member / 'src').mkdir(parents=True)
        (member / 'eldude.toml').write_text(
            'manifest-version=1\n[package]\nname="member"\nversion="0.1.0"\n'
            '[[app]]\nname="hello"\nentry="member::main"\nhost="python::experimental"\n')
        (member / 'src/main.eld').write_text('module member; pub fn main()->Int { 0 }')
        result = self.cli('run')
        self.assertEqual(result.returncode, 2)
        self.assertIn('eldude run --package PACKAGE --app NAME', result.stderr)
        self.assertIn('Available applications:\n  Package app:\n    hello\n'
                      '  Package member:\n    hello\n', result.stderr)
        self.assertEqual(self.cli('run', '--package', 'app', '--app', 'hello').returncode, 0)

    def test_run_without_applications_explains_manifest_declaration(self):
        self.package()
        result = self.cli('run')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, '')
        self.assertIn('no applications selected', result.stderr)
        self.assertIn('[[app]]', result.stderr)
        self.assertNotIn('--app', result.stderr)

    def test_metadata_includes_built_library_ir(self):
        self.package('module app;')
        self.assertEqual(self.cli('build').returncode, 0)
        result = self.cli('metadata')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)['artifacts']), 1)

    def test_explicit_format_scope_does_not_cross_a_nested_package(self):
        self.package('module app;pub fn main()->Int{0}')
        nested = self.root / 'src/nested'
        nested.mkdir()
        (nested / 'eldude.toml').write_text('manifest-version=1\n[package]\nname="nested"\nversion="0.1.0"')
        source = nested / 'child.eld'
        source.write_text('module child;pub fn x()->Int{0}')
        old = source.read_bytes()
        self.assertEqual(self.cli('fmt', 'src').returncode, 0)
        self.assertEqual(source.read_bytes(), old)
        (self.root / 'build').mkdir()
        generated = self.root / 'build/generated.eld'
        generated.write_bytes(old)
        self.assertEqual(self.cli('fmt', 'build').returncode, 0)
        self.assertEqual(generated.read_bytes(), old)

    def test_format_preflights_all_project_pins_and_refuses_file_symlinks(self):
        self.package('module app;pub fn main()->Int{0}')
        first = self.root / 'src/main.eld'
        old = first.read_bytes()
        other = self.root / 'other'
        other.mkdir()
        (other / 'eldude.toml').write_text('manifest-version=1\n[package]\nname="other"\nversion="0.1.0"\n'
                                         '[toolchain]\nversion="99.0.0"')
        (other / 'other.eld').write_text('module other;')
        self.assertEqual(self.cli('fmt', str(first), str(other / 'other.eld')).returncode, 2)
        self.assertEqual(first.read_bytes(), old)
        link = self.root / 'linked.eld'
        link.symlink_to(first)
        self.assertEqual(self.cli('fmt', str(link)).returncode, 2)
        self.assertEqual(first.read_bytes(), old)

    def test_python_root_rejection_does_not_change_library_validity(self):
        self.package('module app; pub fn main()->Bool { true }',
                     '[[app]]\nname="app"\nentry="app::main"\nhost="python::experimental"')
        self.assertEqual(self.cli('check', 'src/main.eld').returncode, 0)
        result = self.cli('check', '--app', 'app')
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn('must return Int', result.stderr)

    def test_duplicate_providers_fail_even_when_unimported(self):
        self.package()
        (self.root / 'src/duplicate.eld').write_text('module app;')
        self.assertEqual(self.cli('check', 'src/main.eld').returncode, 1)

    def test_syntax_and_implementation_limits_have_distinct_statuses(self):
        self.package('module app; fn bad(')
        self.assertEqual(self.cli('check').returncode, 1)
        self.package('module app; pub fn main()->Int { 0 }',
                     '[[app]]\nname="app"\nentry="app::main"\nhost="cli::standard"')
        result = self.cli('check')
        self.assertEqual(result.returncode, 2)
        self.assertIn('unsupported', result.stderr)

    def test_format_updates_each_selected_hardlink_path(self):
        self.package('module app;pub fn main()->Int{0}')
        os.link(self.root / 'src/main.eld', self.root / 'src/alias.eld')
        self.assertEqual(self.cli('fmt').returncode, 0)
        self.assertEqual(self.cli('fmt', '--check').returncode, 0)
