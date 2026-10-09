"""Source type substitution, compatibility, and pattern binding helpers."""
from dataclasses import replace

from eldude.core.rows import Row
from eldude.core.inference import Ty, Fn, InferenceError, permissions, state

NAT, NEVER, UNKNOWN = Ty('Nat'), Ty('Never'), Ty('Unknown')


def substitute(t, types=None, regions=None, effect_variables=None):
    types, regions = types or {}, regions or {}
    if isinstance(t, Fn):
        effect_variables = {n: v for n, v in (effect_variables or {}).items() if n not in {v.name for v in t.effect_vars}}
        tail = t.effects.tail
        row = Row((), (effect_variables or {}).get(tail.name, tail)) if tail else Row()
        if tail and '!' + tail.name in types:
            from eldude.core.traits import effect_row
            row = effect_row(types['!' + tail.name], effect_variables)
        from eldude.core.captures import Variable, substitute_captures
        from eldude.core.traits import capture_row
        replacements = {c: capture_row(types['..' + c.name]) for c in set(t.captures or ()) | set(t.bound)
                        if isinstance(c, Variable) and '..' + c.name in types}
        dup, discard = t.dup, t.discard
        if t.captures and all(c in replacements for c in t.captures):
            usage = [permissions(types['..' + c.name]) for c in t.captures]
            dup, discard = dup or all(u[0] for u in usage), discard or all(u[1] for u in usage)
        return replace(t, parameters=tuple(substitute(p, types, regions, effect_variables) for p in t.parameters),
                       result=substitute(t.result, types, regions, effect_variables),
                       effects=Row(tuple(next((state(v) for k, v in regions.items() if label == state(k)), label)
                                         for label in t.effects.labels) + row.labels, row.tail),
                       bound=frozenset(regions.get(c, c) for c in substitute_captures(t.bound, replacements)),
                       dup=dup, discard=discard,
                       result_owner='region:' + regions.get(t.result_owner[7:], t.result_owner[7:]) if t.result_owner and t.result_owner.startswith('region:') else t.result_owner,
                       captures=None if t.captures is None else frozenset(regions.get(c, c) for c in substitute_captures(t.captures, replacements)))
    if t.name.startswith('$'):
        return types.get(t.name[1:], t)
    return replace(t, args=tuple(substitute(a, types, regions, effect_variables) for a in t.args), region=regions.get(t.region, t.region))


def compatible(left, right):
    if left in (UNKNOWN, NEVER) or right in (UNKNOWN, NEVER):
        return True
    if isinstance(left, Ty) and isinstance(right, Ty):
        return left.name == right.name and left.region == right.region and len(left.args) == len(right.args) and all(
            compatible(a, b) for a, b in zip(left.args, right.args))
    return left == right


def join_type(left, right):
    if left in (UNKNOWN, NEVER):
        return right
    if right in (UNKNOWN, NEVER):
        return left
    if not compatible(left, right):
        raise InferenceError('Branches must have the same type', code='type')
    if isinstance(left, Ty):
        return replace(left, args=tuple(join_type(a, b) for a, b in zip(left.args, right.args)))
    return left


def unwrapped(t):
    return t.args[0] if isinstance(t, Ty) and t.name in ('Linear', 'Affine', 'View', 'Mut') else t


def pattern_bindings(pattern):
    if pattern[0] == 'bind':
        return {pattern[1]}
    return set().union(*(pattern_bindings(p) for p in pattern[1:] if isinstance(p, tuple) and p and isinstance(p[0], str)))

FILE = Ty('Owned', (Ty('File'),))
ASYNC_FILE = Ty('Owned', (Ty('AsyncFile'),))
HOST_TYPES = {'File': FILE, 'AsyncFile': ASYNC_FILE}


OTHER_PRIMITIVES = {'Bool', 'Never', 'Text', 'Nat', 'UInt', 'Char', 'Bytes', 'Byte',
                    'Int8', 'Int16', 'Int32', 'Int128', 'Float32', 'Float64',
                    'UInt8', 'UInt16', 'UInt32', 'UInt64', 'UInt128'}
