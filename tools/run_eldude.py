"""Check and execute .eld files using the bounded fixture host profile."""
import argparse
import json
from pathlib import Path
import sys

from source_pipeline import execute_file
from source_syntax import Diagnostic


def display(value):
    return '()' if value is None else str(value).lower()


def run_examples(strict=False):
    root = Path(__file__).resolve().parents[1] / 'examples'
    manifest = json.loads((root / 'manifest.json').read_text(encoding='utf-8'))
    expected = manifest['runnable'] | manifest['pending']
    files = {str(p.relative_to(root)) for p in root.rglob('*.eld')
             if 'reject' not in p.relative_to(root).parts}
    if files != expected.keys() or manifest['runnable'].keys() & manifest['pending'].keys():
        print('FAIL example manifest must list every positive file exactly once')
        return 1
    passed = skipped = failed = 0
    for name, wanted in sorted(expected.items()):
        try:
            actual = execute_file(root / name).value
        except Diagnostic as error:
            if error.code == 'unsupported' and name in manifest['pending']:
                print(f'SKIP {name}: {error.message}')
                skipped += 1
            else:
                print(f'FAIL {name}: {error}')
                failed += 1
        except (OSError, UnicodeError, RuntimeError) as error:
            print(f'FAIL {name}: {error}')
            failed += 1
        else:
            if type(actual) is not type(wanted) or actual != wanted:
                print(f'FAIL {name}: expected {display(wanted)}, got {display(actual)}')
                failed += 1
            else:
                print(f'PASS {name}: {display(actual)}')
                passed += 1
    print(f'{passed} passed, {skipped} unsupported, {failed} failed')
    return int(bool(failed or (strict and skipped)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', nargs='?', help='Eldude source with an exported, nullary main')
    parser.add_argument('--examples', action='store_true', help='run the complete positive example corpus')
    parser.add_argument('--strict', action='store_true', help='with --examples, also fail for known implementation limits')
    args = parser.parse_args()
    if bool(args.file) == args.examples or (args.strict and not args.examples):
        parser.error('choose a file or --examples; --strict requires --examples')
    if args.examples:
        return run_examples(args.strict)
    try:
        execution = execute_file(args.file)
    except Diagnostic as error:
        print(error, file=sys.stderr)
        return 1
    except (OSError, UnicodeError) as error:
        print(f'{args.file}:1:1: input: {error}', file=sys.stderr)
        return 1
    print(display(execution.value))
    return 0


if __name__ == '__main__':
    sys.exit(main())
