"""Regressions for declaration, ownership, and control-flow integration."""
import unittest
from pathlib import Path

from eldude.core.rows import Row
from eldude.core.handlers import Defect, compile_program, run
from eldude.core.inference import Binding, Context, E, Fn, INT, UNIT, Ty, InferenceError, value, Grant, Owner
from eldude.source.features import FeatureChecker
from eldude.core.types import NAT, UNKNOWN
from eldude.source.pipeline import compile_file

ROOT = Path(__file__).resolve().parents[2]


class SourceFeatureRegressionTests(unittest.TestCase):
    def compile(self, expression, checker=None):
        return compile_program(expression, checker=checker or FeatureChecker())

    def test_record_patterns_cover_fields_in_declaration_order(self):
        program = compile_file(ROOT / 'examples/src/01_values/record_patterns.eld')
        self.assertEqual(run(program.program).value, 42)

    def test_local_try_preserves_an_outer_owned_argument_temporary(self):
        program = compile_file(ROOT / 'examples/src/03_results/try_argument_owner.eld')
        result = run(program.program)
        self.assertEqual(result.value, 42)
        self.assertEqual(result.events, (('acquire', 'File', 1), ('close', 1, 'explicit')))

    def test_repeated_record_field_is_rejected_before_binding(self):
        checker = FeatureChecker()
        record = Ty('Record:R', (Ty('file', (Ty('Owned', (Ty('File'),)),)),))
        with self.assertRaisesRegex(InferenceError, 'Duplicate record pattern field'):
            checker.bind_pattern(('record_pat', 'Record:R', ('file', 'file'),
                                  ('bind', 'a'), ('bind', 'b')), value(record), Context())

    def test_early_return_cannot_smuggle_a_local_region_in_a_closure(self):
        signature = Fn((), INT, Row())
        captured = E('lambda', (), E('seq', E('var', 'cell'), E('int', 42)))
        for tail in (E('early', 'return', captured),
                     E('seq', E('early', 'return', captured), E('lambda', (), E('int', 0)))):
            expression = E('exit_scope', 'return', signature,
                           E('region', 'r', E('let', 'cell', E('ref_new', 'r', E('int', 1)), tail)), False)
            with self.subTest(tail=tail), self.assertRaisesRegex(InferenceError, 'region.*escape|escape.*region'):
                self.compile(expression)

    def test_return_within_the_same_region_preserves_capture_metadata(self):
        signature = Fn((), INT, Row())
        captured = E('lambda', (), E('seq', E('var', 'cell'), E('int', 42)))
        expression = E('region', 'r', E('let', 'cell', E('ref_new', 'r', E('int', 1)),
                       E('let', 'callback', E('exit_scope', 'return', signature,
                         E('seq', E('early', 'return', captured), E('lambda', (), E('int', 0))), False),
                         E('call', 'callback'))))
        self.assertEqual(run(self.compile(expression)).value, 42)
        escaping = E('region', 'r', E('let', 'cell', E('ref_new', 'r', E('int', 1)),
                     E('exit_scope', 'return', signature, E('early', 'return', captured), False)))
        with self.assertRaisesRegex(InferenceError, 'region.*escape|escape.*region'):
            self.compile(escaping)

    def test_early_return_keeps_inferred_closed_callable_captures(self):
        signature = Fn((), INT, Row())
        expression = E('exit_scope', 'return', signature,
                       E('early', 'return', E('lambda', (), E('int', 42))), False)
        result = FeatureChecker().infer(expression)
        self.assertEqual(result.type.captures, frozenset())

    def test_early_return_honors_an_explicit_capture_promise(self):
        signature = Fn((), INT, Row(), captures=frozenset())
        captured = E('lambda', (), E('seq', E('var', 'cell'), E('int', 42)))
        expression = E('region', 'r', E('let', 'cell', E('ref_new', 'r', E('int', 1)),
                       E('exit_scope', 'return', signature, E('early', 'return', captured), False)))
        with self.assertRaisesRegex(InferenceError, 'type mismatch|capture'):
            self.compile(expression)

    def test_early_return_runs_managed_cleanup(self):
        expression = E('exit_scope', 'return', INT,
                       E('using', 'resource', E('acquire', 'File'), E('early', 'return', E('int', 42))), False)
        result = run(self.compile(expression))
        self.assertEqual(result.value, 42)
        self.assertEqual(result.events, (('acquire', 'File', 1), ('close', 1, 'cleanup')))

    def test_early_return_cannot_abandon_a_linear_owner_on_one_branch(self):
        expression = E('exit_scope', 'return', UNIT,
                       E('let', 'resource', E('acquire', 'File'),
                         E('if', E('bool', True), E('early', 'return', E('unit')),
                           E('call', 'close', E('var', 'resource')))), False)
        with self.assertRaisesRegex(InferenceError, 'abandon'):
            self.compile(expression)

    def test_propagation_only_checks_owners_inside_its_target_boundary(self):
        result = Ty('Result', (INT, INT))
        failure = E('variant', result, 'Err', (E('int', 7),))
        propagation = E('exit_scope', 'try', result, E('propagate', 'try', failure), True)
        safe = E('let', 'resource', E('acquire', 'File'),
                 E('seq', propagation, E('call', 'close', E('var', 'resource'))))
        self.assertEqual(run(self.compile(safe)).events,
                         (('acquire', 'File', 1), ('close', 1, 'explicit')))
        unsafe = E('exit_scope', 'try', result,
                   E('let', 'resource', E('acquire', 'File'),
                     E('seq', E('propagate', 'try', failure), E('call', 'close', E('var', 'resource')),
                       E('int', 0))), True)
        with self.assertRaisesRegex(InferenceError, 'abandon'):
            self.compile(unsafe)

    def test_borrowed_freeze_cannot_duplicate_owned_elements(self):
        owned = Ty('Owned', (Ty('File'),))
        def freeze(mode):
            return E('primitive_method', 'freeze', E('var', 'array'), (), mode)
        def close_list(name):
            return E('for_each', ('bind', 'item'), E('var', name), E('call', 'close', E('var', 'item')))
        expression = E('region', 'r', E('let', 'array', E('buffer_new', 'r', owned),
                       E('seq', E('primitive_method', 'push', E('var', 'array'), (E('acquire', 'File'),), 'mut'),
                         E('let', 'first', freeze('view'), E('seq', close_list('first'),
                           E('let', 'second', freeze(''), close_list('second')))))))
        with self.assertRaisesRegex(InferenceError, 'consum'):
            self.compile(expression)

    def test_primitive_temporary_receiver_is_inferred_once(self):
        expression = E('let', 'resource', E('acquire', 'File'),
                       E('method_call', 'push', E('seq', E('call', 'close', E('var', 'resource')),
                         E('list_values', INT, ())), (E('int', 42),), ''))
        result = run(self.compile(expression))
        self.assertEqual(list(result.value), [42])
        self.assertEqual(result.events, (('acquire', 'File', 1), ('close', 1, 'explicit')))

    def test_missing_recursive_constructor_is_a_nonexhaustive_error(self):
        checker = FeatureChecker()
        tree = Ty('Tree')
        checker.variants = {'Tree': {'Node': (tree,), 'Leaf': ()}}
        expression = E('match', E('variant', tree, 'Leaf', ()),
                       ((('variant_pat', 'Tree', 'Leaf'), E('int', 42)),))
        with self.assertRaisesRegex(InferenceError, 'Non-exhaustive'):
            self.compile(expression, checker)

    def test_borrowed_forward_global_read_is_an_initialization_defect(self):
        initial = E('primitive_method', 'length', E('var', 'later'), (), 'view')
        expression = E('definitions', (),
                       (('first', NAT, initial), ('later', Ty('List', (INT,)), E('list_values', INT, (E('int', 42),)))),
                       E('var', 'first'))
        with self.assertRaisesRegex(Defect, 'initializ'):
            run(self.compile(expression))

    def test_buffer_element_region_is_resolved_before_capture_escape_check(self):
        element = Ty('Ref', (INT,), 'r')
        expression = E('region', 'r', E('let', 'array', E('buffer_new', 'r', element),
                       E('seq', E('primitive_method', 'push', E('var', 'array'),
                                  (E('ref_new', 'r', E('int', 42)),), 'mut'),
                         E('primitive_method', 'freeze', E('var', 'array'), (), ''))))
        with self.assertRaisesRegex(InferenceError, 'region.*escape|escape.*region'):
            self.compile(expression)

    def test_mut_wrapper_keeps_provenance_after_contextual_type_normalization(self):
        checker = FeatureChecker()
        reference = Ty('Ref', (INT,), 'r')
        owner = Binding(value(Ty('Option', (UNKNOWN,)), grant=Grant(Owner('r'), 'mut', ('element',))), mode='mut')
        context = Context(bindings={'owner': owner}, active=frozenset({'r'}))
        access = checker._infer(E('access', 'mut', 'owner'), context)
        signature = Fn((Ty('Mut', (Ty('Option', (reference,)),)), reference), UNIT, Row())
        checker._apply(value(signature), [access, value(reference)], context)
        self.assertIn('r', owner.value.captures)

    def test_constructor_unifies_repeated_and_nested_type_parameters(self):
        for field in (Ty('$T'), Ty('Tuple', (Ty('$T'),))):
            checker = FeatureChecker()
            checker.variants = {'Pair': {'Pair': (field, field)}}
            checker.data_parameters = {'Pair': ('T',)}
            arguments = (E('int', 1), E('bool', True))
            if field.name == 'Tuple':
                arguments = tuple(E('tuple', item) for item in arguments)
            expression = E('variant', Ty('Pair', (Ty('$T'),)), 'Pair', arguments)
            with self.subTest(field=field), self.assertRaises(InferenceError):
                self.compile(expression, checker)

    def test_lowered_variant_retains_its_inferred_payload_type(self):
        checker = FeatureChecker()
        checker.variants = {'Box': {'Box': (Ty('$T'),)}}
        checker.data_parameters = {'Box': ('T',)}
        expression = E('variant', Ty('Box', (Ty('$T'),)), 'Box', (E('int', 42),))
        program = self.compile(expression, checker)
        self.assertEqual(run(program).value.type, Ty('Box', (INT,)))

    def test_consuming_user_method_rejects_explicit_borrowed_access(self):
        checker = FeatureChecker()
        ticket = Ty('Record:Ticket')
        checker.methods[(ticket.name, 'redeem')] = ('redeem', Fn((ticket,), INT, Row()))
        expression = E('let', 'ticket', E('record', ticket, ()),
                       E('method_call', 'redeem', E('var', 'ticket'), (), 'view'))
        with self.assertRaisesRegex(InferenceError, 'consum'):
            self.compile(expression, checker)


if __name__ == '__main__':
    unittest.main()
