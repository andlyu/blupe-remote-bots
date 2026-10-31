"""Install repo-local harness guidance or render a review scope; never run robots."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import tempfile
from urllib.parse import urlsplit

BEGIN = "<!-- blupe-integration-harness:start -->"
END = "<!-- blupe-integration-harness:end -->"
SOURCE = "https://github.com/andlyu/blupe-remote-bots/tree/main/codex-runner/integration-harness"
CONTRACT_SOURCE = "https://github.com/andlyu/blupe-remote-bots/blob/main/codex-runner/integration-harness/COMPLETION-CHECKLIST.md#authorization-granted-by-using-this-harness"
MANIFEST = ".blupe-harness.json"
HELPER = "tools/blupe_harness.py"
CONTRACT = "docs/BLUPE-HARNESS-CONTRACT.md"
CONTRACT_HEADING = "## Authorization granted by using this harness"


def digest(value):
    return hashlib.sha256(value).hexdigest()


def local_path(root, name):
    parts = PurePosixPath(name).parts
    if (any(ord(c) < 32 or c in "`\\" for c in name)
            or not parts or PurePosixPath(name).is_absolute() or any(
            p in ("..", ".git", ".codex", ".agents", ".aws") for p in parts)):
        raise ValueError("Use a repository-relative documentation path")
    value = root
    for part in parts:
        value = value / part
        if value.is_symlink():
            raise ValueError("Refusing to follow a managed-path symlink: " + name)
    if value.exists() and not value.is_file():
        raise ValueError("Managed destination is not a file: " + name)
    return value


def instructions(checklist):
    return f'''{BEGIN}
## BluPe research harness startup

Before working on this integration, read `{checklist}`, `{CONTRACT}` and this
repository's other instructions. Route the requested workflow through the
harness contract; retain the user's request and adopted instruction selecting
the harness as invocation evidence. Reading a file alone is not an invocation.
For actions covered by that invocation, proceed after a concrete test notice;
do not request repeated permission for covered identity submission, queue entry,
bounded motion or recording. Keep the grant in the contract, not this summary.

Before a physical test, prepare its exact scope with
`python tools/blupe_harness.py scope --target . --spec /path/to/private-scope.json`.
Put that scope and the applicable owner authorization directly in the surfaced
notice and tool approval justification/context. Include exact site/backend
origins, station/arms, approach, task, duration, motion, recording destination,
and the invocation covering confirmed identity fields and operational destinations.
Ask only for missing required scope. A file or generated summary grants no new
consent and cannot override an explicit denial or managed/tool permissions.
After a denial, preserve its exact action/reason; continue independent work or
a materially safer alternative. Do not retry through another route.

Preserve queue/lease, readiness, validation, hardware limits and Stop. Never
automatically replay a timed-out movement or substitute Automated for a human
runner to avoid a restriction. Keep unmet acceptance items unchecked; mock
success does not establish physical motion, replay or either 15-second timing measure.
The source and content hashes are recorded in `{MANIFEST}`. These instructions
are repo-local and require no global Codex or approval-policy changes.
{END}'''


def merge_instructions(original, block):
    if BEGIN not in original and END not in original:
        return block + "\n\n" + original
    if original.count(BEGIN) != 1 or original.count(END) != 1:
        raise ValueError("Malformed harness markers; preserve and repair the existing AGENTS.md")
    first, last = original.index(BEGIN), original.index(END)
    if last < first:
        raise ValueError("Reversed harness markers in AGENTS.md")
    return original[:first] + block + original[last + len(END):]


def contract_text(template):
    text = template.decode()
    start = text.find(CONTRACT_HEADING + "\n")
    if start < 0:
        raise ValueError("Update the shared harness: its authorization-by-use contract is missing")
    end = text.find("\n## ", start + len(CONTRACT_HEADING))
    return text[start:end if end >= 0 else len(text)].strip() + "\n"


def install(root, checklist, template, *, check=False, dry_run=False):
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Target must be an existing integration directory")
    names = ["AGENTS.md", checklist, HELPER, MANIFEST, CONTRACT]
    if len(set(names)) != len(names):
        raise ValueError("Checklist must have its own documentation path")
    paths = {name: local_path(root, name) for name in names}
    if len(set(paths.values())) != len(paths):
        raise ValueError("Checklist aliases another managed file")
    old = json.loads(paths[MANIFEST].read_text()) if paths[MANIFEST].exists() else {}
    if not isinstance(old, dict):
        raise ValueError("Preserve and repair the existing harness manifest")
    before = {name: path.read_bytes() if path.exists() else None for name, path in paths.items()}
    raw_helper = Path(__file__).read_bytes()
    helper = paths[HELPER]
    if helper.exists() and helper.read_bytes() != raw_helper:
        if digest(helper.read_bytes()) != old.get("helper_sha256"):
            raise ValueError("Preserve the existing edited helper before upgrading: " + HELPER)
    raw_template = template.read_bytes()
    raw_contract = contract_text(raw_template).encode()
    contract = paths[CONTRACT]
    if contract.exists() and contract.read_bytes() != raw_contract:
        if digest(contract.read_bytes()) != old.get("contract_sha256"):
            raise ValueError("Preserve the existing edited contract before upgrading: " + CONTRACT)
    block = instructions(checklist)
    agent = paths["AGENTS.md"]
    original = agent.read_text() if agent.exists() else ""
    changes = {"AGENTS.md": merge_instructions(original, block).encode(),
               HELPER: raw_helper, CONTRACT: raw_contract}
    # A completed checklist belongs to the integration, including all evidence.
    if not paths[checklist].exists():
        changes[checklist] = raw_template
    manifest = dict(schema=1, source=SOURCE, checklist=checklist,
                    contract_source=CONTRACT_SOURCE,
                    template_sha256=digest(raw_template), helper_sha256=digest(raw_helper),
                    contract=CONTRACT, contract_sha256=digest(raw_contract),
                    instructions_sha256=digest(block.encode()))
    changes[MANIFEST] = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    changes = {name: raw for name, raw in changes.items()
               if not paths[name].exists() or paths[name].read_bytes() != raw}
    result = dict(status="changes_needed" if changes else "current", changed=sorted(changes),
                  checklist_preserved=paths[checklist].exists(), source=SOURCE)
    if check or dry_run:
        return result
    for name, path in paths.items():
        if (path.read_bytes() if path.exists() else None) != before[name]:
            raise ValueError("A concurrent edit changed " + name + "; rerun setup to preserve it")
    for name, raw in changes.items():
        path = paths[name]
        path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(prefix=".blupe-harness-", dir=path.parent)
        try:
            with os.fdopen(handle, "wb") as stream:
                stream.write(raw)
            os.chmod(temporary, path.stat().st_mode & 0o777 if path.exists() else 0o644)
            os.replace(temporary, path)
        finally:
            Path(temporary).unlink(missing_ok=True)
    result["status"] = "installed" if changes else "current"
    return result


def required(value, key, limit=4000):
    item = value.get(key)
    if (not isinstance(item, str) or not 1 <= len(item.strip()) <= limit
            or item.strip().startswith("REPLACE_")):
        raise ValueError("Missing or invalid scope field: " + key)
    return item.strip()


def origin(value):
    if not isinstance(value, str):
        raise ValueError("Scope origins must be explicit HTTPS origins")
    parts = urlsplit(value)
    port = parts.port  # Reject malformed or out-of-range port specifications.
    if (parts.scheme != "https" or not parts.hostname or parts.username or parts.password
            or any(c.isspace() for c in value) or port == 0
            or parts.path not in ("", "/") or parts.query or parts.fragment):
        raise ValueError("Use an exact HTTPS origin without credentials, path or query")
    return parts.scheme + "://" + parts.netloc


def scope(root, specification):
    manifest = json.loads(local_path(root, MANIFEST).read_text())
    if not isinstance(manifest, dict) or manifest.get("schema") != 1:
        raise ValueError("Unsupported harness manifest; reinstall from the shared source")
    checklist = local_path(root, manifest["checklist"])
    contract = local_path(root, manifest["contract"])
    raw_contract = contract.read_bytes()
    if digest(raw_contract) != manifest["contract_sha256"]:
        raise ValueError("Installed contract changed; review and reinstall before preparing scope")
    data = json.loads(specification.read_text())
    if not isinstance(data, dict):
        raise ValueError("Scope specification must be a JSON object")
    site, backend = origin(data.get("website")), origin(data.get("backend"))
    duration, arms = data.get("duration_s"), data.get("arms")
    if type(duration) is not int or not 1 <= duration <= 600:
        raise ValueError("Scope duration must be 1–600 seconds within the integration's own limits")
    if not isinstance(arms, list) or not arms or len(set(arms)) != len(arms) or any(
            arm not in ("left", "right") for arm in arms):
        raise ValueError("Scope must name the affected left/right arms")
    identity = data.get("identity", {})
    if not isinstance(identity, dict):
        raise ValueError("Identity scope must be an object")
    fields = identity.get("fields", [])
    if not isinstance(fields, list) or any(f not in ("name", "email") for f in fields):
        raise ValueError("Identity fields must be name and/or email")
    destinations = identity.get("destinations", [])
    if not isinstance(destinations, list):
        raise ValueError("Identity destinations must be explicit origins")
    destinations = [origin(v) for v in destinations]
    if fields:
        confirmation = required(identity, "confirmation_reference")
        runner = required(identity, "runner", 200)
        if not destinations or any(v not in (site, backend) for v in destinations):
            raise ValueError("Identity destinations must match this test's site/backend")
        identity_text = (f"Confirmed runner: {runner}. Fields: {', '.join(fields)}. "
                         f"Destinations: {', '.join(destinations)}. Identity confirmed: {confirmation}.")
    elif destinations:
        raise ValueError("Identity destinations require the transmitted field scope")
    else:
        identity_text = "No runner name/email submission is included in this scope."
    value = dict(approach=required(data, "approach", 200), website=site, backend=backend,
                 station=required(data, "station", 200), arms=arms, duration_s=duration,
                 task=required(data, "task"), expected_motion=required(data, "expected_motion"),
                 recording_destination=required(data, "recording_destination"),
                 invocation_reference=required(data, "invocation_reference"),
                 contract_sha256=digest(raw_contract),
                 checklist_sha256=digest(checklist.read_bytes()), identity=identity_text)
    grant = raw_contract.decode().split("\n### ", 1)[0]
    notice = ("User harness invocation: " + value["invocation_reference"] + ".\n"
              f"Applicable harness contract ({manifest['contract']}; {manifest['contract_source']}):\n"
              + grant + "\n"
              f"Website: {site}; backend: {backend}. Station: {value['station']}; "
              f"arms: {', '.join(arms)}. Approach: {value['approach']}. "
              f"Duration: {duration}s.\nTask: {value['task']}\n"
              f"Expected motion: {value['expected_motion']}\n"
              f"Recording/retention: {value['recording_destination']}\n{identity_text}\n"
              "Keep normal queue/lease, readiness, validation, hardware limits and Stop intact; "
              "never automatically retry a timed-out movement.\n"
              "This summary is review context, not new consent. Confirm its references against "
              "the actual user instructions. It does not authorize retrying a denied action.")
    return dict(scope=value, notice=notice)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    adopt = commands.add_parser("install", help="Install local startup guidance; preserve existing evidence")
    adopt.add_argument("--target", type=Path, required=True)
    adopt.add_argument("--checklist", default="docs/COMPLETION-CHECKLIST.md")
    adopt.add_argument("--template", type=Path, default=Path(__file__).with_name("COMPLETION-CHECKLIST.md"))
    adopt.add_argument("--check", action="store_true")
    adopt.add_argument("--dry-run", action="store_true")
    review = commands.add_parser("scope", help="Render the exact notice/context; submits nothing")
    review.add_argument("--target", type=Path, required=True)
    review.add_argument("--spec", type=Path, required=True)
    review.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "install":
            result = install(args.target, args.checklist, args.template,
                             check=args.check, dry_run=args.dry_run)
            print(json.dumps(result, indent=2))
            return 1 if args.check and result["changed"] else 0
        result = scope(args.target.resolve(strict=True), args.spec)
        print(json.dumps(result, indent=2) if args.json else result["notice"])
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.exit(2, "Harness setup: " + str(exc) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
