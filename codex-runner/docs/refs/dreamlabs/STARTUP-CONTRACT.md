# Pinned Dream SDK startup and observation contract

Verified against official dreamlabs-client1.0.0 and dreamlabs1.0.0 wheel sources used by this integration. This is a source-derived reference; it does not measure a production run.

- `dream/facade.py:DreamClient.__init__` reads the configured credential and binds endpoints; its contract says it sends no request or model session.
- `DreamClient.policy` opens a policy and creates a new observation window. `dream/client_ik.py:ClientIK.__init__` initializes the local solver. For EEF trajectory mode it warms the tick solve synchronously and starts trajectory compilation on a background thread; forward-kinematics initialization is also local. A duration around this whole policy call includes its setup and cannot automatically be called remote model inference.
- `set_observation` retains the newest measured state and a timestamped camera window. The SDK requires monotonic observation timestamps within an episode.
- `get_action` sends the latest state/window and creates or continues a stateful model session. Its EEF conversion/IK uses measured joint state and the commanded chunk anchor. A pre-Home prediction cannot be treated as a fresh post-Home prediction just by changing a flag or timestamp.
- The shared Astra/Codex HomeScene protocol uses actual saved Home observations and strict scene/lease/configuration/freshness checks plus bind/discard hooks. Dream does not implement that protocol. SDK setup may overlap native Home after lease grant; live Dream prediction remains after confirmed Home and fresh state/images.

Source SHA-256 values (wheel contents, not runtime timing evidence):
- `facade.py`: `24d3d83e21aaca76d48e20762864a249f4ca948560eb741a3211a51ad7f31104`
- `client_ik.py`: `6294e874f38d75526756acf42bc1592765367bf1fe2740e610c417297b845057`
