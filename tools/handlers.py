"""Bounded handler experiment over inference.py's annotated expression IR.

One nullary operation per family, scalar operation/handler results, straight-line
clauses and identity or explicit return clauses. Non-Dup frame captures obey an
availability invariant at every resumption; consuming one before resuming is
conservatively rejected. Self recursion, source returns and general control-flow
inference are outside this experiment. This is not an Eldude compiler.
"""
from dataclasses import dataclass, field, replace

from effect_rows import Row
from inference import (Binding, Checker, Context, E, INT, UNIT, Ty, InferenceError,
                       ambient, free_names, permissions, value)


@dataclass(frozen=True)
class Operation:
    mode: str
    result: object

    def __post_init__(self):
        if self.mode not in ('tail', 'once', 'affine') or self.result not in (INT, UNIT):
            raise InferenceError('Handler experiment requires a valid mode and scalar operation result')


@dataclass
class Frame:
    key: str
    family: str
    outside: set
    captures: dict
    sites: list = field(default_factory=list)
    opaque: bool = False
    collecting: bool = True


@dataclass
class Resumption:
    frame: Frame
    operation: Operation
    output: object
    effects: Row
    captures: dict
    pending: tuple
    used: bool = False


class HandlerChecker(Checker):
    def __init__(self, *, operations=None, **kwargs):
        super().__init__(**kwargs)
        self.operations = {'Log': Operation('tail', UNIT), 'Abort': Operation('affine', UNIT)} | (operations or {})
        self.modes = {family: operation.mode for family, operation in self.operations.items()}
        self.frames = {}
        self.in_call = False

    def _obligations(self, context):
        # Snapshot identities as well as values: later straight-line consumption
        # must not retroactively discharge an earlier suspended segment.
        entries = [(name, b.value, b.managed, id(b)) for name, b in context.live if not b.consumed]
        entries.extend(('argument temporary', v, False, id(v)) for v in context.temporaries)
        entries.extend(context.suspended)
        if context.resumption is not None and not context.resumption.used:
            entries.extend(context.resumption.pending)
        return tuple(entries)

    def _control(self, row, context):
        obligations = self._obligations(context)
        for label in row.labels:
            frame = self.frames.get(label)
            if frame and frame.collecting:
                frame.sites.extend(obligations)
                frame.opaque |= self.in_call
        for label in (*row.labels, *(['unknown tail'] if row.tail else [])):
            family = self.handler_ids[label][0] if label in self.handler_ids else label
            if family not in ('suspend', 'unknown tail') and self.modes.get(family) != 'affine':
                continue
            frame = self.frames.get(label)
            outside = frame.outside if frame else set()
            for name, retained, managed, identity in obligations:
                if identity not in outside and not managed and not permissions(retained.type)[1]:
                    raise InferenceError(f'Effects may abandon live resource {name}')

    def _apply(self, function, arguments, context):
        previous, self.in_call = self.in_call, True
        try:
            return super()._apply(function, arguments, context)
        finally:
            self.in_call = previous

    def _resume(self, supplied, context, implicit=False):
        resume = context.resumption
        if resume is None:
            raise InferenceError('resume is available only inside an operation clause')
        if resume.operation.mode == 'tail' and not implicit:
            raise InferenceError('Explicit resume is forbidden in a tail clause')
        if resume.used:
            raise InferenceError('Cannot resume more than once')
        if supplied.type != resume.operation.result:
            raise InferenceError('Incorrect operation result supplied to resumption')
        for name, binding in resume.captures.items():
            if not permissions(binding.value.type)[0]:
                if binding.consumed:
                    raise InferenceError(f'Frame capture {name} was consumed before transfer')
                binding.consumed = True
        resume.used = True
        self._control(resume.effects, context)
        return value(resume.output, ambient(supplied.effects, resume.effects))

    def _clause_context(self, outer, frame):
        copies = {name: replace(b, consumed=False, managed=False) for name, b in frame.captures.items()}
        return Context(bindings=dict(copies), live=list(copies.items()), regions=dict(outer.regions),
                       handlers=outer.handlers, names=dict(outer.names), active=outer.active,
                       trace=False), copies

    @staticmethod
    def _discharge(bindings):
        for name, binding in bindings.items():
            if not binding.consumed and not permissions(binding.value.type)[1]:
                raise InferenceError(f'Unconsumed handler obligation {name}')

    def _handler(self, family, name, body, clause, returning, context):
        if family not in self.operations:
            raise InferenceError('Unknown effect family')
        if len(returning) != 3 or returning[0] != 'returning':
            raise InferenceError('Expected a return clause')
        _, result_name, result_body = returning
        free = free_names(clause) | free_names(returning)
        captures = {}
        for captured in sorted(free & context.bindings.keys()):
            original = context.bindings[captured]
            if original.consumed:
                raise InferenceError(f'{captured} was already consumed')
            captures[captured] = replace(original, managed=False)
            context.references.add(original)
            if not permissions(original.value.type)[0]:
                original.consumed = True
        key = f'{family}@handler:{self.fresh(name)}'
        self.handler_ids[key] = (family, name)
        outside = {entry[3] for entry in self._obligations(context)} | {id(b) for b in captures.values()}
        frame = Frame(key, family, outside, captures)
        self.frames[key] = frame
        old_handlers, old_names, old_active = context.handlers, context.names, context.active
        context.handlers += ((family, key),)
        context.names = context.names | {name: key}
        context.active |= {key}
        start = len(context.live)
        incoming = [(n, b) for n, b in context.live if not b.consumed and not permissions(b.value.type)[1]]
        previously_resumed = context.resumption.used if context.resumption else False
        context.live.extend(captures.items())
        normal = self._infer(body, context)
        del context.live[start:]
        context.handlers, context.names, context.active = old_handlers, old_names, old_active
        frame.collecting = False
        if self.operations[family].mode == 'affine' and key in normal.effects.labels:
            if context.resumption and context.resumption.used != previously_resumed:
                raise InferenceError('Affine completion may skip an enclosing resume')
            for outer_name, binding in incoming:
                if binding.consumed:
                    raise InferenceError(f'Affine completion may skip consumption of {outer_name}')
        if normal.type not in (INT, UNIT):
            raise InferenceError('Handler experiment requires a scalar body result')
        labels = list(normal.effects.labels)
        if key in labels:
            labels.remove(key)
        body_effects = Row(tuple(labels), normal.effects.tail)

        returned_context, returned_captures = self._clause_context(context, frame)
        returned_context.suspended = self._obligations(context)
        result_binding = Binding(replace(normal, effects=Row()))
        returned_context.bindings[result_name] = result_binding
        returned_context.live.append((result_name, result_binding))
        returned = self._infer(result_body, returned_context)
        self._discharge(returned_captures)
        if returned.type not in (INT, UNIT):
            raise InferenceError('Handler experiment requires a scalar output')

        own_ids = {id(b) for b in captures.values()}
        pending = tuple(entry for entry in frame.sites if entry[3] not in own_ids)
        if frame.opaque and self.operations[family].mode != 'affine':
            unknown = value(Ty('Owned', (Ty('Continuation'),)))
            pending += (('opaque suspended continuation', unknown, False, id(frame)),)

        def check_clause(residual):
            clause_context, clause_captures = self._clause_context(context, frame)
            # Resources outside this delimiter survive a successful resume.
            clause_context.suspended = self._obligations(context)
            resume = Resumption(frame, self.operations[family], returned.type,
                                residual, clause_captures, pending)
            clause_context.resumption = resume
            clause_context.blocked_family = family
            if clause == E('forward'):
                effects = self._resolve(Row((family,)), clause_context)
                self._control(effects, clause_context)
                handled = self._resume(value(resume.operation.result, effects), clause_context, implicit=True)
            else:
                handled = self._infer(clause, clause_context)
                if resume.operation.mode == 'tail':
                    handled = self._resume(handled, clause_context, implicit=True)
            if resume.operation.mode == 'once' and not resume.used:
                raise InferenceError('A once clause must resume exactly once')
            if handled.type != returned.type:
                raise InferenceError('Operation clause must produce the handler output')
            self._discharge(clause_captures)
            return ambient(residual, handled.effects)

        residual = ambient(body_effects, returned.effects)
        effects = check_clause(residual)
        # Deep resumption may re-enter this clause. Check its complete residual
        # at resume sites, including effects inferred from the clause itself.
        if effects != residual and check_clause(effects) != effects:
            raise InferenceError('Handler residual did not stabilize in the supported fragment')
        self.handled_rows[name] = effects
        return value(returned.type, effects)

    def _infer(self, expression, context):
        match expression:
            case ('handle', family, name, body, clause, returning):
                return self._handler(family, name, body, clause, returning, context)
            case ('resume', argument):
                return self._resume(self._infer(argument, context), context)
            case ('perform', family, *named):
                if context.blocked_family == family and not named:
                    raise InferenceError('An unqualified same-family operation is forbidden inside its clause')
                if named == ['self']:
                    raise InferenceError('Self recursion is outside the handler experiment')
                result = super()._infer(expression, context)
                return replace(result, type=self.operations[family].result)
            case _:
                return super()._infer(expression, context)


@dataclass(frozen=True)
class Evidence:
    family: str
    instance: int | None = None


@dataclass(frozen=True)
class Program:
    core: tuple
    inferred: object
    operations: dict


def compile_program(expression, *, operations=None):
    """Check first, then lower dispatch and hidden evidence arguments explicitly."""
    checker = HandlerChecker(operations=operations)
    inferred = checker.infer(expression)
    serial = 0

    def evidence_used(term):
        if isinstance(term, Evidence):
            return {term}
        if isinstance(term, tuple):
            return set().union(*(evidence_used(part) for part in term))
        return set()

    def lower(expr, names):
        nonlocal serial
        match expr:
            case ('int', _) | ('unit',) | ('var', _) | ('acquire', _):
                return expr
            case ('seq', *items):
                return E('seq', *(lower(item, names) for item in items))
            case ('let' | 'using' as kind, name, initial, body):
                return E(kind, name, lower(initial, names), lower(body, names))
            case ('call', name, *arguments):
                return E('invoke', name, E('evidence'), tuple(lower(a, names) for a in arguments))
            case ('lambda', parameters, body):
                core = lower(body, names)
                fixed = tuple(sorted(evidence_used(core) & set(names.values()),
                                     key=lambda e: (e.family, e.instance)))
                captures = tuple(sorted(free_names(body, {name for name, _ in parameters})))
                return E('closure', tuple(name for name, _ in parameters), captures, fixed, core)
            case ('perform', family, *named):
                selected = names[named[0]] if named else Evidence(family)
                return E('dispatch', selected)
            case ('resume', supplied):
                return E('resume', lower(supplied, names))
            case ('handle', family, name, body, clause, ('returning', result_name, result_body)):
                serial += 1
                selected = Evidence(family, serial)
                captures = tuple(sorted(free_names(clause) | free_names(E('returning', result_name, result_body))))
                forwarding = clause == E('forward')
                clause_core = E('dispatch', Evidence(family)) if forwarding else lower(clause, names)
                return E('install', selected, name, captures,
                         lower(body, names | {name: selected}), clause_core,
                         result_name, lower(result_body, names), forwarding)
            case _:
                raise InferenceError(f'Expression is outside the executable handler fragment: {expr[0]}')

    return Program(lower(expression, {}), inferred, checker.operations)


@dataclass
class _Slot:
    value: object
    consumed: bool = False


@dataclass
class _Resource:
    name: str
    identity: int
    closed: bool = False


@dataclass
class _Closure:
    parameters: tuple
    body: tuple
    environment: dict
    fixed: dict


@dataclass(eq=False)
class _Handler:
    evidence: Evidence
    name: str
    captures: dict
    outer_evidence: dict
    clause: tuple
    result_name: str
    result_body: tuple
    mode: str
    implicit: bool


@dataclass
class _Request:
    target: _Handler
    continue_with: object
    abandon: object


@dataclass(frozen=True)
class Execution:
    value: object
    events: tuple


def _dup(retained):
    if isinstance(retained, _Resource):
        return False
    if isinstance(retained, _Closure):
        return all(_dup(s.value) for s in retained.environment.values())
    return True


def _read(name, environment):
    if name not in environment and name in ('close', 'yield'):
        return name
    slot = environment[name]
    if slot.consumed:
        raise RuntimeError(f'Consumed runtime binding {name}')
    if not _dup(slot.value):
        slot.consumed = True
    return slot.value


def _bind(computation, then):
    if isinstance(computation, _Request):
        return _Request(computation.target,
                        lambda result: _bind(computation.continue_with(result), then),
                        computation.abandon)
    return then(computation)


def _protect(computation, finish):
    if isinstance(computation, _Request):
        def abandon():
            computation.abandon()
            finish()
        return _Request(computation.target,
                        lambda result: _protect(computation.continue_with(result), finish), abandon)
    finish()
    return computation


class _Machine:
    def __init__(self, operations):
        self.operations, self.events, self.resources = operations, [], []

    def close(self, resource, reason):
        if not isinstance(resource, _Resource) or resource.closed:
            raise RuntimeError('Resource was closed more than once or is invalid')
        if resource.name == 'AsyncFile':
            self.events.append(('suspend', reason == 'cleanup'))
        resource.closed = True
        self.events.append(('close', resource.identity, reason))

    def dispatch(self, selected, evidence):
        if selected not in evidence:
            raise RuntimeError(f'Unbound handler evidence for {selected.family}')
        target = evidence[selected]
        self.events.append(('dispatch', selected.family, target.name))
        return _Request(target, lambda supplied: supplied, lambda: None)

    def invoke(self, function, evidence, arguments):
        if function == 'close':
            self.close(arguments[0], 'explicit')
            return None
        if function == 'yield':
            self.events.append(('suspend', False))
            return None
        if not isinstance(function, _Closure):
            raise RuntimeError('Unknown executable callable')
        environment = {name: replace(slot) for name, slot in function.environment.items()}
        environment.update({name: _Slot(a) for name, a in zip(function.parameters, arguments)})
        return self.evaluate(function.body, environment, evidence | function.fixed)

    def handle(self, frame, computation):
        if not isinstance(computation, _Request):
            environment = frame.captures | {frame.result_name: _Slot(computation)}
            return self.evaluate(frame.result_body, environment, frame.outer_evidence)
        if computation.target is not frame:
            return _Request(computation.target,
                            lambda supplied: self.handle(frame, computation.continue_with(supplied)),
                            computation.abandon)
        clause_environment = {name: replace(slot) for name, slot in frame.captures.items()}
        resumed, abandoned = False, False

        def resume(supplied):
            nonlocal resumed
            if resumed or abandoned:
                raise RuntimeError('Runtime resumption capability already used')
            resumed = True
            frame.captures = {name: replace(slot) for name, slot in clause_environment.items()}
            for name, slot in clause_environment.items():
                if not _dup(slot.value):
                    if slot.consumed:
                        raise RuntimeError(f'Consumed frame capture {name} cannot be transferred')
                    slot.consumed = True
            self.events.append(('resume', frame.name, supplied))
            return self.handle(frame, computation.continue_with(supplied))

        def abandon():
            nonlocal abandoned
            if not resumed and not abandoned:
                abandoned = True
                self.events.append(('abandon', frame.name))
                computation.abandon()

        clause = self.evaluate(frame.clause, clause_environment, frame.outer_evidence,
                               None if frame.implicit else resume)
        if frame.implicit:
            clause = _bind(clause, resume)

        def completed(result):
            if frame.mode == 'once' and not resumed:
                raise RuntimeError('Once clause completed without resuming')
            return result
        return _protect(_bind(clause, completed), abandon)

    def evaluate(self, term, environment, evidence, resume=None):
        # ponytail: recursive continuation closures suffice for these finite
        # examples; an explicit machine stack is needed for unbounded programs.
        match term:
            case ('int', number):
                return number
            case ('unit',):
                return None
            case ('var', name):
                return _read(name, environment)
            case ('evidence',):
                return evidence
            case ('acquire', name):
                resource = _Resource(name, len(self.resources) + 1)
                self.resources.append(resource)
                self.events.append(('acquire', name, resource.identity))
                return resource
            case ('closure', parameters, captures, fixed, body):
                retained = {name: _Slot(_read(name, environment)) for name in captures if name in environment}
                return _Closure(parameters, body, retained, {key: evidence[key] for key in fixed})
            case ('let' | 'using' as kind, name, initial, body):
                def enter(retained):
                    result = self.evaluate(body, environment | {name: _Slot(retained)}, evidence, resume)
                    if kind == 'using':
                        def cleanup():
                            if not retained.closed:
                                self.close(retained, 'cleanup')
                        return _protect(result, cleanup)
                    return result
                return _bind(self.evaluate(initial, environment, evidence, resume), enter)
            case ('seq', first, *rest):
                result = self.evaluate(first, environment, evidence, resume)
                return _bind(result, lambda _: self.evaluate(E('seq', *rest), environment, evidence, resume)) if rest else result
            case ('invoke', name, supplied_evidence, arguments):
                function = _read(name, environment)
                passed = self.evaluate(supplied_evidence, environment, evidence, resume)

                def argument(index, values):
                    if index == len(arguments):
                        return self.invoke(function, passed, values)
                    return _bind(self.evaluate(arguments[index], environment, evidence, resume),
                                 lambda retained: argument(index + 1, values + [retained]))
                return argument(0, [])
            case ('dispatch', selected):
                return self.dispatch(selected, evidence)
            case ('resume', supplied):
                if resume is None:
                    raise RuntimeError('No runtime resumption capability')
                return _bind(self.evaluate(supplied, environment, evidence, resume), resume)
            case ('install', selected, name, captures, body, clause, result_name, result_body, forwarding):
                retained = {n: _Slot(_read(n, environment)) for n in captures if n in environment}
                mode = self.operations[selected.family].mode
                frame = _Handler(selected, name, retained, evidence, clause, result_name, result_body,
                                 mode, mode == 'tail' or forwarding)
                inner = evidence | {selected: frame, Evidence(selected.family): frame}
                return self.handle(frame, self.evaluate(body, environment, inner, resume))
            case _:
                raise RuntimeError(f'Unknown lowered expression: {term!r}')


def run(program):
    """Execute a checked closed program; events expose dispatch and real cleanup."""
    if program.inferred.effects.tail or any(label not in ('suspend', 'diverge')
                                           for label in program.inferred.effects.labels):
        raise InferenceError('Execution requires closed handler evidence')
    machine = _Machine(program.operations)
    result = machine.evaluate(program.core, {}, {})
    if isinstance(result, _Request):
        result.abandon()
        raise RuntimeError('Unhandled runtime evidence target')
    if any(not resource.closed for resource in machine.resources):
        raise RuntimeError('An owned resource was leaked')
    return Execution(result, tuple(machine.events))
