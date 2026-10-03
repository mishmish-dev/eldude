"""Handler clauses are checked from bodies; execution tests use lowered evidence."""
import unittest

from effect_rows import Row
from inference import E, Fn, INT, UNIT, InferenceError
from handlers import HandlerChecker, Operation, compile_program, run


OPERATIONS = {
    'Read': Operation('tail', INT),
    'Step': Operation('once', UNIT),
    'Stop': Operation('affine', UNIT),
}


def handle(family, name, body, clause, result=None):
    return E('handle', family, name, body, clause,
             result or E('returning', 'answer', E('var', 'answer')))


def check(expression):
    checker = HandlerChecker(operations=OPERATIONS)
    return checker, checker.infer(expression)


class ClauseTests(unittest.TestCase):
    def test_tail_returns_operation_result_even_when_handler_returns_unit(self):
        _, result = check(handle('Read', 'read',
            E('seq', E('perform', 'Read'), E('unit')), E('int', 40)))
        self.assertEqual((result.type, result.effects), (UNIT, Row()))

    def test_tail_rejects_wrong_result_and_explicit_resume(self):
        for clause, message in [(E('unit'), 'operation result'),
                                (E('resume', E('int', 40)), 'tail')]:
            with self.subTest(clause=clause), self.assertRaisesRegex(InferenceError, message):
                check(handle('Read', 'read', E('perform', 'Read'), clause))

    def test_once_transfers_frame_resource_to_return_clause(self):
        program = E('let', 'file', E('acquire', 'File'),
            handle('Step', 'step', E('seq', E('perform', 'Step'), E('int', 42)),
                E('resume', E('unit')),
                E('returning', 'answer', E('seq', E('call', 'close', E('var', 'file')),
                    E('var', 'answer')))))
        _, result = check(program)
        self.assertEqual((result.type, result.effects), (INT, Row()))

    def test_once_requires_exactly_one_resume(self):
        for clause in (E('unit'), E('seq', E('resume', E('unit')), E('resume', E('unit')))):
            with self.subTest(clause=clause), self.assertRaisesRegex(InferenceError, 'resume'):
                check(handle('Step', 'step', E('perform', 'Step'), clause))

    def test_frame_capture_cannot_be_used_after_resume_or_consumed_before_transfer(self):
        close = E('call', 'close', E('var', 'file'))
        for clause in (E('seq', E('resume', E('unit')), close),
                       E('seq', close, E('resume', E('unit')))):
            with self.subTest(clause=clause), self.assertRaisesRegex(InferenceError, 'consumed|transfer'):
                check(E('let', 'file', E('acquire', 'File'),
                    handle('Step', 'step', E('perform', 'Step'), clause,
                        E('returning', 'answer', close))))

    def test_resume_cannot_escape_in_a_nested_closure(self):
        clause = E('let', 'later', E('lambda', (), E('resume', E('unit'))), E('call', 'later'))
        with self.assertRaisesRegex(InferenceError, 'resume.*clause'):
            check(handle('Step', 'step', E('perform', 'Step'), clause))

    def test_nested_affine_handler_cannot_skip_the_enclosing_once_resume(self):
        clause = handle('Stop', 'stop',
            E('seq', E('perform', 'Stop'), E('resume', E('unit'))), E('unit'))
        with self.assertRaisesRegex(InferenceError, 'skip.*resume'):
            check(handle('Step', 'step', E('perform', 'Step'), clause))

    def test_affine_rejects_naked_resource_in_captured_segment(self):
        body = E('let', 'file', E('acquire', 'File'),
            E('seq', E('perform', 'Stop'), E('call', 'close', E('var', 'file'))))
        with self.assertRaisesRegex(InferenceError, 'abandon.*file'):
            check(handle('Stop', 'stop', body, E('unit')))

    def test_affine_accepts_structural_cleanup_and_discharges_its_frame(self):
        program = E('let', 'frame_file', E('acquire', 'File'),
            handle('Stop', 'stop', E('using', 'body_file', E('acquire', 'File'),
                    E('perform', 'Stop')),
                E('call', 'close', E('var', 'frame_file')),
                E('returning', 'answer', E('call', 'close', E('var', 'frame_file')))))
        _, result = check(program)
        self.assertEqual(result.effects, Row())

    def test_affine_does_not_abandon_resource_outside_its_delimiter(self):
        _, result = check(E('let', 'file', E('acquire', 'File'),
            E('seq', handle('Stop', 'stop', E('perform', 'Stop'), E('unit')),
              E('call', 'close', E('var', 'file')))))
        self.assertEqual(result.effects, Row())

    def test_affine_cannot_skip_consumption_of_an_outer_linear_resource(self):
        body = E('seq', E('perform', 'Stop'), E('call', 'close', E('var', 'file')))
        with self.assertRaisesRegex(InferenceError, 'skip.*file'):
            check(E('let', 'file', E('acquire', 'File'),
                handle('Stop', 'stop', body, E('unit'))))

    def test_forwarding_preserves_outer_instance_and_residual_row(self):
        checker, result = check(handle('Read', 'outer',
            handle('Read', 'inner', E('perform', 'Read'), E('forward')), E('int', 42)))
        self.assertEqual((result.type, result.effects), (INT, Row()))
        inner = checker.handled_rows['inner']
        self.assertEqual(len(inner.labels), 1)
        self.assertEqual(checker.label_name(inner.labels[0]), 'outer')
        _, outward = check(handle('Read', 'inner', E('perform', 'Read'), E('forward')))
        self.assertEqual(outward.effects, Row(('Read',)))

    def test_same_family_clause_dispatch_requires_explicit_outer_name(self):
        with self.assertRaisesRegex(InferenceError, 'unqualified'):
            check(handle('Read', 'read', E('perform', 'Read'), E('perform', 'Read')))
        _, result = check(handle('Read', 'outer',
            handle('Read', 'inner', E('perform', 'Read'), E('perform', 'Read', 'outer')),
            E('int', 42)))
        self.assertEqual(result.effects, Row())

    def test_outward_affine_effect_cannot_abandon_a_suspended_once_segment(self):
        body = E('let', 'file', E('acquire', 'File'),
            E('seq', E('perform', 'Step'), E('call', 'close', E('var', 'file'))))
        inner = handle('Step', 'step', body,
            E('seq', E('perform', 'Stop', 'stop'), E('resume', E('unit'))))
        with self.assertRaisesRegex(InferenceError, 'abandon.*file'):
            check(handle('Stop', 'stop', inner, E('unit')))

    def test_outward_control_cannot_assume_an_opaque_once_segment_is_discardable(self):
        checker = HandlerChecker(operations=OPERATIONS,
            imports={'opaque': Fn((), UNIT, Row(('Step',)))})
        inner = handle('Step', 'step', E('call', 'opaque'),
            E('seq', E('perform', 'Stop', 'stop'), E('resume', E('unit'))))
        with self.assertRaisesRegex(InferenceError, 'opaque.*continuation'):
            checker.infer(handle('Stop', 'stop', inner, E('unit')))

    def test_post_resume_outward_exit_preserves_outside_resource_obligations(self):
        inner = handle('Step', 'step', E('perform', 'Step'),
            E('seq', E('resume', E('unit')), E('perform', 'Stop', 'stop')))
        body = E('let', 'file', E('acquire', 'File'),
            E('seq', inner, E('call', 'close', E('var', 'file'))))
        with self.assertRaisesRegex(InferenceError, 'abandon.*file'):
            check(handle('Stop', 'stop', body, E('unit')))

    def test_resumption_admits_effects_of_reentered_clauses(self):
        clause = E('let', 'local', E('acquire', 'File'),
            E('seq', E('resume', E('unit')), E('call', 'close', E('var', 'local')),
                E('perform', 'Stop', 'stop')))
        inner = handle('Step', 'step', E('seq', E('perform', 'Step'), E('perform', 'Step')), clause)
        with self.assertRaisesRegex(InferenceError, 'abandon.*local'):
            check(handle('Stop', 'stop', inner, E('unit')))

    def test_clause_local_resource_is_not_transferred_as_a_frame_capture(self):
        clause = E('let', 'local', E('acquire', 'File'), E('resume', E('unit')))
        with self.assertRaisesRegex(InferenceError, 'Unconsumed resource local'):
            check(handle('Step', 'step', E('perform', 'Step'), clause))

    def test_clause_can_close_its_local_resource_after_a_pure_resumption(self):
        clause = E('let', 'local', E('acquire', 'File'),
            E('seq', E('resume', E('unit')), E('call', 'close', E('var', 'local'))))
        result = run(compile_program(handle('Step', 'step', E('perform', 'Step'), clause),
            operations=OPERATIONS))
        self.assertEqual(result.events, (('dispatch', 'Step', 'step'), ('acquire', 'File', 1),
            ('resume', 'step', None), ('close', 1, 'explicit')))


class ExecutionTests(unittest.TestCase):
    def execute(self, expression):
        return run(compile_program(expression, operations=OPERATIONS))

    def test_tail_finishes_clause_cleanup_before_implicit_resumption(self):
        body = E('let', 'answer', E('perform', 'Read'),
            E('let', 'file', E('acquire', 'File'),
              E('seq', E('call', 'close', E('var', 'file')), E('var', 'answer'))))
        clause = E('using', 'temporary', E('acquire', 'File'), E('int', 40))
        result = self.execute(handle('Read', 'read', body, clause))
        self.assertEqual(result.value, 40)
        self.assertEqual(result.events, (
            ('dispatch', 'Read', 'read'), ('acquire', 'File', 1),
            ('close', 1, 'cleanup'), ('resume', 'read', 40),
            ('acquire', 'File', 2), ('close', 2, 'explicit')))

    def test_once_deep_reentry_closes_frame_resource_once_and_continues_after_resume(self):
        clause = E('seq', E('resume', E('unit')), E('int', 99))
        returning = E('returning', 'answer',
            E('seq', E('call', 'close', E('var', 'file')), E('var', 'answer')))
        result = self.execute(E('let', 'file', E('acquire', 'File'),
            handle('Step', 'step',
                E('seq', E('perform', 'Step'), E('perform', 'Step'), E('int', 42)),
                clause, returning)))
        self.assertEqual(result.value, 99)
        self.assertEqual(result.events, (
            ('acquire', 'File', 1), ('dispatch', 'Step', 'step'), ('resume', 'step', None),
            ('dispatch', 'Step', 'step'), ('resume', 'step', None), ('close', 1, 'explicit')))

    def test_affine_abandons_body_and_runs_masked_cleanup(self):
        body = E('using', 'file', E('acquire', 'AsyncFile'),
            E('seq', E('perform', 'Stop'), E('call', 'yield')))
        result = self.execute(handle('Stop', 'stop', body, E('unit')))
        self.assertIsNone(result.value)
        self.assertEqual(result.events, (
            ('acquire', 'AsyncFile', 1), ('dispatch', 'Stop', 'stop'),
            ('abandon', 'stop'), ('suspend', True), ('close', 1, 'cleanup')))

    def test_affine_zero_path_consumes_frame_and_unwinds_only_inner_cleanup(self):
        close_frame = E('call', 'close', E('var', 'frame_file'))
        program = E('let', 'outside', E('acquire', 'File'),
            E('let', 'frame_file', E('acquire', 'File'),
              E('seq', handle('Stop', 'stop',
                E('using', 'inside', E('acquire', 'File'), E('perform', 'Stop')),
                close_frame, E('returning', 'answer', close_frame)),
                E('call', 'close', E('var', 'outside')))))
        result = self.execute(program)
        self.assertEqual([e for e in result.events if e[0] == 'close'],
                         [('close', 2, 'explicit'), ('close', 3, 'cleanup'), ('close', 1, 'explicit')])

    def test_forwarding_uses_outer_evidence_and_resumes_inner_computation(self):
        result = self.execute(handle('Read', 'outer',
            handle('Read', 'inner', E('perform', 'Read'), E('forward')), E('int', 42)))
        self.assertEqual(result.value, 42)
        self.assertEqual(result.events, (
            ('dispatch', 'Read', 'inner'), ('dispatch', 'Read', 'outer'),
            ('resume', 'outer', 42), ('resume', 'inner', 42)))

    def test_callbacks_receive_ambient_evidence_and_retain_named_evidence(self):
        body = E('let', 'fixed', E('lambda', (), E('perform', 'Read', 'outer')),
            E('let', 'ambient', E('lambda', (), E('perform', 'Read')),
              handle('Read', 'inner', E('seq', E('call', 'fixed'), E('call', 'ambient')), E('int', 20))))
        result = self.execute(handle('Read', 'outer', body, E('int', 10)))
        self.assertEqual(result.value, 20)
        self.assertEqual([e for e in result.events if e[0] == 'dispatch'],
                         [('dispatch', 'Read', 'outer'), ('dispatch', 'Read', 'inner')])

    def test_outward_affine_exit_unwinds_the_suspended_once_continuation(self):
        inner = handle('Step', 'step',
            E('using', 'file', E('acquire', 'File'),
              E('seq', E('perform', 'Step'), E('int', 42))),
            E('seq', E('perform', 'Stop', 'stop'), E('resume', E('unit'))))
        result = self.execute(handle('Stop', 'stop', inner, E('int', 7)))
        self.assertEqual(result.value, 7)
        self.assertEqual(result.events, (
            ('acquire', 'File', 1), ('dispatch', 'Step', 'step'), ('dispatch', 'Stop', 'stop'),
            ('abandon', 'stop'), ('abandon', 'step'), ('close', 1, 'cleanup')))

    def test_compilation_rejects_unsafe_program_before_execution(self):
        bad = handle('Step', 'step', E('perform', 'Step'),
            E('seq', E('resume', E('unit')), E('resume', E('unit'))))
        with self.assertRaisesRegex(InferenceError, 'more than once'):
            compile_program(bad, operations=OPERATIONS)


if __name__ == '__main__':
    unittest.main()
