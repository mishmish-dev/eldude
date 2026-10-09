"""Library bodies and cell contracts go through the source pipeline."""
from pathlib import Path
import unittest

from eldude.core.handlers import run
from eldude.core.inference import Fn, Ty, capture_free
from eldude.core.rows import Row
from eldude.source.pipeline import compile_source
from eldude.source.elaboration import SourceElaborator
from eldude.source.modules import load_modules
from eldude.source.syntax import Diagnostic, parse_source

ROOT = Path(__file__).resolve().parents[2]


class LibraryBodyTests(unittest.TestCase):
    def test_imported_callable_fixed_result_dependency_is_not_capture_free(self):
        signature = Fn((), Ty('Any:Read'), Row(), bound=frozenset({'outer'}), captures=frozenset())
        self.assertFalse(capture_free(Fn.loads(signature.dumps())))

    def test_bundled_set_body_is_checked_and_executed(self):
        ast = parse_source('''module m; import state::ref::{Ref};
pub fn main()->Int {region r {let cell:Ref<Int,@r> = Ref::new(0); cell.set(42); cell.get()}}''')
        for body, expected in (('();', 0), ('false', None)):
            graph = load_modules(ast)
            original = graph.modules['state::ref']
            path = Path(original.span.filename)
            changed = parse_source(path.read_text().replace('self.replace(value);', body), str(path))
            graph.modules['state::ref'] = changed
            graph.exports['state::ref']['Ref'] = next(d for d in changed.items[1] if d.kind == 'struct')
            with self.subTest(body=body):
                if expected is None:
                    with self.assertRaises(Diagnostic) as caught:
                        SourceElaborator(ast, graph).compile()
                    self.assertEqual(caught.exception.span.filename, str(path))
                    self.assertEqual(caught.exception.code, 'type')
                else:
                    self.assertEqual(run(SourceElaborator(ast, graph).compile().program).value, expected)

    def test_capture_free_cell(self):
        for name in ('capture_free_cell', 'capture_free_erasure'):
            path = ROOT / 'examples/src/05_state_and_collections' / (name + '.eld')
            with self.subTest(name=name):
                checked = compile_source(path.read_text(), str(path))
                self.assertEqual(run(checked.program).value, 42)
                for signature in checked.functions.values():
                    imported = Fn.loads(signature.dumps())
                    self.assertEqual(imported.dumps(), signature.dumps())
                    if imported.effects.tail and imported.effect_vars:
                        self.assertIn(imported.effects.tail, imported.effect_vars)

    def test_library_combinators(self):
        for name in ('library_combinators', 'library_owned_combinators'):
            path = ROOT / 'examples/src/03_results' / (name + '.eld')
            with self.subTest(name=name):
                execution = run(compile_source(path.read_text(), str(path)).program)
                self.assertEqual(execution.value, 42)
                if name == 'library_owned_combinators':
                    self.assertEqual([e[1] for e in execution.events if e[0] == 'close'], [1, 2, 3])

    def test_library_callback_contracts(self):
        for name, message in (('map_escape', 'region would escape'),
                              ('map_linear_callback', 'discardable')):
            path = ROOT / 'examples/reject/semantics' / ('library_' + name + '.eld')
            with self.subTest(name=name):
                with self.assertRaises(Diagnostic) as caught:
                    compile_source(path.read_text(), str(path))
                self.assertIn(message, caught.exception.message)
                self.assertEqual(caught.exception.span.filename, str(path))

    def test_task_helpers_own_and_clean_captures(self):
        for name in ('resources', 'cancel'):
            path = ROOT / 'examples/src/06_tasks' / ('library_' + name + '.eld')
            with self.subTest(name=name):
                checked = compile_source(path.read_text(), str(path))
                execution = run(checked.program)
                self.assertEqual(execution.value, 42)
                self.assertEqual(sorted(e[1] for e in execution.events if e[0] == 'close'), [1, 2])

    def test_cell_restriction_depends_on_type(self):
        for name in ('nested_cell', 'empty_list', 'generic', 'fixed_region', 'erased',
                     'forged_erasure', 'enum_alternative', 'spoof', 'missing_discard'):
            path = ROOT / 'examples/reject/semantics' / ('capture_free_' + name + '.eld')
            with self.subTest(name=name):
                with self.assertRaises(Diagnostic) as caught:
                    compile_source(path.read_text(), str(path))
                self.assertIn('discardable' if name == 'missing_discard' else 'CaptureFree', caught.exception.message)
                self.assertEqual(caught.exception.span.filename, str(path))

    def test_unknown_cell_region_is_a_diagnostic(self):
        path = ROOT / 'examples/reject/semantics/capture_free_unknown_region.eld'
        with self.assertRaises(Diagnostic) as caught:
            compile_source(path.read_text(), str(path))
        self.assertEqual(caught.exception.code, 'name')
        self.assertIn('Unknown region', caught.exception.message)
