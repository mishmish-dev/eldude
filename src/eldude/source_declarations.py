"""Checked recursive declarations and eager, ordered module initialization.

The frontend supplies SCC/source-ordered globals. These hooks keep declaration
visibility separate from runtime availability; they introduce no trace events.
"""
from dataclasses import dataclass, replace

from eldude.effect_rows import Row
from eldude.handlers import Defect, _Closure, _bind
from eldude.inference import Binding, Context, E, Fn, UNIT, Ty, InferenceError, free_names, permissions, value


UNKNOWN = Ty('Unknown')
UNINITIALIZED = object()


@dataclass
class _Cell:
    value: object = UNINITIALIZED


@dataclass
class GlobalSlot:
    """Copies of an environment slot share the same initialization cell."""
    cell: _Cell
    consumed: bool = False

    @property
    def value(self):
        return self.cell.value

    @value.setter
    def value(self, retained):
        self.cell.value = retained


class DeclarationClosure(_Closure):
    """Named closures are reusable; their shared slots can form runtime cycles."""


def read_slot(name, slot, expression=None):
    """Called by the runtime's ordinary read path for GlobalSlot bindings."""
    if slot.value is UNINITIALIZED:
        raise Defect(f'Module binding {name} is not initialized', expression or E('var', name))
    return slot.value


def _calls(expression, methods, dynamic):
    if not isinstance(expression, tuple) or not expression:
        return set()
    called = {expression[1]} if expression[0] == 'call' else set()
    if expression[0] == 'method_call' and id(expression) in methods:
        called.add(methods[id(expression)][0])
    if id(expression) in dynamic:
        called.update(dynamic[id(expression)][1])
    for child in expression:
        if isinstance(child, tuple):
            called.update(_calls(child, methods, dynamic))
    return called


def _check_recursion(checker, functions):
    methods = getattr(checker, 'method_calls', {})
    dynamic = getattr(checker, 'dynamic_calls', {})
    graph = {name: _calls(body, methods, dynamic) for name, body, _ in functions}
    structural = getattr(checker, 'structural_functions', set())
    for name, body, signature in functions:
        visited, pending = set(), list(graph[name])
        while pending:
            called = pending.pop()
            if called == name:
                if name not in structural and 'diverge' not in signature.effects.labels:
                    raise InferenceError('Recursive function requires structural descent or diverge',
                                         expression=body, subject=name, code='effect')
                break
            if called not in visited:
                visited.add(called)
                pending.extend(graph.get(called, ()))


def infer_declarations(checker, expression, context):
    if expression[0] != 'definitions':
        return None
    _, functions, globals, body = expression
    bindings = {name: Binding(value(signature)) for name, _, signature in functions}
    bindings.update({name: Binding(value(declared or UNKNOWN)) for name, declared, _ in globals})
    if len(bindings) != len(functions) + len(globals):
        raise InferenceError('Duplicate module binding')
    local = replace(context, bindings=context.bindings | bindings,
                    live=context.live + list(bindings.items()), references=set(context.references))

    # Type inference may visit a later initializer first. Evaluation never does.
    # Forward reads therefore remain startup defects, not undefined identifiers.
    pending = list(globals)
    while pending:
        unknown = {name for name, binding in bindings.items() if binding.value.type == UNKNOWN}
        ready = next((entry for entry in pending if not (free_names(entry[2]) & unknown)), None)
        if ready is None:
            name, _, initial = pending[0]
            raise InferenceError('Cyclic global type inference requires an annotation',
                                 expression=initial, subject=name, code='type')
        name, declared, initial = ready
        retained = checker._infer(initial, local)
        if retained.effects.labels or retained.effects.tail:
            raise InferenceError('Module initializer must be pure and terminating', expression=initial, code='effect')
        if permissions(retained.type) != (True, True):
            raise InferenceError('Module initializer result must satisfy Dup + Discard', expression=initial)
        if declared is not None and declared != UNKNOWN:
            checker._apply(value(Fn((declared,), UNIT, Row())), [retained], local)
        bindings[name].value = replace(retained, effects=Row())
        pending.remove(ready)

    for name, closure, signature in functions:
        scope = replace(local, regions=local.regions | {r: r for r in signature.regions},
                        active=local.active | frozenset(signature.regions))
        actual = checker._infer(closure, scope)
        expected = replace(signature, bound=actual.type.bound)
        if hasattr(checker, 'annotate'):
            actual = checker.annotate(closure, actual, expected)
        else:
            checker._apply(value(Fn((expected,), UNIT, Row())), [actual], scope)
            actual = replace(actual, type=replace(actual.type, effects=signature.effects,
                                                  type_vars=signature.type_vars, regions=signature.regions,
                                                  effect_vars=signature.effect_vars))
        if permissions(actual.type) != (True, True):
            raise InferenceError('Named declaration environment must satisfy Dup + Discard', expression=closure)
        bindings[name].value = actual
    _check_recursion(checker, functions)
    return checker._infer(body, local)


def lower_declarations(expression, names, lower):
    if expression[0] != 'definitions':
        return None
    _, functions, globals, body = expression
    return E('definitions', tuple((name, lower(closure, names)) for name, closure, _ in functions),
             tuple((name, lower(initial, names)) for name, _, initial in globals), lower(body, names))


def evaluate_declarations(machine, term, environment, evidence, resume=None):
    if term[0] != 'definitions':
        return NotImplemented
    _, functions, globals, body = term
    local = environment | {name: GlobalSlot(_Cell()) for name, _ in (*functions, *globals)}
    for name, closure in functions:
        _, parameters, captures, fixed, code = closure
        retained = {symbol: local[symbol] for symbol in captures if symbol in local}
        local[name].value = DeclarationClosure(parameters, code, retained,
                                              {key: evidence[key] for key in fixed})

    def initialize(index):
        if index == len(globals):
            return machine.evaluate(body, local, evidence, resume)
        name, initial = globals[index]

        def available(retained):
            local[name].value = retained
            return initialize(index + 1)

        return _bind(machine.evaluate(initial, local, evidence, resume), available)

    return initialize(0)
