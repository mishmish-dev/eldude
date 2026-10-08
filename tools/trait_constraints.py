"""Canonical first-order trait evidence and associated normalization (§10)."""
from collections import Counter
from dataclasses import dataclass, field, replace


def variables(term):
    return Counter({term.name: 1}) if term.name.startswith('$') else sum((variables(a) for a in term.args), Counter())


def size(term):
    return 1 + sum(size(a) for a in term.args)


def substitute(term, types=None, regions=None):
    types, regions = types or {}, regions or {}
    if term.name.startswith('$') and term.name[1:] in types:
        return types[term.name[1:]]
    return replace(term, args=tuple(substitute(a, types, regions) for a in term.args),
                   region=regions.get(term.region, term.region))


def match(pattern, goal, type_vars, region_vars=(), types=None, regions=None):
    """Instantiate only implementation binders; caller variables stay rigid."""
    types, regions = {} if types is None else types, {} if regions is None else regions
    if pattern.name.startswith('$') and pattern.name[1:] in type_vars:
        name = pattern.name[1:]
        previous = types.setdefault(name, goal)
        if previous != goal:
            raise ValueError('Trait head mismatch')
    else:
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
        name = prefix + t.name if t.name.startswith('$') and t.name[1:] in impl.type_vars else t.name
        region = prefix + t.region if t.region in impl.region_vars else t.region
        return replace(t, name=name, args=tuple(rename(a, prefix, impl) for a in t.args), region=region)
    assignments, region_assignments = {}, {}
    def occurs(name, term):
        if term.name == name:
            return True
        if term.name in assignments:
            return occurs(name, assignments[term.name])
        return any(occurs(name, a) for a in term.args)
    def unify(a, b):
        while a.name in assignments:
            a = assignments[a.name]
        while b.name in assignments:
            b = assignments[b.name]
        if a == b:
            return True
        if a.name.startswith(('L$', 'R$')):
            if occurs(a.name, b):
                return False
            assignments[a.name] = b
            return True
        if b.name.startswith(('L$', 'R$')):
            return unify(b, a)
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

    def add(self, implementation):
        head = implementation.head
        for prerequisite in implementation.prerequisites:
            if any(v > variables(head)[k] for k, v in variables(prerequisite).items()):
                raise ValueError('Implementation prerequisite introduces uncovered variables')
            if prerequisite.name not in ('Trait:Dup', 'Trait:Discard', 'Equality') and size(prerequisite) >= size(head):
                raise ValueError('Implementation prerequisites must strictly decrease')
        if any(overlap(old, implementation) for old in self.implementations):
            raise ValueError('Overlapping trait implementation heads')
        self.implementations.append(implementation)

    def select_impl(self, goal, evidence=()):
        from inference import permissions
        if goal in evidence:
            return None, {}, {}
        if goal.name in ('Trait:Dup', 'Trait:Discard'):
            if permissions(goal.args[0])[goal.name == 'Trait:Discard']:
                return None, {}, {}
            raise ValueError('Missing trait evidence for ' + goal.name[6:])
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
                if term.name in variables(equation.args[1]):
                    raise ValueError('Associated equation occurs check failed')
                return self.normalize_type(equation.args[1], evidence, active | {term})
        term = replace(term, args=tuple(self.normalize_type(a, evidence, active) for a in term.args))
        if term.name.startswith('Projection:'):
            _, trait, member = term.name.split(':', 2)
            from inference import Ty
            goal = Ty('Trait:' + trait, term.args)
            try:
                implementation, types, regions = self.select_impl(goal, evidence)
            except ValueError:
                if any(variables(a) for a in term.args):
                    return term
                raise
            if implementation is not None and member in implementation.equations:
                return self.normalize_type(substitute(implementation.equations[member], types, regions), evidence, active | {term})
        return term
