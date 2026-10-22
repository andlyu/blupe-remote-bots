# HLS audio renditions

Use the full pinned1.7.2 build (`static/hls.min.js`) for the shared viewer. See README-1.7.2.md, Build tasks: the light distribution excludes AudioTrackController and AudioStreamController. MediaMTX can advertise a separate audio URI through EXT-X-MEDIA even when the variant CODECS lists AAC. The light player then decodes only video; manifest codec metadata and a fulfilled play() do not prove audio decoding. The shared page must load the full build. Keep the light asset for existing video-only consumers.
