"""Evidence selection never instantiates the caller or ignores prerequisites."""
import unittest

from eldude.inference import Ty, INT
from eldude.trait_constraints import TraitSolver, Implementation, overlap


class TraitConstraintTests(unittest.TestCase):
    def test_prerequisites_and_one_way_selection(self):
        t = Ty('$T')
        leaf = Ty('Leaf')
        goal = lambda x: Ty('Trait:Read', (x,))
        wrapper = lambda x: Ty('Wrapper', (x,))
        solver = TraitSolver()
        solver.add(Implementation(goal(wrapper(t)), ('T',), prerequisites=(goal(t),)))
        with self.assertRaisesRegex(ValueError, 'Missing trait evidence'):
            solver.select_impl(goal(wrapper(leaf)))
        solver.add(Implementation(goal(leaf)))
        selected, types, _ = solver.select_impl(goal(wrapper(leaf)))
        self.assertEqual(types, {'T': leaf})
        self.assertEqual(selected.head, goal(wrapper(t)))
        with self.assertRaisesRegex(ValueError, 'Missing trait evidence'):
            solver.select_impl(goal(Ty('$Caller')))
        self.assertEqual(solver.select_impl(goal(t), (goal(t),)), (None, {}, {}))

    def test_overlap_occurs_check_and_full_arguments(self):
        t, u = Ty('$T'), Ty('$U')
        head = lambda a, b: Ty('Trait:Read', (a, b))
        a = Implementation(head(t, Ty('List', (t,))), ('T',))
        b = Implementation(head(Ty('List', (u,)), u), ('U',))
        self.assertFalse(overlap(a, b))
        solver = TraitSolver()
        solver.add(Implementation(head(Ty('Box'), INT)))
        solver.add(Implementation(head(Ty('Box'), Ty('Bool'))))
        with self.assertRaisesRegex(ValueError, 'Overlapping'):
            solver.add(Implementation(head(Ty('Box'), t), ('T',)))

    def test_equations_preserve_obligations_and_reject_cycles(self):
        solver = TraitSolver()
        projection = Ty('Projection:Read:Item', (Ty('Leaf'),))
        solver.add(Implementation(Ty('Trait:Read', (Ty('Leaf'),)),
                                  prerequisites=(Ty('Trait:Dup', (Ty('Owned'),)),), equations={'Item': INT}))
        with self.assertRaisesRegex(ValueError, 'Missing trait evidence'):
            solver.normalize_type(projection)
        variable = Ty('$T')
        with self.assertRaisesRegex(ValueError, 'occurs'):
            solver.normalize_type(variable, (Ty('Equality', (variable, Ty('List', (variable,)))),))
        p, q = Ty('Projection:X:A', (variable,)), Ty('Projection:X:B', (variable,))
        with self.assertRaisesRegex(ValueError, 'Cyclic'):
            solver.normalize_type(p, (Ty('Equality', (p, q)), Ty('Equality', (q, p))))
