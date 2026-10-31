"""Offline acceptance/evidence checks; no model, network or robot calls."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


HARNESS = Path(__file__).resolve().parents[1] / 'integration-harness'
spec = importlib.util.spec_from_file_location('audit_completion', HARNESS / 'audit_completion.py')
audit_completion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit_completion)


class CompletionAuditTest(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.copy = self.root / 'integration.md'
        self.template = audit_completion.TEMPLATE.read_text()
        self.total = len(audit_completion.requirements(self.template))
        (self.root / 'receipt.txt').write_text('Synthetic fixture; not physical evidence.\n')

    def write_copy(self, *, checked=True, evidence='[receipt](receipt.txt) — fixture observation'):
        lines = []
        for line in self.template.splitlines():
            if line.startswith('- [ ] '):
                line = line.replace('- [ ] ', '- [x] ', 1) if checked else line
            lines.append(line)
            # Evidence may precede continuation lines without changing the requirement.
            if line.startswith('- [x] ') and evidence is not None:
                lines.append('  Evidence: ' + evidence)
        self.copy.write_text('\n'.join(lines) + '\n')

    def test_new_integration_reports_every_open_requirement(self):
        self.write_copy(checked=False)
        result = audit_completion.audit(self.copy)
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(len(result['remaining']), self.total)
        self.assertEqual(result['checked'], 0)

    def test_model_completion_assertion_and_checked_boxes_are_insufficient(self):
        self.write_copy(evidence=None)
        with self.copy.open('a') as stream:
            stream.write('\nThe model says all work is complete.\n')
        result = audit_completion.audit(self.copy)
        self.assertEqual(result['status'], 'incomplete')
        self.assertEqual(len(result['remaining']), self.total)

    def test_evidence_receipts_produce_reviewable_state_never_success(self):
        self.write_copy()
        result = audit_completion.audit(self.copy)
        self.assertEqual(result['status'], 'ready_for_review')
        self.assertEqual(result['remaining'], [])
        self.assertNotIn('success', result)
        self.assertIn('independently inspect', result['limitation'])

    def test_followup_retains_existing_evidence_and_open_items(self):
        self.write_copy()
        self.copy.write_text(self.copy.read_text().replace('- [x] ', '- [ ] ', 1)
                             + '\n## Goal context\nAmendment: verify updated deployment.\n')
        result = audit_completion.audit(self.copy)
        self.assertEqual(result['checked'], self.total - 1)
        self.assertEqual([row['item'] for row in result['remaining']], [1])

    def test_missing_empty_and_unsupported_evidence_fail_closed(self):
        (self.root / 'empty.txt').touch()
        for link in ('missing.txt', 'empty.txt', 'javascript:alert', '#nothing', 'https://'):
            with self.subTest(link=link):
                self.write_copy(evidence=f'[receipt]({link})')
                self.assertEqual(audit_completion.audit(self.copy)['status'], 'incomplete')

    def test_remote_evidence_is_only_structurally_reviewable(self):
        self.write_copy(evidence='[run](https://blupe.io/runs/fixture) — inspect this independently')
        self.assertEqual(audit_completion.audit(self.copy)['status'], 'ready_for_review')

    def test_changed_deleted_or_duplicate_requirements_cannot_pass(self):
        self.write_copy()
        original = self.copy.read_text()
        for text in (original.replace('A usable website exists', 'A plan exists', 1),
                     original.replace('- [x] ', '  ', 1),
                     original.replace('## Completion requirements',
                                      '## Completion requirements\n- [x] Additional fake requirement')):
            with self.subTest(text=text[:60]):
                self.copy.write_text(text)
                try:
                    self.assertEqual(audit_completion.audit(self.copy)['status'], 'invalid_contract')
                except ValueError:
                    pass  # Invalid section syntax is also a closed gate.

    def test_current_contract_addition_reopens_an_old_copy(self):
        self.write_copy()
        newer = self.root / 'newer-template.md'
        newer.write_text(self.template.replace('## Completion requirements',
                         '## Completion requirements\n\n- [ ] New acceptance requirement'))
        self.assertEqual(audit_completion.audit(self.copy, newer)['status'], 'invalid_contract')

    def test_detailed_rules_and_final_deployed_verification_cannot_be_removed(self):
        self.write_copy()
        original = self.copy.read_text()
        for text in (original.replace('`t1 - t0 <= 15 seconds`', '`t1 - t0 <= 500 seconds`'),
                     original.replace('## Final verification before completion', '## Optional review'),
                     original.replace('never automatically retry a timed-out movement', 'always retry a timed-out movement')):
            with self.subTest(text=text[:60]):
                self.copy.write_text(text)
                self.assertEqual(audit_completion.audit(self.copy)['status'], 'invalid_contract')

    def test_run_evidence_and_documented_exceptions_can_be_filled(self):
        self.write_copy()
        self.copy.write_text(self.copy.read_text().replace('| | | | | |',
            '| fixture run | 10:00 | 10:01 / receipt.txt | 60 | exception |')
            .replace('- Exception record (repeat for each affected run):',
                     '- Exception record (repeat for each affected run): fixture only')
            .replace('- Website URL:', '- Website URL: https://blupe.io/fixture'))
        self.assertEqual(audit_completion.audit(self.copy)['status'], 'ready_for_review')

    def test_cli_exit_codes_and_no_checklist_mutation(self):
        for checked, evidence, status, code in (
                (False, None, 'incomplete', 1),
                (True, None, 'incomplete', 1),
                (True, '[receipt](receipt.txt)', 'ready_for_review', 0)):
            self.write_copy(checked=checked, evidence=evidence)
            before = self.copy.read_bytes()
            process = subprocess.run([sys.executable, str(HARNESS / 'audit_completion.py'), str(self.copy)],
                                     capture_output=True, text=True)
            self.assertEqual(process.returncode, code)
            self.assertEqual(json.loads(process.stdout)['status'], status)
            self.assertEqual(self.copy.read_bytes(), before)
        self.copy.unlink()
        process = subprocess.run([sys.executable, str(HARNESS / 'audit_completion.py'), str(self.copy)],
                                 capture_output=True, text=True)
        self.assertEqual(process.returncode, 2)
        self.assertEqual(json.loads(process.stdout)['status'], 'invalid_contract')


if __name__ == '__main__':
    unittest.main()
