# Meeting playground UI

The accepted October 31 UI uses Observer as the main presentation, other real
cameras as surrounding tiles, and a centered row of meeting controls. Task chat
opens by default on desktop without stealing keyboard focus. Phones start with
chat closed; the labeled Chat control opens and closes the same panel without
recreating its state. Visitors can close it, switch
to public visitor chat, use the existing model/run options, or scroll down for the
run library and guide. Phones retain Observer above a bounded chat sheet when it is opened.

The persistent “Prompt the arms” composer delegates to the shared run lifecycle.
Three robot-specific suggestions appear below it and fill an editable draft;
choosing a suggestion never starts a run. Stop mirrors the existing session-owned
Stop action. No microphone or device camera controls are invented.

Defaults for Robo-house YAM (`yam-1`): Put the apple onto the plate; Put the markers
into the cup; Stack the blocks. YAM2 (`yam-2`): Stack the blocks; Put the orange
block on the towel; Put the towel into the bin.

`GET /api/task-suggestions` follows existing robot routing. The authenticated
controller editor at `/robots/<id>/prompt-suggestions` belongs to the hosting
repository. Both services use `YAM_TASK_SUGGESTIONS_DATABASE`, or the sibling
`task-suggestions.sqlite3` of `YAM_ROBOT_ORDER_DATABASE`. The portal writes this
private SQLite file; the playground reads it. Without overrides, shared defaults
apply. Saves refresh within five seconds without restarting the playground.

Release review preserves the current model picker, inline steering, queue,
identity, recording history, assessments and hosted extensions. The existing incoming robot-audio toggle lives in the meeting toolbar. A compact
emoji picker reuses the existing reaction actions; effects and errors remain
visible after the picker closes. On phones, camera-view and visitor-chat controls
are available in More. The camera stage and canonical prompt remain the
single presentation/task surfaces; older quick-entry nodes retain their existing
listeners but are visually hidden in this shell.

Validation: full shared Python/Node suites, controller owner/Origin/persistence
checks, browser desktop/phone review and simulated Stop. No model or physical
robot execution is required for this presentation change.

“What have people run?” beside the task suggestions opens the existing Past Runs
Cloud, scrolls to its point graph, and focuses its keyboard controls. It preserves
current model/search/label/highlight filters and run previews. Reduced-motion
preferences use an immediate scroll.

Hosted applications may provide `yamApplication.robotChoices(robots)` and set
`showPendingRobots` false. These change selector choices while preserving the
underlying robot registry and recordings. Standalone configured choices remain
available; hosted-only exclusions belong to the application's configuration.

Mobile interaction references: Google Meet [chat](https://support.google.com/meet/answer/9308979) and [call controls](https://support.google.com/meet/answer/12562325). These inform explicit chat access and a primary reaction picker; they do not add browser microphone capture.
