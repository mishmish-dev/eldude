"""Path graphs, lock ownership, and package-scoped source imports."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from eldude.source_syntax import Diagnostic


class ProjectResolverTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()

    def package(self, name, dependencies='', source=None):
        root = self.root / name
        (root / 'src').mkdir(parents=True, exist_ok=True)
        (root / 'eldude.toml').write_text(
            f'manifest-version=1\n[package]\nname="{name}"\nversion="0.1.0"\n' + dependencies)
        (root / 'src' / 'code.eld').write_text(source or f'module {name}; pub fn value()->Int {{ 42 }}')
        return root

    def test_lock_is_deterministic_and_locked_refuses_stale_requirements(self):
        from eldude.project_model import select_project
        from eldude.project_resolver import resolve, reconcile_lock
        self.package('lib')
        app = self.package('app', '[dependencies]\nlib={path="../lib"}')
        graph = resolve(select_project(app))
        with self.assertRaisesRegex(Diagnostic, 'lock'):
            reconcile_lock(graph, locked=True)
        self.assertTrue(reconcile_lock(graph))
        lock = app / 'eldude.lock'
        original, stamp = lock.read_bytes(), lock.stat().st_mtime_ns
        self.assertFalse(reconcile_lock(resolve(select_project(app)), locked=True))
        self.assertEqual((lock.read_bytes(), lock.stat().st_mtime_ns), (original, stamp))
        manifest = app / 'eldude.toml'
        manifest.write_text(manifest.read_text().replace('path="../lib"', 'path="../lib", version=">=0.1.0"'))
        with self.assertRaisesRegex(Diagnostic, 'stale'):
            reconcile_lock(resolve(select_project(app)), locked=True)
        self.assertEqual(lock.read_bytes(), original)

    def test_dependency_uses_own_environment_but_transitive_import_is_rejected(self):
        from eldude.project_model import select_project
        from eldude.project_resolver import resolve, module_sources
        from eldude.source_pipeline import check_file
        self.package('base')
        self.package('lib', '[dependencies]\nbase={path="../base"}',
                     'module lib; import base::{value}; pub fn answer()->Int { value() }')
        app = self.package('app', '[dependencies]\nlib={path="../lib"}',
                           'module app; import lib::{answer}; pub fn value()->Int { answer() }')
        graph = resolve(select_project(app))
        sources, allowed = module_sources(graph, graph.selection.packages)
        check_file(app / 'src/code.eld', sources=sources, import_allowed=allowed)
        (app / 'src/code.eld').write_text('module app; import base::{value};')
        with self.assertRaisesRegex(Diagnostic, 'direct dependency'):
            check_file(app / 'src/code.eld', sources=sources, import_allowed=allowed)

    def test_test_dependencies_do_not_leak_into_production(self):
        from eldude.project_model import select_project
        from eldude.project_resolver import resolve, module_sources
        from eldude.source_pipeline import check_file
        self.package('helper')
        app = self.package('app', '[dev-dependencies]\nhelper={path="../helper"}',
                           'module app; import helper::{value};')
        (app / 'tests').mkdir()
        test = app / 'tests/test.eld'
        test.write_text('module suite; import helper::{value}; pub fn main()->Int { value() }')
        graph = resolve(select_project(app))
        sources, allowed = module_sources(graph, graph.selection.packages, tests=True)
        check_file(test, sources=sources, import_allowed=allowed)
        with self.assertRaisesRegex(Diagnostic, 'direct dependency'):
            check_file(app / 'src/code.eld', sources=sources, import_allowed=allowed)

    def test_cycles_and_name_mismatches_fail_before_lock_publication(self):
        from eldude.project_model import select_project
        from eldude.project_resolver import resolve
        a = self.package('a', '[dependencies]\nb={path="../b"}')
        self.package('b', '[dependencies]\na={path="../a"}')
        with self.assertRaisesRegex(Diagnostic, 'cycle'):
            resolve(select_project(a))
        (a / 'eldude.toml').write_text((a / 'eldude.toml').read_text().replace('b={', 'wrong={'))
        with self.assertRaisesRegex(Diagnostic, 'name'):
            resolve(select_project(a))
        self.assertFalse((a / 'eldude.lock').exists())

    def test_remote_sources_remain_explicitly_unsupported(self):
        from eldude.project_model import select_project
        from eldude.project_resolver import resolve
        app = self.package('app', '[dependencies]\nremote={version="1.0.0",registry="https://example.invalid"}')
        with self.assertRaises(Diagnostic) as caught:
            resolve(select_project(app))
        self.assertEqual(caught.exception.code, 'unsupported')
        graph = resolve(select_project(app), inspect=True)
        self.assertEqual(len(graph.unresolved), 1)
        self.assertFalse((app / 'eldude.lock').exists())

    def test_source_file_links_cannot_import_tests_or_nested_packages(self):
        from eldude.project_model import select_project
        from eldude.project_resolver import resolve, module_sources
        app = self.package('app')
        (app / 'tests').mkdir()
        (app / 'tests/helper.eld').write_text('module helper;')
        link = app / 'src/link.eld'
        link.symlink_to(app / 'tests/helper.eld')
        graph = resolve(select_project(app))
        with self.assertRaisesRegex(Diagnostic, 'source'):
            module_sources(graph, graph.selection.packages)
        link.unlink()
        (app / 'src/nested').mkdir()
        (app / 'src/nested/eldude.toml').write_text('manifest-version=1\n[package]\nname="nested"\nversion="0.1.0"')
        (app / 'src/nested/helper.eld').write_text('module helper;')
        link.symlink_to(app / 'src/nested/helper.eld')
        with self.assertRaisesRegex(Diagnostic, 'nested package'):
            module_sources(graph, graph.selection.packages)
