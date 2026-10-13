# Audible autoplay and media lifecycle

Primary references reviewed2026-10-13UTC:

- Chrome policy: https://developer.chrome.com/blog/autoplay (current guidance, Chrome66+).
  Audible autoplay depends on prior interaction/engagement; always inspect play()'s
  Promise and expose a click control after rejection. Do not display playing before
  fulfillment. Developer test flags: `--autoplay-policy=no-user-gesture-required`
  and `--disable-features=PreloadMediaEngagementData,MediaEngagementBypassAutoplayPolicies`.
- HTMLMediaElement.play(): https://developer.mozilla.org/en-US/docs/Web/API/HTMLMediaElement/play
  Promise fulfills once playback starts; NotAllowedError indicates browser policy.
  Permission prompts can delay settlement, so ignore stale attempts after switching.
- WebKit policy: https://webkit.org/blog/6784/new-video-policies-for-ios/
  Audible media remains subject to user gesture restrictions; call play() directly
  from the fallback click when a remote stream is already ready.

Implementation: static/robot-audio.js. Default intent is enabled; explicit choices
persist locally. A rejected autoplay attempt retains the one current stream for
an immediate gesture retry. Switching/hiding tears down the prior reader and tracks;
showing reconnects according to intent. Never request browser microphone access,
change browser policies, or claim a blocked play() produced audible playback.
