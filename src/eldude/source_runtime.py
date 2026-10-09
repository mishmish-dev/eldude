"""Runtime values, pattern matching, and execution of source feature IR."""
from dataclasses import dataclass, replace

from eldude.handlers import Defect, _bind, _protect_call, _Slot, _Request, _read


@dataclass(frozen=True)
class Variant:
    type: object
    tag: str
    fields: tuple = ()


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
        from eldude.source_declarations import read_slot
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
            from eldude.source_declarations import evaluate_declarations
            return evaluate_declarations(machine, term, environment, evidence, resume)
        case ('using_method', name, initial, body, cleanup):
            def enter(retained):
                slot = _Slot(retained)
                def finish():
                    if not slot.consumed:
                        slot.consumed = True
                        machine.invoke(_read(cleanup, environment), evidence, [retained])
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
            return machine.evaluate_arguments(items, environment, evidence, resume, tuple)
        case ('ref_new', _, initial):
            return _bind(evaluate(initial), Cell)
        case ('buffer_new', _, _):
            return Buffer([])
        case ('primitive_method', method, receiver, arguments, mode):
            inspected = mode in ('view', 'mut') and receiver[0] == 'var'
            first = inspect(receiver[1]) if inspected else evaluate(receiver)
            def invoke(retained):
                def apply(args):
                    if method == 'get':
                        return retained.value
                    if method in ('replace', 'set'):
                        previous, retained.value = retained.value, args[0]
                        return previous if method == 'replace' else None
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
                        return tuple(retained.values)
                    if method == 'remove':
                        index = args[0]
                        if 0 <= index < len(retained):
                            return Variant(None, 'Ok', ((retained[index], retained[:index] + retained[index+1:]),))
                        return Variant(None, 'Err', (({'index': index, 'length': len(retained)}, retained),))
                    if method == 'map':
                        if retained.tag in ('None', 'Err'):
                            return retained
                        return _bind(machine.invoke(args[0], evidence, [retained.fields[0]]), lambda result: Variant(retained.type, retained.tag, (result,)))
                    if method == 'cancel':
                        machine.tasks.cancel(retained)
                        return None
                    raise RuntimeError('Unknown primitive method ' + method)
                return machine.evaluate_arguments(arguments, environment, evidence, resume, apply)
            return _bind(first, invoke)
        case ('for_each', pattern, iterable, body):
            def loop(items, index=0):
                if index == len(items):
                    return None
                bindings = {}
                if not match_value(pattern, items[index], bindings):
                    raise Defect('Nonmatching iteration pattern', term)
                return _bind(evaluate(body, environment | bindings), lambda _: loop(items, index+1))
            return _bind(evaluate(iterable), loop)
        case ('taskgroup', _, body):
            group = machine.tasks.enter()
            def finish(result):
                machine.tasks.leave(group)
                return result
            def shutdown():
                if not group.closed:
                    machine.tasks.leave(group, abnormal=True)
            return _protect_call(lambda: _bind(evaluate(body), finish), shutdown)
        case ('spawn', closure):
            def spawn(function):
                def child():
                    result = machine.invoke(function, evidence, [])
                    while isinstance(result, _Request):
                        result = machine.handle(result.target, result)
                    return result
                return machine.tasks.spawn(child)
            return _bind(evaluate(closure), spawn)
        case ('await', task):
            machine.events.append(('suspend', False))
            return _bind(evaluate(task), machine.tasks.await_result)
    raise RuntimeError('Unknown extended core expression ' + repr(term))
