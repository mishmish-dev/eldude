"""Per-execution cooperative tasks for already checked, synchronous thunks.

Source effects, handler installation, resource cleanup and capture validation
belong to the interpreter. TaskCancelled must follow its structural unwind path.
Children begin without a current group; their own taskgroup establishes one.

# ponytail: recursive stepping uses the Python stack; bounded examples only.
Suspended children resume in stack order, while new children start FIFO. A
child cannot wait on a suspended ancestor. A resumable interpreter/trampoline
is needed for arbitrary dependency graphs or unbounded suspension depth.
"""
from collections import deque
from dataclasses import dataclass, field
import sys


class TaskCancelled(BaseException):
    """Cooperative structural exit, never a child business-error value."""


@dataclass(eq=False)
class Group:
    scheduler: object
    parent: object
    owner: object
    children: list = field(default_factory=list)
    failure: BaseException | None = None
    closed: bool = False
    closing: bool = False


@dataclass(eq=False)
class TaskHandle:
    group: Group
    thunk: object
    consumed: bool = False
    cancel_requested: bool = False
    cancel_delivered: bool = False
    running: bool = False
    done: bool = False
    result: object = None
    error: BaseException | None = None
    mask_depth: int = 0


class TaskScheduler:
    def __init__(self):
        self.current_group = None
        self._current_task = None
        self._ready = deque()

    def enter(self):
        group = Group(self, self.current_group, self._current_task)
        self.current_group = group
        return group

    def leave(self, group, abnormal=False):
        """Drain and close a group, preserving an active primary exception.

        Call abnormal leave from the interpreter's exception handler before
        re-raising its structural outcome. Secondary defects become exception
        notes. Defects supersede structural exits, represented by direct
        BaseException subclasses (including TaskCancelled), while Exception
        subclasses represent defects. Host interrupts retain precedence.
        With no active exception, shutdown defects are raised directly.
        """
        if group.scheduler is not self or group is not self.current_group:
            raise RuntimeError('taskgroup must leave in lexical order')
        if group.closed or group.closing or group.owner is not self._current_task:
            raise RuntimeError('taskgroup is closed or not owned by this strand')
        primary = sys.exception() if abnormal else None
        group.closing = True
        task = self._current_task
        if task is not None:
            task.mask_depth += 1
        if abnormal or group.failure is not None:
            self._cancel_group(group)
        try:
            while any(not child.done for child in group.children):
                try:
                    self._step()
                except BaseException as error:
                    self._record_failure(group, error)
        finally:
            group.closed = True
            self.current_group = group.parent
            if task is not None:
                task.mask_depth -= 1
        if group.failure is not None:
            if isinstance(primary, (Exception, KeyboardInterrupt, SystemExit)):
                self._secondary(primary, group.failure)
            else:
                raise group.failure
        if not abnormal:
            self._checkpoint()

    def spawn(self, thunk):
        group = self.current_group
        if group is None or group.closed or group.closing:
            raise RuntimeError('spawn requires an active taskgroup')
        handle = TaskHandle(group, thunk)
        group.children.append(handle)
        self._ready.append(handle)
        return handle

    def await_result(self, handle):
        self._consume(handle)
        while not handle.done:
            self._checkpoint()
            self._step()
            self._checkpoint()
        if handle.error is not None:
            raise handle.error
        return handle.result

    def cancel(self, handle):
        self._consume(handle)
        handle.cancel_requested = True

    def yield_now(self):
        self._checkpoint()
        if self._ready:
            self._step()
        self._checkpoint()

    def _consume(self, handle):
        if not isinstance(handle, TaskHandle) or handle.group.scheduler is not self:
            raise RuntimeError('task handle belongs to another scheduler')
        if handle.consumed:
            raise RuntimeError('task handle already consumed')
        if handle.group.closed:
            raise RuntimeError('taskgroup is closed')
        handle.consumed = True

    def _checkpoint(self):
        task = self._current_task
        if (task is not None and task.cancel_requested
                and not task.cancel_delivered and not task.mask_depth):
            task.cancel_delivered = True
            raise TaskCancelled()

    def _cancel_group(self, group):
        for child in group.children:
            if not child.done:
                child.cancel_requested = True

    @staticmethod
    def _secondary(primary, secondary):
        if primary is not secondary:
            primary.add_note(f'Suppressed child defect: {type(secondary).__name__}: {secondary}')

    def _record_failure(self, group, error):
        if group.failure is None:
            group.failure = error
        else:
            self._secondary(group.failure, error)
        self._cancel_group(group)

    def _step(self):
        if not self._ready:
            raise RuntimeError('Cooperative prototype cannot await a suspended ancestor')
        child = self._ready.popleft()
        previous_task, previous_group = self._current_task, self.current_group
        self._current_task, self.current_group = child, None
        child.running = True
        try:
            child.result = child.thunk()
        except TaskCancelled as error:
            child.error = error
        except BaseException as error:
            child.error = error
            self._record_failure(child.group, error)
        finally:
            child.running = False
            child.done = True
            child.thunk = None
            self._current_task, self.current_group = previous_task, previous_group
        if child.error is not None and not isinstance(child.error, TaskCancelled):
            raise child.error
