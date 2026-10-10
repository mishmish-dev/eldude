"""Handler acceptance/rejection corpus, source origins, and cleanup traces."""
from pathlib import Path
import unittest

from eldude.core.rows import Row
from eldude.core.inference import INT, UNIT
from eldude.core.handlers import Defect, run
from eldude.source.syntax import Diagnostic

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / 'eldude-program-examples/src/07_source_pipeline'
REJECT = ROOT / 'eldude-program-examples/reject/semantics/source_pipeline'
MULTI_REJECT = ROOT / 'eldude-program-examples/reject/semantics/multi_operations'
MULTI_FAILURES = {
    'incomplete': ('semantic', 'Incomplete handler.*stop'),
    'duplicate_declaration': ('name', 'Duplicate operation declaration'),
    'duplicate_clause': ('name', 'Duplicate handler operation'),
    'duplicate_forward': ('name', 'Duplicate handler operation'),
    'duplicate_fallback': ('name', 'Duplicate forwarding clause'),
    'unknown_clause': ('name', 'Unknown handler operation'),
    'unknown_forward': ('name', 'Unknown handler operation'),
    'unknown_call': ('name', 'Unknown operation'),
    'call_arity': ('type', 'Operation arity'),
    'clause_arity': ('type', 'Operation clause arity'),
    'argument_type': ('type', 'Type mismatch'),
    'tail_result': ('semantic', 'operation result'),
    'once_result': ('semantic', 'operation result'),
    'affine_result': ('semantic', 'handler output'),
    'same_family_sibling': ('semantic', 'unqualified same-family'),
    'tail_resume': ('semantic', 'Explicit resume.*tail'),
    'missing_resume': ('semantic', 'once clause must resume exactly once'),
    'repeated_resume': ('semantic', 'more than once'),
    'escaping_resume': ('semantic', 'resume.*only inside an operation clause'),
    'frame_transfer': ('semantic', 'frame was already consumed'),
    'clause_local': ('semantic', 'Unconsumed resource local'),
    'unsafe_affine': ('semantic', 'abandon live resource file'),
    'skipped_consumption': ('semantic', 'skip consumption of outside'),
    'skipped_enclosing_resume': ('semantic', 'skip an enclosing resume'),
    'post_resume_outward': ('semantic', 'abandon live resource outside'),
    'opaque_affine_family': ('semantic', 'abandon live resource file'),
    'argument_effect': ('effect', 'exceeds its declared effect row'),
    'argument_abandonment': ('semantic', 'abandon live resource file'),
    'sibling_residual': ('semantic', 'abandon live resource local'),
}

class SourceFixtureTests(unittest.TestCase):
    def test_cleanup_defects_preserve_primary_and_discharge_outer_owners(self):
        from eldude.source.pipeline import compile_file
        from eldude.source.syntax import grammar
        for name in ('cleanup_abandon', 'cleanup_primary'):
            path = ROOT / 'eldude-program-examples/reject/runtime' / (name + '.eld')
            with self.subTest(name=name):
                self.assertTrue(grammar().accepts(path.read_text()))
                with self.assertRaisesRegex(Defect, 'division or remainder by zero') as caught:
                    run(compile_file(path).program)
                self.assertEqual(caught.exception.events[-1], ('close', 1, 'cleanup'))
                self.assertEqual(caught.exception.__notes__,
                                 ['Suppressed cleanup defect: Defect: Integer arithmetic overflow'] *
                                 (4 if name == 'cleanup_primary' else 1))

    def fixture(self, name):
        from eldude.source.pipeline import compile_file
        return compile_file(FIXTURES / (name + '.eld'))

    def test_multi_operations_dispatch_cleanup_and_complete_residual(self):
        from eldude.source.syntax import grammar
        self.assertTrue(grammar().accepts((FIXTURES / 'multi_operations.eld').read_text()))
        checked = self.fixture('multi_operations')
        self.assertEqual((checked.inferred.type, checked.inferred.effects), (INT, Row()))
        self.assertEqual(len(checked.handled_rows['inner'].labels), 1)
        self.assertIn('outer', checked.handled_rows['inner'].labels[0])
        result = run(checked.program)
        self.assertEqual(result.value, 42)
        self.assertEqual(result.events, (
            ('acquire', 'File', 1), ('dispatch', 'Multi', 'inner', 'step'),
            ('resume', 'inner', None), ('dispatch', 'Multi', 'inner', 'read'),
            ('dispatch', 'Multi', 'outer', 'read'), ('acquire', 'File', 2),
            ('close', 2, 'cleanup'), ('resume', 'outer', 42), ('resume', 'inner', 42),
            ('close', 1, 'cleanup')))

    def test_named_dispatch_and_generated_forwarding_keep_source_origins(self):
        checked = self.fixture('multi_operations')
        text = (FIXTURES / 'multi_operations.eld').read_text()
        def dispatches(term):
            if isinstance(term, tuple):
                if term and term[0] == 'dispatch':
                    yield term
                for part in term:
                    yield from dispatches(part)
        origins = []
        for dispatch in dispatches(checked.program.core):
            self.assertIn(id(dispatch), checked.program.origins)
            span = checked.program.origins[id(dispatch)]
            origins.append(text[span.start:span.end])
        self.assertCountEqual(origins, ['!Multi::step()', '!Multi::read(42)', 'forward ..;', 'forward ..;'])

    def test_multi_operation_deep_reentry_shares_one_frame_and_fresh_check_states(self):
        checked = self.fixture('multi_operations_deep')
        self.assertEqual((checked.inferred.type, checked.inferred.effects), (INT, Row()))
        self.assertEqual(len(checked.handled_rows['shared'].labels), 1)
        self.assertIn('mark', checked.handled_rows['shared'].labels[0])
        result = run(checked.program)
        self.assertEqual(result.value, 42)
        self.assertEqual(result.events, (
            ('acquire', 'File', 1), ('dispatch', 'Multi', 'shared', 'step'),
            ('resume', 'shared', None), ('dispatch', 'Multi', 'inner', 'step'),
            ('resume', 'inner', None), ('dispatch', 'Multi', 'inner', 'read'),
            ('dispatch', 'Multi', 'shared', 'read'),
            ('acquire', 'File', 2), ('dispatch', 'Mark', 'mark'), ('resume', 'mark', None),
            ('close', 2, 'cleanup'), ('resume', 'shared', 42), ('resume', 'inner', 42),
            ('close', 1, 'explicit'),
            ('acquire', 'File', 3), ('close', 3, 'cleanup')))

    def test_multi_operation_affine_forwarding_unwinds_and_preserves_outside(self):
        checked = self.fixture('multi_operations_affine')
        self.assertEqual((checked.inferred.type, checked.inferred.effects), (INT, Row()))
        result = run(checked.program)
        self.assertEqual(result.value, 7)
        self.assertEqual(result.events, (
            ('acquire', 'File', 1), ('acquire', 'File', 2),
            ('dispatch', 'Multi', 'inner', 'step'), ('resume', 'inner', None),
            ('dispatch', 'Multi', 'inner', 'stop'), ('dispatch', 'Multi', 'outer', 'stop'),
            ('abandon', 'outer'), ('abandon', 'inner'),
            ('close', 2, 'cleanup'), ('close', 1, 'explicit')))

    def test_multi_operation_rejection_fixtures_parse_and_fail_at_marked_source(self):
        from eldude.source.pipeline import compile_file
        from eldude.source.syntax import grammar
        self.assertEqual(set(MULTI_FAILURES), {p.stem for p in MULTI_REJECT.glob('*.eld')})
        for name, (code, message) in MULTI_FAILURES.items():
            path = MULTI_REJECT / (name + '.eld')
            source = path.read_text()
            with self.subTest(name=name):
                self.assertTrue(grammar().accepts(source))
                with self.assertRaises(Diagnostic) as caught:
                    compile_file(path)
                diagnostic = caught.exception
                self.assertEqual(diagnostic.code, code, str(diagnostic))
                self.assertRegex(diagnostic.message, message)
                offset = source.index('/*error*/') + len('/*error*/')
                while source[offset].isspace():
                    offset += 1
                self.assertEqual((diagnostic.span.filename, diagnostic.span.start,
                                  diagnostic.span.line, diagnostic.span.column),
                                 (str(path), offset, source.count('\n', 0, offset) + 1,
                                  offset - source.rfind('\n', 0, offset)))
                if name in ('frame_transfer', 'clause_local', 'unsafe_affine', 'skipped_consumption',
                            'post_resume_outward', 'opaque_affine_family', 'argument_abandonment',
                            'sibling_residual'):
                    self.assertTrue(diagnostic.related, str(diagnostic))
                if name == 'frame_transfer':
                    self.assertEqual([message for message, _ in diagnostic.related],
                                     ['Binding declared here', 'Ownership transferred here'])

    def test_residual_recheck_diagnostics_do_not_retain_a_later_transfer(self):
        from eldude.source.pipeline import compile_file
        with self.assertRaises(Diagnostic) as caught:
            compile_file(MULTI_REJECT / 'sibling_residual.eld')
        self.assertRegex(caught.exception.message, 'abandon live resource local')
        self.assertEqual([message for message, _ in caught.exception.related], ['Binding declared here'])

    def test_existing_literal_and_source_functions(self):
        from eldude.source.pipeline import execute_file
        self.assertEqual(execute_file(ROOT / 'eldude-program-examples/src/01_values/literal.eld').value, 42)
        self.assertEqual(run(self.fixture('functions').program).value, 42)

    def test_operation_arguments_forward_and_resume_through_source_functions(self):
        checked = self.fixture('operation_arguments')
        self.assertEqual((checked.inferred.type, checked.inferred.effects), (INT, Row()))
        self.assertEqual(checked.functions['request'].effects, Row(('Echo',)))
        result = run(checked.program)
        self.assertEqual(result.value, 42)
        self.assertEqual(result.events, (
            ('acquire', 'File', 1), ('dispatch', 'Step', 'step'),
            ('dispatch', 'Echo', 'inner'), ('dispatch', 'Echo', 'outer'),
            ('acquire', 'File', 2), ('close', 2, 'cleanup'),
            ('resume', 'outer', 7), ('resume', 'inner', 7), ('resume', 'step', 7),
            ('dispatch', 'Step', 'step'), ('dispatch', 'Echo', 'inner'),
            ('dispatch', 'Echo', 'outer'), ('acquire', 'File', 3), ('close', 3, 'cleanup'),
            ('resume', 'outer', 42), ('resume', 'inner', 42), ('resume', 'step', 42),
            ('close', 1, 'explicit'), ('acquire', 'File', 4), ('close', 4, 'cleanup'),
            ('acquire', 'File', 5), ('close', 5, 'cleanup')))

    def test_tail_cleanup_precedes_resumption(self):
        result = run(self.fixture('tail_cleanup').program)
        self.assertEqual(result.value, 40)
        self.assertEqual(result.events, (
            ('dispatch', 'Read', 'read'), ('acquire', 'File', 1),
            ('close', 1, 'cleanup'), ('resume', 'read', 40),
            ('acquire', 'File', 2), ('close', 2, 'explicit')))
        output = self.fixture('tail_output')
        self.assertEqual(output.inferred.type, UNIT)
        self.assertEqual(run(output.program).events,
                         (('dispatch', 'Read', 'read'), ('resume', 'read', 40)))

    def test_deep_once_moves_and_closes_one_frame_obligation(self):
        result = run(self.fixture('once_deep').program)
        self.assertEqual(result.value, 99)
        self.assertEqual(result.events, (
            ('acquire', 'File', 1), ('dispatch', 'Step', 'step'), ('resume', 'step', None),
            ('dispatch', 'Step', 'step'), ('resume', 'step', None), ('close', 1, 'explicit')))

    def test_nested_return_threads_frame_ownership_through_deep_reentry(self):
        checked = self.fixture('nested_return')
        self.assertEqual((checked.inferred.type, checked.inferred.effects), (INT, Row()))
        result = run(checked.program)
        self.assertEqual(result.value, 42)
        self.assertEqual(result.events, (
            ('acquire', 'File', 1), ('dispatch', 'Step', 'step'),
            ('acquire', 'File', 2), ('dispatch', 'Read', 'read'),
            ('resume', 'read', 7), ('close', 2, 'cleanup'), ('resume', 'step', None),
            ('dispatch', 'Step', 'step'), ('acquire', 'File', 3),
            ('dispatch', 'Read', 'read'), ('resume', 'read', 7),
            ('close', 3, 'cleanup'), ('resume', 'step', None), ('close', 1, 'explicit'),
            ('acquire', 'File', 4), ('close', 4, 'cleanup'),
            ('acquire', 'File', 5), ('close', 5, 'cleanup')))

    def test_clause_local_resource_survives_resume(self):
        result = run(self.fixture('clause_local').program)
        self.assertIsNone(result.value)
        self.assertEqual(result.events, (
            ('dispatch', 'Step', 'step'), ('acquire', 'File', 1),
            ('resume', 'step', None), ('close', 1, 'explicit')))

    def test_affine_abandonment_preserves_outside_and_masks_async_cleanup(self):
        result = run(self.fixture('affine_scope').program)
        self.assertEqual(result.value, 7)
        self.assertEqual(result.events, (
            ('acquire', 'File', 1), ('acquire', 'File', 2), ('acquire', 'File', 3),
            ('dispatch', 'Stop', 'stop'), ('close', 2, 'explicit'), ('abandon', 'stop'),
            ('close', 3, 'cleanup'), ('close', 1, 'explicit')))
        checked = self.fixture('affine_async')
        self.assertEqual(checked.inferred.effects, Row(('suspend',)))
        self.assertEqual(run(checked.program).events, (
            ('acquire', 'AsyncFile', 1), ('dispatch', 'Stop', 'stop'), ('abandon', 'stop'),
            ('suspend', True), ('close', 1, 'cleanup')))

    def test_forwarding_retains_outer_slot_and_callbacks_choose_evidence(self):
        checked = self.fixture('forwarding')
        self.assertEqual(checked.inferred.effects, Row())
        self.assertEqual(len(checked.handled_rows['inner'].labels), 1)
        self.assertIn('outer', checked.handled_rows['inner'].labels[0])
        self.assertEqual(run(checked.program).value, 42)
        self.assertEqual(run(checked.program).events, (
            ('dispatch', 'Read', 'inner'), ('dispatch', 'Read', 'outer'),
            ('resume', 'outer', 42), ('resume', 'inner', 42)))
        result = run(self.fixture('callbacks').program)
        self.assertEqual(result.value, 20)
        self.assertEqual([e for e in result.events if e[0] == 'dispatch'],
                         [('dispatch', 'Read', 'outer'), ('dispatch', 'Read', 'inner')])

    def test_combined_nested_handlers_forward_resume_and_cleanup(self):
        checked = self.fixture('combined')
        self.assertEqual((checked.inferred.type, checked.inferred.effects), (INT, Row()))
        self.assertTrue(checked.program.origins)
        result = run(checked.program)
        self.assertEqual(result.value, 42)
        self.assertEqual(result.events, (
            ('acquire', 'File', 1), ('acquire', 'File', 2),
            ('dispatch', 'Step', 'step'), ('resume', 'step', None),
            ('dispatch', 'Step', 'step'), ('resume', 'step', None),
            ('dispatch', 'Read', 'inner'), ('dispatch', 'Read', 'outer'),
            ('acquire', 'File', 3), ('close', 3, 'cleanup'),
            ('resume', 'outer', 42), ('resume', 'inner', 42),
            ('close', 1, 'explicit'), ('acquire', 'File', 4), ('close', 4, 'cleanup'),
            ('acquire', 'File', 5), ('close', 5, 'cleanup'), ('close', 2, 'cleanup')))

    def test_unsafe_source_fixtures_are_static_located_rejections(self):
        from eldude.source.pipeline import compile_file
        from eldude.source.syntax import grammar
        cases = {
            'wrong_operation_result': ('operation result', 11, 20),
            'tail_resume': ('Explicit resume.*tail', 11, 20),
            'missing_resume': ('once clause must resume exactly once', 11, 19),
            'repeated_resume': ('more than once', 13, 13),
            'escaping_resume': ('resume.*only inside an operation clause', 12, 33),
            'frame_transfer': ('file was already consumed', 16, 19),
            'clause_local': ('Unconsumed resource local', 14, 13),
            'unsafe_affine': ('abandon live resource file', 12, 9),
            'skipped_outer_resume': ('skip an enclosing resume', 16, 13),
            'skipped_consumption': ('skip consumption of file', 12, 9),
            'outward_pending': ('abandon live resource file', 21, 17),
            'deep_residual': ('abandon live resource local', 21, 17),
            'post_resume': ('abandon live resource file', 21, 17),
            'same_family': ('unqualified same-family', 11, 20),
            'nested_return_affine_skip': ('skip an enclosing resume', 20, 30),
            'nested_return_repeated': ('more than once', 22, 13),
            'nested_return_frame_transfer': ('frame was already consumed', 26, 19),
            'nested_return_outward': ('abandon live resource outside', 29, 21),
            'nested_return_residual': ('abandon live resource local', 30, 21),
        }
        self.assertEqual(set(cases), {p.stem for p in REJECT.glob('*.eld')})
        for name, (message, line, column) in cases.items():
            path = REJECT / (name + '.eld')
            with self.subTest(name=name):
                self.assertTrue(grammar().accepts(path.read_text(encoding='utf-8')))
                # Compile only. A runtime leak assertion cannot satisfy this test.
                with self.assertRaises(Diagnostic) as caught:
                    compile_file(path)
                diagnostic = caught.exception
                self.assertEqual(diagnostic.code, 'semantic', str(diagnostic))
                self.assertRegex(diagnostic.message, message)
                self.assertEqual((diagnostic.span.filename, diagnostic.span.line, diagnostic.span.column),
                                 (str(path), line, column))
                if name in ('frame_transfer', 'unsafe_affine', 'post_resume', 'deep_residual',
                            'nested_return_frame_transfer', 'nested_return_outward', 'nested_return_residual'):
                    self.assertTrue(diagnostic.related)
                if name == 'frame_transfer':
                    self.assertEqual([span.line for _, span in diagnostic.related], [10, 15])
                if name == 'nested_return_frame_transfer':
                    self.assertEqual([span.line for _, span in diagnostic.related], [14, 24])

    def test_operation_argument_failures_are_static_located_rejections(self):
        from eldude.source.pipeline import compile_file
        from eldude.source.syntax import grammar
        directory = ROOT / 'eldude-program-examples/reject/semantics/operation_arguments'
        cases = {
            'type': ('type', 'Type mismatch', 9, 9),
            'arity': ('type', 'Operation arity mismatch', 9, 9),
            'clause_arity': ('type', 'Operation clause arity mismatch', 11, 9),
            'abandonment': ('semantic', 'abandon live resource file', 12, 25),
        }
        self.assertEqual(set(cases), {p.stem for p in directory.glob('*.eld')})
        for name, (code, message, line, column) in cases.items():
            path = directory / (name + '.eld')
            with self.subTest(name=name):
                self.assertTrue(grammar().accepts(path.read_text(encoding='utf-8')))
                with self.assertRaises(Diagnostic) as caught:
                    compile_file(path)
                diagnostic = caught.exception
                self.assertEqual(diagnostic.code, code)
                self.assertRegex(diagnostic.message, message)
                self.assertEqual((diagnostic.span.filename, diagnostic.span.line, diagnostic.span.column),
                                 (str(path), line, column))
                if name == 'abandonment':
                    self.assertEqual(diagnostic.related[0][1].line, 10)



if __name__ == '__main__':
    unittest.main()
