"""Observable scheduling, ownership and shutdown contracts of the prototype."""
import unittest

from eldude.task_runtime import TaskCancelled, TaskScheduler


class TaskRuntimeTests(unittest.TestCase):
    def test_spawn_defers_and_normal_exit_drains_discarded_handles(self):
        scheduler = TaskScheduler()
        group = scheduler.enter()
        events = []
        scheduler.spawn(lambda: events.append('first'))
        scheduler.spawn(lambda: events.append('second'))
        self.assertEqual(events, [])
        scheduler.leave(group)
        self.assertEqual(events, ['first', 'second'])
        self.assertTrue(group.closed)
        self.assertIsNone(scheduler.current_group)

    def test_child_yield_makes_fifo_progress(self):
        scheduler = TaskScheduler()
        group = scheduler.enter()
        events = []

        def first():
            events.append('first start')
            scheduler.yield_now()
            events.append('first end')
            return 7

        handle = scheduler.spawn(first)
        scheduler.spawn(lambda: events.append('second'))
        scheduler.spawn(lambda: events.append('third'))
        self.assertEqual(scheduler.await_result(handle), 7)
        self.assertEqual(events, ['first start', 'second', 'first end'])
        scheduler.leave(group)
        self.assertEqual(events[-1], 'third')

    def test_observation_and_cancel_consume_handle_once(self):
        scheduler = TaskScheduler()
        group = scheduler.enter()
        handle = scheduler.spawn(lambda: 42)
        self.assertEqual(scheduler.await_result(handle), 42)
        for operation in (scheduler.await_result, scheduler.cancel):
            with self.assertRaisesRegex(RuntimeError, 'consumed'):
                operation(handle)
        cancelled = scheduler.spawn(lambda: 1)
        scheduler.cancel(cancelled)
        with self.assertRaisesRegex(RuntimeError, 'consumed'):
            scheduler.await_result(cancelled)
        scheduler.leave(group)

    def test_nested_groups_restore_each_strands_context(self):
        scheduler = TaskScheduler()
        outer = scheduler.enter()
        events = []

        def child():
            self.assertIsNone(scheduler.current_group)
            inner = scheduler.enter()
            handle = scheduler.spawn(lambda: events.append('grandchild'))
            scheduler.await_result(handle)
            self.assertIs(scheduler.current_group, inner)
            scheduler.leave(inner)
            self.assertIsNone(scheduler.current_group)

        scheduler.spawn(child)
        scheduler.spawn(lambda: events.append('sibling'))
        scheduler.yield_now()
        self.assertIs(scheduler.current_group, outer)
        scheduler.spawn(lambda: events.append('last'))
        scheduler.leave(outer)
        self.assertEqual(events, ['sibling', 'grandchild', 'last'])

    def test_cancel_is_request_only_and_delivers_at_yield(self):
        scheduler = TaskScheduler()
        group = scheduler.enter()
        events = []

        def child():
            try:
                events.append('start')
                scheduler.yield_now()
                events.append('unreachable')
            finally:
                events.append('cleanup')

        handle = scheduler.spawn(child)
        scheduler.cancel(handle)
        self.assertEqual(events, [])
        scheduler.leave(group)
        self.assertEqual(events, ['start', 'cleanup'])

    def test_cancel_during_yield_and_completion_race(self):
        scheduler = TaskScheduler()
        group = scheduler.enter()
        events = []

        def child():
            try:
                scheduler.yield_now()
                events.append('unreachable')
            finally:
                events.append('cleanup')

        handle = scheduler.spawn(child)
        scheduler.spawn(lambda: scheduler.cancel(handle))
        pure = scheduler.spawn(lambda: events.append('pure completed'))
        scheduler.cancel(pure)
        scheduler.leave(group)
        self.assertEqual(events, ['cleanup', 'pure completed'])

    def test_abnormal_exit_cancels_and_drains(self):
        scheduler = TaskScheduler()
        group = scheduler.enter()
        events = []

        def child():
            try:
                scheduler.yield_now()
                events.append('unreachable')
            finally:
                events.append('cleanup')

        scheduler.spawn(child)
        scheduler.leave(group, abnormal=True)
        self.assertEqual(events, ['cleanup'])
        self.assertTrue(group.closed)
        self.assertIsNone(scheduler.current_group)

    def test_incomplete_await_delivers_cancellation_and_drains_nested_group(self):
        scheduler = TaskScheduler()
        outer = scheduler.enter()
        events = []
        nested = []

        def grandchild():
            try:
                scheduler.yield_now()
                events.append('unreachable')
            finally:
                events.append('grandchild cleanup')

        def child():
            inner = scheduler.enter()
            nested.append(inner)
            handle = scheduler.spawn(grandchild)
            try:
                scheduler.await_result(handle)
            except BaseException:
                scheduler.leave(inner, abnormal=True)
                raise
            finally:
                events.append('child cleanup')

        handle = scheduler.spawn(child)
        scheduler.cancel(handle)
        scheduler.leave(outer)
        self.assertEqual(events, ['grandchild cleanup', 'child cleanup'])
        self.assertTrue(nested[0].closed)
        self.assertIsNone(scheduler.current_group)

    def test_group_shutdown_masks_owner_cancellation_until_children_drain(self):
        scheduler = TaskScheduler()
        outer = scheduler.enter()
        events = []
        nested = []

        def grandchild():
            scheduler.yield_now()
            events.append('grandchild completed')

        def child():
            inner = scheduler.enter()
            nested.append(inner)
            scheduler.spawn(grandchild)
            try:
                scheduler.leave(inner)
                events.append('unreachable')
            finally:
                events.append('child cleanup')

        handle = scheduler.spawn(child)
        scheduler.spawn(lambda: scheduler.cancel(handle))
        scheduler.leave(outer)
        self.assertEqual(events, ['grandchild completed', 'child cleanup'])
        self.assertTrue(nested[0].closed)

    def test_delivered_cancellation_does_not_interrupt_cleanup_yields(self):
        scheduler = TaskScheduler()
        group = scheduler.enter()
        events = []

        def child():
            try:
                scheduler.yield_now()
            finally:
                scheduler.yield_now()
                events.append('cleanup completed')

        handle = scheduler.spawn(child)
        scheduler.cancel(handle)
        scheduler.leave(group)
        self.assertEqual(events, ['cleanup completed'])

    def test_child_failure_cancels_siblings_and_closes_group(self):
        scheduler = TaskScheduler()
        group = scheduler.enter()
        events = []
        defect = ValueError('child defect')

        def fail():
            raise defect

        def sibling():
            try:
                scheduler.yield_now()
                events.append('unreachable')
            finally:
                events.append('cleanup')

        scheduler.spawn(fail)
        scheduler.spawn(sibling)
        with self.assertRaises(ValueError) as caught:
            scheduler.leave(group)
        self.assertIs(caught.exception, defect)
        self.assertEqual(events, ['cleanup'])
        self.assertTrue(group.closed)
        self.assertIsNone(scheduler.current_group)

    def test_shutdown_preserves_primary_defect(self):
        scheduler = TaskScheduler()
        group = scheduler.enter()

        def fail():
            raise ValueError('secondary')

        scheduler.spawn(fail)
        primary = RuntimeError('primary')
        try:
            raise primary
        except RuntimeError:
            scheduler.leave(group, abnormal=True)
        self.assertIn('secondary', '\n'.join(primary.__notes__))
        self.assertTrue(group.closed)

    def test_child_defect_supersedes_pending_cancellation(self):
        scheduler = TaskScheduler()
        group = scheduler.enter()
        scheduler.spawn(lambda: 1 / 0)
        with self.assertRaises(ZeroDivisionError):
            try:
                raise TaskCancelled()
            except TaskCancelled:
                scheduler.leave(group, abnormal=True)
        self.assertTrue(group.closed)

    def test_child_defect_supersedes_pending_structural_return(self):
        class StructuralReturn(BaseException):
            pass

        scheduler = TaskScheduler()
        group = scheduler.enter()
        scheduler.spawn(lambda: 1 / 0)
        with self.assertRaises(ZeroDivisionError):
            try:
                raise StructuralReturn()
            except StructuralReturn:
                scheduler.leave(group, abnormal=True)
        self.assertTrue(group.closed)

    def test_awaited_business_error_is_an_ordinary_value(self):
        scheduler = TaskScheduler()
        group = scheduler.enter()
        error = ('Result::Err', 'missing')
        handle = scheduler.spawn(lambda: error)
        self.assertIs(scheduler.await_result(handle), error)
        scheduler.leave(group)

    def test_scheduler_and_group_boundaries_are_enforced(self):
        first, second = TaskScheduler(), TaskScheduler()
        with self.assertRaisesRegex(RuntimeError, 'taskgroup'):
            first.spawn(lambda: 1)
        group = first.enter()
        handle = first.spawn(lambda: 1)
        with self.assertRaisesRegex(RuntimeError, 'scheduler'):
            second.await_result(handle)
        first.leave(group)
        with self.assertRaisesRegex(RuntimeError, 'closed'):
            first.await_result(handle)


if __name__ == '__main__':
    unittest.main()
