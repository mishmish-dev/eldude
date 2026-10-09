"""Project selection and validation against real temporary manifests."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from source_syntax import Diagnostic


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
        from project_model import select_project
        a, b = self.package('a'), self.package('b')
        (self.root / 'eldude.toml').write_text('manifest-version = 1\n[workspace]\nmembers = ["a", "b"]\n')
        self.assertEqual([p.name for p in select_project(self.root).packages], ['a', 'b'])
        selected = select_project(a / 'src')
        self.assertEqual([p.name for p in selected.packages], ['a'])
        self.assertEqual(selected.root, self.root)
        self.assertEqual([p.name for p in select_project(a, workspace=True).packages], ['a', 'b'])
        self.assertEqual(select_project(b, package='a').packages[0].path.parent, a)

    def test_unknown_fields_bad_versions_missing_hosts_and_roots_have_locations(self):
        from project_model import read_manifest
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

    def test_discovery_excludes_nested_packages_builds_and_symlink_directories(self):
        from project_model import read_manifest, source_files
        root = self.package()
        (root / 'src' / 'one.eld').write_text('module one;')
        nested = self.package('nested', root / 'src')
        (nested / 'src' / 'two.eld').write_text('module two;')
        (root / 'src' / 'linked').symlink_to(nested / 'src', target_is_directory=True)
        (root / 'src' / 'build').mkdir()
        (root / 'src' / 'build' / 'generated.eld').write_text('module generated;')
        self.assertEqual(source_files(read_manifest(root / 'eldude.toml')), [root / 'src' / 'one.eld'])

    def test_versions_use_semantic_order_and_explicit_prerelease_constraints(self):
        from project_model import satisfies
        cases = [('0.10.0', '>=0.2.0, <1.0.0', True),
                 ('1.0.0-alpha.2', '<1.0.0', False),
                 ('1.0.0-alpha.2', '>=1.0.0-alpha.1, <1.0.0', True),
                 ('1.0.0-alpha.10', '>1.0.0-alpha.2', True),
                 ('1.0.0+build', '1.0.0', True)]
        for version, constraint, wanted in cases:
            with self.subTest(version=version, constraint=constraint):
                self.assertEqual(satisfies(version, constraint), wanted)

    def test_member_cannot_override_workspace_pin(self):
        from project_model import select_project
        a = self.package('a', extra='[toolchain]\nversion="0.1.0"')
        (self.root / 'eldude.toml').write_text('manifest-version=1\n[workspace]\nmembers=["a"]')
        with self.assertRaisesRegex(Diagnostic, 'toolchain'):
            select_project(a)

    def test_manifest_diagnostic_points_to_the_responsible_table(self):
        from project_model import read_manifest
        root = self.package(extra='[toolchain]\nversion="not-a-version"\n')
        with self.assertRaises(Diagnostic) as caught:
            read_manifest(root / 'eldude.toml')
        self.assertEqual(caught.exception.span.line, 6)

    def test_nested_workspace_cannot_hide_its_ownership_from_a_member(self):
        from project_model import select_project
        inner = self.root / 'inner'
        child = self.package('child', inner)
        (inner / 'eldude.toml').write_text('manifest-version=1\n[workspace]\nmembers=["child"]')
        (self.root / 'eldude.toml').write_text('manifest-version=1\n[workspace]\nmembers=["inner"]')
        with self.assertRaisesRegex(Diagnostic, 'nested workspace'):
            select_project(child)

    def test_two_workspaces_cannot_own_the_same_package(self):
        from project_model import select_project
        inner = self.root / 'inner'
        child = self.package('child', inner)
        (inner / 'eldude.toml').write_text('manifest-version=1\n[workspace]\nmembers=["child"]')
        (self.root / 'eldude.toml').write_text('manifest-version=1\n[workspace]\nmembers=["inner/child"]')
        for start in (self.root, child):
            with self.subTest(start=start), self.assertRaisesRegex(Diagnostic, 'workspace'):
                select_project(start)

    def test_workspace_manifest_symlink_cannot_redirect_to_another_package(self):
        from project_model import select_project
        outside = self.package('outside')
        workspace = self.root / 'workspace'
        (workspace / 'member').mkdir(parents=True)
        (workspace / 'member/eldude.toml').symlink_to(outside / 'eldude.toml')
        (workspace / 'eldude.toml').write_text('manifest-version=1\n[workspace]\nmembers=["member"]')
        with self.assertRaisesRegex(Diagnostic, 'workspace'):
            select_project(workspace)
