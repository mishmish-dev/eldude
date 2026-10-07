"""Finite capture unions and lexically scoped argument sources (§13)."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Argument:
    index: int
    depth: int = 0
    dup: bool = True
    discard: bool = True


def substitute_captures(expression, substitutions):
    """Replace whole sources; unlike effect rows, unions are idempotent."""
    return frozenset().union(*(substitutions.get(atom, {atom}) for atom in expression))


def encode_captures(expression):
    return sorted(({'argument': a.index, 'depth': a.depth, 'dup': a.dup, 'discard': a.discard}
                   if isinstance(a, Argument) else a for a in expression), key=str)


def decode_captures(expression):
    return frozenset(Argument(a['argument'], a['depth'], a['dup'], a['discard'])
                     if isinstance(a, dict) else a for a in expression)
