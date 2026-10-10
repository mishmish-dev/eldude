"""List storage costs and sharing, alongside source-level contract coverage."""
import unittest
from unittest.mock import patch

from eldude.core import handlers
from eldude.runtime.features import ListValue, list_next


class ListStorageTests(unittest.TestCase):
    def test_large_list_construction_uses_constant_stack(self):
        machine = handlers._Machine({})
        values = machine.tasks.run(machine.evaluate(('list_values', None, tuple(('int', n) for n in range(4096))), {}, {}))
        self.assertEqual(list(values), list(range(4096)))

    def test_append_and_next_share_storage_without_rescanning_elements(self):
        values = ListValue.from_items([])
        storage = values.items
        with patch.object(handlers, '_dup', wraps=handlers._dup) as duplication:
            for number in range(4096):
                values = values.push(number)
                self.assertTrue(handlers._dup(values))
            self.assertLessEqual(duplication.call_count, 8192)
        self.assertIs(values.items, storage)
        self.assertEqual(len(values), 4096)
        with patch.object(handlers, '_dup', wraps=handlers._dup) as duplication:
            for number in range(4096):
                result = list_next(values)
                self.assertEqual(result.tag, 'Item')
                head, values = result.fields
                self.assertEqual(head, number)
                if values:
                    self.assertIs(values.items, storage)
                self.assertTrue(handlers._dup(values))
            self.assertLessEqual(duplication.call_count, 4096)
        self.assertEqual(list_next(values).tag, 'Done')

    def test_branching_append_copies_only_the_visible_range(self):
        original = ListValue.from_items([10, 20, 30])
        tail = list_next(original).fields[1]
        grown = tail.push(40)
        branch = tail.push(50)
        self.assertIs(grown.items, original.items)
        self.assertIsNot(branch.items, original.items)
        self.assertEqual(branch.items, [20, 30, 50])
        for values, expected in ((original, [10, 20, 30]), (tail, [20, 30]),
                                 (grown, [20, 30, 40]), (branch, [20, 30, 50])):
            self.assertEqual(list(values), expected)
            self.assertEqual(len(values), len(expected))
            with self.assertRaises(IndexError):
                values[len(values)]
            with self.assertRaises(IndexError):
                values[-1]

    def test_owned_elements_still_consume_runtime_bindings(self):
        resource = handlers._Resource('File', 1)
        values = ListValue.from_items([]).push(resource)
        environment = {'values': handlers._Slot(values)}
        self.assertIs(handlers._read('values', environment), values)
        with self.assertRaisesRegex(RuntimeError, 'Consumed'):
            handlers._read('values', environment)
        first, empty = list_next(values).fields
        self.assertIs(first, resource)
        self.assertEqual(list(empty), [])
        self.assertEqual(list(empty.push(42)), [42])


if __name__ == '__main__':
    unittest.main()
