"""Finite capture unions and lexically scoped argument sources (§13)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Argument:
    index: int
    depth: int = 0
    dup: bool = True
    discard: bool = True


@dataclass(frozen=True)
class Variable:
    name: str
    rigid: bool = True


class CaptureSolver:
    def __init__(self):
        self.constraints = []

    def equal(self, left, right):
        self.constraints.append((frozenset(left), frozenset(right), True))

    def include(self, actual, allowed):
        self.constraints.append((frozenset(actual), frozenset(allowed), False))

    def solve(self):
        substitutions, pending = {}, list(self.constraints)
        while True:
            progress, residual = False, []
            for left, right, equal in pending:
                left = substitute_captures(left, substitutions)
                right = substitute_captures(right, substitutions)
                if left == right or not equal and left <= right:
                    continue
                variables = {v for v in left | right if isinstance(v, Variable) and not v.rigid}
                if len(variables) == 1:
                    variable = next(iter(variables))
                    if variable in left and equal and variable not in right:
                        if not left - {variable}:
                            substitutions[variable] = right - (left - {variable})
                            progress = True
                            continue
                    if variable in right and variable not in left:
                        if not equal or not right - {variable}:
                            substitutions[variable] = left - (right - {variable})
                            progress = True
                            continue
                if not variables:
                    raise ValueError('Capture row mismatch')
                residual.append((left, right, equal))
            if not progress:
                return substitutions, tuple(residual)
            pending = residual


def substitute_captures(expression, substitutions):
    """Replace whole sources; unlike effect rows, unions are idempotent."""
    return frozenset().union(*(substitutions.get(atom, {atom}) for atom in expression))


def encode_captures(expression):
    return sorted(({'argument': a.index, 'depth': a.depth, 'dup': a.dup, 'discard': a.discard}
                   if isinstance(a, Argument) else {'variable': a.name, 'rigid': a.rigid}
                   if isinstance(a, Variable) else a for a in expression), key=str)


def decode_captures(expression):
    return frozenset(Argument(a['argument'], a['depth'], a['dup'], a['discard'])
                     if isinstance(a, dict) and 'argument' in a else Variable(a['variable'], a['rigid'])
                     if isinstance(a, dict) else a for a in expression)
