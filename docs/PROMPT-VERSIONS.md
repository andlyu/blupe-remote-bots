
## Editable chat prompts

The chat model panel offers per-robot/per-provider/per-model system prompt drafts, saved in the browser and applied only when starting a new Cartesian YAM run. Opus initially selects `roboharm-cartesian`; other models retain With Haste. Selecting a preset or resetting replaces the draft. Custom text is limited to 16,000 UTF-8 bytes. The run records its effective prompt and SHA-256. Server-side motion checks and station workspace constraints remain in force.

The RoboHarm Cartesian preset adapts the task strategy from [this reference run](https://7c9bfe0c.roboharm-artifacts.pages.dev/logs/omen-2_rig-4_adhoc_121d2b0b), whose metadata reports Haiku 5.5 at high effort, not Opus. It preserves the existing MIT RoboCurve embodiment prompt and adds an independently worded Cartesian strategy. It does not import the source rig's 0.65 m base spacing, 224-pixel camera scales, empty-gripper thresholds, table-zero assertion, below-table contact allowance, or claim that unsafe commands are clamped. This is an adaptation, not a verbatim copy or a physical calibration. The editor does not alter inference speed or effort.
