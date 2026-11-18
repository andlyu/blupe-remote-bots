# Prepared physical lifecycle and recorder

This is source preparation, not a physical readiness claim. Public robot Run
still returns503 before persistence/dispatch. Production worker remains e075e8d3;
Site7 is unchanged. Session API60 provides the dedicated no-email admission.
Google funding, worker SSH access and YAM1 connectivity remain unresolved.

The host PhysicalRun composes the existing GeneratedControllerProvider with the
actual RunnerController.join_and_run, its preparation worker, FIFO/capability,
lease, native Home, packet/feedback/Stop and interaction log. A single object
cannot restart/replay a run, including after an unknown outcome. Original website
Start is retained separately from the native session clock. Stop revokes the
canonical session before closing generated execution. Terminal controller status
is not proof that its worker/capture have ended; wait/status retain those facts
and container cleanup uncertainty explicitly. No object outcome or observed
motion time is inferred from packets, return values or controller completion.

stage_controller reads the exact retained simulation controller/station bytes
with bounded no-symlink reads and verifies their host receipt/source/image hashes.
It stages the existing keyless runtime, canonical model/safety assets and captured
calibration into a separate job. The real channel binds/rechecks controller source
before launching any process. Changed source produces zero process/queue activity;
a closed channel cannot start again. No API key, contact or lease enters this
runtime. The same native validation remains in the host command path.

PhysicalRun defaults to the existing PublicCameraReplay, using Gemini Robotics
as its approach. That shared recorder now takes an explicit model parameter;
RoboHarness defaults and recovery behavior are preserved. Capture and recovered
metadata must keep the same approach and station; one approach cannot consume
another's pending frames. Timestamped 2Hz overhead footage uses the existing
streaming ffmpeg encoder and gap labels. This is separate from simulation video.
The host Pillow12.3.0 dependency is pinned to the tested SDK environment; official
references/license are retained in docs/refs/pillow. ffmpeg/libx264 must actually
exist and be qualified on the worker; no host installation occurred here.

Release preflight passes72tests:63integration cases and9canonical recorder cases.
The unrelated RoboHarness application UI test imports its own OpenCV policy stack;
its complete10-case native suite passed separately in the existing native venv.
An initial combined-env broader run failed that import (cv2 absent), not encoding;
no package was installed to conceal it. The first lifecycle fixture omitted the
channel start/ready method and failed prequeue; the fixture was completed and all
7new lifecycle cases pass through the actual controller/HTTP serializer with a
mock station. Recorder cases encode synthetic frames, never physical footage.
Removing PhysicalRun cases from actual discovery makes preflight exit1 before
execution (0.5268s negative control, no source mutation). See
evidence/physical-lifecycle for measured receipts and logs.

The worker package now includes the canonical controller/recorder source, exact
public staging assets and license notices instead of only four read transports.
Packaging executes the required gate. These files are built from their owning
shared repository; no editable source was copied into the private repository.

Still required: compose this lifecycle with the worker run store/Stop watcher and
quiet attributed session client after source-bound simulation; expose retained
physical receipts/video through authenticated gateway/history/UI; qualify the
actual host executor/encoder; establish fresh matched task-scene/contact and
native-control evidence; run the selected model and representative manipulation;
verify original-Start/queue/Home/observed-motion timings and final normal-UI live
and immediate/historical replay. Those remaining items are neither replaced by
these tests nor checked off. The full checklist remains1/17.
