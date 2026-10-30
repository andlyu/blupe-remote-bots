# Playground packet service

The standalone website creates its own session through RunnerController. The
Playground integration instead uses a private packet service. The Playground
retains its one queue admission, lease, motor commands, measured completion,
recording and Stop. The worker receives observations and emits packets; it has
no robot-session capability and never creates another robot session.

Run the worker in its own environment:

```sh
./run.sh --worker --port 8798 --service-token-file /private/path/agp-worker-token \
  --agent docker --data /var/lib/agp-remote-yam
```

The token file must contain a random secret of at least 32 characters and stay
outside Git. The default bind is loopback. Real untrusted/public prompts use the
existing per-run Docker isolation and require server-configured model auth; the
trusted local Codex mode reuses the operator's existing login. Never copy login
credentials into run workspaces. See README's hosting limits before public use.

Configure a shared Playground version containing `remote_yam.agent_policy_service`:

```sh
export YAM_AGENT_POLICY_ORIGIN=http://127.0.0.1:8798
export YAM_AGENT_POLICY_TOKEN_FILE=/private/path/agp-worker-token
export YAM_AGENT_POLICY_MODEL=gpt-6-astra
export YAM_AGENT_POLICY_ROBOT_ID=yam-1
```

The existing launcher then advertises **Agent as Policy** and **Agent as Policy +
MEMO**. Visitors cannot choose worker origins, credentials or arbitrary models.
Use existing task-chat steering for corrections. The MEMO panel shows the pinned
retrieval version, retrieved IDs and saved guidance/templates. BluPe-hosted guest
admission belongs in apps/blupe_web and must retain its existing run allowance.
Configure only supported YAM stations; the worker checks its robot identity.

## Service protocol

All endpoints require `Authorization: Bearer TOKEN`. No credential is exposed to
the browser or generated agent code. JSON bodies are bounded to 512 KB.

| Method / path | Contract |
| --- | --- |
| GET /health | Configured robot and encoder identity |
| POST /runs | Idempotent client_run_id, private namespace, task, robot_id, memo, measured observation; returns worker run ID |
| POST /runs/ID/poll | Observation, completed-packet acknowledgement, event cursor, corrections; returns one pending packet, events, delivery receipts and status |
| POST /runs/ID/stop | Idempotently cancel agent process; the host controller separately stops its robot lease |

Packets retain their IDs across lost polls. The worker unblocks a command only
after the host acknowledges the matching final cursor and settled observation.
Duplicate acknowledgements are harmless. A wrong lease/cursor or uncertain
motion fails without replay. A missing host poll cancels the agent after 15 s;
the robot gateway and host remain responsible for the physical lease/Stop.
Restarts mark unfinished workers interrupted and never resume motion.

The shared runner and this service are separate processes with separate pinned
dependencies. No private BluPe source or deployment state is needed to install
this repository. The provider, steering acknowledgement hook and UI additions
live in blupe-remote-yam/codex-runner.
