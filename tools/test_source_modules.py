"""Module identity, visibility, and startup dependency ordering."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from source_syntax import Diagnostic, parse_source


class SourceModuleTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name).resolve()

    def write(self, name, source):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding='utf-8')
        return path

    def load(self, source, roots=()):
        from source_modules import load_modules
        ast = parse_source(source, str(self.root / 'main.eld'))
        graph = load_modules(ast, roots)
        self.assertIs(graph.modules[ast.items[0].items[0]], ast)
        return graph

    def test_discovers_declared_identity_and_only_parses_dependencies(self):
        self.write('arbitrary/path.eld', '// header\nmodule math /* gap */ :: value;\npub fn answer()->Int { 42 }')
        self.write('unrelated.eld', 'module unused; fn broken(')
        self.write('bad_lexing.eld', 'module unused_lex; $')
        graph = self.load('module app; import math::value::{answer as value}; fn main()->Int { value() }')
        self.assertEqual(graph.order, ('math::value', 'app'))
        self.assertEqual(set(graph.modules), {'math::value', 'app'})
        self.assertEqual(set(graph.exports['math::value']), {'answer'})

    def test_explicit_roots_and_overlapping_roots(self):
        with TemporaryDirectory() as directory:
            library = Path(directory)
            (library / 'other.eld').write_text('module lib; pub fn value()->Int { 1 }', encoding='utf-8')
            graph = self.load('module app; import lib::{value};', (library, self.root, library))
            self.assertEqual(graph.order, ('lib', 'app'))

    def test_missing_and_private_names_report_the_import_location(self):
        self.write('lib.eld', 'module lib; fn secret()->Int { 1 }')
        for imported, name, code in (('absent', 'x', 'module'), ('lib', 'missing', 'name'), ('lib', 'secret', 'visibility')):
            with self.subTest(code=code), self.assertRaises(Diagnostic) as caught:
                self.load(f'module app;\nimport {imported}::{{{name}}};')
            error = caught.exception
            self.assertEqual(error.code, code)
            self.assertEqual(error.span.filename, str(self.root / 'main.eld'))
            self.assertEqual(error.span.line, 2)
            self.assertIn(imported if code == 'module' else name, error.message)

    def test_duplicate_identity_points_to_both_source_files(self):
        first = self.write('one.eld', 'module lib; pub fn value()->Int { 1 }')
        second = self.write('two.eld', 'module lib; pub fn value()->Int { 2 }')
        with self.assertRaises(Diagnostic) as caught:
            self.load('module app; import lib::{value};')
        self.assertEqual(caught.exception.code, 'module')
        self.assertIn(str(first), str(caught.exception))
        self.assertIn(str(second), str(caught.exception))

    def test_dependency_syntax_error_keeps_dependency_location(self):
        path = self.write('bad.eld', 'module lib;\npub fn value()->Int { $ }')
        with self.assertRaises(Diagnostic) as caught:
            self.load('module app; import lib::{value};')
        self.assertEqual(caught.exception.code, 'syntax')
        self.assertEqual(caught.exception.span.filename, str(path))
        self.assertEqual(caught.exception.span.line, 2)

    def test_reexports_preserve_defining_declaration_and_alias(self):
        self.write('base.eld', 'module base; pub fn value()->Int { 7 }')
        self.write('facade.eld', 'module facade; pub import base::{value as answer};')
        graph = self.load('module app; import facade::{answer};')
        self.assertEqual(graph.order, ('base', 'facade', 'app'))
        self.assertIs(graph.exports['facade']['answer'], graph.exports['base']['value'])

    def test_cycles_are_lexically_ordered_after_dependencies(self):
        self.write('a.eld', 'module a; import z::{z}; import b::{b}; pub fn a()->Int { 1 }')
        self.write('b.eld', 'module b; import a::{a}; pub fn b()->Int { 2 }')
        self.write('z.eld', 'module z; pub fn z()->Int { 3 }')
        graph = self.load('module app; import b::{b};')
        self.assertEqual(graph.order, ('z', 'a', 'b', 'app'))
        self.assertEqual(graph.dependencies['b'], ('a',))

    def test_newly_ready_component_competes_in_lexical_order(self):
        self.write('a.eld', 'module a; import b::{b}; pub fn a()->Int { 1 }')
        self.write('b.eld', 'module b; pub fn b()->Int { 2 }')
        self.write('z.eld', 'module z; pub fn z()->Int { 3 }')
        graph = self.load('module app; import z::{z}; import a::{a};')
        self.assertEqual(graph.order, ('b', 'a', 'z', 'app'))

    def test_host_fixture_imports_do_not_require_a_source_file(self):
        graph = self.load('module app; import eldude::fixture::{emit};')
        self.assertEqual(graph.order, ('app',))
        self.assertEqual(graph.dependencies['app'], ())

    def test_bundled_stdlib_is_available_to_an_external_root(self):
        graph = self.load('module app; import core::option::{Option};')
        self.assertEqual(graph.order, ('core::option', 'app'))
        self.assertEqual(graph.exports['core::option']['Option'].kind, 'enum')

    def test_public_top_level_values_are_exported(self):
        self.write('values.eld', 'module values; pub let answer = 42; let hidden = 1;')
        graph = self.load('module app; import values::{answer};')
        self.assertEqual(set(graph.exports['values']), {'answer'})

    def test_public_type_aliases_are_exported(self):
        self.write('types.eld', 'module types; pub type Number = Int;')
        graph = self.load('module app; import types::{Number};')
        self.assertEqual(graph.exports['types']['Number'].kind, 'type_alias')

    def test_cyclic_reexports_resolve_to_a_real_definition(self):
        self.write('a.eld', 'module a; pub import b::{answer}; pub fn value()->Int { 7 }')
        self.write('b.eld', 'module b; pub import a::{value as answer};')
        graph = self.load('module app; import a::{answer};')
        self.assertIs(graph.exports['a']['answer'], graph.exports['a']['value'])
        self.assertEqual(graph.order, ('a', 'b', 'app'))


if __name__ == '__main__':
    unittest.main()
