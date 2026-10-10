"""Check local Markdown links/anchors, chapter/code maps, and example results."""
from collections import Counter
import json
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[4]
# ponytail: inline links and ATX headings cover this repo; extend for reference
# links or Setext headings if the documentation starts using them.
LINK = re.compile(r'\[([^\]\n]*)\]\(([^)\s]+)\)')


def prose(text):
    """Yield source line numbers and text outside fenced code blocks."""
    fence = None
    for number, line in enumerate(text.splitlines(), 1):
        marker = re.match(r' {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if (marker and marker[1][0] == fence[0] and
                    len(marker[1]) >= len(fence) and not marker[2].strip()):
                fence = None
        elif marker:
            fence = marker[1]
        else:
            yield number, line


def anchors(text):
    explicit, headings = set(), set()
    for _, line in prose(text):
        explicit.update(re.findall(r'<a\b[^>]*\bid=[\"\']([^\"\']+)',
                                   re.sub(r'(`+).*?\1', '', line)))
        heading = re.match(r' {0,3}#{1,6}\s+(.+?)(?:\s+#+)?$', line)
        if heading:
            title = LINK.sub(r'\1', heading[1])
            slug = re.sub(r'[^\w -]', '', title.lower()).replace(' ', '-')
            name, suffix = slug, 0
            while name in headings:
                suffix += 1
                name = f'{slug}-{suffix}'
            headings.add(name)
    return explicit | headings


def check(root):
    root = Path(root).resolve()
    files = list(root.glob('*.md'))
    for directory in ('docs', 'eldude-program-examples', 'eldude-stdlib'):
        files.extend((root / directory).rglob('*.md'))
    texts = {path: path.read_text(encoding='utf-8') for path in sorted(files)}
    ids = {path: anchors(text) for path, text in texts.items()}
    targets, errors = {}, []
    for path, text in texts.items():
        targets[path] = set()
        for number, line in prose(text):
            for match in LINK.finditer(re.sub(r'(`+).*?\1', '', line)):
                link = match[2]
                url = urlsplit(link)
                if url.scheme or url.netloc:
                    continue
                target = (path.parent / unquote(url.path)).resolve() if url.path else path
                targets[path].add(target)
                location = f'{path.relative_to(root)}:{number}'
                if not target.exists():
                    errors.append(f'{location}: missing target {link}')
                elif url.fragment and target.suffix == '.md' and unquote(url.fragment) not in ids.get(target, set()):
                    errors.append(f'{location}: missing anchor {link}')

    maps = {
        root / 'docs/index.md': (root / 'docs/language-spec').glob('[0-9][0-9]-*.md'),
        root / 'docs/implementation.md': [*(root / 'python-impl/src/eldude').rglob('*.py'), *(root / 'python-impl/tests').rglob('test_*.py')],
    }
    for page, paths in maps.items():
        for path in sorted(paths):
            if path not in targets.get(page, set()):
                errors.append(f'{page.relative_to(root)}: missing map entry for {path.relative_to(root)}')

    manifest = json.loads((root / 'eldude-program-examples/manifest.json').read_text(encoding='utf-8'))
    expected = manifest['runnable'] | manifest['pending']
    page = root / 'eldude-program-examples/README.md'
    rows = re.findall(r'^\|.*?\]\(([^)]+\.eld)\) \| `([^`]+)` \|',
                      '\n'.join(line for _, line in prose(texts.get(page, ''))), re.M)
    counts = Counter(name for name, _ in rows)
    for name in sorted(counts.keys() | expected.keys()):
        if name not in expected or counts[name] != 1:
            errors.append(f'eldude-program-examples/README.md: expected exactly one manifest entry for {name}; found {counts[name]}')
    for name, value in rows:
        try:
            actual = None if value == '()' else json.loads(value.removesuffix('nat'))
        except ValueError:
            errors.append(f'eldude-program-examples/README.md: invalid expected value {value!r} for {name}')
            continue
        if name in expected and (type(actual) is not type(expected[name]) or actual != expected[name]):
            errors.append(f'eldude-program-examples/README.md: {name} documents {value}, manifest expects {expected[name]!r}')
    return errors


def main():
    try:
        errors = check(ROOT)
    except (OSError, ValueError, KeyError) as error:
        sys.exit(f'Documentation check failed: {error}')
    if errors:
        sys.exit('\n'.join(errors))
    print('Documentation checked: local links, anchors, chapter/code maps, and example results')


if __name__ == '__main__':
    main()
