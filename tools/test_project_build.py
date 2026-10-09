"""Built Python artifacts execute checked IR, independently of source files."""
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from handlers import run
from source_pipeline import compile_file

ROOT = Path(__file__).resolve().parents[1]


class ProjectBuildTests(unittest.TestCase):
    def test_module_artifacts_keep_module_and_package_identities(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'src').mkdir()
            (root / 'src/one.eld').write_text('module a::b;')
            (root / 'src/two.eld').write_text('module a_b;')
            (root / 'src/three.eld').write_text('module Demo;')
            (root / 'src/four.eld').write_text('module demo;')
            child = root / 'child'
            (child / 'src').mkdir(parents=True)
            (child / 'src/child.eld').write_text('module child;')
            (child / 'eldude.toml').write_text('manifest-version=1\n[package]\nname="child"\nversion="0.1.0"')
            (root / 'eldude.toml').write_text('manifest-version=1\n[package]\nname="a_root"\nversion="0.1.0"\n'
                                            '[workspace]\nmembers=["child"]')
            result = subprocess.run([sys.executable, str(ROOT / 'eldude'), 'build', '--message-format=json'],
                                    cwd=root, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            artifacts = [json.loads(line) for line in result.stdout.splitlines() if json.loads(line)['kind'] == 'artifact']
            self.assertEqual(len({Path(a['path']).stat().st_ino for a in artifacts}), 5)
            self.assertEqual(sorted(a['package'] for a in artifacts), ['a_root'] * 4 + ['child'])

    def test_artifacts_are_reproducible_across_project_locations(self):
        with TemporaryDirectory() as directory:
            outputs = []
            for name in ('first', 'second'):
                root = Path(directory) / name
                (root / 'src').mkdir(parents=True)
                (root / 'src/main.eld').write_text('module app; pub fn main()->Int { 0 }')
                (root / 'eldude.toml').write_text('manifest-version=1\n[package]\nname="app"\nversion="0.1.0"\n'
                    '[[app]]\nname="app"\nentry="app::main"\nhost="python::experimental"')
                result = subprocess.run([sys.executable, str(ROOT / 'eldude'), 'build', '--message-format=json'],
                                        cwd=root, text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                artifact = next(json.loads(line)['path'] for line in result.stdout.splitlines()
                                if json.loads(line)['kind'] == 'artifact' and json.loads(line)['artifact_kind'] == 'application')
                outputs.append(Path(artifact).read_bytes())
            self.assertEqual(outputs[0], outputs[1])

    def test_ir_roundtrip_preserves_results_events_and_origins(self):
        from ir_artifact import encode_program, decode_program
        manifest = json.loads((ROOT / 'examples/manifest.json').read_text())
        for name, expected in manifest['runnable'].items():
            with self.subTest(name=name):
                checked = compile_file(ROOT / 'examples' / name).program
                wire = encode_program(checked)
                restored = decode_program(json.loads(json.dumps(wire, sort_keys=True)))
                actual, original = run(restored), run(checked)
                self.assertEqual(actual.value, expected)
                self.assertEqual(actual.events, original.events)
                self.assertTrue(restored.origins)

    def test_build_run_profiles_isolation_and_failed_rebuild(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'src').mkdir()
            source = root / 'src/main.eld'
            source.write_text('module app; pub fn start()->Int { 7 } pub fn tests()->Int { 0 }')
            (root / 'eldude.toml').write_text('manifest-version=1\n[package]\nname="app"\nversion="0.1.0"\n'
                '[[app]]\nname="app"\nentry="app::start"\nhost="python::experimental"\n'
                '[[test]]\nname="unit"\nentry="app::tests"\nhost="python::experimental"\n')
            def cli(*args):
                return subprocess.run([sys.executable, str(ROOT / 'eldude'), *args], cwd=root, text=True, capture_output=True)
            built = cli('build', '--message-format=json')
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            artifact = next(json.loads(line)['path'] for line in built.stdout.splitlines()
                            if json.loads(line)['kind'] == 'artifact' and json.loads(line)['artifact_kind'] == 'application')
            self.assertEqual(cli('run').returncode, 7)
            self.assertEqual(cli('run', '--release').returncode, 7)
            self.assertEqual(cli('test').returncode, 0)
            source.write_text('module app; pub fn start()->Int { true }')
            self.assertEqual(cli('run').returncode, 1)
            # The old artifact remains a complete snapshot, but run never launches it after the failed rebuild.
            result = subprocess.run([sys.executable, artifact], cwd=root, capture_output=True)
            self.assertEqual(result.returncode, 7, result.stderr)

    def test_failing_runner_and_out_of_range_exit_are_reported(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'src').mkdir()
            (root / 'src/main.eld').write_text('module app; pub fn main()->Int { 256 }')
            (root / 'eldude.toml').write_text('manifest-version=1\n[package]\nname="app"\nversion="0.1.0"\n'
                '[[test]]\nname="unit"\nentry="app::main"\nhost="python::experimental"\n')
            result = subprocess.run([sys.executable, str(ROOT / 'eldude'), 'test', '--message-format=json'],
                                    cwd=root, text=True, capture_output=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            events = [json.loads(line) for line in result.stdout.splitlines()]
            self.assertTrue(any(e['kind'] == 'output' and 'exit' in e['text'] for e in events))
            self.assertEqual(events[-1]['failed'], 1)
