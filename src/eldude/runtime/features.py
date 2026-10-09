"""Runtime values, pattern matching, and execution of source feature IR."""
from dataclasses import dataclass, replace

from eldude.core.handlers import Defect, _bind, _protect_call, _Slot, _Request, _read


@dataclass(frozen=True)
class Variant:
    type: object
    tag: str
    fields: tuple = ()


@dataclass(frozen=True, slots=True, eq=False)
class ListValue:
    items: list
    start: int
    end: int
    duplicable: bool

    @classmethod
    def from_items(cls, items):
        from eldude.core.handlers import _dup
        return cls(items, 0, len(items), all(_dup(item) for item in items))

    def __len__(self):
        return self.end - self.start

    def __iter__(self):
        return (self.items[index] for index in range(self.start, self.end))

    def __getitem__(self, index):
        if not 0 <= index < len(self):
            raise IndexError(index)
        return self.items[self.start + index]

    def push(self, item):
        from eldude.core.handlers import _dup
        # Fixed bounds keep earlier values unchanged when their storage grows.
        if self.end != len(self.items):
            return ListValue.from_items([*self, item])
        self.items.append(item)
        return ListValue(self.items, self.start, self.end + 1, self.duplicable and _dup(item))

    def tail(self):
        if len(self) == 1:
            return ListValue.from_items([])
        # shortcut: nonempty tails retain storage; compact if long-lived tails need reclamation.
        # The unchanged element type permits a conservative cached Dup result.
        return ListValue(self.items, self.start + 1, self.end, self.duplicable)


def list_next(retained):
    return Variant(None, 'Item', (retained[0], retained.tail())) if retained else Variant(None, 'Done')


@dataclass
class Record:
    type: object
    fields: dict


@dataclass
class Cell:
    value: object


@dataclass
class Buffer:
    values: list


@dataclass
class Package:
    type: object
    value: object
    methods: dict


class EarlyExit(BaseException):
    def __init__(self, key, result):
        self.key, self.result = key, result


def catch_exit(compute, key, finish):
    try:
        result = compute()
    except EarlyExit as error:
        if error.key != key:
            raise
        return error.result
    if isinstance(result, _Request):
        return replace(result, continue_with=lambda supplied: catch_exit(lambda: result.continue_with(supplied), key, finish))
    return finish(result)


def match_value(pattern, retained, output):
    kind = pattern[0]
    if kind == 'wild':
        return True
    if kind == 'bind':
        output[pattern[1]] = _Slot(retained)
        return True
    if kind == 'literal_pat':
        return type(retained) is type(pattern[1]) and retained == pattern[1]
    if kind == 'tuple_pat':
        return isinstance(retained, tuple) and len(retained) == len(pattern)-1 and all(match_value(p, v, output) for p, v in zip(pattern[1:], retained))
    if kind == 'variant_pat':
        return isinstance(retained, Variant) and retained.tag == pattern[2] and len(retained.fields) == len(pattern)-3 and all(match_value(p, v, output) for p, v in zip(pattern[3:], retained.fields))
    if kind == 'record_pat':
        fields = retained.fields if isinstance(retained, Record) else retained
        return all(match_value(p, fields[n], output) for n, p in zip(pattern[2], pattern[3:]))
    return False


def evaluate_feature(machine, term, environment, evidence, resume):
    def evaluate(body, local=environment):
        return machine.evaluate(body, local, evidence, resume)
    def inspect(name):
        from eldude.core.declarations import read_slot
        slot = environment[name]
        if slot.consumed:
            raise RuntimeError(f'Consumed runtime binding {name}')
        return read_slot(name, slot, term)
    match term:
        case ('pack', t, methods, initial):
            return _bind(evaluate(initial), lambda retained: replace(retained, type=t) if isinstance(retained, Package)
                         else Package(t, retained, {method: _read(name, environment) for method, name in methods}))
        case ('dynamic_call', method, receiver, arguments):
            def invoke_package(package):
                # Generic arguments are erased; the checked interface gives
                # exactly one dictionary slot for this canonical trait/member.
                target = next(function for (trait, _, member), function in package.methods.items()
                              if trait == method[0] and member == method[2])
                return machine.evaluate_arguments(arguments, environment, evidence, resume,
                    lambda args: machine.invoke(target, evidence, [package.value, *args]))
            return _bind(evaluate(receiver), invoke_package)
        case ('definitions', _, _, _):
            from eldude.core.declarations import evaluate_declarations
            return evaluate_declarations(machine, term, environment, evidence, resume)
        case ('using_method', name, initial, body, cleanup):
            def enter(retained):
                slot = _Slot(retained)
                def finish():
                    if not slot.consumed:
                        slot.consumed = True
                        task = machine.tasks._current_task
                        if task is not None:
                            task.mask_depth += 1
                        try:
                            machine.invoke(_read(cleanup, environment), evidence, [retained])
                        finally:
                            if task is not None:
                                task.mask_depth -= 1
                return _protect_call(lambda: evaluate(body, environment | {name: slot}), finish)
            return _bind(evaluate(initial), enter)
        case ('nat', number):
            return number
        case ('variant', t, tag, args):
            return machine.evaluate_arguments(args, environment, evidence, resume, lambda values: Variant(t, tag, tuple(values)))
        case ('bindpat', pattern, initial, body):
            def enter(retained):
                bindings = {}
                if not match_value(pattern, retained, bindings):
                    raise Defect('Nonmatching binding pattern', term)
                return evaluate(body, environment | bindings)
            return _bind(evaluate(initial), enter)
        case ('match', subject, arms):
            def select(retained):
                for pattern, body in arms:
                    bindings = {}
                    if match_value(pattern, retained, bindings):
                        return evaluate(body, environment | bindings)
                raise Defect('Non-exhaustive runtime match', term)
            return _bind(evaluate(subject), select)
        case ('exit_scope', key, expected, body, wrap):
            return catch_exit(lambda: evaluate(body), key,
                              lambda result: Variant(expected, 'Ok', (result,)) if wrap else result)
        case ('early', key, argument):
            def leave(result):
                raise EarlyExit(key, result)
            return _bind(evaluate(argument), leave)
        case ('propagate', key, argument):
            def propagate(result):
                if result.tag == 'Err':
                    raise EarlyExit(key, result)
                return result.fields[0]
            return _bind(evaluate(argument), propagate)
        case ('coalesce', option, fallback):
            return _bind(evaluate(option), lambda result: evaluate(fallback) if result.tag == 'None' else result.fields[0])
        case ('access', _, name):
            return inspect(name)
        case ('list_values', _, items):
            return machine.evaluate_arguments(items, environment, evidence, resume, ListValue.from_items)
        case ('ref_new', _, initial):
            return _bind(evaluate(initial), Cell)
        case ('buffer_new', _, _):
            return Buffer([])
        case ('primitive_method', method, receiver, arguments, mode):
            inspected = mode in ('view', 'mut') and receiver[0] == 'var'
            first = inspect(receiver[1]) if inspected else evaluate(receiver)
            def invoke(retained):
                def apply(args):
                    if isinstance(retained, ListValue):
                        if method == 'push':
                            return retained.push(args[0])
                        if method in ('get', 'with'):
                            index = args[0]
                            if not 0 <= index < len(retained):
                                return Variant(None, 'None')
                            if method == 'get':
                                return Variant(None, 'Some', (retained[index],))
                            return _bind(machine.invoke(args[1], evidence, [retained[index]]),
                                         lambda result: Variant(None, 'Some', (result,)))
                        if method in ('remove', 'replace'):
                            index = args[0]
                            if not 0 <= index < len(retained):
                                failure = ({'index': index, 'length': len(retained)}, retained, *args[1:])
                                return Variant(None, 'Err', (failure,))
                            rest = list(retained)
                            rest[index:index+1] = args[1:]
                            return Variant(None, 'Ok', ((retained[index], ListValue.from_items(rest)),))
                        if method in ('filter', 'partition'):
                            selected, rejected = [], []
                            for item in retained:
                                (selected if machine.invoke(args[0], evidence, [item]) else rejected).append(item)
                            return ListValue.from_items(selected) if method == 'filter' else (ListValue.from_items(selected), ListValue.from_items(rejected))
                        if method == 'next':
                            return list_next(retained)
                    if method == 'get':
                        return retained.value
                    if method == 'replace':
                        previous, retained.value = retained.value, args[0]
                        return previous
                    if method == 'length':
                        return len(retained.values if isinstance(retained, Buffer) else retained)
                    if method == 'push':
                        retained.values.append(args[0])
                        return None
                    if method == 'pop':
                        return Variant(None, 'Some', (retained.values.pop(),)) if retained.values else Variant(None, 'None')
                    if method == 'withMut':
                        index, callback = args
                        if not 0 <= index < len(retained.values):
                            return Variant(None, 'None')
                        return _bind(machine.invoke(callback, evidence, [retained.values[index]]),
                                     lambda result: Variant(None, 'Some', (result,)))
                    if method == 'freeze':
                        return ListValue.from_items(retained.values)
                    if method == 'cancel':
                        machine.tasks.cancel(retained)
                        return None
                    raise RuntimeError('Unknown primitive method ' + method)
                return machine.evaluate_arguments(arguments, environment, evidence, resume, apply)
            return _bind(first, invoke)
        case ('for_each', pattern, iterable, body, step):
            def run_body(result):
                bindings = {}
                if not match_value(pattern, result.fields[0], bindings):
                    raise Defect('Nonmatching iteration pattern', term)
                return evaluate(body, environment | bindings)
            def accept(result):
                if result.tag == 'Done':
                    return None
                return _bind(run_body(result), lambda _: loop(result.fields[1]))
            def loop(iterator):
                while True:
                    result = machine.invoke(_read(step, environment), evidence, [iterator]) if step else list_next(iterator)
                    if isinstance(result, _Request):
                        return _bind(result, accept)
                    if result.tag == 'Done':
                        return None
                    body_result = run_body(result)
                    iterator = result.fields[1]
                    if isinstance(body_result, _Request):
                        return _bind(body_result, lambda _: loop(iterator))
            return _bind(evaluate(iterable), loop)
        case ('taskgroup', _, body):
            group = machine.tasks.enter()
            group.handler_evidence = dict(evidence)
            def finish(result):
                machine.tasks.leave(group)
                return result
            def shutdown():
                if not group.closed:
                    machine.tasks.leave(group, abnormal=True)
            return _protect_call(lambda: _bind(evaluate(body), finish), shutdown)
        case ('spawn', closure):
            def spawn(function):
                baseline = machine.tasks.current_group.handler_evidence
                def child():
                    result = machine.invoke(function, baseline, [])
                    while isinstance(result, _Request):
                        result = machine.handle(result.target, result)
                    return result
                return machine.tasks.spawn(child)
            return _bind(evaluate(closure), spawn)
        case ('await', task):
            machine.events.append(('suspend', False))
            return _bind(evaluate(task), machine.tasks.await_result)
    raise RuntimeError('Unknown extended core expression ' + repr(term))
