"""Observable scheduling, ownership and shutdown contracts of resumable tasks."""
import unittest

from eldude.core.handlers import Defect
from eldude.runtime.control import Bind, Call, Ensure, Raise
from eldude.runtime.tasks import TaskCancelled, TaskScheduler


def after(computation, following):
    return Bind(computation, lambda _: Call(following))


def group(scheduler, body):
    def enter():
        scope = scheduler.enter()
        return Ensure(Call(body), lambda error: scheduler.leave(scope, error))
    return Call(enter)


class TaskRuntimeTests(unittest.TestCase):
    def test_spawn_defers_and_normal_exit_drains_discarded_handles(self):
        scheduler, events, scopes = TaskScheduler(), [], []
        def body():
            scopes.append(scheduler.current_group)
            scheduler.spawn(lambda: events.append('first'))
            scheduler.spawn(lambda: events.append('second'))
            self.assertEqual(events, [])
        scheduler.run(group(scheduler, body))
        self.assertEqual(events, ['first', 'second'])
        self.assertTrue(scopes[0].closed)
        self.assertIsNone(scheduler.current_group)

    def test_child_yield_resumes_at_the_back_of_the_fifo_queue(self):
        scheduler, events = TaskScheduler(), []
        def first():
            events.append('first start')
            return after(scheduler.yield_now(), lambda: events.append('first end') or 7)
        def body():
            handle = scheduler.spawn(first)
            scheduler.spawn(lambda: events.append('second'))
            scheduler.spawn(lambda: events.append('third'))
            return scheduler.await_result(handle)
        self.assertEqual(scheduler.run(group(scheduler, body)), 7)
        self.assertEqual(events, ['first start', 'second', 'third', 'first end'])

    def test_observation_and_cancel_consume_handle_once(self):
        scheduler = TaskScheduler()
        def body():
            handle = scheduler.spawn(lambda: 42)
            def completed(result):
                self.assertEqual(result, 42)
                for operation in (scheduler.await_result, scheduler.cancel):
                    with self.assertRaisesRegex(RuntimeError, 'consumed'):
                        operation(handle)
                cancelled = scheduler.spawn(lambda: 1)
                scheduler.cancel(cancelled)
                with self.assertRaisesRegex(RuntimeError, 'consumed'):
                    scheduler.await_result(cancelled)
            return Bind(scheduler.await_result(handle), completed)
        scheduler.run(group(scheduler, body))

    def test_nested_groups_restore_each_strands_context(self):
        scheduler, events = TaskScheduler(), []
        def child():
            self.assertIsNone(scheduler.current_group)
            def inner():
                scope = scheduler.current_group
                handle = scheduler.spawn(lambda: events.append('grandchild'))
                return after(scheduler.await_result(handle), lambda: self.assertIs(scheduler.current_group, scope))
            return after(group(scheduler, inner), lambda: self.assertIsNone(scheduler.current_group))
        def body():
            outer = scheduler.current_group
            scheduler.spawn(child)
            scheduler.spawn(lambda: events.append('sibling'))
            def continued():
                self.assertIs(scheduler.current_group, outer)
                scheduler.spawn(lambda: events.append('last'))
            return after(scheduler.yield_now(), continued)
        scheduler.run(group(scheduler, body))
        self.assertEqual(events, ['sibling', 'grandchild', 'last'])

    def test_cancel_is_request_only_and_delivers_at_yield(self):
        scheduler, events = TaskScheduler(), []
        def child():
            events.append('start')
            return Ensure(after(Call(scheduler.yield_now), lambda: events.append('unreachable')),
                          lambda _: events.append('cleanup'))
        def body():
            scheduler.cancel(scheduler.spawn(child))
            self.assertEqual(events, [])
        scheduler.run(group(scheduler, body))
        self.assertEqual(events, ['start', 'cleanup'])

    def test_cancel_during_yield_and_completion_race(self):
        scheduler, events = TaskScheduler(), []
        def body():
            handle = scheduler.spawn(lambda: Ensure(
                after(Call(scheduler.yield_now), lambda: events.append('unreachable')),
                lambda _: events.append('cleanup')))
            scheduler.spawn(lambda: scheduler.cancel(handle))
            scheduler.cancel(scheduler.spawn(lambda: events.append('pure completed')))
        scheduler.run(group(scheduler, body))
        self.assertEqual(events, ['pure completed', 'cleanup'])

    def test_abnormal_exit_cancels_and_drains(self):
        scheduler, events, scopes = TaskScheduler(), [], []
        def body():
            scopes.append(scheduler.current_group)
            scheduler.spawn(lambda: Ensure(
                after(Call(scheduler.yield_now), lambda: events.append('unreachable')),
                lambda _: events.append('cleanup')))
            return Raise(TaskCancelled())
        with self.assertRaises(TaskCancelled):
            scheduler.run(group(scheduler, body))
        self.assertEqual(events, ['cleanup'])
        self.assertTrue(scopes[0].closed)

    def test_incomplete_await_delivers_cancellation_and_drains_nested_group(self):
        scheduler, events, scopes = TaskScheduler(), [], []
        def inner():
            scopes.append(scheduler.current_group)
            handle = scheduler.spawn(lambda: Ensure(
                after(Call(scheduler.yield_now), lambda: events.append('unreachable')),
                lambda _: events.append('grandchild cleanup')))
            return scheduler.await_result(handle)
        def body():
            child = scheduler.spawn(lambda: Ensure(group(scheduler, inner), lambda _: events.append('child cleanup')))
            scheduler.cancel(child)
        scheduler.run(group(scheduler, body))
        self.assertEqual(events, ['grandchild cleanup', 'child cleanup'])
        self.assertTrue(scopes[0].closed)

    def test_group_shutdown_masks_owner_cancellation_until_children_drain(self):
        scheduler, events, scopes = TaskScheduler(), [], []
        def inner():
            scopes.append(scheduler.current_group)
            scheduler.spawn(lambda: after(Call(scheduler.yield_now), lambda: events.append('grandchild completed')))
        def body():
            handle = scheduler.spawn(lambda: Ensure(
                after(group(scheduler, inner), lambda: events.append('unreachable')),
                lambda _: events.append('child cleanup')))
            scheduler.spawn(lambda: scheduler.cancel(handle))
        scheduler.run(group(scheduler, body))
        self.assertEqual(events, ['grandchild completed', 'child cleanup'])
        self.assertTrue(scopes[0].closed)

    def test_delivered_cancellation_does_not_interrupt_cleanup_yields(self):
        scheduler, events = TaskScheduler(), []
        def body():
            child = scheduler.spawn(lambda: Ensure(Call(scheduler.yield_now), lambda _: after(
                Call(scheduler.yield_now), lambda: events.append('cleanup completed'))))
            scheduler.cancel(child)
        scheduler.run(group(scheduler, body))
        self.assertEqual(events, ['cleanup completed'])

    def test_child_failure_cancels_siblings_and_closes_group(self):
        scheduler, events, scopes = TaskScheduler(), [], []
        defect = ValueError('child defect')
        def body():
            scopes.append(scheduler.current_group)
            scheduler.spawn(lambda: Raise(defect))
            scheduler.spawn(lambda: Ensure(
                after(Call(scheduler.yield_now), lambda: events.append('unreachable')),
                lambda _: events.append('cleanup')))
        with self.assertRaises(ValueError) as caught:
            scheduler.run(group(scheduler, body))
        self.assertIs(caught.exception, defect)
        self.assertEqual(events, ['cleanup'])
        self.assertTrue(scopes[0].closed)

    def test_shutdown_preserves_primary_defect(self):
        scheduler, scopes = TaskScheduler(), []
        primary = RuntimeError('primary')
        def body():
            scopes.append(scheduler.current_group)
            scheduler.spawn(lambda: Raise(ValueError('secondary')))
            return Raise(primary)
        with self.assertRaises(RuntimeError) as caught:
            scheduler.run(group(scheduler, body))
        self.assertIs(caught.exception, primary)
        self.assertIn('secondary', '\n'.join(primary.__notes__))
        self.assertTrue(scopes[0].closed)

    def test_child_defect_supersedes_pending_structural_exit(self):
        class StructuralReturn(BaseException):
            pass
        for primary in (TaskCancelled(), StructuralReturn()):
            scheduler, scopes = TaskScheduler(), []
            def body():
                scopes.append(scheduler.current_group)
                scheduler.spawn(lambda: 1 / 0)
                return Raise(primary)
            with self.subTest(primary=type(primary)), self.assertRaises(ZeroDivisionError):
                scheduler.run(group(scheduler, body))
            self.assertTrue(scopes[0].closed)

    def test_awaited_business_error_is_an_ordinary_value(self):
        scheduler = TaskScheduler()
        error = ('Result::Err', 'missing')
        def body():
            return scheduler.await_result(scheduler.spawn(lambda: error))
        self.assertIs(scheduler.run(group(scheduler, body)), error)

    def test_consumption_releases_completed_result_and_execution_storage(self):
        scheduler, handles = TaskScheduler(), []
        result = object()
        def body():
            handle = scheduler.spawn(lambda: result)
            handles.append(handle)
            def observed(value):
                self.assertIs(value, result)
                self.assertIsNone(handle.result)
                self.assertIsNone(handle.runner)
                completed = scheduler.spawn(lambda: result)
                handles.append(completed)
                return after(Call(scheduler.yield_now), lambda: scheduler.cancel(completed))
            return Bind(scheduler.await_result(handle), observed)
        scheduler.run(group(scheduler, body))
        self.assertTrue(all(handle.result is None and handle.runner is None for handle in handles))

    def test_masked_observer_can_receive_a_child_completion_that_won_cancellation(self):
        scheduler, observed = TaskScheduler(), []
        def body():
            first = scheduler.spawn(lambda: 42)
            def observer():
                task = scheduler._current_task
                task.mask_depth += 1
                def finish(_):
                    task.mask_depth -= 1
                return Ensure(Bind(Call(scheduler.await_result, (first,)), observed.append), finish)
            scheduler.spawn(observer)
            return Raise(TaskCancelled())
        with self.assertRaises(TaskCancelled):
            scheduler.run(group(scheduler, body))
        self.assertEqual(observed, [42])

    def test_scheduler_and_group_boundaries_are_enforced(self):
        first, second = TaskScheduler(), TaskScheduler()
        handles = []
        with self.assertRaisesRegex(RuntimeError, 'taskgroup'):
            first.spawn(lambda: 1)
        def body():
            handle = first.spawn(lambda: 1)
            handles.append(handle)
            with self.assertRaisesRegex(RuntimeError, 'scheduler'):
                second.await_result(handle)
        first.run(group(first, body))
        with self.assertRaisesRegex(RuntimeError, 'closed'):
            first.await_result(handles[0])

    def test_sibling_can_await_a_previously_started_suspended_task(self):
        scheduler = TaskScheduler()
        def body():
            first = scheduler.spawn(lambda: after(Call(scheduler.yield_now), lambda: 40))
            second = scheduler.spawn(lambda: Bind(scheduler.await_result(first), lambda result: result + 2))
            return scheduler.await_result(second)
        self.assertEqual(scheduler.run(group(scheduler, body)), 42)

    def test_dependency_cycle_defects_and_unwinds_each_strand_once(self):
        scheduler, handles, events, scopes = TaskScheduler(), [], [], []
        def body():
            scopes.append(scheduler.current_group)
            for number in range(2):
                def child(number=number):
                    return Ensure(Call(scheduler.await_result, (handles[1 - number],)),
                                  lambda _: events.append(number))
                handles.append(scheduler.spawn(child))
        with self.assertRaisesRegex(Defect, 'dependency cycle'):
            scheduler.run(group(scheduler, body))
        self.assertEqual(sorted(events), [0, 1])
        self.assertTrue(scopes[0].closed)
        self.assertTrue(all(handle.done for handle in handles))


if __name__ == '__main__':
    unittest.main()
