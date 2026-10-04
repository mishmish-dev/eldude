"""Small annotated-core inference experiment for Eldude.

Infers result types, ambient effect rows, whole-value capture bounds and a
ownership checks with conservative branch joins. Inputs are expression IR, not Eldude
source. Parameter types/usage bounds and primitive contracts are supplied.
Only tail handler delimiters are modeled; handler clause bodies, resumptions,
tasks, traits, higher-rank types, loops and general mutable grants are not.
Cancellation is a static abandonment check, not an executed scheduler.
"""
from collections import Counter
from dataclasses import dataclass, field, replace
import json

from effect_rows import Row, Solver, Var


class InferenceError(ValueError):
    def __init__(self, message, *, expression=None, subject=None, code='semantic'):
        super().__init__(message)
        self.expression, self.subject, self.code = expression, subject, code


@dataclass(frozen=True)
class Ty:
    name: str
    args: tuple = ()
    region: str | None = None


INT, UNIT, BOOL = Ty('Int'), Ty('Unit'), Ty('Bool')


@dataclass(frozen=True)
class Fn:
    parameters: tuple
    result: object
    effects: Row
    bound: frozenset = frozenset()
    type_vars: tuple = ()
    regions: tuple = ()
    effect_vars: tuple = ()
    dup: bool = True
    discard: bool = True

    def dumps(self):
        def encode(t):
            if isinstance(t, Ty):
                return {'type': t.name, 'args': [encode(a) for a in t.args], 'region': t.region}
            return {'parameters': [encode(p) for p in t.parameters], 'result': encode(t.result),
                    'effects': list(t.effects.labels),
                    'tail': t.effects.tail.name if t.effects.tail else None,
                    'bound': sorted(t.bound), 'type_vars': list(t.type_vars),
                    'regions': list(t.regions), 'effect_vars': [v.name for v in t.effect_vars],
                    'dup': t.dup, 'discard': t.discard}
        return json.dumps(encode(self), sort_keys=True)

    @staticmethod
    def loads(wire):
        def decode(data, variables):
            if 'type' in data:
                return Ty(data['type'], tuple(decode(a, variables) for a in data['args']), data['region'])
            if 'bound' not in data:
                raise InferenceError('Imported callable is missing its capture bound')
            quantified = tuple(Var(name, rigid=True) for name in data['effect_vars'])
            scope = variables | {v.name: v for v in quantified}
            tail = scope[data['tail']] if data['tail'] is not None else None
            return Fn(tuple(decode(p, scope) for p in data['parameters']),
                      decode(data['result'], scope), Row(tuple(data['effects']), tail),
                      frozenset(data['bound']), tuple(data['type_vars']),
                      tuple(data['regions']), quantified, data['dup'], data['discard'])
        try:
            result = decode(json.loads(wire), {})
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise InferenceError('Malformed imported contract') from error
        if not isinstance(result, Fn):
            raise InferenceError('Expected a callable contract')
        return result


def E(kind, *arguments):
    """Construct one expression in the deliberately small input IR."""
    return (kind, *arguments)


@dataclass(frozen=True)
class Value:
    type: object
    effects: Row = Row()
    captures: frozenset = frozenset()


@dataclass(eq=False)
class Binding:
    value: Value
    consumed: bool = False
    managed: bool = False
    mode: str | None = None


@dataclass
class Context:
    bindings: dict = field(default_factory=dict)
    live: list = field(default_factory=list)
    regions: dict = field(default_factory=dict)
    handlers: tuple = ()
    names: dict = field(default_factory=dict)
    active: frozenset = frozenset()
    references: set = field(default_factory=set)
    named_references: set = field(default_factory=set)
    temporaries: list = field(default_factory=list)
    trace: bool = True
    resumption: object = None
    suspended: tuple = ()
    blocked_family: str | None = None
    group: object = None


def state(region):
    return f'state<@{region}>'


def permissions(t):
    if isinstance(t, Fn):
        return t.dup, t.discard
    if t.name.startswith('Record:'):
        fields = [permissions(f.args[0]) for f in t.args]
        return all(p[0] for p in fields), all(p[1] for p in fields)
    if t.name == 'Linear':
        return False, False
    if t.name in ('View', 'Mut'):
        return True, True
    if t.name == 'Affine':
        return False, permissions(t.args[0])[1]
    if t.name == 'Task':
        return False, True
    if t.name.startswith('$') or t.name == 'Owned':
        return False, False
    if t.name == 'DynArray':
        return False, permissions(t.args[0])[1]
    if t.name == 'Ref':
        return True, True
    return all(permissions(a)[0] for a in t.args), all(permissions(a)[1] for a in t.args)


def capture_free(t):
    # Unknown callable environments/opaque types are deliberately conservative.
    return isinstance(t, Ty) and (t.name in ('Int', 'Unit', 'Bool', 'Nat', 'Never') or
        (t.name in ('List', 'Tuple', 'Option', 'Result') and all(capture_free(a) for a in t.args)) or
        (t.name.startswith('Record:') and all(capture_free(a.args[0]) for a in t.args)))


def required_captures(t):
    if isinstance(t, Fn):
        result = set(required_captures(t.result))
        for p in t.parameters:
            result.update(required_captures(p))
        for label in t.effects.labels:
            if label.startswith('state<@'):
                result.add(label[7:-1])
            elif '@handler:' in label:
                result.add(label)
        return frozenset(result.difference(t.regions))
    result = {t.region} if t.region else set()
    for a in t.args:
        result.update(required_captures(a))
    return frozenset(result)


def value(t, effects=Row(), captures=frozenset()):
    captures = frozenset() if capture_free(t) else frozenset(captures) | required_captures(t)
    return Value(t, effects, captures)


def ambient(*rows):
    """Common ambient row: permitted weakening, never execution-count addition."""
    if not rows:
        return Row()
    rigid = {r.tail for r in rows if r.tail and r.tail.rigid}
    if rigid:
        if len(rigid) != 1 or any(r.tail and r.tail not in rigid for r in rows):
            raise InferenceError('Independent rigid effect tails need a shared-row contract')
        prefix = Counter()
        for row in rows:
            prefix |= Counter(row.labels)
        return Row(tuple(prefix.elements()), next(iter(rigid)))
    solver = Solver()
    result = solver.weaken(rows[0])
    for row in rows[1:]:
        solver.unify(result, solver.weaken(row))
    result = solver.resolve(result)
    if result.tail:
        solver.unify(Row((), result.tail), Row())
    return solver.resolve(result)


def free_names(expression, bound=frozenset()):
    match expression:
        case ('variant', _, _, args):
            return set().union(*(free_names(a, bound) for a in args))
        case ('bindpat', pattern, initial, body) | ('for_each', pattern, initial, body):
            from source_features import pattern_bindings
            return free_names(initial, bound) | free_names(body, bound | pattern_bindings(pattern))
        case ('match', subject, arms):
            from source_features import pattern_bindings
            return free_names(subject, bound) | set().union(*(free_names(body, bound | pattern_bindings(p)) for p, body in arms))
        case ('exit_scope', _, _, body, _):
            return free_names(body, bound)
        case ('list_values', _, items):
            return set().union(*(free_names(a, bound) for a in items))
        case ('primitive_method' | 'method_call', _, receiver, args, _):
            return free_names(receiver, bound) | set().union(*(free_names(a, bound) for a in args))
        case ('access', _, name):
            return {name} - bound
        case ('definitions', functions, globals_, body):
            local = bound | {s for s, _, _ in functions} | {s for s, _, _ in globals_}
            return free_names(body, local) | set().union(*(free_names(b, local) for _, b, _ in functions),
                                                         *(free_names(b, local) for _, _, b in globals_))
        case ('var', name):
            return {name} - bound
        case ('call', name, *arguments):
            return ({name} - bound).union(*(free_names(a, bound) for a in arguments))
        case ('let' | 'using', name, initializer, body):
            return free_names(initializer, bound) | free_names(body, bound | {name})
        case ('unpack', pattern, initializer, body):
            return free_names(initializer, bound) | free_names(body, bound | pattern_names(pattern))
        case ('record', _, _, *items):
            return set().union(*(free_names(a, bound) for a in items))
        case ('specialize', callee, _):
            return free_names(callee, bound)
        case ('lambda', parameters, body):
            return free_names(body, bound | {name for name, _ in parameters})
        case ('clause', parameters, body):
            return free_names(body, bound | set(parameters))
        case ('perform_args', _, arguments, *_):
            return set().union(*(free_names(a, bound) for a in arguments))
        case ('perform_op', _, _, arguments, *_):
            return set().union(*(free_names(a, bound) for a in arguments))
        case ('handle_ops', _, _, body, clauses, returning):
            return free_names(body, bound) | free_names(returning, bound) | set().union(
                *(free_names(clause, bound) for _, clause in clauses))
        case ('returning', name, body):
            return free_names(body, bound | {name})
        case _:
            children = [a for a in expression[1:] if isinstance(a, tuple)]
            return set().union(*(free_names(a, bound) for a in children))


def pattern_names(pattern):
    return set().union(*(pattern_names(p) for p in pattern)) if isinstance(pattern, tuple) else {pattern}


class Checker:
    def __init__(self, imports=None, cleanups=None):
        self.functions = {
            'yield': Fn((), UNIT, Row(('suspend',))),
            'close': Fn((Ty('Owned', (Ty('File'),)),), UNIT, Row()),
            'freeze': Fn((Ty('DynArray', (Ty('$T'),), 'r'),),
                         Ty('List', (Ty('$T'),)), Row((state('r'),)),
                         frozenset(('arg:0',)), type_vars=('T',), regions=('r',)),
        } | (imports or {})
        self.cleanup_rows = {'File': Row(), 'AsyncFile': Row(('suspend',))} | (cleanups or {})
        self.modes = {'Log': 'tail', 'Abort': 'affine'}
        self.handler_ids = {}
        self.dispatches, self.cleanups, self.handled_rows = [], [], {}
        self.scope_depth = {}
        self.counter = 0
        self.current_expression = None
        self.transfers = {}

    def fresh(self, name):
        self.counter += 1
        return f'{name}#{self.counter}'

    def label_name(self, label):
        return self.handler_ids[label][1]

    def infer(self, expression):
        return self._infer(expression, Context())

    def define(self, name, parameters, body, *, type_vars=(), regions=(), effect_vars=()):
        context = Context(regions={r: r for r in regions}, active=frozenset(regions), trace=False)
        result = self._function(parameters, body, context)
        signature = replace(result.type, type_vars=tuple(type_vars), regions=tuple(regions),
                            effect_vars=tuple(effect_vars))
        allowed = {f'arg:{i}' for i in range(len(parameters))} | set(regions)
        if not signature.bound <= allowed:
            raise InferenceError('Definition has an unexpressible public capture bound')
        self.functions[name] = signature
        return signature

    def _lookup(self, name, context):
        if name not in context.bindings:
            if name in self.functions:
                return value(self.functions[name])
            raise InferenceError(f'Unknown value {name}')
        binding = context.bindings[name]
        if binding.consumed:
            raise InferenceError(f'{name} was already consumed', subject=name)
        context.references.add(binding)
        if binding.mode and not permissions(binding.value.type)[0]:
            raise InferenceError('Access grant cannot transfer its owner', subject=name)
        if not permissions(binding.value.type)[0]:
            binding.consumed = True
            self.transfers[name] = self.current_expression
        return binding.value

    def _resolve(self, row, context):
        labels = Counter()
        for label, count in Counter(row.labels).items():
            selected = []
            if label in self.handler_ids:
                if label not in context.active:
                    raise InferenceError('Named handler is outside its scope')
                selected = [label] * count
            elif label in self.modes:
                matches = [key for family, key in reversed(context.handlers) if family == label]
                selected = matches[:count] + [label] * max(0, count - len(matches))
            else:
                if label.startswith('state<@') and label.endswith('>'):
                    if label[7:-1] not in context.active:
                        raise InferenceError('State region is outside its scope')
                elif label not in ('suspend', 'diverge'):
                    raise InferenceError(f'Unknown effect {label}')
                selected = [label] * count
            # Selection may discover that a named and an ambient demand use
            # the same instance. Reuse that slot; row equality stays unchanged.
            labels |= Counter(selected)
            if context.trace:
                self.dispatches.extend(self.handler_ids[key] for key in selected if key in self.handler_ids)
        return Row(tuple(labels.elements()), row.tail)

    def _abandoning(self, row, masked=False):
        if row.tail is not None:
            return True
        for label in row.labels:
            family = self.handler_ids[label][0] if label in self.handler_ids else label
            if (family == 'suspend' and not masked) or self.modes.get(family) == 'affine':
                return True
        return False

    def _operation_effects(self, family, named, context):
        if family not in self.modes:
            raise InferenceError('Unknown effect family')
        label = family
        if named:
            if len(named) != 1 or named[0] not in context.names:
                raise InferenceError('Unknown handler name')
            label = context.names[named[0]]
            if self.handler_ids[label][0] != family:
                raise InferenceError('Named handler family mismatch')
            context.named_references.add(label)
        return self._resolve(Row((label,)), context)

    def _control(self, row, context):
        if not self._abandoning(row):
            return
        for name, binding in context.live:
            if not binding.consumed and not binding.managed and not permissions(binding.value.type)[1]:
                raise InferenceError(f'Effects may abandon live resource {name}')
        if any(not permissions(v.type)[1] for v in context.temporaries):
            raise InferenceError('Effects may abandon an owned argument temporary')

    def _function(self, parameters, body, outer):
        free = free_names(body, {name for name, _ in parameters})
        copies = {name: replace(binding, managed=False)
                  for name, binding in outer.bindings.items() if name in free}
        originals = {binding: outer.bindings[name] for name, binding in copies.items()}
        context = Context(bindings=copies, live=list(copies.items()),
                          regions=dict(outer.regions), names=dict(outer.names),
                          active=outer.active, trace=False, blocked_family=outer.blocked_family)
        parameter_bindings, sources = [], {}
        if len({name for name, _ in parameters}) != len(parameters):
            raise InferenceError('Duplicate parameter name')
        for index, (name, t) in enumerate(parameters):
            source = self.fresh('argument')
            sources[source] = f'arg:{index}'
            mode = t.name.lower() if isinstance(t, Ty) and t.name in ('View', 'Mut') else None
            binding = Binding(value(t.args[0] if mode else t, captures={source}), mode=mode)
            context.bindings[name] = binding
            parameter_bindings.append((name, binding))
            context.live.append((name, binding))
        result = self._infer(body, context)
        for name, binding in parameter_bindings:
            if not binding.mode and not binding.consumed and not permissions(binding.value.type)[1]:
                raise InferenceError(f'Unconsumed parameter {name}')
        captures, captured_types = set(), []
        for copy in context.references & originals.keys():
            original = originals[copy]
            if original.mode:
                raise InferenceError('Access grants cannot be captured by a function')
            if original.consumed:
                raise InferenceError('Closure captures a consumed value')
            if not permissions(original.value.type)[0]:
                original.consumed = True
            outer.references.add(original)
            captures.update(original.value.captures)
            captured_types.append(original.value.type)
        named = context.named_references & set(outer.names.values())
        captures.update(named)
        outer.named_references.update(named)
        bound = set(result.captures)
        if bound & captures:
            bound = (bound - captures) | {'env'}
        bound = {sources.get(source, source) for source in bound}
        signature = Fn(tuple(t for _, t in parameters), result.type, result.effects,
                       frozenset(bound), dup=all(permissions(t)[0] for t in captured_types),
                       discard=all(permissions(t)[1] for t in captured_types))
        return value(signature, captures=captures)

    def _apply(self, function, arguments, context):
        signature = function.type
        if not isinstance(signature, Fn) or len(arguments) != len(signature.parameters):
            raise InferenceError('Callable arity mismatch', code='type')
        types, regions, row_checks = {}, {}, []
        variables = {v: Var(v.name) for v in signature.effect_vars}

        def match(expected, actual, invariant=False):
            if isinstance(actual, Ty) and actual.name in ('Never', 'Unknown'):
                return
            if isinstance(expected, Ty) and expected.name == 'Unknown':
                return
            if isinstance(expected, Ty) and expected.name.startswith('$'):
                name = expected.name[1:]
                if name not in signature.type_vars:
                    if expected != actual:
                        raise InferenceError('Rigid type parameter mismatch')
                elif name in types and types[name] != actual:
                    raise InferenceError('Type parameter mismatch')
                else:
                    types[name] = actual
                return
            if isinstance(expected, Fn) and isinstance(actual, Fn):
                if invariant and (expected.dup, expected.discard) != (actual.dup, actual.discard):
                    raise InferenceError('Invariant callback usage mismatch')
                if (expected.dup and not actual.dup) or (expected.discard and not actual.discard):
                    raise InferenceError('Callback must be duplicable and discardable')
                if len(expected.parameters) != len(actual.parameters):
                    raise InferenceError('Callback arity mismatch')
                for a, b in zip(expected.parameters, actual.parameters):
                    match(a, b, invariant=True)
                match(expected.result, actual.result, invariant)
                row_checks.append((expected, actual, invariant))
                return
            if not isinstance(expected, Ty) or not isinstance(actual, Ty) or expected.name != actual.name:
                raise InferenceError('Type mismatch', code='type')
            if expected.region in signature.regions:
                previous = regions.setdefault(expected.region, actual.region)
                if previous != actual.region:
                    raise InferenceError('Region parameter mismatch')
            elif expected.region != actual.region:
                raise InferenceError('Region mismatch')
            if len(expected.args) != len(actual.args):
                raise InferenceError('Type arity mismatch')
            for a, b in zip(expected.args, actual.args):
                match(a, b, invariant=True)

        for p, a in zip(signature.parameters, arguments):
            match(p, a.type)
        solver = Solver()

        def row(r):
            labels = tuple(next((state(actual) for formal, actual in regions.items()
                                 if label == state(formal)), label) for label in r.labels)
            return Row(labels, variables.get(r.tail, r.tail))

        try:
            for expected, actual, invariant in row_checks:
                solver.unify(row(expected.effects), actual.effects if invariant else solver.weaken(actual.effects))
                bound = {regions.get(source, source) for source in expected.bound}
                compatible = actual.bound == bound if invariant else actual.bound <= bound
                if not capture_free(actual.result) and not compatible:
                    raise InferenceError('Callback capture contract would lose retained provenance')
            effects = solver.resolve(row(signature.effects))
            if effects.tail is not None and not effects.tail.rigid:
                solver.unify(Row((), effects.tail), Row())
            effects = self._resolve(solver.resolve(effects), context)
        except ValueError as error:
            raise InferenceError(str(error)) from error

        def substitute(t):
            if isinstance(t, Fn):
                return replace(t, parameters=tuple(substitute(p) for p in t.parameters),
                               result=substitute(t.result), effects=solver.resolve(row(t.effects)),
                               bound=frozenset(regions.get(source, source) for source in t.bound))
            if t.name.startswith('$') and t.name[1:] in types:
                return types[t.name[1:]]
            return Ty(t.name, tuple(substitute(a) for a in t.args), regions.get(t.region, t.region))

        captures = set()
        for source in signature.bound:
            if source.startswith('arg:'):
                captures.update(arguments[int(source[4:])].captures)
            elif source == 'env':
                captures.update(function.captures)
            else:
                captures.add(regions.get(source, source))
        self._control(effects, context)
        return value(substitute(signature.result), effects, captures)

    def _infer(self, expression, context):
        previous, self.current_expression = self.current_expression, expression
        try:
            return self._infer_expression(expression, context)
        except InferenceError as error:
            if error.expression is None:
                error.expression = expression
            raise
        finally:
            self.current_expression = previous

    def _infer_expression(self, expression, context):
        match expression:
            case ('int', number) if type(number) is int:
                return value(INT)
            case ('bool', boolean) if type(boolean) is bool:
                return value(BOOL)
            case ('unit',):
                return value(UNIT)
            case ('tuple', *items) | ('record', _, _, *items):
                values = []
                start = len(context.temporaries)
                for item in items:
                    element = self._infer(item, context)
                    values.append(element)
                    context.temporaries.append(element)
                del context.temporaries[start:]
                if expression[0] == 'record':
                    result = expression[1]
                    from source_features import unwrapped
                    fields = {f.name: f.args[0] for f in unwrapped(result).args}
                    type_vars, regions = set(), set()
                    def parameters(t):
                        if isinstance(t, Fn):
                            for part in (*t.parameters, t.result):
                                parameters(part)
                        else:
                            if t.name.startswith('$'):
                                type_vars.add(t.name[1:])
                            if t.region and t.region not in context.regions and t.region not in context.active:
                                regions.add(t.region)
                            for part in t.args:
                                parameters(part)
                    parameters(result)
                    constructor = Fn(tuple(fields[n] for n in expression[2]), result, Row(),
                                     type_vars=tuple(sorted(type_vars)), regions=tuple(sorted(regions)))
                    result = self._apply(value(constructor), values, context).type
                else:
                    result = Ty('Tuple', tuple(v.type for v in values))
                return value(result, ambient(*(v.effects for v in values)),
                             frozenset().union(*(v.captures for v in values)))
            case ('field', name, base):
                record = self._infer(base, context)
                if not isinstance(record.type, Ty) or not record.type.name.startswith('Record:'):
                    raise InferenceError('Field access requires a record', code='type')
                fields = {f.name: f.args[0] for f in record.type.args}
                if name not in fields:
                    raise InferenceError('Unknown record field ' + name, code='type')
                if not permissions(record.type)[0]:
                    raise InferenceError('Implementation limit: field copies require a duplicable record', code='unsupported')
                return value(fields[name], record.effects, record.captures)
            case ('unpack', pattern, initializer, body):
                initial = self._infer(initializer, context)
                bound = {}
                def bind(pattern, t):
                    if isinstance(pattern, tuple):
                        if not isinstance(t, Ty) or t.name != 'Tuple' or len(t.args) != len(pattern):
                            raise InferenceError('Tuple pattern shape mismatch', code='type')
                        for p, part in zip(pattern, t.args):
                            bind(p, part)
                    else:
                        bound[pattern] = Binding(value(t, captures=initial.captures))
                bind(pattern, initial.type)
                previous = context.bindings
                start = len(context.live)
                context.bindings = previous | bound
                context.live.extend(bound.items())
                result = self._infer(body, context)
                for name, binding in bound.items():
                    if not binding.consumed and not permissions(binding.value.type)[1]:
                        raise InferenceError(f'Unconsumed resource {name}', subject=name)
                context.bindings = previous
                del context.live[start:]
                return replace(result, effects=ambient(initial.effects, result.effects))
            case ('unary', operator, operand):
                result = self._infer(operand, context)
                if operator not in ('+', '-') or result.type != INT:
                    raise InferenceError('Unary arithmetic requires Int', code='type')
                return result
            case ('binary', operator, left, right):
                first = self._infer(left, context)
                context.temporaries.append(first)
                second = self._infer(right, context)
                context.temporaries.pop()
                nat = Ty('Nat')
                allowed = (INT, nat, BOOL, UNIT) if operator in ('==', '!=') else (INT, nat)
                if first.type != second.type or first.type not in allowed:
                    raise InferenceError('Invalid operand types for ' + operator, code='type')
                result = BOOL if operator in ('==', '!=', '<', '<=', '>', '>=') else first.type
                return value(result, ambient(first.effects, second.effects))
            case ('if', condition, then, otherwise):
                test = self._infer(condition, context)
                if test.type != BOOL:
                    raise InferenceError('Condition must have type Bool', expression=condition, code='type')
                bindings = set(context.bindings.values()) | {b for _, b in context.live}
                incoming = {b: b.consumed for b in bindings}
                resumption = context.resumption
                used = resumption.used if resumption else False
                first = self._infer(then, context)
                outgoing = {b: b.consumed for b in bindings}
                resumed = resumption.used if resumption else False
                for binding, consumed in incoming.items():
                    binding.consumed = consumed
                if resumption:
                    resumption.used = used
                second = self._infer(otherwise, context)
                from source_features import join_type, NEVER
                result_type = join_type(first.type, second.type)
                if first.type != NEVER and second.type != NEVER and any(b.consumed != consumed for b, consumed in outgoing.items()):
                    raise InferenceError('Branches must agree on ownership consumption')
                if first.type != NEVER and second.type != NEVER and resumption and resumption.used != resumed:
                    raise InferenceError('Branches must agree on resumption use')
                if second.type == NEVER and first.type != NEVER:
                    for b, consumed in outgoing.items():
                        b.consumed = consumed
                    if resumption:
                        resumption.used = resumed
                return value(result_type, ambient(test.effects, first.effects, second.effects),
                             first.captures | second.captures)
            case ('var', name):
                return self._lookup(name, context)
            case ('specialize', callee, arguments):
                function = self._infer(callee, context)
                signature = function.type
                if not isinstance(signature, Fn) or not signature.type_vars or len(signature.type_vars) != len(arguments):
                    raise InferenceError('Generic type argument arity mismatch', code='type')
                substitutions = dict(zip(signature.type_vars, arguments))
                def substitute(t):
                    if isinstance(t, Ty):
                        return substitutions.get(t.name[1:], t) if t.name.startswith('$') else replace(t, args=tuple(substitute(a) for a in t.args))
                    return replace(t, parameters=tuple(substitute(p) for p in t.parameters), result=substitute(t.result))
                return replace(function, type=replace(substitute(signature), type_vars=()))
            case ('lambda', parameters, body):
                return self._function(parameters, body, context)
            case ('let' | 'using' as kind, name, initializer, body):
                initial = self._infer(initializer, context)
                previous = context.bindings.get(name)
                binding = Binding(replace(initial, effects=Row()), managed=kind == 'using')
                context.bindings[name] = binding
                context.live.append((name, binding))
                result = self._infer(body, context)
                cleanup = Row()
                if kind == 'using':
                    if isinstance(initial.type, Ty) and initial.type.name == 'Owned':
                        cleanup = self.cleanup_rows[initial.type.args[0].name]
                    elif hasattr(self, 'cleanup_contract'):
                        cleanup = self.cleanup_contract(expression, initial, context)
                    else:
                        raise InferenceError('using requires a canonical cleanup resource')
                    if self._abandoning(cleanup, masked=True):
                        raise InferenceError('Canonical cleanup may abandon its resource')
                    if initial.captures & result.captures:
                        raise InferenceError('Cleanup-owned resource would escape using')
                    if not binding.consumed:
                        self.cleanups.append((name, True))
                elif not binding.consumed and not permissions(initial.type)[1]:
                    raise InferenceError(f'Unconsumed resource {name}', subject=name)
                if previous is None:
                    del context.bindings[name]
                else:
                    context.bindings[name] = previous
                context.live.pop()
                return replace(result, effects=ambient(initial.effects, result.effects, cleanup))
            case ('while', condition, body):
                before = {b: b.consumed for b in context.bindings.values()}
                resumed = context.resumption.used if context.resumption else False
                test = self._infer(condition, context)
                if test.type != BOOL:
                    raise InferenceError('While condition must have type Bool', code='type')
                result = self._infer(body, context)
                if result.type not in (UNIT, Ty('Never')):
                    raise InferenceError('While body must return Unit', code='type')
                if any(b.consumed != old for b, old in before.items()):
                    raise InferenceError('Repeated loop cannot consume an outside owner')
                if context.resumption and context.resumption.used != resumed:
                    raise InferenceError('Repeated loop cannot consume a resumption')
                return value(UNIT, ambient(test.effects, result.effects, Row(('diverge',))))
            case ('seq', *expressions) if expressions:
                rows = []
                for index, item in enumerate(expressions):
                    result = self._infer(item, context)
                    rows.append(result.effects)
                    if result.type == Ty('Never'):
                        break
                    if index != len(expressions) - 1 and not permissions(result.type)[1]:
                        raise InferenceError('Cannot discard an owned intermediate value', expression=item)
                return replace(result, effects=ambient(*rows))
            case ('call', name, *expressions):
                function = self._lookup(name, context)
                start = len(context.temporaries)
                context.temporaries.append(function)
                arguments = []
                for item in expressions:
                    argument = self._infer(item, context)
                    arguments.append(argument)
                    context.temporaries.append(argument)
                del context.temporaries[start:]
                result = self._apply(function, arguments, context)
                return replace(result, effects=ambient(function.effects, *(a.effects for a in arguments), result.effects))
            case ('each', values, callback):
                xs, f = self._infer(values, context), self._infer(callback, context)
                if not isinstance(xs.type, Ty) or xs.type.name != 'List':
                    raise InferenceError('Traversal requires a finite List')
                if not isinstance(f.type, Fn) or not f.type.dup or not f.type.discard:
                    raise InferenceError('Traversal callback must be duplicable and discardable')
                if not permissions(xs.type.args[0])[1]:
                    raise InferenceError('This traversal fragment requires discardable elements')
                result = self._apply(f, [value(xs.type.args[0], captures=xs.captures)], context)
                if result.type != UNIT:
                    raise InferenceError('Traversal callback must return Unit')
                return value(UNIT, ambient(xs.effects, f.effects, result.effects))
            case ('perform', family, *named):
                effects = self._operation_effects(family, named, context)
                self._control(effects, context)
                return value(UNIT, effects)
            case ('handle', family, name, body):
                if self.modes.get(family) != 'tail':
                    raise InferenceError('Prototype supports tail handler delimiters only')
                key = f'{family}@handler:{self.fresh(name)}'
                self.handler_ids[key] = (family, name)
                old_handlers, old_names, old_active = context.handlers, context.names, context.active
                context.handlers += ((family, key),)
                context.names = context.names | {name: key}
                context.active |= {key}
                result = self._infer(body, context)
                if key in result.captures:
                    raise InferenceError('Named handler capture would escape')
                remaining = list(result.effects.labels)
                if key in remaining:
                    remaining.remove(key)
                effects = Row(tuple(remaining), result.effects.tail)
                self.handled_rows[name] = effects
                context.handlers, context.names, context.active = old_handlers, old_names, old_active
                return replace(result, effects=effects)
            case ('region', name, body):
                key = self.fresh(name)
                old_regions, old_active = context.regions, context.active
                self.scope_depth[key] = len(context.active)
                context.regions = context.regions | {name: key}
                context.active |= {key}
                result = self._infer(body, context)
                if key in result.captures or key in required_captures(result.type):
                    raise InferenceError('Local region would escape through the result')
                effects = Row(tuple(label for label in result.effects.labels if label != state(key)), result.effects.tail)
                context.regions, context.active = old_regions, old_active
                return replace(result, effects=effects)
            case ('ref' | 'buffer' as kind, region, initializer):
                initial = self._infer(initializer, context)
                scope = context.regions[region]
                if kind == 'ref':
                    if not permissions(initial.type)[1]:
                        raise InferenceError('Ref payload must be discardable')
                    self._horizon(scope, initial.captures)
                    t = Ty('Ref', (initial.type,), scope)
                else:
                    if not isinstance(initial.type, Ty) or initial.type.name != 'List':
                        raise InferenceError('Buffer initialization requires a List')
                    t = Ty('DynArray', initial.type.args, scope)
                return value(t, ambient(initial.effects, Row((state(scope),))), initial.captures | {scope})
            case ('get', reference):
                ref = self._infer(reference, context)
                if not isinstance(ref.type, Ty) or ref.type.name != 'Ref' or not permissions(ref.type.args[0])[0]:
                    raise InferenceError('Reading Ref requires a duplicable payload')
                return value(ref.type.args[0], ambient(ref.effects, Row((state(ref.type.region),))), ref.captures)
            case ('set', reference, payload):
                ref, new = self._infer(reference, context), self._infer(payload, context)
                if not isinstance(ref.type, Ty) or ref.type.name != 'Ref' or ref.type.args[0] != new.type:
                    raise InferenceError('Ref write type mismatch')
                self._horizon(ref.type.region, new.captures)
                return value(UNIT, ambient(ref.effects, new.effects, Row((state(ref.type.region),))))
            case ('list', *items) if items:
                values = []
                start = len(context.temporaries)
                for item in items:
                    element = self._infer(item, context)
                    values.append(element)
                    context.temporaries.append(element)
                del context.temporaries[start:]
                if any(v.type != values[0].type for v in values):
                    raise InferenceError('List elements must have equal types')
                return value(Ty('List', (values[0].type,)), ambient(*(v.effects for v in values)),
                             frozenset().union(*(v.captures for v in values)))
            case ('acquire', name) if name in self.cleanup_rows:
                return value(Ty('Owned', (Ty(name),)), captures={self.fresh('owned:' + name)})
            case _:
                raise InferenceError(f'Unsupported expression: {expression!r}')

    def _horizon(self, region, captures):
        for capture in captures:
            if capture not in self.scope_depth or self.scope_depth[capture] > self.scope_depth.get(region, -1):
                raise InferenceError('Stored capture violates the cell retention horizon')
