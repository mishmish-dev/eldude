"""Per-execution FIFO strands, suspended only at explicit runtime operations."""
from collections import deque
from dataclasses import dataclass, field

from eldude.runtime.control import Bind, Call, Pause, Raise, Runner


class TaskCancelled(BaseException):
    """Cooperative structural exit, never a child business-error value."""


@dataclass(eq=False)
class Group:
    scheduler: object
    parent: object
    owner: object
    children: list = field(default_factory=list)
    remaining: int = 0
    failure: BaseException | None = None
    failure_delivered: bool = False
    closed: bool = False
    closing: bool = False
    handler_evidence: dict = field(default_factory=dict)


@dataclass(eq=False)
class TaskHandle:
    group: Group | None
    runner: Runner | None
    consumed: bool = False
    cancel_requested: bool = False
    cancel_delivered: bool = False
    done: bool = False
    result: object = None
    error: BaseException | None = None
    mask_depth: int = 0
    handler_copies: dict = field(default_factory=dict)
    current_group: Group | None = None
    waiting: Pause | None = None
    waiter: object = None
    queued: bool = False


class TaskScheduler:
    def __init__(self):
        self.current_group = None
        self._current_task = None
        self._ready = deque()
        self._live = set()

    def run(self, computation):
        if self._current_task is not None:
            raise RuntimeError('Scheduler is already running')
        root = TaskHandle(None, Runner(computation))
        self._live.add(root)
        self._enqueue(root)
        try:
            while not root.done:
                if not self._ready:
                    self._deadlock()
                task = self._ready.popleft()
                task.queued = False
                self._current_task, self.current_group = task, task.current_group
                pause = task.runner.advance()
                task.current_group = self.current_group
                if task.runner.done:
                    self._complete(task)
                elif pause.kind == 'yield':
                    self._enqueue(task)
                else:
                    task.waiting = pause
                    if pause.kind == 'await':
                        pause.target.waiter = task
        finally:
            self._current_task, self.current_group = None, None
        if root.error is not None:
            raise root.error
        return root.result

    def enter(self):
        group = Group(self, self.current_group, self._current_task)
        self.current_group = group
        return group

    def leave(self, group, primary=None):
        """Drain with cancellation masked, retaining an earlier primary defect."""
        if group.scheduler is not self or group is not self.current_group:
            raise RuntimeError('taskgroup must leave in lexical order')
        if group.closed or group.closing or group.owner is not self._current_task:
            raise RuntimeError('taskgroup is closed or not owned by this strand')
        group.closing = True
        task = self._current_task
        task.mask_depth += 1
        if primary is not None or group.failure is not None:
            self._cancel_group(group)

        def finished(_):
            group.closed = True
            self.current_group = group.parent
            task.mask_depth -= 1
            if group.failure is not None:
                if isinstance(primary, (Exception, KeyboardInterrupt, SystemExit)):
                    self._secondary(primary, group.failure)
                else:
                    if primary is not None:
                        group.failure.add_note(f'Suppressed structural exit: {type(primary).__name__}')
                    raise group.failure
            if primary is None:
                self._checkpoint()
        return Bind(Pause('drain', group) if group.remaining else None, finished)

    def spawn(self, thunk):
        group = self.current_group
        if group is None or group.closed or group.closing:
            raise RuntimeError('spawn requires an active taskgroup')
        handle = TaskHandle(group, Runner(Call(thunk)))
        group.children.append(handle)
        group.remaining += 1
        self._live.add(handle)
        self._enqueue(handle)
        return handle

    def await_result(self, handle):
        self._consume(handle)
        if handle.done:
            return self._result(handle)
        self._checkpoint()
        def completed(_):
            self._checkpoint()
            return self._result(handle)
        return Bind(Pause('await', handle), completed)

    def _result(self, handle):
        if handle.error is not None:
            if handle.group.owner is self._current_task:
                handle.group.failure_delivered = True
            raise handle.error
        if not handle.done:
            raise RuntimeError('Task resumed before its dependency completed')
        result, handle.result = handle.result, None
        return result

    def cancel(self, handle):
        self._consume(handle)
        self._request_cancel(handle)
        handle.result = None

    def yield_now(self):
        self._checkpoint()
        return Bind(Pause('yield'), lambda _: self._checkpoint())

    def _consume(self, handle):
        if not isinstance(handle, TaskHandle) or handle.group is None or handle.group.scheduler is not self:
            raise RuntimeError('task handle belongs to another scheduler')
        if handle.consumed:
            raise RuntimeError('task handle already consumed')
        if handle.group.closed:
            raise RuntimeError('taskgroup is closed')
        handle.consumed = True

    def _checkpoint(self):
        task = self._current_task
        group = self.current_group
        while group is not None:
            if group.failure is not None and not group.closing and not group.failure_delivered:
                group.failure_delivered = True
                raise group.failure
            group = group.parent
        if (task is not None and task.cancel_requested
                and not task.cancel_delivered and not task.mask_depth):
            task.cancel_delivered = True
            raise TaskCancelled()

    def _request_cancel(self, task):
        if task.done:
            return
        task.cancel_requested = True
        if (task.waiting is not None and task.waiting.kind == 'await'
                and not task.mask_depth and not task.cancel_delivered):
            self._enqueue(task)

    def _cancel_group(self, group):
        for child in group.children:
            self._request_cancel(child)

    @staticmethod
    def _secondary(primary, secondary):
        if primary is not secondary:
            primary.add_note(f'Suppressed child defect: {type(secondary).__name__}: {secondary}')
            for note in getattr(secondary, '__notes__', ()):
                primary.add_note(note)

    def _record_failure(self, group, error):
        if group.failure is None:
            group.failure = error
        else:
            self._secondary(group.failure, error)
        self._cancel_group(group)
        owner = group.owner
        if not group.failure_delivered and owner.waiting is not None and owner.waiting.kind == 'await':
            self._enqueue(owner)

    def _enqueue(self, task):
        if task.done or task.queued:
            return
        if task.waiting is not None and task.waiting.kind == 'await':
            task.waiting.target.waiter = None
        task.waiting = None
        task.queued = True
        self._ready.append(task)

    def _complete(self, task):
        task.done = True
        task.result, task.error = task.runner.result, task.runner.error
        task.runner = None
        if task.consumed and task.waiter is None:
            task.result = None
        self._live.remove(task)
        if task.group is not None:
            group = task.group
            group.remaining -= 1
            if task.error is not None and not isinstance(task.error, TaskCancelled):
                self._record_failure(group, task.error)
            if not group.remaining and group.closing:
                self._enqueue(group.owner)
        if task.waiter is not None:
            self._enqueue(task.waiter)

    def _deadlock(self):
        from eldude.core.handlers import Defect
        blocked = next((task for task in self._live if task.waiting is not None
                        and task.waiting.kind == 'await'), None)
        if blocked is None:
            raise RuntimeError('No runnable strand can discharge taskgroup shutdown')
        blocked.runner.computation = Raise(Defect('Unprogressable task dependency cycle', ('await',)))
        self._enqueue(blocked)
