"""Declaration visibility and ordered startup through the executable IR."""
import unittest

from eldude.core.rows import Row
from eldude.core.handlers import Defect, compile_program, run
from eldude.core.inference import E, Fn, INT, UNIT, Ty, InferenceError
from eldude.source.features import FeatureChecker
from eldude.core.types import UNKNOWN


def function(name, body, parameters=(), effects=Row()):
    return name, E('lambda', parameters, body), Fn(tuple(t for _, t in parameters), INT, effects)


class SourceDeclarationTests(unittest.TestCase):
    def execute(self, functions=(), globals=(), body=E('unit')):
        return run(compile_program(E('definitions', tuple(functions), tuple(globals), body), checker=FeatureChecker()))

    def test_forward_function_references(self):
        functions = (function('first', E('call', 'later')), function('later', E('int', 42)))
        result = self.execute(functions, body=E('call', 'first'))
        self.assertEqual((result.value, result.events), (42, ()))

    def test_mutual_recursion_uses_checked_signatures(self):
        def body(other):
            return E('if', E('binary', '==', E('var', 'n'), E('int', 0)), E('int', 42),
                     E('call', other, E('binary', '-', E('var', 'n'), E('int', 1))))
        functions = tuple(function(name, body(other), (('n', INT),), Row(('diverge',)))
                          for name, other in (('a', 'b'), ('b', 'a')))
        self.assertEqual(self.execute(functions, body=E('call', 'a', E('int', 4))).value, 42)

    def test_unproved_recursion_requires_diverge(self):
        with self.assertRaisesRegex(InferenceError, 'diverge'):
            self.execute((function('forever', E('call', 'forever')),))

    def test_unproved_method_recursion_requires_diverge(self):
        checker = FeatureChecker()
        record = Ty('Record:R')
        signature = Fn((record,), record, Row())
        checker.methods[(record.name, 'again')] = ('again', signature)
        closure = E('lambda', (('self', record),), E('method_call', 'again', E('var', 'self'), (), ''))
        expression = E('definitions', (('again', closure, signature),), (), E('unit'))
        with self.assertRaisesRegex(InferenceError, 'diverge'):
            compile_program(expression, checker=checker)

    def test_every_function_body_is_checked_even_when_unused(self):
        with self.assertRaises(InferenceError):
            self.execute((function('unused', E('bool', True)),))

    def test_globals_initialize_in_order_and_functions_see_shared_slots(self):
        functions = (function('read', E('var', 'second')),)
        globals = (('first', UNKNOWN, E('int', 40)),
                   ('second', UNKNOWN, E('binary', '+', E('var', 'first'), E('int', 2))))
        result = self.execute(functions, globals, E('call', 'read'))
        self.assertEqual((result.value, result.events), (42, ()))

    def test_unused_initializer_still_runs_and_first_defect_stops_startup(self):
        first = E('binary', '/', E('int', 1), E('int', 0))
        later = E('binary', '+', E('int', 9223372036854775807), E('int', 1))
        with self.assertRaisesRegex(Defect, 'zero'):
            self.execute(globals=(('unused', INT, first), ('later', INT, later)))

    def test_forward_global_reads_are_runtime_initialization_defects(self):
        for initial in (E('var', 'later'), E('call', 'read')):
            with self.subTest(initial=initial), self.assertRaisesRegex(Defect, 'initializ'):
                self.execute((function('read', E('var', 'later')),),
                             (('first', INT, initial), ('later', INT, E('int', 42))))

    def test_global_lambda_defers_global_read_until_invocation(self):
        globals = (('callback', UNKNOWN, E('lambda', (), E('var', 'later'))),
                   ('later', UNKNOWN, E('int', 42)))
        self.assertEqual(self.execute(globals=globals, body=E('call', 'callback')).value, 42)

    def test_impure_diverging_and_resource_initializers_are_rejected(self):
        for initializer in (E('call', 'yield'), E('acquire', 'File')):
            with self.subTest(initializer=initializer), self.assertRaises(InferenceError):
                self.execute(globals=(('bad', UNKNOWN, initializer),))
        with self.assertRaisesRegex(InferenceError, 'pure|terminat'):
            self.execute((function('f', E('int', 1), effects=Row(('diverge',))),),
                         (('bad', INT, E('call', 'f')),))


if __name__ == '__main__':
    unittest.main()
