"""Inference experiments over a small annotated expression IR, not Eldude syntax."""
import unittest

from eldude.effect_rows import Row, Var
from eldude.inference import Checker, Fn, Ty, E, INT, UNIT, InferenceError


def traversal(checker):
    effects = Var('e', rigid=True)
    callback = Fn((INT,), UNIT, Row((), effects))
    return checker.define(
        'visit', (('values', Ty('List', (INT,))), ('f', callback)),
        E('each', E('var', 'values'), E('var', 'f')),
        effect_vars=(effects,))


def freeze_wrapper():
    checker = Checker()
    return checker.define(
        'freeze_wrapper', (('buffer', Ty('DynArray', (Ty('$T'),), 'r')),),
        E('call', 'freeze', E('var', 'buffer')),
        type_vars=('T',), regions=('r',))


class InferenceTests(unittest.TestCase):
    def test_traversal_infers_and_instantiates_callback_effects(self):
        checker = Checker()
        signature = traversal(checker)
        self.assertEqual(signature.result, UNIT)
        self.assertEqual(signature.effects.labels, ())
        self.assertIs(signature.effects.tail, signature.effect_vars[0])
        callback = E('lambda', (('n', INT),), E('perform', 'Log'))
        result = checker.infer(E('call', 'visit', E('list', E('int', 1)), callback))
        self.assertEqual(result.type, UNIT)
        self.assertEqual(result.effects, Row(('Log',)))

    def test_repeated_callback_uses_one_effect_slot(self):
        checker = Checker()
        traversal(checker)
        callback = E('lambda', (('n', INT),),
                     E('seq', E('perform', 'Log'), E('perform', 'Log')))
        result = checker.infer(E('call', 'visit', E('list', E('int', 1)), callback))
        self.assertEqual(result.effects, Row(('Log',)))

    def test_traversal_rejects_a_callback_owning_a_linear_resource(self):
        checker = Checker()
        traversal(checker)
        program = E('let', 'file', E('acquire', 'File'),
                    E('call', 'visit', E('list', E('int', 1)),
                      E('lambda', (('n', INT),),
                        E('call', 'close', E('var', 'file')))))
        with self.assertRaisesRegex(InferenceError, 'duplicable.*discardable'):
            checker.infer(program)

    def test_named_and_ambient_callbacks_choose_different_handlers(self):
        checker = Checker()
        program = E('handle', 'Log', 'outer',
                    E('let', 'fixed', E('lambda', (), E('perform', 'Log', 'outer')),
                      E('let', 'ambient', E('lambda', (), E('perform', 'Log')),
                        E('handle', 'Log', 'inner',
                          E('seq', E('call', 'ambient'), E('call', 'fixed'))))))
        result = checker.infer(program)
        self.assertEqual(result.effects, Row())
        self.assertEqual(checker.dispatches[-2:], [('Log', 'inner'), ('Log', 'outer')])
        inner = checker.handled_rows['inner']
        self.assertEqual(len(inner.labels), 1)
        self.assertEqual(checker.label_name(inner.labels[0]), 'outer')

    def test_same_spelling_handler_binders_do_not_alias(self):
        checker = Checker()
        result = checker.infer(E('handle', 'Log', 'h',
            E('let', 'fixed', E('lambda', (), E('perform', 'Log', 'h')),
              E('handle', 'Log', 'h',
                E('seq', E('perform', 'Log'), E('call', 'fixed'))))))
        self.assertEqual(result.effects, Row())
        self.assertEqual(len(checker.handler_ids), 2)

    def test_named_handler_capture_cannot_escape(self):
        with self.assertRaisesRegex(InferenceError, 'handler.*escape'):
            Checker().infer(E('handle', 'Log', 'log',
                E('lambda', (), E('perform', 'Log', 'log'))))

    def test_named_and_ambient_requirements_can_resolve_to_one_instance(self):
        result = Checker().infer(E('handle', 'Log', 'outer',
            E('let', 'f', E('lambda', (),
                E('seq', E('perform', 'Log'), E('perform', 'Log', 'outer'))),
              E('call', 'f'))))
        self.assertEqual(result.effects, Row())

    def test_duplicate_ambient_slots_select_distinct_nested_handlers(self):
        checker = Checker(imports={'both': Fn((), UNIT, Row(('Log', 'Log')))})
        result = checker.infer(E('handle', 'Log', 'outer',
            E('handle', 'Log', 'inner', E('call', 'both'))))
        self.assertEqual(result.effects, Row())
        self.assertEqual(checker.dispatches, [('Log', 'inner'), ('Log', 'outer')])

    def test_scoped_state_is_eliminated_for_a_scalar_result(self):
        result = Checker().infer(E('region', 'r',
            E('let', 'cell', E('ref', 'r', E('int', 42)),
              E('get', E('var', 'cell')))))
        self.assertEqual((result.type, result.effects, result.captures),
                         (INT, Row(), frozenset()))

    def test_reference_and_closure_cannot_escape_region(self):
        for result in (E('var', 'cell'),
                       E('lambda', (), E('get', E('var', 'cell')))):
            with self.subTest(result=result), self.assertRaisesRegex(InferenceError, 'region.*escape'):
                Checker().infer(E('region', 'r',
                    E('let', 'cell', E('ref', 'r', E('int', 42)), result)))

    def test_outer_cell_cannot_store_an_inner_closure(self):
        program = E('region', 'outer',
            E('let', 'slot', E('ref', 'outer', E('lambda', (), E('unit'))),
              E('region', 'inner',
                E('let', 'cell', E('ref', 'inner', E('int', 1)),
                  E('set', E('var', 'slot'),
                    E('lambda', (), E('seq', E('var', 'cell'), E('unit'))))))))
        with self.assertRaisesRegex(InferenceError, 'retention horizon'):
            Checker().infer(program)

    def test_mutable_reference_preserves_its_callback_effect_contract(self):
        checker = Checker()
        effectful = Fn((), UNIT, Row(('Log',)))
        checker.define('install', (('slot', Ty('Ref', (effectful,), 'r')),),
            E('set', E('var', 'slot'), E('lambda', (), E('perform', 'Log'))),
            regions=('r',))
        program = E('region', 'local',
            E('let', 'slot', E('ref', 'local', E('lambda', (), E('unit'))),
              E('seq', E('call', 'install', E('var', 'slot')),
                E('let', 'f', E('get', E('var', 'slot')), E('call', 'f')))))
        with self.assertRaises(InferenceError):
            checker.infer(program)

    def test_cancellation_rejects_unprotected_owned_resource(self):
        program = E('let', 'file', E('acquire', 'File'),
                    E('seq', E('call', 'yield'), E('call', 'close', E('var', 'file'))))
        with self.assertRaisesRegex(InferenceError, 'abandon.*file'):
            Checker().infer(program)

    def test_shadowing_does_not_hide_a_live_resource_from_cancellation(self):
        program = E('let', 'file', E('acquire', 'File'),
            E('seq', E('let', 'file', E('unit'), E('call', 'yield')),
              E('call', 'close', E('var', 'file'))))
        with self.assertRaisesRegex(InferenceError, 'abandon.*file'):
            Checker().infer(program)

    def test_effectful_closure_creation_does_not_capture_unused_resources(self):
        result = Checker().infer(E('let', 'file', E('acquire', 'File'),
            E('let', 'later', E('lambda', (), E('call', 'yield')),
              E('seq', E('call', 'close', E('var', 'file')), E('call', 'later')))))
        self.assertEqual(result.effects, Row(('suspend',)))

    def test_suspending_closure_must_protect_its_own_resource_capture(self):
        with self.assertRaisesRegex(InferenceError, 'abandon.*file'):
            Checker().infer(E('let', 'file', E('acquire', 'File'),
                E('lambda', (), E('seq', E('call', 'yield'),
                  E('call', 'close', E('var', 'file'))))))

    def test_higher_order_call_cannot_erase_a_callback_result_capture(self):
        checker = Checker()
        returned = Fn((), UNIT, Row())
        # This parameter promises a result independent of its environment.
        factory = Fn((), returned, Row(), bound=frozenset())
        checker.define('invoke', (('factory', factory),), E('call', 'factory'))
        program = E('region', 'local',
            E('let', 'cell', E('ref', 'local', E('int', 42)),
              E('call', 'invoke', E('lambda', (),
                E('lambda', (), E('seq', E('var', 'cell'), E('unit')))))))
        with self.assertRaisesRegex(InferenceError, 'Callback capture contract'):
            checker.infer(program)

    def test_nested_parameters_have_distinct_capture_sources(self):
        checker = Checker()
        pure = Fn((), UNIT, Row())
        make = checker.define('make', (('seed', pure),),
            E('lambda', (('candidate', pure),),
              E('seq', E('var', 'seed'), E('var', 'candidate'))))
        self.assertEqual(make.result.bound, frozenset({'arg:0'}))
        program = E('let', 'select', E('call', 'make', E('lambda', (), E('unit'))),
            E('region', 'local',
              E('let', 'cell', E('ref', 'local', E('int', 42)),
                E('call', 'select', E('lambda', (),
                  E('seq', E('var', 'cell'), E('unit')))))))
        with self.assertRaisesRegex(InferenceError, 'region.*escape'):
            checker.infer(program)

    def test_traversal_composes_state_handlers_and_cancellation_protection(self):
        checker = Checker()
        traversal(checker)
        program = E('region', 'local',
            E('using', 'file', E('acquire', 'AsyncFile'),
              E('let', 'cell', E('ref', 'local', E('int', 0)),
                E('let', 'callback', E('lambda', (('n', INT),),
                    E('seq', E('set', E('var', 'cell'), E('var', 'n')),
                      E('perform', 'Log'), E('call', 'yield'))),
                  E('seq', E('handle', 'Log', 'log',
                    E('call', 'visit', E('list', E('int', 1), E('int', 2)), E('var', 'callback'))),
                    E('get', E('var', 'cell')))))))
        result = checker.infer(program)
        self.assertEqual((result.type, result.effects, result.captures),
                         (INT, Row(('suspend',)), frozenset()))

    def test_using_protects_resource_and_masks_suspending_cleanup(self):
        checker = Checker()
        result = checker.infer(E('using', 'file', E('acquire', 'AsyncFile'),
                                 E('call', 'yield')))
        self.assertEqual(result.effects, Row(('suspend',)))
        self.assertEqual(checker.cleanups, [('file', True)])

    def test_cleanup_mask_does_not_neutralize_affine_effects(self):
        checker = Checker(cleanups={'Bad': Row(('Abort',))})
        with self.assertRaisesRegex(InferenceError, 'cleanup.*abandon'):
            checker.infer(E('using', 'bad', E('acquire', 'Bad'), E('unit')))

    def test_unknown_imported_effect_cannot_be_assumed_non_abandoning(self):
        checker = Checker(imports={'unknown': Fn((), UNIT, Row(('Unregistered',)))})
        with self.assertRaisesRegex(InferenceError, 'Unknown effect'):
            checker.infer(E('let', 'file', E('acquire', 'File'),
                E('seq', E('call', 'unknown'), E('call', 'close', E('var', 'file')))))

    def test_imported_state_effect_requires_a_live_region(self):
        checker = Checker(imports={'bad': Fn((), UNIT, Row(('state<@missing>',)))})
        with self.assertRaisesRegex(InferenceError, 'State region'):
            checker.infer(E('call', 'bad'))

    def test_owned_argument_is_live_while_later_arguments_evaluate(self):
        checker = Checker(imports={'consume': Fn(
            (Ty('Owned', (Ty('File'),)), UNIT), UNIT, Row())})
        with self.assertRaisesRegex(InferenceError, 'abandon'):
            checker.infer(E('call', 'consume', E('acquire', 'File'), E('call', 'yield')))

    def test_resource_cannot_be_consumed_twice(self):
        with self.assertRaisesRegex(InferenceError, 'consumed'):
            Checker().infer(E('let', 'file', E('acquire', 'File'),
                E('seq', E('call', 'close', E('var', 'file')),
                  E('call', 'close', E('var', 'file')))))

    def test_imported_freeze_wrapper_has_only_a_serialized_contract(self):
        signature = freeze_wrapper()
        self.assertEqual(signature.result, Ty('List', (Ty('$T'),)))
        self.assertEqual(signature.effects, Row(('state<@r>',)))
        self.assertIn('arg:0', signature.bound)
        wire = signature.dumps()
        self.assertNotIn('body', wire)
        imported = Fn.loads(wire)
        checker = Checker(imports={'freeze_wrapper': imported})
        result = checker.infer(E('region', 'local',
            E('call', 'freeze_wrapper', E('buffer', 'local', E('list', E('int', 42))))))
        self.assertEqual((result.type, result.effects, result.captures),
                         (Ty('List', (INT,)), Row(), frozenset()))

    def test_imported_freeze_wrapper_conservatively_rejects_outer_references(self):
        checker = Checker(imports={'freeze_wrapper': Fn.loads(freeze_wrapper().dumps())})
        program = E('region', 'outer',
            E('let', 'cell', E('ref', 'outer', E('int', 42)),
              E('region', 'inner', E('call', 'freeze_wrapper',
                E('buffer', 'inner', E('list', E('var', 'cell')))))))
        with self.assertRaisesRegex(InferenceError, 'region.*escape'):
            checker.infer(program)

    def test_imported_effect_variables_are_fresh_at_each_call(self):
        exporter = Checker()
        signature = Fn.loads(traversal(exporter).dumps())
        checker = Checker(imports={'visit': signature})
        calls = [E('call', 'visit', E('list', E('int', 1)),
                   E('lambda', (('n', INT),), body))
                 for body in (E('perform', 'Log'), E('call', 'yield'))]
        result = checker.infer(E('seq', *calls))
        self.assertEqual(result.effects, Row(('Log', 'suspend')))

    def test_missing_imported_capture_contract_is_rejected(self):
        import json
        data = json.loads(freeze_wrapper().dumps())
        del data['bound']
        with self.assertRaisesRegex(InferenceError, 'capture bound'):
            Fn.loads(json.dumps(data))


if __name__ == '__main__':
    unittest.main()
