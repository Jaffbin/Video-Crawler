# Save from Chrome

This Manifest V3 extension sends a page link to the existing local Video Grabber queue.
Keep Video Grabber running; a hidden Windows tray session works too. It does not start the app.
The downloader's existing supported-site and login requirements still apply.

## Install this development version

1. Start Video Grabber, open **Settings and help**, turn on **Allow the Chrome extension to connect**,
   and keep the app running. The setting is off by default so other programs on the computer
   cannot connect the same way.
2. In Chrome, open `chrome://extensions` and enable **Developer mode**.
3. Click **Load unpacked** and select this repository's `browser-extension/chrome` folder.
   Alternatively extract `artifacts/video-grabber-chrome-extension.zip` and select the extracted folder.
   The folder must contain `manifest.json`. In a Portable ZIP, select **Chrome Extension**.
4. Pin **Video Grabber — Save from Chrome** using Chrome's extensions menu.
5. Open a video or music page, click the extension, check **Save to**, choose video/MP3/source audio
   and quality, then click **Add to queue**. **View queue** reopens the desktop window, or opens
   the local web interface if the app is running in browser mode.

After a source update, click **Reload** on the extension's Chrome management page.
The extension is now version **0.2.0**. It adds the `contextMenus` permission for two explicit
right-click actions; it still has no permission to read all websites in the background.

## Keyboard and right-click access

- **Alt+Shift+V** opens the same confirmation popup for the active page. Chrome handles this as
  its reserved extension-action command. Use **Change shortcut** in the popup (or open
  `chrome://extensions/shortcuts`) to reassign it if the OS or another extension uses that key.
- Right-click an HTTP/HTTPS page and choose **Send this page to Video Grabber…**, or right-click
  a link and choose **Send this link to Video Grabber…**. The selected link is shown explicitly;
  it does not silently switch to the page containing the link or a newly focused tab.
- Every entry point asks for output and quality before **Add to queue**. No context menu or
  keyboard shortcut immediately starts a download. The existing-file review still applies.
- If Chrome cannot open the action popup, a packaged confirmation page opens in a tab instead.
  Programmatic popups are available for normal extensions in Chrome 127+; see the
  [Chrome action API](https://developer.chrome.com/docs/extensions/reference/api/action#method-openPopup).
  A context selection can be opened once and is valid for two minutes; choose it again if it
  expires. A stale confirmation never falls back to a different page.
This is an unpacked development build, not a Chrome Web Store listing. Normal store installation
requires a separate publishing step and review. No store account is needed for local testing.

## Connection and privacy

- The popup reads the active tab only after an explicit toolbar/shortcut action (`activeTab`).
  A right-click action captures only the page or link selected by that action.
- The only host permission is HTTP on `127.0.0.1`, for the local app. There are no content scripts,
  cookies permissions, history permissions, remote services or analytics.
- Discovery checks the app's normal ports 8765–8784. For `--port` outside that range, expand
  **Connection settings**, enter the numeric port and click **Connect**.
- Multiple discovered instances require choosing a save folder, unless a previous choice still exists.
  If a restarted app changes that folder, reconnect and confirm it before submitting again.
- The existing app session token is read from its local page and verified against its authenticated API.
  It stays in service-worker memory. Persistent storage contains only format/quality/connection
  preferences, not page links, titles or session tokens. Context-menu selections briefly use
  extension-only session storage with opaque IDs, not URLs in the confirmation-page address.
  Selections are removed on consumption; expired/older selections are pruned on subsequent
  menu actions (at most 20 retained), and session storage clears when Chrome exits. This uses
  Chrome 102+'s session-storage API. The app keeps its normal download history.
- The background service worker completes the submission even if the popup is dismissed.
  With the current app, existing complete files are shown before enqueueing. Choose to use them
  or download a separate copy, or open Library to review their quality. No new task is created
  until that choice. A copy retains the original files. Reload the extension after updating it.
  A network failure after submission is never automatically retried: check Queue before retrying.
- Quick submissions are a single item, without playlists or subtitles. The current app automatically
  saves available website covers for video downloads. MP3 uses the chosen
  bitrate; source audio keeps the best available source container. Main-window cookie/proxy settings
  are not copied into the extension; use New download for downloads requiring those settings.
- Browser UI/internal/file pages cannot be sent. URLs containing embedded credentials are rejected.
- The UI follows Chrome's language (English, Simplified/Traditional Chinese or Japanese) and the
  system light/dark preference.

## Development

No npm dependencies or frontend bundling are required. Load `chrome/` directly.

```powershell
node --test browser-extension/tests/connection.test.js
.venv\Scripts\python.exe browser-extension/build.py
```

`build.py` generates the PNG arrow icons and ZIP; edit the generator rather than editing generated
icons manually. It uses Pillow from the app's desktop dependencies. Extension pages use packaged
scripts/styles and a strict CSP. The app's existing Host/token checks and CORS behavior are unchanged.
