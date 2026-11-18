# Prepared host lifecycle evidence

No real camera, model, physical queue, human contact or email was used.

- package-gate-72.json/txt: current required72-case gate; actual canonical
  controller/client plus mock station and synthetic camera encoding/recovery.
- physical-lifecycle-preflight.json/txt: historical71-case gate before the
  additional recorder-start failure regression; retained rather than replaced.
- physical-replay-broader-tests.json/txt: complete10-case canonical recorder suite
  in the existing native environment, including the separate RoboHarness UI.
- physical-capture-start-red.json/txt: reconstructed immediately preceding
  prepared behavior without the start-failure Stop handler. It fails the same
  actual-controller test, then all mock threads are stopped. This is not an old
  deployed revision. Current source passes the matching test in the72-case gate.
- missing-physical-coverage.json: removing PhysicalRun cases from actual discovery
  makes the release gate fail before execution; source was never mutated.
- physical-lifecycle-package-probe.json:184-file archive, every manifest hash
  matched, canonical imports/recorder/validator initialized solely from extracted
  archive with network rejected. No session or generated process was started.

Archive a00d13b64bd52dddce09f7bc9fc8545ecefdedc6ecbfe6817683eb3abbc4b00f is
prepared, not deployed. These checks do not establish matched task/contact,
actual host isolation, physical safety/task/outcome, observed motion timing or
UI live/immediate/historical physical replay. Public robot Run remains unavailable.
