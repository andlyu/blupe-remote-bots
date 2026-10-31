"""Read-only checklist/evidence gate; never establishes physical/site success."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit


TEMPLATE = Path(__file__).with_name('COMPLETION-CHECKLIST.md')
ITEM = re.compile(r'^- \[([ xX])\] (.*)$')
LINK = re.compile(r'\[([^\]\n]+)\]\((?:<([^>\n]+)>|([^\s)]+))\)')


def verification_errors(current: str, canonical: str) -> list[str]:
    """Retain the detailed contract while allowing filled evidence/run tables."""
    errors = []
    current_sections = re.split(r'^## ', current, flags=re.MULTILINE)
    sections = {}
    for section in current_sections[1:]:
        title, _, body = section.partition('\n')
        if title in sections:
            errors.append('Duplicate contract section: ' + title)
        sections[title] = body
    for section in re.split(r'^## ', canonical, flags=re.MULTILINE)[1:]:
        title, _, body = section.partition('\n')
        if title not in sections:
            errors.append('Missing contract section: ' + title)
            continue
        if title in ('Completion requirements', 'Integration and evidence'):
            continue
        actual = ' '.join(sections[title].split())
        for paragraph in body.split('\n\n'):
            # These fields/tables are intentionally filled by the researcher.
            if paragraph.startswith(('- ', '| ')):
                continue
            if ' '.join(paragraph.split()) not in actual:
                errors.append('Missing/changed verification guidance in: ' + title)
                break
    return errors


def requirements(text: str) -> list[dict]:
    """Read only canonical acceptance items, allowing Evidence lines in copies."""
    section = False
    rows = []
    for line in text.splitlines():
        if line == '## Completion requirements':
            if section or rows:
                raise ValueError('Duplicate Completion requirements section')
            section = True
            continue
        if section and line.startswith('## '):
            section = False
        if not section or not line.strip():
            continue
        match = ITEM.fullmatch(line)
        if match:
            rows.append(dict(checked=match[1].lower() == 'x', text=[match[2]], evidence=[]))
        elif rows and line.startswith('  Evidence:'):
            rows[-1]['evidence'].append(line.removeprefix('  Evidence:').strip())
        elif rows and line.startswith('  '):
            rows[-1]['text'].append(line.strip())
        else:
            raise ValueError('Unexpected text in Completion requirements: ' + line)
    if not rows:
        raise ValueError('Missing Completion requirements')
    for row in rows:
        row['text'] = ' '.join(' '.join(row['text']).split())
    return rows


def evidence_errors(lines: list[str], directory: Path) -> list[str]:
    links = [match for line in lines for match in LINK.finditer(line)]
    if not links:
        return ['Checked requirement needs an Evidence line with a Markdown link']
    errors = []
    for match in links:
        target = match[2] or match[3]
        parsed = urlsplit(target)
        if parsed.scheme in ('http', 'https') and parsed.netloc:
            continue  # The reviewing agent must open and verify remote evidence.
        if parsed.scheme or parsed.netloc or not parsed.path:
            errors.append('Unsupported evidence link: ' + target)
            continue
        path = Path(unquote(parsed.path))
        if not path.is_absolute():
            path = directory / path
        if not path.is_file():
            errors.append('Missing evidence file: ' + target)
        elif path.stat().st_size == 0:
            errors.append('Empty evidence file: ' + target)
    return errors


def audit(checklist: Path, template: Path = TEMPLATE) -> dict:
    canonical_text = template.read_text(encoding='utf-8')
    current_text = checklist.read_text(encoding='utf-8')
    canonical = requirements(canonical_text)
    current = requirements(current_text)
    errors = verification_errors(current_text, canonical_text)
    if [row['text'] for row in current] != [row['text'] for row in canonical]:
        errors.append('Completion requirements differ from the current template; restore/reconcile all items without weakening them')
    if errors:
        return dict(status='invalid_contract', errors=errors,
            total=len(canonical), checked=sum(row['checked'] for row in current))
    remaining = []
    for index, row in enumerate(current, 1):
        errors = (evidence_errors(row['evidence'], checklist.parent) if row['checked']
                  else ['Requirement is unchecked'])
        if errors:
            remaining.append(dict(item=index, requirement=row['text'], reasons=errors))
    return dict(status='incomplete' if remaining else 'ready_for_review',
                total=len(current), checked=sum(row['checked'] for row in current),
                remaining=remaining,
                limitation='Structural evidence check only; independently inspect evidence and the full contract before native goal completion')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checklist', type=Path, help='The integration-specific checklist copy')
    args = parser.parse_args()
    try:
        result = audit(args.checklist)
    except (OSError, ValueError) as exc:
        print(json.dumps(dict(status='invalid_contract', errors=[str(exc)])))
        return 2
    print(json.dumps(result, indent=2))
    return 0 if result['status'] == 'ready_for_review' else 1


if __name__ == '__main__':
    raise SystemExit(main())
