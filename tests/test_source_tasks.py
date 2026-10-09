"""Task checking, lowering, execution and inherited handler contracts."""
import unittest

from eldude.handlers import Operation, compile_program, run
from eldude.inference import BOOL, INT, UNIT, E, InferenceError
from eldude.source_features import FeatureChecker


def spawn(body):
    return E('spawn', E('lambda', (), body))


def group(body, key='main'):
    return E('taskgroup', 'taskgroup:' + key, body)


def handle(body, *, returning=None, clause=None, family='Log'):
    return E('handle', family, 'handler', body,
             E('unit') if clause is None else clause,
             E('returning', 'answer', E('var', 'answer')) if returning is None else returning)


class SourceTaskTests(unittest.TestCase):
    def compile(self, expression, **kwargs):
        return compile_program(expression, checker=FeatureChecker(**kwargs))

    def execute(self, expression, **kwargs):
        return run(self.compile(expression, **kwargs))

    def test_two_children_join_to_42(self):
        expression = group(E('let', 'left', spawn(E('int', 20)),
            E('let', 'right', spawn(E('int', 22)),
              E('binary', '+', E('await', E('var', 'left')), E('await', E('var', 'right'))))))
        program = self.compile(expression)
        self.assertEqual(program.inferred.type, INT)
        self.assertIn('suspend', program.inferred.effects.labels)
        self.assertEqual(run(program).value, 42)

    def test_spawn_defers_children_and_await_starts_them_fifo(self):
        first = E('using', 'file', E('acquire', 'File'), E('int', 20))
        second = E('using', 'file', E('acquire', 'AsyncFile'), E('int', 22))
        parent = E('using', 'file', E('acquire', 'File'), E('unit'))
        expression = group(E('let', 'first', spawn(first),
            E('let', 'second', spawn(second), E('seq', parent,
              E('binary', '+', E('await', E('var', 'second')), E('await', E('var', 'first')))))))
        result = self.execute(expression)
        self.assertEqual(result.value, 42)
        self.assertEqual(result.events, (
            ('acquire', 'File', 1), ('close', 1, 'cleanup'),
            ('suspend', False),
            ('acquire', 'File', 2), ('close', 2, 'cleanup'),
            ('acquire', 'AsyncFile', 3), ('suspend', True), ('close', 3, 'cleanup'),
            ('suspend', False)))

    def test_discarded_task_handle_still_drains_child_cleanup(self):
        child = E('using', 'file', E('acquire', 'File'), E('int', 7))
        result = self.execute(group(E('seq', spawn(child), E('int', 42))))
        self.assertEqual(result.value, 42)
        self.assertEqual(result.events, (('acquire', 'File', 1), ('close', 1, 'cleanup')))

    def test_task_handle_cannot_escape_directly_or_inside_aggregate(self):
        for body in (spawn(E('int', 42)), E('tuple', spawn(E('int', 42)), E('int', 7))):
            with self.subTest(body=body), self.assertRaisesRegex(InferenceError, 'escape.*taskgroup'):
                self.compile(group(body))

    def test_spawned_result_must_be_discardable(self):
        with self.assertRaisesRegex(InferenceError, 'Discard'):
            self.compile(group(E('seq', spawn(E('acquire', 'File')), E('unit'))))

    def test_task_handle_cannot_be_awaited_twice(self):
        expression = group(E('let', 'task', spawn(E('int', 42)),
            E('seq', E('await', E('var', 'task')), E('await', E('var', 'task')))))
        with self.assertRaisesRegex(InferenceError, 'consumed'):
            self.compile(expression)

    def test_nested_lambda_does_not_inherit_spawn_permission(self):
        expression = group(E('let', 'helper', E('lambda', (),
            E('seq', spawn(E('int', 42)), E('unit'))), E('call', 'helper')))
        with self.assertRaisesRegex(InferenceError, 'lexical taskgroup'):
            self.compile(expression)

    def test_nested_lambda_may_establish_its_own_group(self):
        expression = group(E('let', 'helper', E('lambda', (), group(
            E('let', 'task', spawn(E('int', 42)), E('await', E('var', 'task'))), 'helper')),
            E('call', 'helper')))
        self.assertEqual(self.execute(expression).value, 42)

    def test_identity_baseline_handler_accepts_int_and_bool_children(self):
        for child_result, child_type, expected in ((E('int', 42), INT, 42), (E('bool', True), BOOL, True)):
            child = E('seq', E('perform', 'Log'), child_result)
            expression = handle(group(E('let', 'task', spawn(child), E('await', E('var', 'task')))))
            with self.subTest(type=child_type):
                program = self.compile(expression)
                self.assertEqual(program.inferred.type, child_type)
                result = run(program)
                self.assertEqual(result.value, expected)
                self.assertIn(('dispatch', 'Log', 'handler'), result.events)

    def test_inherited_bool_child_preserves_its_type_inside_int_parent(self):
        child = E('seq', E('perform', 'Log'), E('bool', True))
        expression = handle(group(E('let', 'task', spawn(child),
            E('if', E('await', E('var', 'task')), E('int', 42), E('int', 0)))))
        self.assertEqual(self.execute(expression).value, 42)

    def test_answer_changing_baseline_return_cannot_be_inherited(self):
        child = E('seq', E('perform', 'Log'), E('int', 41))
        returning = E('returning', 'answer', E('binary', '+', E('var', 'answer'), E('int', 1)))
        expression = handle(group(E('let', 'task', spawn(child), E('await', E('var', 'task')))),
                            returning=returning)
        with self.assertRaisesRegex(InferenceError, 'Inherited handler.*preserve'):
            self.compile(expression)

    def test_answer_changing_baseline_operation_cannot_be_inherited(self):
        child = E('seq', E('perform', 'Step'), E('int', 41))
        clause = E('binary', '+', E('resume', E('unit')), E('int', 1))
        expression = handle(group(E('let', 'task', spawn(child), E('await', E('var', 'task')))),
                            clause=clause, family='Step')
        with self.assertRaisesRegex(InferenceError, 'Inherited handler.*preserve'):
            self.compile(expression, operations={'Step': Operation('once', UNIT)})

    def test_child_local_handler_may_change_its_answer(self):
        returning = E('returning', 'answer', E('binary', '+', E('var', 'answer'), E('int', 1)))
        child = handle(E('seq', E('perform', 'Log'), E('int', 41)), returning=returning)
        expression = group(E('let', 'task', spawn(child), E('await', E('var', 'task'))))
        self.assertEqual(self.execute(expression).value, 42)

    def test_inherited_once_clause_preserves_result_with_effects_and_aliases(self):
        cleanup = E('using', 'file', E('acquire', 'File'), E('unit'))
        clauses = (
            E('seq', cleanup, E('resume', E('unit'))),
            E('let', 'saved', E('resume', E('unit')), E('seq', cleanup, E('var', 'saved'))),
            E('let', 'unused', E('int', 7), E('resume', E('unit'))),
            E('using', 'file', E('acquire', 'File'), E('resume', E('unit'))),
            E('if', E('bool', True), E('resume', E('unit')), E('resume', E('unit'))),
        )
        returning = E('returning', 'answer', E('let', 'alias', E('var', 'answer'), E('var', 'alias')))
        for clause in clauses:
            child = E('seq', E('perform', 'Step'), E('bool', True))
            expression = handle(group(E('let', 'task', spawn(child),
                E('if', E('await', E('var', 'task')), E('int', 42), E('int', 0)))),
                clause=clause, returning=returning, family='Step')
            with self.subTest(clause=clause):
                self.assertEqual(self.execute(expression, operations={'Step': Operation('once', UNIT)}).value, 42)

    def test_inheritance_rejects_discarded_or_duplicated_results_and_zero_resume(self):
        clauses = (
            ('once', E('seq', E('resume', E('unit')), E('int', 42))),
            ('once', E('let', 'saved', E('resume', E('unit')),
                E('seq', E('var', 'saved'), E('var', 'saved')))),
            ('once', E('let', 'saved', E('resume', E('unit')),
                E('binary', '+', E('var', 'saved'), E('int', 0)))),
            ('affine', E('int', 42)),
        )
        for mode, clause in clauses:
            child = E('seq', E('perform', 'Step'), E('int', 42))
            expression = handle(group(E('let', 'task', spawn(child), E('await', E('var', 'task')))),
                                clause=clause, family='Step')
            with self.subTest(mode=mode, clause=clause), self.assertRaisesRegex(InferenceError, 'Inherited handler.*preserve'):
                self.compile(expression, operations={'Step': Operation(mode, UNIT)})

    def test_tail_and_affine_identity_clauses_can_be_inherited(self):
        cleanup = E('using', 'file', E('acquire', 'File'), E('unit'))
        for mode, clause in (('tail', cleanup), ('affine', E('seq', cleanup, E('resume', E('unit'))))):
            child = E('seq', E('perform', 'Step'), E('bool', True))
            expression = handle(group(E('let', 'task', spawn(child), E('await', E('var', 'task')))),
                                clause=clause, family='Step')
            with self.subTest(mode=mode):
                result = self.execute(expression, operations={'Step': Operation(mode, UNIT)})
                self.assertIs(result.value, True)
                self.assertIn(('close', 1, 'cleanup'), result.events)


if __name__ == '__main__':
    unittest.main()
