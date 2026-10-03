"""Scoped-row unification prototype for specification §16.5.

Labels are already-resolved, opaque keys (including applied arguments or named
instance identity where needed). This does not infer Eldude source, select
handlers, unify type arguments, or check ownership/control obligations.
Closed-expression weakening is explicit; equality never drops duplicates.
Discard a solver after an unsuccessful unification.
"""
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True, eq=False)
class Var:
    """Binder identity is independent of its diagnostic spelling."""
    name: str
    rigid: bool = False


@dataclass(frozen=True)
class Row:
    labels: tuple[str, ...] = ()
    tail: Var | None = None

    def __post_init__(self):
        object.__setattr__(self, 'labels', tuple(sorted(self.labels)))


class Solver:
    def __init__(self):
        self.substitutions = {}

    def resolve(self, row):
        labels, tail = list(row.labels), row.tail
        while tail in self.substitutions:
            bound = self.substitutions[tail]
            labels.extend(bound.labels)
            tail = bound.tail
        return Row(tuple(labels), tail)

    def weaken(self, row):
        """Give a closed expression a fresh ambient tail at a permitted use site."""
        row = self.resolve(row)
        return row if row.tail is not None else Row(row.labels, Var('ambient'))

    def _bind(self, variable, row):
        row = self.resolve(row)
        if row.tail is variable:
            if row.labels:
                raise ValueError('Infinite effect row')
            return
        if variable is None or variable.rigid:
            raise ValueError('Cannot extend a closed row or instantiate a rigid tail')
        self.substitutions[variable] = row

    def unify(self, left, right):
        left, right = self.resolve(left), self.resolve(right)
        left_counts, right_counts = Counter(left.labels), Counter(right.labels)
        left_only = tuple((left_counts - right_counts).elements())
        right_only = tuple((right_counts - left_counts).elements())

        if left.tail is right.tail:
            if left_only or right_only:
                raise ValueError('Different prefixes over the same tail')
            return
        if not left_only and not right_only:
            if left.tail is not None and not left.tail.rigid:
                self._bind(left.tail, Row((), right.tail))
            else:
                self._bind(right.tail, Row((), left.tail))
        elif not left_only:
            self._bind(left.tail, Row(right_only, right.tail))
        elif not right_only:
            self._bind(right.tail, Row(left_only, left.tail))
        else:
            if (left.tail is None or right.tail is None
                    or left.tail.rigid or right.tail.rigid):
                raise ValueError('Unmatched labels require two flexible tails')
            shared = Var('shared')
            self._bind(left.tail, Row(right_only, shared))
            self._bind(right.tail, Row(left_only, shared))
