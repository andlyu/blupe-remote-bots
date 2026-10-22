# Viewer media and public replays

The shared local and hosted viewers use the same video, audio, optional clarity
preview, error handling and robot selection code. HLS includes the audio-capable
player build. Supported continuous station streams start with low-latency HLS;
other streams retain WebRTC with HLS fallback. Canvas presentation samples the
latest frame at up to eight frames per second without queuing older frames.
Playback health reports stale frames and estimated delay; those estimates do not
establish physical camera-to-screen latency.

Microphone sound uses the camera's video element and playback timeline. Audio
requires the station's version-two audio metadata and an audio track. Browser
autoplay policy may require pressing **Enable audio**. Explicit mute persists
across reloads and robot changes. Controller capture and relay configuration are
deployment responsibilities. See [observer enhancement](observer-enhancement.md)
for the opt-in before/after clarity preview and CPU worker.

Public replays have two delivery paths:

- Published originals and edited replays are hosted in the public Hugging Face
  dataset. The local launcher gets the replay catalog from the hosted playground.
- A ready quick-preview MP4 can be served first from the hosted playground's
  replay cache. The local launcher forwards the narrowly matched public video
  route and byte-range requests so the same player can seek. It forwards no local
  cookies or authorization headers. Cache clips retain their existing 16 MiB
  bound. Missing clips keep their upstream status rather than creating a replay.

Replay preparation uses an indeterminate indicator. The viewer checks for a
ready video and can replace a quick preview with the final edit after playback
ends. Closing the dialog or changing robots discards old readiness responses.
These routes serve public recordings; they do not create a private replay library
or change publication policy. Robot recording, export and dataset upload remain
outside this repository's website runner.

Serve `hls.min.js`, `robot-audio.js`, `robot-audio.css`, `replay-progress.js` and
`observer-enhancement-worker.js` with the other shared static files. The built-in
runner does this. A reverse proxy with an asset allowlist needs the same paths.
Worker loading uses the existing same-origin script policy. Sites providing an
ordered robot catalog can set `default_order: true`; the viewer preserves that
order and keeps explicit robot selections.
