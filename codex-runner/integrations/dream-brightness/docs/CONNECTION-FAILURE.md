# Dream1 request failure investigation

Status: **DONE_WITH_CONCERNS**. The client-side failure is identified; why the remote service closed the connection is not established without provider/gateway logs. This is a diagnosis, not a claimed repair.

| Field | Finding |
| --- | --- |
| Symptom | RuntimeError: Dream request failed (DreamProtocolError; connection_failure; RemoteDisconnected; response_headers) |
| Actual run | ep_2eda4cf9ffcf4ae0 / run_6cabc090460b4af9b2c16e4628539485, Andrew, Dream-1 beta, 50% brightness, requested120s |
| Observed failure boundary | Fourth policy prediction failed in HTTP response headers; SDK reported176.414ms RTT,261939 request bytes and0 response bytes. No HTTP status was received. |
| Before the failure | Three successful Dream responses and three completed motion packets,24+25+24=73 confirmed waypoints. Hardware feedback before prediction4 was settled/consistent and safety.ok=true. |
| Calibration involvement | Local observation forward kinematics completed. The fourth prediction never reached inverse-kinematics/action output or packet submission. No calibration mismatch, calibration validator failure or IK failure appears in this error path. Whether any physical calibration changed independently is not verified. |
| Root cause conclusion | The HTTP peer closed the Dream inference connection before replying. This error is not evidence that calibration caused the failure. Provider-side reason for closure is unavailable from the local trace. |
| Fix | None applied: no evidence justifies changing calibration or adding a retry for an ambiguously processed inference. |
| Fresh verification | Read the actual failed-run journal and matching worker prediction4 trace; traced installed Dream SDK1.0.0 transport._exchange -> HTTPConnection.getresponse -> HTTPResponse._read_status and actual adapter error handling. |
| Regression test | Not added; no code was changed. Existing transport error handling intentionally reports/stops rather than generating a fourth actuator packet. |
| Related | Runner77cee11e includes prior idle-connection replacement and HTTP keep-alive changes. The current logs establish header EOF, not whether the SDK's internal stale-connection retry was used. Do not claim it was only a stale socket without more evidence. |
| Experiment scoring | Treat this as model transport/infrastructure failure; do not count it as evidence of brightness robustness or calibration accuracy. The run remains unscored in the local results ledger. |

Evidence: [sanitized exact failure events and SDK stages](connection-failure-evidence.json). No model request, physical retry, calibration write, software restart or source repair was performed by this investigation. The existing localhost8798 server remains live.
