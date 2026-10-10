"""Source acceptance for heap evaluation and resumable structured concurrency."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from eldude.core.handlers import Defect, _Machine, run
from eldude.runtime.artifact import decode_program, encode_program
from eldude.source.pipeline import compile_file, compile_source
from eldude.source.syntax import Diagnostic


ROOT = Path(__file__).resolve().parents[2]


class RuntimeContinuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.programs = {path.stem: compile_file(path).program
                        for path in (ROOT / 'examples/src').rglob('runtime_*.eld')}

    def execute(self, name):
        return run(self.programs['runtime_' + name])

    def test_deep_non_tail_and_structurally_terminating_calls(self):
        for name in ('recursion', 'structural_values'):
            with self.subTest(name=name):
                self.assertEqual(self.execute(name).value, 2048)

    def test_fixed_evidence_keeps_the_lexical_instance_during_recursive_reentry(self):
        self.assertEqual(self.execute('fixed_recursion').value, 42)

    def test_repeated_tail_and_once_resumptions_preserve_post_resume_work(self):
        result = self.execute('resumptions')
        self.assertEqual(result.value, 2048)
        self.assertEqual(sum(event[0] == 'dispatch' for event in result.events), 4096)
        self.assertEqual(sum(event[0] == 'resume' for event in result.events), 4096)

    def test_deep_affine_abandonment_closes_each_scope_once_in_reverse_order(self):
        result = self.execute('abandon_cleanup')
        self.assertEqual(result.value, 42)
        self.assertEqual([event[1] for event in result.events if event[0] == 'close'],
                         list(range(2049, 0, -1)))
        self.assertEqual(sum(event[0] == 'abandon' for event in result.events), 1)

    def test_return_and_result_propagation_wait_for_suspending_cleanup(self):
        result = self.execute('cleanup_propagation')
        self.assertEqual(result.value, 42)
        self.assertEqual(result.events, (('suspend', False),) * 2049)

    def test_sibling_await_and_deep_nested_group_dependencies(self):
        for name in ('await_dependency', 'nested_groups'):
            with self.subTest(name=name):
                self.assertEqual(self.execute(name).value, 42)

    def test_repeated_yields_complete_all_children(self):
        result = self.execute('yields')
        self.assertEqual(result.value, 4096)
        self.assertEqual(result.events, (('suspend', False),) * 4096)

    def test_cancellation_during_await_and_shutdown_closes_both_scopes(self):
        for name in ('cancel_await', 'cancel_shutdown'):
            with self.subTest(name=name):
                result = self.execute(name)
                self.assertEqual(result.value, 42)
                self.assertEqual([event[1] for event in result.events if event[0] == 'close'], [2, 1])

    def test_inherited_delimiters_run_without_dispatch_and_keep_parent_only_handlers_out(self):
        for name in ('inherited_return', 'parent_handler'):
            with self.subTest(name=name):
                result = self.execute(name)
                self.assertEqual(result.value, 42)
                self.assertFalse(any(event[0] == 'dispatch' for event in result.events))

    def test_inherited_callback_returned_through_children_keeps_lexical_evidence(self):
        self.assertEqual(self.execute('inherited_closure').value, 42)

    def test_child_defect_is_delivered_once_so_suspending_cleanup_finishes(self):
        self.assertEqual(self.execute('defect_cleanup').value, 42)
        path = ROOT / 'examples/src/06_tasks/runtime_defect_cleanup.eld'
        source = path.read_text().replace('exercise(false)', 'exercise(true)')
        with self.assertRaisesRegex(Defect, 'zero') as caught:
            run(compile_source(source, str(path)).program)
        self.assertEqual(caught.exception.events[-2:], (('acquire', 'File', 1), ('close', 1, 'cleanup')))

    def test_runtime_stack_depth_does_not_follow_calls_resumptions_or_tasks(self):
        original = _Machine._evaluate
        depths, count = [], 0
        def sampled(machine, *arguments):
            nonlocal count
            count += 1
            if count % 257 == 0:
                depth, frame = 0, sys._getframe()
                while frame is not None:
                    depth += 1
                    frame = frame.f_back
                depths.append(depth)
            return original(machine, *arguments)
        limit = sys.getrecursionlimit()
        with patch.object(_Machine, '_evaluate', sampled):
            for name in ('recursion', 'resumptions', 'nested_groups', 'cleanup_propagation'):
                self.execute(name)
        self.assertGreater(len(depths), 100)
        self.assertLessEqual(max(depths) - min(depths), 2)
        self.assertEqual(sys.getrecursionlimit(), limit)

    def test_artifact_roundtrip_keeps_inheritance_and_resumption_frames(self):
        for name in ('resumptions', 'inherited_return', 'parent_handler'):
            program = self.programs['runtime_' + name]
            with self.subTest(name=name):
                restored = decode_program(encode_program(program))
                self.assertEqual(run(restored), run(program))

    def test_consumed_handles_and_unprotected_recursive_suspension_are_rejected(self):
        for name, expected in (('cancel_then_await', 'already consumed'),
                               ('recursive_suspension_owner', 'abandon live resource file')):
            path = ROOT / 'examples/reject/semantics' / ('runtime_' + name + '.eld')
            with self.subTest(name=name), self.assertRaises(Diagnostic) as caught:
                compile_file(path)
            self.assertEqual(caught.exception.code, 'semantic')
            self.assertIn(expected, caught.exception.message)


if __name__ == '__main__':
    unittest.main()
