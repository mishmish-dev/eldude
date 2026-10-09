"""Executable counterexamples for the scoped-row design; not Eldude type tests."""
import unittest

from eldude.effect_rows import Row, Solver, Var


class EffectRowTests(unittest.TestCase):
    def test_unrelated_labels_commute_but_duplicate_layers_remain(self):
        solver = Solver()
        solver.unify(Row(('Console', 'Store<Int>', 'Console')),
                     Row(('Console', 'Console', 'Store<Int>')))
        with self.assertRaises(ValueError):
            solver.unify(Row(('Console', 'Console')), Row(('Console',)))

    def test_handling_inner_layer_preserves_outer_layer(self):
        solver, residual = Solver(), Var('residual')
        solver.unify(Row(('Log',), residual), Row(('Log', 'Log', 'suspend')))
        self.assertEqual(solver.resolve(Row((), residual)), Row(('Log', 'suspend')))

    def test_handling_only_layer_leaves_empty_row(self):
        solver, residual = Solver(), Var('residual')
        solver.unify(Row(('Log',), residual), Row(('Log',)))
        self.assertEqual(solver.resolve(Row((), residual)), Row())

    def test_forwarding_retains_an_outer_requirement(self):
        solver, outer = Solver(), Var('outer')
        solver.unify(Row(('Log',), outer), Row(('Log', 'Log')))
        with self.assertRaises(ValueError):
            solver.unify(Row((), outer), Row())

    def test_distinct_applied_families_do_not_match(self):
        solver, residual = Solver(), Var('residual')
        solver.unify(Row(('Store<Int>',), residual),
                     Row(('Store<Bool>', 'Store<Int>')))
        self.assertEqual(solver.resolve(Row((), residual)), Row(('Store<Bool>',)))
        with self.assertRaises(ValueError):
            Solver().unify(Row(('Store<Int>',)), Row(('Store<Bool>',)))

    def test_named_instance_keys_cannot_be_interchanged(self):
        solver, residual = Solver(), Var('residual')
        solver.unify(Row(('Log@inner',), residual),
                     Row(('Log@inner', 'Log@outer')))
        self.assertEqual(solver.resolve(Row((), residual)), Row(('Log@outer',)))

    def test_open_rows_share_one_fresh_tail(self):
        solver, left, right = Solver(), Var('left'), Var('right')
        solver.unify(Row(('Console',), left), Row(('File',), right))
        left_row, right_row = solver.resolve(Row((), left)), solver.resolve(Row((), right))
        self.assertEqual(left_row.labels, ('File',))
        self.assertEqual(right_row.labels, ('Console',))
        self.assertIs(left_row.tail, right_row.tail)
        solver.unify(Row((), left_row.tail), Row(('suspend',)))
        self.assertEqual(solver.resolve(Row(('Console',), left)),
                         Row(('Console', 'File', 'suspend')))

    def test_closed_callback_effects_widen_to_common_ambient_row(self):
        solver = Solver()
        first = solver.weaken(Row(('Console',)))
        second = solver.weaken(Row(('File',)))
        solver.unify(first, second)
        solver.unify(first, Row(('Console', 'File')))
        self.assertEqual(solver.resolve(second), Row(('Console', 'File')))

    def test_repeated_calls_do_not_add_handler_layers(self):
        solver, ambient = Solver(), Var('ambient')
        solver.unify(Row(('Log',), ambient), solver.weaken(Row(('Log',))))
        solver.unify(Row(('Log',), ambient), solver.weaken(Row(('Log',))))
        solver.unify(Row((), ambient), Row())
        self.assertEqual(solver.resolve(Row(('Log',), ambient)), Row(('Log',)))

    def test_shared_tail_cannot_hide_different_prefixes(self):
        for left, right in ((('Log',), ()), (('Log',), ('File',)),
                            (('Log', 'Log'), ('Log',))):
            with self.subTest(left=left, right=right):
                solver, tail = Solver(), Var('e')
                with self.assertRaises(ValueError):
                    solver.unify(Row(left, tail), Row(right, tail))

    def test_indirect_infinite_row_is_rejected(self):
        solver, first, second = Solver(), Var('first'), Var('second')
        solver.unify(Row((), first), Row(('Log',), second))
        with self.assertRaises(ValueError):
            solver.unify(Row((), second), Row(('File',), first))

    def test_generic_tail_is_rigid_while_instantiation_is_flexible(self):
        solver, generic, fresh = Solver(), Var('e', rigid=True), Var('instance')
        solver.unify(Row(('Log',), generic), Row(('Log',), fresh))
        self.assertIs(solver.resolve(Row((), fresh)).tail, generic)
        with self.assertRaises(ValueError):
            solver.unify(Row((), generic), Row(('File',)))

    def test_same_spelling_does_not_alias_distinct_binders(self):
        solver, first, second = Solver(), Var('e'), Var('e')
        solver.unify(Row((), first), Row(('Log',)))
        solver.unify(Row((), second), Row(('File',)))
        self.assertEqual(solver.resolve(Row((), first)), Row(('Log',)))
        self.assertEqual(solver.resolve(Row((), second)), Row(('File',)))


if __name__ == '__main__':
    unittest.main()
