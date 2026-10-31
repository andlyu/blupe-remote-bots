"""Exercise installation and review-context generation in disposable repositories."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "adopt.py"


class Adoption(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name) / "integration"
        self.root.mkdir()

    def run_cli(self, *arguments, ok=0):
        result = subprocess.run([sys.executable, str(SCRIPT), *map(str, arguments)],
                                text=True, capture_output=True)
        self.assertEqual(result.returncode, ok, result.stderr + result.stdout)
        return result

    def install(self):
        return self.run_cli("install", "--target", self.root)

    def specification(self):
        return dict(website="https://fixture.example", backend="https://api.fixture.example",
                    station="fixture-yam", arms=["left"], approach="Fixture method",
                    duration_s=60, task="Disposable fixture; no physical action",
                    expected_motion="No movement occurs in this test",
                    recording_destination="Fixture workspace; no camera is recorded",
                    invocation_reference="Synthetic test fixture only; no actual task authorization",
                    identity=dict(fields=[]))

    def scope(self, value, ok=0):
        spec = self.root / "private-test-scope.json"
        spec.write_text(json.dumps(value))
        return self.run_cli("scope", "--target", self.root, "--spec", spec, "--json", ok=ok)

    def test_existing_instructions_and_completed_evidence_survive_idempotent_install(self):
        instructions = "# Existing instructions\nPreserve my release process.\n"
        (self.root / "AGENTS.md").write_text(instructions)
        checklist = self.root / "docs/COMPLETION-CHECKLIST.md"
        checklist.parent.mkdir()
        evidence = b"# Accepted evidence\n- [x] Runfixture123 with retained footage.\n"
        checklist.write_bytes(evidence)
        self.install()
        agents = (self.root / "AGENTS.md").read_text()
        self.assertTrue(agents.endswith(instructions))
        self.assertEqual(checklist.read_bytes(), evidence)
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = self.run_cli("install", "--target", self.root, "--check")
        self.assertEqual(json.loads(result.stdout)["status"], "current")
        self.install()
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_check_and_dry_run_have_no_file_side_effects(self):
        self.run_cli("install", "--target", self.root, "--check", ok=1)
        self.run_cli("install", "--target", self.root, "--dry-run")
        self.assertEqual(list(self.root.iterdir()), [])
        self.install()
        self.assertTrue((self.root / "docs/COMPLETION-CHECKLIST.md").is_file())

    def test_malformed_markers_refuse_all_changes(self):
        value = "# Owner instructions\n<!-- blupe-integration-harness:start -->\n"
        (self.root / "AGENTS.md").write_text(value)
        self.run_cli("install", "--target", self.root, ok=2)
        self.assertEqual((self.root / "AGENTS.md").read_text(), value)
        self.assertEqual(len(list(self.root.iterdir())), 1)

    def test_old_template_cannot_silently_omit_the_invocation_contract(self):
        template = Path(self.scratch.name) / "old-checklist.md"
        template.write_text("# Previous checklist\nNo invocation contract here.\n")
        self.run_cli("install", "--target", self.root, "--template", template, ok=2)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_symlinks_and_protected_paths_cannot_write_outside_integration(self):
        outside = Path(self.scratch.name) / "outside"
        outside.mkdir()
        (self.root / "tools").symlink_to(outside, target_is_directory=True)
        self.run_cli("install", "--target", self.root, ok=2)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse((self.root / "AGENTS.md").exists())
        (self.root / "tools").unlink()
        for path in ("../outside/evidence.md", ".codex/AGENTS.md", ".git/config", "/tmp/evidence.md",
                     "./AGENTS.md", "tools//blupe_harness.py", "docs/evidence\n.md"):
            self.run_cli("install", "--target", self.root, "--checklist", path, ok=2)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_edited_helper_is_preserved_before_any_other_upgrade(self):
        self.install()
        helper = self.root / "tools/blupe_harness.py"
        edited = helper.read_bytes() + b"\n# Owner edit\n"
        helper.write_bytes(edited)
        before = (self.root / "AGENTS.md").read_bytes()
        self.run_cli("install", "--target", self.root, ok=2)
        self.assertEqual(helper.read_bytes(), edited)
        self.assertEqual((self.root / "AGENTS.md").read_bytes(), before)

    def test_identity_scope_requires_confirmed_fields_and_exact_destinations(self):
        self.install()
        value = self.specification()
        value["identity"] = dict(fields=["name", "email"], runner="Synthetic tester",
                                 destinations=[value["website"], value["backend"]])
        self.assertIn("confirmation_reference", self.scope(value, ok=2).stderr)
        value["identity"]["confirmation_reference"] = "Synthetic identity fixture, not real permission"
        result = json.loads(self.scope(value).stdout)
        self.assertIn("Synthetic tester", result["notice"])
        self.assertIn("not new consent", result["notice"])
        self.assertIn("https://api.fixture.example", result["notice"])
        self.assertIn("User harness invocation: Synthetic test fixture", result["notice"])
        self.assertIn("Authorization granted by using this harness", result["notice"])
        self.assertNotIn("<task request", result["notice"])
        value["identity"]["destinations"].append("https://unrelated.example")
        self.scope(value, ok=2)

    def test_scope_rejects_unfilled_examples_credentials_and_invalid_bounds(self):
        self.install()
        self.scope([], ok=2)
        for field, item in (("invocation_reference", "REPLACE_OWNER_REFERENCE"),
                            ("website", "https://fixture:password@example.com"),
                            ("backend", "https://api.fixture.example/?token=fixture"),
                            ("backend", "https://api.fixture.example:invalid"),
                            ("duration_s", True), ("duration_s", 601), ("arms", ["unknown"])):
            value = self.specification()
            value[field] = item
            self.scope(value, ok=2)

    def test_installed_helper_works_without_source_checkout_or_global_configuration(self):
        self.install()
        value = self.specification()
        spec = self.root / "scope.json"
        spec.write_text(json.dumps(value))
        helper = self.root / "tools/blupe_harness.py"
        result = subprocess.run([sys.executable, str(helper), "scope", "--target", str(self.root),
                                 "--spec", str(spec)], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Fixture method", result.stdout)
        self.assertIn("No runner name/email submission", result.stdout)

    def test_changed_contract_cannot_silently_become_review_authorization(self):
        self.install()
        contract = self.root / "docs/BLUPE-HARNESS-CONTRACT.md"
        contract.write_text(contract.read_text() + "\nFixture edit.\n")
        self.scope(self.specification(), ok=2)
        self.run_cli("install", "--target", self.root, ok=2)

    def test_rendering_context_does_not_change_the_integration_or_store_identity(self):
        self.install()
        spec = self.root / "fixture-scope.json"
        spec.write_text(json.dumps(self.specification()))
        before = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.run_cli("scope", "--target", self.root, "--spec", spec)
        after = {p.relative_to(self.root): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
