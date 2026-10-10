"""Heap continuations shared by evaluation, handlers, and cooperative strands."""
from dataclasses import dataclass


@dataclass
class Call:
    function: object
    arguments: tuple = ()


@dataclass
class Bind:
    computation: object
    then: object


@dataclass
class Ensure:
    computation: object
    finish: object


@dataclass
class Catch:
    computation: object
    recover: object


@dataclass
class Handle:
    computation: object
    handler: object
    returned: object
    operation: object


@dataclass
class Restore:
    computation: object
    frames: list


@dataclass
class Raise:
    error: BaseException


@dataclass
class Pause:
    kind: str
    target: object = None


class _Abandon(BaseException):
    """Unwind only the captured segment, without returning through its binds."""


class Continuation:
    def __init__(self, request, frames):
        self.request, self.frames = request, frames

    def _take(self):
        if self.frames is None:
            raise RuntimeError('Runtime resumption capability already used')
        frames, self.frames = self.frames, None
        return frames

    def resume(self, result):
        return Restore(Call(self.request.continue_with, (result,)), self._take())

    def abandon(self):
        def abandoned(error):
            if not isinstance(error, _Abandon):
                raise error
        unwind = Bind(Call(self.request.abandon), lambda _: Raise(_Abandon()))
        return Catch(Restore(unwind, self._take()), abandoned)


class Runner:
    """Reduce a computation until it finishes or reaches a semantic suspension."""
    def __init__(self, computation):
        self.computation = computation
        self.frames = []
        self.done = False
        self.result = None
        self.error = None

    @staticmethod
    def _cleanup_error(primary, secondary):
        if isinstance(primary, (Exception, KeyboardInterrupt, SystemExit)):
            if primary is not secondary:
                primary.add_note(f'Suppressed cleanup defect: {type(secondary).__name__}: {secondary}')
                for note in getattr(secondary, '__notes__', ()):
                    primary.add_note(note)
            return primary
        return secondary

    def advance(self):
        from dataclasses import replace
        from eldude.core.handlers import _Request
        current = self.computation
        while True:
            try:
                if isinstance(current, Call):
                    current = current.function(*current.arguments)
                elif isinstance(current, Bind):
                    self.frames.append(('bind', current.then))
                    current = current.computation
                elif isinstance(current, Ensure):
                    self.frames.append(('ensure', current.finish))
                    current = current.computation
                elif isinstance(current, Catch):
                    self.frames.append(('catch', current.recover))
                    current = current.computation
                elif isinstance(current, Handle):
                    self.frames.append(current)
                    current = current.computation
                elif isinstance(current, Restore):
                    self.frames.extend(current.frames)
                    current = current.computation
                elif isinstance(current, Pause):
                    self.computation = None
                    return current
                elif isinstance(current, _Request):
                    index = len(self.frames) - 1
                    while index >= 0:
                        frame = self.frames[index]
                        if isinstance(frame, Handle) and frame.handler is current.target:
                            break
                        index -= 1
                    if index < 0:
                        raise RuntimeError('Unhandled runtime evidence target')
                    continuation = Continuation(current, self.frames[index + 1:])
                    del self.frames[index:]
                    request = replace(current, continue_with=continuation.resume, abandon=continuation.abandon)
                    current = Call(frame.operation, (frame.handler, request))
                elif isinstance(current, Raise):
                    if not self.frames:
                        self.error, self.done = current.error, True
                        return None
                    frame = self.frames.pop()
                    if isinstance(frame, Handle):
                        continue
                    kind, *args = frame
                    if kind == 'ensure':
                        self.frames.append(('finished', None, current.error))
                        current = Call(args[0], (current.error,))
                    elif kind == 'catch':
                        current = Call(args[0], (current.error,))
                    elif kind == 'finished' and args[1] is not None:
                        current = Raise(self._cleanup_error(args[1], current.error))
                elif not self.frames:
                    self.result, self.done = current, True
                    return None
                else:
                    frame = self.frames.pop()
                    if isinstance(frame, Handle):
                        current = Call(frame.returned, (frame.handler, current))
                        continue
                    kind, *args = frame
                    if kind == 'bind':
                        current = Call(args[0], (current,))
                    elif kind == 'ensure':
                        self.frames.append(('finished', current, None))
                        current = Call(args[0], (None,))
                    elif kind == 'finished':
                        result, error = args
                        current = Raise(error) if error is not None else result
            except BaseException as error:
                current = Raise(error)
