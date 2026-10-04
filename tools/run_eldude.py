"""Check and execute one .eld file using the bounded fixture host profile."""
import argparse
import sys

from source_pipeline import execute_file
from source_syntax import Diagnostic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('file', help='Eldude source with an exported, nullary main')
    args = parser.parse_args()
    try:
        execution = execute_file(args.file)
    except Diagnostic as error:
        print(error, file=sys.stderr)
        return 1
    except (OSError, UnicodeError) as error:
        print(f'{args.file}:1:1: input: {error}', file=sys.stderr)
        return 1
    print('()' if execution.value is None else execution.value)
    return 0


if __name__ == '__main__':
    sys.exit(main())
