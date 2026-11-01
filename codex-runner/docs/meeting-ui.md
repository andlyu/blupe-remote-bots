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
visible after the picker closes. Camera views and Visitors remain directly available on phones. The three-dot
More menu is removed; per-camera expand controls and the guide below remain. The camera stage and canonical prompt remain the
single presentation/task surfaces; older quick-entry nodes retain their existing
listeners but are visually hidden in this shell.

The live **Your run result** assessment is a dedicated footer of **Task & notes**.
The implementation appends the existing `liveAssessment` node to
`sidePrompt.closest('.watchInteraction')`, outside the scrolling
`liveConversationPanel`, with a nonshrinking flex footer rule. When that parent
is absent, it falls back to placement after the prompt disclosure. Selecting
visitor chat hides the footer through `visitorChatSelected`, keeping run results
with task chat. Its existing button nodes, handlers, `data-label` values,
disabled states and server `can_edit` checks remain in place. A task caption
immediately above the buttons comes from this assessment
scope's own `state.task` or `state.prompt`, with its previous task retained when
ending metadata omits it. It therefore stays tied to the assessed run even if the
public chat shows a different prompt. The caption is clamped to two lines with
its full text in the `title` attribute and is hidden when no task is available.
Visible **Neutral**, **Failure** and **Success** labels replace the compact
assessment presentation. Neutral retains the empty value mapped to `null`,
leaving the run unscored. Saving, provisional/final and review-window messages
remain visible in their existing status elements. These result controls are
separate from the emoji reaction picker, whose actions are unchanged.

The assessment placement review inspected `static/hosted.js`,
`static/hosted.css`, `static/run-assessments.js` and the test definitions in
`tests/test_assessment_placement_ui.cjs` and `tests/test_run_assessment_ui.cjs`.
The placement definition checks that the footer receives the original assessment
node while preserving button identity, disabled states, handlers and labels. The
assessment definition checks retention of the run's own task when ending metadata
omits it. Existing assessment requests and mutation behavior are unchanged.
This is source-conformance evidence only; this documentation pass ran no tests
or browser and establishes no rendered desktop/phone result.

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

The task chat offers two views: `<current model> notes` and `Visitor chat`. The
model label follows the active run or selected model; Convo mode is removed.
The meeting visitor shortcut opens the same Visitor chat view.

On phones, Observer retains a full-width 16:9 camera row independently of the
remaining viewport height. Browser toolbars, run status and suggestions must not
collapse that row. Open chat follows the camera in normal document flow instead
of covering it. Short screens scroll to supporting content and controls; the
Observer remains uncropped. The keyboard may use a compact camera row while
editing a task. Desktop composition is unchanged.
