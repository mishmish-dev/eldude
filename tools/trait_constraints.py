"""Canonical first-order trait evidence and associated normalization (§10)."""
from collections import Counter
from dataclasses import dataclass, field, replace


def children(term):
    from inference import Fn
    return (*term.parameters, term.result, *term.constraints) if isinstance(term, Fn) else term.args


def variables(term):
    return Counter({term.name: 1}) if getattr(term, 'name', '').startswith('$') else sum((variables(a) for a in children(term)), Counter())


def size(term):
    return 1 + sum(size(a) for a in children(term))


def projections(term):
    if getattr(term, 'name', '').startswith('Projection:'):
        yield term
    for child in children(term):
        yield from projections(child)


def effect_row(term, variables=None):
    from effect_rows import Row, Var
    from inference import state
    variables = variables or {}
    if term.name.startswith('$!'):
        name = term.name[2:]
        return Row((), variables.get(name) or Var(name, rigid=True))
    if term.name != 'Effects':
        raise ValueError('Expected an effect-row argument')
    labels, tail = [], None
    for entry in term.args:
        if entry.name == 'Effects' or entry.name.startswith('$!'):
            nested = effect_row(entry, variables)
            labels.extend(nested.labels)
            if tail is not None and nested.tail is not None:
                raise ValueError('Independent effect tails need a shared-row contract')
            tail = nested.tail or tail
        else:
            labels.append(state(entry.region) if entry.name == 'state' else entry.name)
    return Row(tuple(labels), tail)


def capture_row(term):
    from capture_rows import Variable
    if term.name.startswith('$..'):
        return frozenset({Variable(term.name[3:])})
    if term.name != 'Captures':
        raise ValueError('Expected a capture-row argument')
    return frozenset().union(*(capture_row(e) if e.name in ('Captures',) or e.name.startswith('$..')
                              else {e.region if e.name == 'Region' else e.name.removeprefix('Capture:')}
                              for e in term.args))


def substitute(term, types=None, regions=None):
    types, regions = types or {}, regions or {}
    from inference import Fn
    if isinstance(term, Fn):
        from source_features import substitute as substitute_type
        return replace(substitute_type(term, types, regions),
                       constraints=tuple(substitute(a, types, regions) for a in term.constraints))
    if term.name.startswith('$') and term.name[1:] in types:
        return types[term.name[1:]]
    return replace(term, args=tuple(substitute(a, types, regions) for a in term.args),
                   region=regions.get(term.region, term.region))


def match(pattern, goal, type_vars, region_vars=(), types=None, regions=None):
    """Instantiate only implementation binders; caller variables stay rigid."""
    types, regions = {} if types is None else types, {} if regions is None else regions
    from inference import Fn
    if isinstance(pattern, Fn):
        if not isinstance(goal, Fn) or replace(pattern, parameters=(), result=None, constraints=()) != replace(goal, parameters=(), result=None, constraints=()) or len(children(pattern)) != len(children(goal)):
            raise ValueError('Trait head mismatch')
        for p, a in zip(children(pattern), children(goal)):
            match(p, a, type_vars, region_vars, types, regions)
        return types, regions
    if pattern.name.startswith('$') and pattern.name[1:] in type_vars:
        name = pattern.name[1:]
        previous = types.setdefault(name, goal)
        if previous != goal:
            raise ValueError('Trait head mismatch')
    else:
        if isinstance(goal, Fn):
            raise ValueError('Trait head mismatch')
        if pattern.name != goal.name or len(pattern.args) != len(goal.args):
            raise ValueError('Trait head mismatch')
        if pattern.region in region_vars:
            previous = regions.setdefault(pattern.region, goal.region)
            if previous != goal.region:
                raise ValueError('Trait region mismatch')
        elif pattern.region != goal.region:
            raise ValueError('Trait region mismatch')
        for p, a in zip(pattern.args, goal.args):
            match(p, a, type_vars, region_vars, types, regions)
    return types, regions


def overlap(left, right):
    """First-order unification, with apart-renamed binders and occurs checks."""
    def rename(t, prefix, impl):
        from inference import Fn
        if isinstance(t, Fn):
            return replace(t, parameters=tuple(rename(a, prefix, impl) for a in t.parameters),
                           result=rename(t.result, prefix, impl), constraints=tuple(rename(a, prefix, impl) for a in t.constraints))
        name = prefix + t.name if t.name.startswith('$') and t.name[1:] in impl.type_vars else t.name
        region = prefix + t.region if t.region in impl.region_vars else t.region
        return replace(t, name=name, args=tuple(rename(a, prefix, impl) for a in t.args), region=region)
    assignments, region_assignments = {}, {}
    def occurs(name, term):
        if getattr(term, 'name', None) == name:
            return True
        if getattr(term, 'name', None) in assignments:
            return occurs(name, assignments[term.name])
        return any(occurs(name, a) for a in children(term))
    def unify(a, b):
        while getattr(a, 'name', None) in assignments:
            a = assignments[a.name]
        while getattr(b, 'name', None) in assignments:
            b = assignments[b.name]
        if a == b:
            return True
        if getattr(a, 'name', '').startswith(('L$', 'R$')):
            if occurs(a.name, b):
                return False
            assignments[a.name] = b
            return True
        if getattr(b, 'name', '').startswith(('L$', 'R$')):
            return unify(b, a)
        from inference import Fn
        if isinstance(a, Fn) or isinstance(b, Fn):
            return (isinstance(a, Fn) and isinstance(b, Fn)
                    and replace(a, parameters=(), result=None, constraints=()) == replace(b, parameters=(), result=None, constraints=())
                    and len(children(a)) == len(children(b))
                    and all(unify(x, y) for x, y in zip(children(a), children(b))))
        if a.name != b.name or len(a.args) != len(b.args):
            return False
        ar, br = a.region, b.region
        while ar in region_assignments:
            ar = region_assignments[ar]
        while br in region_assignments:
            br = region_assignments[br]
        if ar != br:
            if isinstance(ar, str) and ar.startswith(('L', 'R')):
                region_assignments[ar] = br
            elif isinstance(br, str) and br.startswith(('L', 'R')):
                region_assignments[br] = ar
            else:
                return False
        return all(unify(x, y) for x, y in zip(a.args, b.args))
    return unify(rename(left.head, 'L', left), rename(right.head, 'R', right))


@dataclass
class Implementation:
    head: object
    type_vars: tuple = ()
    region_vars: tuple = ()
    prerequisites: tuple = ()
    equations: dict = field(default_factory=dict)
    methods: dict = field(default_factory=dict)


class TraitSolver:
    def __init__(self):
        self.implementations = []
        self.operations = {}

    def add(self, implementation):
        head = implementation.head
        if any(projections(head)):
            raise ValueError('Implementation heads must be projection-free')
        for prerequisite in implementation.prerequisites:
            if any(projections(prerequisite)):
                raise ValueError('Implementation prerequisites must be projection-free')
            if any(v > variables(head)[k] for k, v in variables(prerequisite).items()):
                raise ValueError('Implementation prerequisite introduces uncovered variables')
            if prerequisite.name not in ('Trait:Dup', 'Trait:Discard', 'Trait:NonAbandoning', 'Equality') and size(prerequisite) >= size(head):
                raise ValueError('Implementation prerequisites must strictly decrease')
        for equation in implementation.equations.values():
            if variables(equation).keys() - variables(head).keys():
                raise ValueError('Associated equation introduces uncovered variables')
            for projection in projections(equation):
                inputs = projection.args
                if any(any(projections(a)) for a in inputs):
                    raise ValueError('Associated equation projection inputs must be projection-free')
                if sum(size(a) for a in inputs) >= sum(size(a) for a in head.args):
                    raise ValueError('Associated equation projection inputs must strictly decrease')
                occurrences = sum((variables(a) for a in inputs), Counter())
                if any(v > variables(head)[k] for k, v in occurrences.items()):
                    raise ValueError('Associated equation projection repeats an input variable')
        if any(overlap(old, implementation) for old in self.implementations):
            raise ValueError('Overlapping trait implementation heads')
        self.implementations.append(implementation)

    def select_impl(self, goal, evidence=()):
        from inference import permissions
        def identity(t):
            from inference import Fn
            if isinstance(t, Fn):
                return replace(t, parameters=tuple(identity(a) for a in t.parameters), result=identity(t.result))
            return replace(t, args=tuple(identity(a) for a in t.args if not (t.name.startswith('$') and getattr(a, 'name', None) in ('Dup', 'Discard'))))
        if any(identity(goal) == identity(e) for e in evidence):
            return None, {}, {}
        if goal.name in ('Trait:Dup', 'Trait:Discard'):
            if permissions(goal.args[0])[goal.name == 'Trait:Discard']:
                return None, {}, {}
            raise ValueError('Missing trait evidence for ' + goal.name[6:])
        if goal.name == 'Trait:NonAbandoning':
            def admitted(row):
                if row.name == 'Effects':
                    return all(admitted(a) for a in row.args)
                if row.name.startswith('$!'):
                    from inference import Ty
                    return any(e.name == goal.name and e.args[0] in (row, Ty('Effects', (row,))) for e in evidence)
                return row.name in ('state', 'diverge') or row.name in self.operations and not any(op.mode == 'affine' for op in self.operations[row.name].values())
            row = goal.args[0]
            if not admitted(row):
                raise ValueError('Effect row does not satisfy NonAbandoning')
            return None, {}, {}
        candidates = []
        for implementation in self.implementations:
            try:
                types, regions = match(implementation.head, goal, implementation.type_vars, implementation.region_vars)
            except ValueError:
                continue
            candidates.append((implementation, types, regions))
        if len(candidates) != 1:
            raise ValueError('Missing trait evidence for ' + goal.name.removeprefix('Trait:'))
        implementation, types, regions = candidates[0]
        for prerequisite in implementation.prerequisites:
            self.check(substitute(prerequisite, types, regions), evidence)
        return implementation, types, regions

    def check(self, constraint, evidence=()):
        if constraint.name == 'Equality':
            if self.normalize_type(constraint.args[0], evidence) != self.normalize_type(constraint.args[1], evidence):
                raise ValueError('Associated type equality is not established')
        else:
            self.select_impl(constraint, evidence)

    def normalize_type(self, term, evidence=(), active=frozenset()):
        if term in active:
            raise ValueError('Cyclic associated type equation')
        for equation in evidence:
            if equation.name == 'Equality' and equation.args[0] == term:
                if getattr(term, 'name', None) in variables(equation.args[1]):
                    raise ValueError('Associated equation occurs check failed')
                return self.normalize_type(equation.args[1], evidence, active | {term})
        from inference import Fn
        if isinstance(term, Fn):
            return replace(term, parameters=tuple(self.normalize_type(a, evidence, active) for a in term.parameters),
                           result=self.normalize_type(term.result, evidence, active),
                           constraints=tuple(self.normalize_type(a, evidence, active) for a in term.constraints))
        term = replace(term, args=tuple(self.normalize_type(a, evidence, active) for a in term.args))
        if term.name.startswith('Projection:'):
            trait, member = term.name.removeprefix('Projection:').rsplit(':', 1)
            from inference import Ty
            goal = Ty('Trait:' + trait, term.args)
            try:
                implementation, types, regions = self.select_impl(goal, evidence)
            except ValueError:
                if any(variables(a) for a in term.args):
                    return term
                raise
            if implementation is None and not any(variables(a) for a in term.args):
                try:
                    implementation, types, regions = self.select_impl(goal, tuple(e for e in evidence if e != goal))
                except ValueError:
                    pass
            if implementation is not None and member in implementation.equations:
                return self.normalize_type(substitute(implementation.equations[member], types, regions), evidence, active | {term})
        return term
