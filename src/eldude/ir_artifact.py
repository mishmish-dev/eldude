"""Versioned experimental checked-IR artifacts; not canonical semantic interfaces."""
from dataclasses import fields
import json
import os
from pathlib import Path
import sys
import zipfile

from eldude.capture_rows import Argument, Variable
from eldude.effect_rows import Row, Var
from eldude.handlers import Defect, Evidence, Operation, Program, run
from eldude.inference import Fn, Ty, Value
from eldude.source_model import Symbol, Diagnostic, Span


RECORDS = {cls.__name__: cls for cls in (Argument, Variable, Row, Var, Evidence, Operation, Fn, Ty, Span)}


def encode_program(program, *, root=None):
    from eldude.source_modules import STDLIB

    records = {}

    def encode(value):
        if isinstance(value, Symbol):
            return {'symbol': [value.spelling, int(value.rsplit('#', 1)[1])]}
        if value is None or type(value) in (str, int, bool):
            return value
        if isinstance(value, tuple):
            result = {'tuple': [encode(item) for item in value]}
            if id(value) in program.origins:
                result['span'] = encode(program.origins[id(value)])
            return result
        if isinstance(value, frozenset):
            return {'set': [encode(item) for item in sorted(value, key=repr)]}
        if isinstance(value, dict):
            return {'map': [[encode(key), encode(item)] for key, item in sorted(value.items(), key=lambda p: repr(p[0]))]}
        if type(value) in RECORDS.values():
            if id(value) in records:
                return {'ref': records[id(value)]}
            serial = records[id(value)] = len(records)
            values = {f.name: getattr(value, f.name) for f in fields(value)}
            if isinstance(value, Span) and root is not None and Path(value.filename).is_absolute():
                filename = Path(value.filename)
                values['filename'] = ('<stdlib>/' + filename.relative_to(STDLIB).as_posix()
                                      if filename.is_relative_to(STDLIB) else Path(os.path.relpath(filename, root)).as_posix())
            return {'record': type(value).__name__, 'id': serial,
                    'fields': {name: encode(item) for name, item in values.items()}}
        raise ValueError(f'unsupported IR artifact value {type(value).__name__}')

    return {'ir_version': 1, 'core': encode(program.core), 'operations': encode(program.operations),
            'result': encode(program.inferred.type), 'effects': encode(program.inferred.effects)}


def decode_program(data):
    if data.get('ir_version') != 1:
        raise ValueError('unsupported Python IR artifact version')
    origins, records = {}, {}

    def decode(value):
        if value is None or type(value) in (str, int, bool):
            return value
        if 'symbol' in value:
            return Symbol(*value['symbol'])
        if 'tuple' in value:
            result = tuple(decode(item) for item in value['tuple'])
            if 'span' in value:
                origins[id(result)] = decode(value['span'])
            return result
        if 'set' in value:
            return frozenset(decode(item) for item in value['set'])
        if 'map' in value:
            return {decode(key): decode(item) for key, item in value['map']}
        if 'ref' in value:
            return records[value['ref']]
        cls = RECORDS[value['record']]
        result = cls(**{f.name: decode(value['fields'][f.name]) for f in fields(cls)})
        records[value['id']] = result
        return result

    core, operations = decode(data['core']), decode(data['operations'])
    inferred = Value(decode(data['result']), decode(data['effects']))
    return Program(core, inferred, operations, origins)


def main():
    try:
        with zipfile.ZipFile(sys.argv[0]) as archive:
            program = decode_program(json.loads(archive.read('program.json')))
        result = run(program).value
        if type(result) is not int or not 0 <= result <= 255:
            print('defect: Python host exit result must be an Int from 0 through 255', file=sys.stderr)
            return 1
        return result
    except Defect as error:
        span = program.origins.get(id(error.expression), Span('<artifact>', 0, 0, 1, 1))
        print(Diagnostic('defect', str(error), span), file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    except Exception as error:
        print(f'internal-error: {type(error).__name__}: {error}', file=sys.stderr)
        return 2
