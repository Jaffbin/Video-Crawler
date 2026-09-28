# Third-party components

The Windows Portable ZIP downloads and runs third-party software. Those components retain their
own licenses; this file does not license the Video Grabber project itself.

- CPython — Python Software Foundation License. The embedded distribution includes its `LICENSE.txt`.
  Source: <https://www.python.org/downloads/windows/>
- pip — MIT License. License metadata is included in the Python package distribution.
  Source: <https://github.com/pypa/pip>
- yt-dlp and its Python dependencies — their respective licenses and package metadata apply.
  Source: <https://github.com/yt-dlp/yt-dlp>
- pywebview and pythonnet — BSD-style and MIT licenses respectively. On Windows the application uses
  the Microsoft Edge WebView2 Runtime already distributed with Windows 11 and most Windows 10
  installations. Sources: <https://github.com/r0x0r/pywebview>, <https://github.com/pythonnet/pythonnet>
- FFmpeg build from `yt-dlp/FFmpeg-Builds` — GPL build. FFmpeg license and corresponding source/build
  information are published with that release. Source: <https://github.com/yt-dlp/FFmpeg-Builds>
- Deno — MIT License. Source: <https://github.com/denoland/deno>
- Playwright (optional) — Apache License 2.0. Source: <https://github.com/microsoft/playwright-python>

Open **Diagnostics** in the application to see installed versions. `runtime/components.json`
records the exact downloaded release URL and SHA-256 digest for native components.
