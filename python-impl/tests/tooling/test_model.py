"""Project selection and validation against real temporary manifests."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from eldude.source.syntax import Diagnostic


class ProjectModelTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()

    def package(self, name='app', parent=None, extra=''):
        root = (parent or self.root) / name
        (root / 'src').mkdir(parents=True, exist_ok=True)
        (root / 'eldude.toml').write_text(
            f'manifest-version = 1\n[package]\nname = "{name}"\nversion = "0.1.0"\n' + extra)
        return root

    def test_workspace_root_member_and_explicit_selection(self):
        from eldude.tooling.model import select_project
        a, b = self.package('a'), self.package('b')
        (self.root / 'eldude.toml').write_text('manifest-version = 1\n[workspace]\nmembers = ["a", "b"]\n')
        self.assertEqual([p.name for p in select_project(self.root).packages], ['a', 'b'])
        selected = select_project(a / 'src')
        self.assertEqual([p.name for p in selected.packages], ['a'])
        self.assertEqual(selected.root, self.root)
        self.assertEqual([p.name for p in select_project(a, workspace=True).packages], ['a', 'b'])
        self.assertEqual(select_project(b, package='a').packages[0].path.parent, a)

    def test_unknown_fields_bad_versions_missing_hosts_and_roots_have_locations(self):
        from eldude.tooling.model import read_manifest
        cases = [('[toolchain]\nversoin = "0.1.0"', 'versoin'),
                 ('[[app]]\nname="app"\nentry="app::main"', 'host'),
                 ('[dependencies]\nfoo={path="../foo",git="https://example.invalid"}', 'source'),
                 ('[toolchain]\nversion="1.2"', 'version')]
        for extra, message in cases:
            path = self.package(extra=extra) / 'eldude.toml'
            with self.subTest(extra=extra), self.assertRaisesRegex(Diagnostic, message) as caught:
                read_manifest(path)
            self.assertEqual(caught.exception.code, 'configuration')
            self.assertEqual(caught.exception.span.filename, str(path))
        path.write_text('manifest-version=1\n[package]\nname="app"\nversion="0.1.0"\nsource-dir="../"')
        with self.assertRaisesRegex(Diagnostic, 'source-dir'):
            read_manifest(path)

    def test_second_target_validation_points_to_its_own_field(self):
        from eldude.tooling.model import read_manifest
        for kind in ('app', 'test', 'embed'):
            entries = 'exports=["app::main"]' if kind == 'embed' else 'entry="app::main"'
            for invalid, line in (('host="invalid"', 12), ('typo="bad"', 12),
                                  ('name="same"', 10), ('', 9)):
                name = 'same' if invalid.startswith('name=') else 'second'
                second = f'name="{name}"\n{entries}\n' + (invalid if not invalid.startswith('name=') else 'host="python::experimental"')
                root = self.package(extra=(
                    f'[[{kind}]]\nname="same"\n{entries}\nhost="python::experimental"\n'
                    f'[[{kind}]]\n{second}\n'))
                with self.subTest(kind=kind, invalid=invalid):
                    with self.assertRaises(Diagnostic) as caught:
                        read_manifest(root / 'eldude.toml')
                    self.assertEqual(caught.exception.span.line, line)

    def test_apps_inherit_package_host_and_can_override_it(self):
        from eldude.tooling.model import read_manifest
        root = self.package(extra=(
            'host="python::experimental"\n'
            '[[app]]\nname="inherited"\nentry="app::main"\n'
            '[[app]]\nname="override"\nentry="app::main"\nhost="cli::standard"\n'))
        manifest = read_manifest(root / 'eldude.toml')
        self.assertEqual([target['host'] for target in manifest.data['app']],
                         ['python::experimental', 'cli::standard'])

    def test_invalid_package_and_app_hosts_have_locations(self):
        from eldude.tooling.model import read_manifest
        for value in ('"invalid"', '""', '42'):
            for package_host in (True, False):
                extra = (f'host={value}\n' if package_host else
                         'host="python::experimental"\n[[app]]\nname="app"\n'
                         f'entry="app::main"\nhost={value}\n')
                root = self.package(extra=extra)
                with self.subTest(value=value, package_host=package_host):
                    with self.assertRaisesRegex(Diagnostic, 'invalid string value') as caught:
                        read_manifest(root / 'eldude.toml')
                    self.assertEqual(caught.exception.code, 'configuration')
                    self.assertEqual(caught.exception.span.line, 5 if package_host else 9)

    def test_tests_and_embeddings_still_require_their_own_host(self):
        from eldude.tooling.model import read_manifest
        for kind, entries in (('test', 'entry="app::main"'),
                              ('embed', 'exports=["app::main"]')):
            root = self.package(extra=(
                f'host="python::experimental"\n[[{kind}]]\nname="runner"\n{entries}\n'))
            with self.subTest(kind=kind), self.assertRaisesRegex(Diagnostic, 'missing required field host'):
                read_manifest(root / 'eldude.toml')

    def test_discovery_excludes_nested_packages_builds_and_symlink_directories(self):
        from eldude.tooling.model import read_manifest, source_files
        root = self.package()
        (root / 'src' / 'one.eld').write_text('module one;')
        nested = self.package('nested', root / 'src')
        (nested / 'src' / 'two.eld').write_text('module two;')
        (root / 'src' / 'linked').symlink_to(nested / 'src', target_is_directory=True)
        (root / 'src' / 'build').mkdir()
        (root / 'src' / 'build' / 'generated.eld').write_text('module generated;')
        self.assertEqual(source_files(read_manifest(root / 'eldude.toml')), [root / 'src' / 'one.eld'])

    def test_versions_use_semantic_order_and_explicit_prerelease_constraints(self):
        from eldude.tooling.model import satisfies
        cases = [('0.10.0', '>=0.2.0, <1.0.0', True),
                 ('1.0.0-alpha.2', '<1.0.0', False),
                 ('1.0.0-alpha.2', '>=1.0.0-alpha.1, <1.0.0', True),
                 ('1.0.0-alpha.10', '>1.0.0-alpha.2', True),
                 ('1.0.0+build', '1.0.0', True)]
        for version, constraint, wanted in cases:
            with self.subTest(version=version, constraint=constraint):
                self.assertEqual(satisfies(version, constraint), wanted)

    def test_member_cannot_override_workspace_pin(self):
        from eldude.tooling.model import select_project
        a = self.package('a', extra='[toolchain]\nversion="0.1.0"')
        (self.root / 'eldude.toml').write_text('manifest-version=1\n[workspace]\nmembers=["a"]')
        with self.assertRaisesRegex(Diagnostic, 'toolchain'):
            select_project(a)

    def test_manifest_diagnostic_points_to_the_responsible_table(self):
        from eldude.tooling.model import read_manifest
        root = self.package(extra='[toolchain]\nversion="not-a-version"\n')
        with self.assertRaises(Diagnostic) as caught:
            read_manifest(root / 'eldude.toml')
        self.assertEqual(caught.exception.span.line, 6)

    def test_nested_workspace_cannot_hide_its_ownership_from_a_member(self):
        from eldude.tooling.model import select_project
        inner = self.root / 'inner'
        child = self.package('child', inner)
        (inner / 'eldude.toml').write_text('manifest-version=1\n[workspace]\nmembers=["child"]')
        (self.root / 'eldude.toml').write_text('manifest-version=1\n[workspace]\nmembers=["inner"]')
        with self.assertRaisesRegex(Diagnostic, 'nested workspace'):
            select_project(child)

    def test_two_workspaces_cannot_own_the_same_package(self):
        from eldude.tooling.model import select_project
        inner = self.root / 'inner'
        child = self.package('child', inner)
        (inner / 'eldude.toml').write_text('manifest-version=1\n[workspace]\nmembers=["child"]')
        (self.root / 'eldude.toml').write_text('manifest-version=1\n[workspace]\nmembers=["inner/child"]')
        for start in (self.root, child):
            with self.subTest(start=start), self.assertRaisesRegex(Diagnostic, 'workspace'):
                select_project(start)

    def test_workspace_manifest_symlink_cannot_redirect_to_another_package(self):
        from eldude.tooling.model import select_project
        outside = self.package('outside')
        workspace = self.root / 'workspace'
        (workspace / 'member').mkdir(parents=True)
        (workspace / 'member/eldude.toml').symlink_to(outside / 'eldude.toml')
        (workspace / 'eldude.toml').write_text('manifest-version=1\n[workspace]\nmembers=["member"]')
        with self.assertRaisesRegex(Diagnostic, 'workspace'):
            select_project(workspace)
