# Camera recorder image dependency

Version12.3.0, installed/measured in the selected simulation/SDK verification environment. Retrieved 2026-11-18T23:01:01.425231+00:00.

- [Image.rst](https://raw.githubusercontent.com/python-pillow/Pillow/12.3.0/docs/reference/Image.rst), SHA256 76e3c86d7a509034ae6bbcac641bcaf19e9dbfb2eb0892409c18b33ef7b83f50
- [README.md](https://raw.githubusercontent.com/python-pillow/Pillow/12.3.0/README.md), SHA256 1b521e0e7b6004d492632a7d0797c3be451a8ff7f77a288f0ebbdf0a74fea859
- [LICENSE](https://raw.githubusercontent.com/python-pillow/Pillow/12.3.0/LICENSE), SHA256 15181e7363dca9aed78b79bebebc7fde7f1814b8bd311ea3b87ae8ccadfc185b

The reused canonical recorder uses Image.open(BytesIO(JPEG)), convert, thumbnail, new and save; its bounded camera decoder validates JPEG type and dimensions before composition. No model/GPU pipeline is introduced by pinning this host-side dependency. The existing recorder calls ffmpeg/libx264 externally; the worker still needs its actual encoder installed/qualified.
