# Using Video Grabber

The application works locally in a desktop WebView or a browser. The sidebar separates
**New download**, **Queue**, **Auto-download**, and **Library**. The sidebar's bottom tools are,
from top to bottom: **Getting started**, **Open folder**, **Language**, **Settings and help**,
and **Close behavior**. Open **Settings and help** for updates and component diagnostics.
In narrow windows, **More tools** in the top bar opens the independent guide and close settings;
**Language** retains its own top-bar icon. Close behavior is available in the desktop app.

On Windows desktop, the main window's **×** asks whether to **Run in background** or **Exit app**.
Choose **Always run in background** together with the background action to skip future confirmations.
The sidebar's **Close behavior** entry changes this preference back to **Ask every time**;
in narrow windows, the same setting is available in **More tools**.
**Exit directly** closes without a prompt when there are no unfinished downloads. Running and
queued downloads, including waiting tasks in a paused queue, still trigger the confirmation.
Click the tray icon to reopen it. Right-click the icon for **Quick download** or **Exit**.
The close dialog shows the current unfinished task count and updates while tasks finish.
An explicit tray **Exit** also asks when downloads are running or waiting, even if the main
window normally closes to the background. Failed, canceled and completed records are excluded.
Exit stops the application; unfinished running tasks retain their existing queue recovery state.
Closing a normal browser tab does not use this tray behavior. If the tray fails to start,
background is unavailable; the app stays visible until you confirm an exit.

On Windows 10/11 desktop, a background download batch produces one system notification when the
whole queue is idle. Use **Play** (or **Open image**), **Open folder**, or **View queue** directly
from the notification. For several completed downloads, file actions explicitly refer to the
latest completed item, whose filename is shown. A wholly failed batch only offers **View queue**.
Paused queues with waiting tasks are not treated as finished. Canceled tasks are not counted as
failures, and previous history is not announced again after restarting the app.

The top-bar bell turns completion notifications on or off and remembers the setting independently
of close behavior. Foreground downloads retain the ordinary in-app completion message. Native
background notifications do not depend on the WebView continuing to poll. File actions work only
while the app is running and recheck that the file is still available; moved or removed files take
you back to Queue. Exiting clears pending completion notifications. Windows **Do Not Disturb** or
disabled notifications for **Video Grabber** may suppress banners; the app does not bypass those
settings. Missing native notification dependencies fall back to a text-only tray reminder; update
the source checkout's desktop dependencies with the same Python used to launch the app:
`python -m pip install -e ".[desktop]"`. The Portable launcher prepares these dependencies itself.
The app registers its notification identity for the current Windows user; no administrator access
or startup registration is required.

**Quick download** opens a small separate window. Paste one HTTP/HTTPS link or click **Read clipboard**,
choose video or audio (MP3 or source audio) and quality, check the save location, then start.
The link enters the same queue as the main window. **View queue** brings the main window forward.
Closing the quick panel keeps downloads running and preserves its current draft until the app exits.
This panel handles one item at a time with playlists and subtitles disabled. Videos automatically
save the website cover when available. Audio covers remain an option in the main window. Use
New download for batch links, playlists, images and companion-file options. Nothing reads the
clipboard automatically. Language and theme follow the main window.

**Download preset** in New download offers **Everyday video** (up to 1080p), **High-quality MP3**
(320 kbps), **Keep source audio**, and **Cover only**. Applying a preset never starts a download.
Adjust the output as needed, then choose **Save current as preset** to create a named custom preset.
Custom presets can be renamed or deleted after selection; built-ins stay available. Up to 50 custom
presets are stored in this app/browser profile. They save format, quality/bitrate, subtitle options
and cover options only, leaving links, playlist selection, sign-in, network and save-folder settings
alone. A higher MP3 bitrate cannot restore quality missing from the source. Quick download and the
Chrome extension retain their existing separate workflows.

Open **Settings and help → Backup and restore** to export one JSON file (up to 16 MiB). It contains
output preferences, custom presets, theme/language, desktop notification and close preferences, and
Library favorites, collections, tags, notes and playback progress. Downloaded media, thumbnails,
subtitles, download queues/history, audio playback queues, subscriptions, source URLs, login data
and proxy information are excluded.
Keep a separate copy of media with the same paths relative to the library root; a backup of these
annotations does not recreate media. Backup files can contain personal filenames and notes.
The desktop window opens a native save dialog for exports; a browser uses its download settings.
Only annotations attached to readable media in the current library are exported; missing files and
Recovery items are excluded.

Choose a backup to see a read-only preview before restoring. Existing scalar values, including
saved appearance/download/desktop settings, take precedence; even an existing empty note or an
explicitly unfavorited item is retained. Tags and collection membership combine within existing
limits. Collections are matched by name, and existing custom presets win name/ID conflicts.
Only missing settings are filled. Therefore a restored setting may intentionally leave the current
appearance unchanged. Library records match by relative path and byte size, not content hash;
missing, inaccessible or differently sized files are listed and skipped. Copy the matching media
first and import again to restore those records. Recovery contents are excluded.

Restoring does not change the save folder, move media, alter active jobs or create subscriptions.
If relevant data changes after the preview, preview again before applying it. Metadata/settings
files are staged with recovery copies so ordinary write failures roll back. Browser settings are
applied after the library commit; if browser storage fails, the dialog explicitly reports that the
library restored and offers a fresh preview to retry the settings. No existing browser values are
intentionally removed. Theme/language and presets update without restarting the app.

The optional Chrome extension provides the same single-item workflow from a video or music page.
Install the development version using [the Chrome extension instructions](../browser-extension/README.md).
Click its toolbar icon, choose the output and quality, confirm the save folder and add to the queue.
First turn on **Allow the Chrome extension to connect** in **Settings and help**; it is off by default.
Keep the app running (the Windows tray is enough). If disconnected, open the app and click Reconnect.
Press **Alt+Shift+V** to open the extension for the current page, or right-click a web page/link and
choose **Send this page/link to Video Grabber…**. Confirm the displayed link, format and quality
before adding it to Queue. These actions are independent of any future desktop-pet feature.
Use **Change shortcut** in the extension to customize the key. A context-menu selection is valid
once for two minutes; if expired, select it again. Chrome may open a confirmation tab when an
action popup is unavailable. Reload the extension in Chrome after updating to version 0.2.0.
With multiple app instances, select a save folder first. The extension has its own output preferences
and does not inherit the main window's cookie/proxy settings; use New download when those are required.

Use the sun/moon switch in the top bar to change appearance. In light mode the sun is red;
in dark mode the moon is yellow. A moving ring also identifies the selected mode. The app
starts in dark mode and remembers your selection on this device when browser storage is
available. The switch supports keyboard activation and respects reduced-motion preferences.
Light mode spreads outward from the switch; dark mode spreads from five staggered raindrop
points. Rapid clicks replace the previous transition. Resizing finishes the change immediately.
Reduced motion or an older browser without the required animation support uses a direct switch.

The interface adapts to the window: wide download pages use two columns, narrow windows
use bottom navigation, and short windows reduce spacing. Download actions remain visible
while the form scrolls. Queue keeps its search toolbar visible in spacious windows; narrow
or short windows scroll the toolbar with the list so it cannot cover task controls. Library
keeps its search visible. Long lists and expanded settings retain vertical scrolling so controls
stay readable. Queue titles are shortened to fit; hover over a title to read it in full, and
action buttons wrap as the available width decreases.

The guide checks download readiness automatically. On supported Windows installations, click
**Prepare download features** to install missing components; the app restarts its service if needed.
The guide shows three steps: check and prepare, paste the first link, and find results in Library.
Preparation displays the current stage without requiring tool paths or terminal commands. If a
connection check or installation fails, use **Check again** or **Try preparation again**. Components
already prepared are reused. After a preparation restart, the guide reopens; **Start downloading**
opens New download and focuses the link field. Source installs outside a virtual environment use
the current Python's user package directory during preparation; portable and virtual environments
keep their existing package locations.
If Windows blocks a component, open **Technical details** for the specific file. Preparation does
not change Windows security policy. You can still choose **Download images for now**.

Queue errors show a short explanation and actions such as preparation, opening a folder, repair,
or retry. For sites requiring sign-in, open the source page and sign in, then choose a browser and
confirm its use for retry. The app does not read a browser session before that confirmation.
Expand **Log** for technical details. Completed downloads offer **Play video**, **Play audio**,
or **View image**, alongside **Show in folder**.

## Your first download

1. Paste one or more links, one per line, in **New download**.
2. Choose **Video**, **Audio** or **Images**. Audio offers MP3 or **Keep source audio**;
   Images offers **Video cover** or **Direct image**. Expand **Subtitles and cover** for attachments.
   **Analyze link** is optional.
3. Click **Start download**. The app opens **Queue** automatically.

MP3 offers **Highest quality** (320 kbps), **Standard quality (recommended)** (192 kbps), and
**Save space** (128 kbps). Expand **Custom bitrate** for 96 or 256 kbps and the other exact values.
Existing saved bitrates are retained. Higher MP3 bitrates do not restore details missing from the source.

**Keep source audio** selects the best available site audio without re-encoding. The file format
depends on the source, such as M4A or Opus, and older players may not support it. This is the site's
offered audio, not necessarily the original recording. Covers are saved as separate JPG files in this
mode. It is also available for Auto-download subscriptions. Unsupported extraction fails with a
message rather than silently converting to MP3; you can choose MP3 for broader playback compatibility.

Before starting, **You will save** summarizes the format, quality, subtitles, covers and playlist
selection. It does not require link analysis. Without a preview, the summary explains whether a
playlist link would download every entry, a specified range, or just one video.

**Save to** shows the current folder. Click **Change folder** to choose an existing writable folder
using the system dialog. Finish or cancel queued downloads first. The app remembers your choice
and restarts automatically to apply it. Canceling the dialog changes nothing. Each folder has its
own Library, Queue history, Recovery and Auto-download settings; switching folders does not move
or delete anything. Switch back to manage the original folder again. An explicit `--dir` takes
priority over the saved selection.

Temporary connection resets, timeouts and temporary HTTP errors retry the affected item at most
twice. Queue shows **Reconnecting (1/2)** or **Reconnecting (2/2)** while waiting. Completed playlist
entries are kept. Cancel stops the retry wait immediately. Sign-in, permission, certificate and
Windows application-control errors require attention rather than repeated requests.

![New download](images/new-download.jpg)

Analysis previews the first link only. Supported sites can provide a title, thumbnail,
duration and available video resolutions. The size estimate describes the selected format;
MP3 estimates use duration and output bitrate. Estimates are not final sizes: conversion,
container overhead and site metadata can change the result. Unknown sizes remain unknown.
After changing quality or format, analyze again to update the estimate.

For a single playlist link, the preview displays up to 100 entries using their original
playlist indices. Check entries to download only that selection. Selecting none disables
download. **Select preview entries** selects only the displayed entries, not the whole
playlist. To download other entries, use the advanced **Playlist range** setting instead.
Existing simple ranges are reflected in the preview; advanced slice syntax stays in the
range field without being approximated by the checkboxes. Preview-generated selections
apply to the current link and are cleared when it changes or is submitted.

Analysis does not download media, but it connects to the source site. It uses the configured
proxy, cookies and Referer. An analysis failure does not guarantee that download will fail.

## Download covers and images

Choose **Video cover** for a video page supported by yt-dlp. The app extracts its thumbnail URLs
and tries the best available supported image, without downloading the video or converting the
image. Files go under `covers/`; playlist covers retain their playlist numbering. Missing covers
are reported as failures, and recorded failed playlist entries can be retried from Queue.
MP4 downloads automatically save the best available website cover beside the video and embed it
when supported. Library prefers this saved image and fits the whole image without cropping it.
Embedding errors are logged without discarding the downloaded video or separate cover.
Sites without a cover (including most direct MP4 links) still use a video frame in Library.
Existing downloads are not changed automatically. MP3 cover downloads remain optional.

Choose **Direct image** for a URL that returns image bytes. A page containing pictures, a gallery
page or an HTML sign-in page is not a direct image URL. JPG/JPEG, PNG, WebP, GIF and AVIF are
supported, with a 100 MiB limit per image. The app checks the response type and image signature
and saves the original bytes under `images/`. URLs do not need a filename extension. Analysis
reads the image header to report its format and known size; it does not save a file.

Both modes use the configured proxy, cookies, Referer, download speed limit and request delay.
They do not require ffmpeg. Unsupported responses, expired links and authentication failures
produce failed tasks. Incomplete downloads stay hidden and are removed on cancellation or error;
retry starts the image download again. These modes support manual tasks only; Auto-download
subscriptions support MP4, MP3 and source audio.

## Manage the queue

New download, Quick download and the Chrome extension check for existing complete files before
adding tasks. You can open the saved files, open Library, use the existing downloads, or download
another copy. Other new links in a batch are still added. Copies receive a separate filename;
existing videos, audio and companion files are retained. Saved quality/bitrate is shown when
known, and differing settings are called out. Older files without quality records are labeled
as unknown. Files that are missing, empty, in Recovery or incomplete do not prevent a new download.
This check does not claim that an entire playlist or multi-stream page has been downloaded.

**Skip videos that were already downloaded** (New download) covers playlists and Auto-download
too. Before each task, complete files in Library whose source link maps to a known site video are
added to the skip list, so videos saved before the option was turned on are skipped as well.
Video and audio keep separate lists (`.archive.txt` and `.archive-audio.txt` in the download
folder): having a video as MP3 does not stop an MP4 download. A file you deleted or moved to
Recovery is downloaded again. Direct media links and sites without a matching extractor are not
recognized and are downloaded again.

MP4, MP3 and source audio tasks verify that ffmpeg can start before downloading media. A missing or blocked
executable fails the task immediately; expand its log and open Diagnostics to see the selected
path and launch error. The application does not change Windows application control policies.

![Queue controls](images/queue.jpg)

- **Pause queue** prevents workers from starting waiting tasks; running downloads continue.
  Resume to start waiting tasks again. Pause and waiting order are saved across restarts.
- Move waiting tasks up or down. Running jobs cannot be reordered.
- Select individual tasks, or **Select visible** after filtering the list.
- **Cancel selected** requests cancellation of queued/running jobs.
- **Retry selected** creates new tasks with the original settings for failed/canceled jobs.
  For failures with recorded playlist indices, only those indices are retried, preserving
  playlist numbering and filenames. Failed individual links can also be retried separately.
  Expand **failed items** to see the recorded entries. If an error cannot be attributed to an
  entry (for example, the playlist itself cannot be loaded), Retry uses the original selection.
  Canceled jobs retry the original selection so unattempted entries are not lost.
- **Remove selected** removes finished task records, not downloaded files.

The result message reports processed and skipped tasks. A task that changed state, or is not
eligible for the chosen action, is skipped. Cancellation of a running download can take time;
partial files may remain. Worker concurrency means several tasks may start close together.

Waiting and interrupted running tasks return to the queue automatically when the application
restarts, with interrupted transfers placed before the saved waiting order. A paused queue
stays paused. Explicitly canceled tasks stay canceled. Existing partial video downloads are
continued when the source supports it; MP3 work uses a persistent hidden work directory across
restarts/retries. Recovery does not guarantee continuation through conversion or an expired URL.
Completed entries may be checked again when an interrupted playlist resumes; enable the download
archive to skip completed entries. Keep the download folder and history file together.

Submitting the same link with the same settings while it is queued or running skips that duplicate
and reports the skipped count. Different settings and finished tasks can still be submitted.
Duplicate retries are also skipped. This checks links/settings, not whether different URLs point
to the same underlying video.

## Manage your library

### Continuous audio playback

Choose **Play audio** on a completed audio file to start or select it in the persistent bottom
bar. **More > Add to playback queue** adds without starting playback. Audio details reuse this
player, so closing details or switching between New download, Queue, Auto-download and Library
does not interrupt audio. Starting an in-app video pauses audio; starting audio pauses the
open in-app video. External system players are controlled separately.
On Windows, audio already started in the main window continues when minimized or hidden using
the app's background/tray action. Fully exiting the app stops playback.

**Play filtered audio** replaces the playback queue with up to the first 500 matching audio files
in the current sort order, across Library pages. Collection, smart-collection, favorite and text
filters all apply. **Add filtered audio to queue** appends instead. Select files and choose
**Add selected audio to queue** to append only selected completed audio. Videos, images and
unfinished outputs are excluded. A path appears once per queue; the limit is 500 tracks.
The playback queue is separate from Queue's download jobs and from saved collections.

The bottom bar offers play/pause, previous/next, 15-second backward/forward jumps, a seek bar,
0.5x–2x speed, volume, shuffle and repeat off/all/one. Repeat-one applies on natural completion;
Next still advances. Previous restarts a track after its first three seconds, otherwise goes to
the previous track. Shuffle avoids revisiting tracks until the current cycle finishes unless
the queue changes. Without repeat, playback stops at the end. No sleep timer is provided.

Open **Playback queue** to drag tracks before another track, use accessible up/down buttons,
select a track or remove entries. Large queues show 25 tracks per page. Removing entries or
clearing the queue only changes playback; it does not delete Library files.

Queue order, current track, position, speed, volume, shuffle and repeat are stored locally per
library in this app/browser profile. Restarting restores them paused; click Play to continue.
Progress is also saved through Library's existing playback API. Storage failures are reported
and session playback remains available. Playback queues are excluded from JSON backups.

An in-app rename updates queued paths. Files no longer discovered by Library remain in the
queue as unavailable and cannot start playing; returning a file and refreshing restores access.
If the current file becomes unavailable, playback pauses. A changed file at the same path is
reloaded paused from the start. Unsupported codecs and autoplay restrictions provide an error
instead of repeatedly advancing. Use Next or the system-player fallback when needed.

### Browsing and selection

Library remembers search, filters, sorting, page and page size for the current library, including
after switching views or restarting. **Reset browsing** restores the defaults. The selected files
themselves are not restored across sessions. In Library and Queue, **View selected** reviews the
whole selection and lets you remove individual entries. **Clear selection** stays available when
the current filter has no results; selections on other pages or outside the filter are counted
explicitly before a batch action.

Library is the default page for a new installation. Existing users retain their last page, and
a direct page link still takes precedence. The guide's **Open Library** action lets you import
and organize files even before download components are prepared.

**Import local files** accepts videos, audio and images. Choose files with the system picker,
or drop them into the import dialog, then confirm **Import selected files**. Files are copied
into `imports/` under the current save folder. Originals remain in place, so imported copies
use additional disk space. You can choose up to 100 files per batch, up to 8 GiB each. Import
shows upload progress. Stop/close cancels unfinished work; completed files remain in Library.
Duplicate imported content with the same extension is skipped when its previous copy is unchanged.
An occupied filename is never overwritten. Unsuccessful files remain selected for retry.

Switch between **Grid view** and **List view**; the choice is remembered. Cards show separate
covers when available, and supported videos can show a first frame. Images retain their fitted/original
size preview. Click a title or video/audio artwork to open **Media details**, showing the source,
file information, collections and preview. Unsupported codecs have system-player or download fallbacks.

Use **Tags (comma separated)** and **Note**, then **Save tags and note**. Up to 20 tags of
40 characters each and a 2000-character note are supported. Search matches titles, filenames,
tags and notes. **Insert current time** places the built-in player's current timestamp in the note.
Opening a detail view does not change saved progress. Playing inside the app saves progress
periodically, on pause and when closing the detail view; completed playback is marked accordingly.
**Continue watching / listening** shows unfinished saved progress, and reopening its player resumes
at the saved time. Browser codec support applies, and external players do not report playback progress.
Tags, notes and progress remain with a file through in-app rename, Recovery and restore.

Click a file's star to favorite or unfavorite it. **Favorites** filters the list; search and the
other filters still apply. Select files to favorite them in batches. Use an individual file's
star to remove it from Favorites. **Select this page** only adds files to the selection;
use **Clear selection** to clear it, or uncheck individual files.

Each file keeps playback/preview and favorite controls visible. Open **More** for download,
show in folder, original page, collections, rename and recovery actions. Only one file's
extra actions open at a time; Escape closes them and returns focus to More. Repair remains
visible for unfinished files that can be repaired locally. More opens a floating action panel
without resizing the card or moving the list. Choosing an action closes the panel.

Use **Manage collections** to create or rename collections such as Music, Study or Watch later.
Use a file's collection button, or **Organize selected collections**, to add or remove files. A file
can belong to multiple collections. **Filters** groups media type, source site, format, collection
and sorting in a floating panel. Changes update the list immediately and keep the panel open.
The button shows how many of these five settings differ from their defaults. A compact summary
below the controls lists the active settings, including the collection name and non-default sort
order, even after the panel closes. Default settings are omitted. Favorites and
Continue watching / listening remain visible outside the panel. **Reset filters**
returns to all files. These actions never move or copy the actual files.
Both floating panels stay within the window. Click outside, press Escape, or scroll the page
to close one; scrolling inside a panel keeps it open. Escape returns focus to its trigger.
In narrow Library windows, only the search field stays fixed so file actions remain reachable.
The compact layout uses a shorter Resume playback label, tighter spacing and hides routine
completed-scan information. Incomplete-scan warnings remain visible. Filtered results show the
matching count against the library total (or discovered files for an incomplete scan).
An empty library offers a starting point; an empty search/filter result offers **Clear all conditions**
to return to the discovered files without changing them.

Deleting a collection requires confirmation and removes only that classification. Files and favorites
remain. Favorites and membership survive app restarts, in-app file renames, and Recovery/Undo.
Each download folder has its own collections, as it does its own Library.

### Smart collections

Open **Manage collections > Smart collections**, or choose a built-in view under
**Filters > Collection**. The built-ins are **Saved in the last 30 days**, **Not started in this
app**, **Continue watching / listening** and **Favorites**.

Create a named collection with any combination of media type, source site, file format, one tag,
favorite status, recent saved date and playback status. All selected conditions must match.
Tags match a complete tag ignoring letter case, rather than a substring. The preview reports
the number of matching discovered files; zero matches is allowed. Rules update when downloads,
file details or the refreshed Library change. Active recent-date views recheck their time window
each minute. For older files without a saved date, the file modification time is used.

Playback conditions apply to completed video/audio files and this app's playback records only.
Images and processing-incomplete files are excluded from playback views. **Not started in this
app** includes files without a recorded position or with a zero position; it does not detect
whether you played the file in another application.

Smart collections are dynamic views: their members are not manually assigned, and deleting one
removes only its rule definition. Files, favorites and manual collections remain unchanged.
Use **Edit rules** to rename or change conditions, or **View** to open a collection with other
filters cleared. The Collection dropdown distinguishes manual, built-in and custom smart views;
its selected name remains visible in the filter summary. Up to 100 custom smart collections can
be saved per library. Switching away and restarting preserve the selected collection.

Custom smart collections are included in settings/library backups, including when no matching
media exists yet. Restore previews show their added count; an existing ID or name keeps the
current definition. Older backups remain supported. Earlier app versions do not restore this
optional backup field.

Files whose transfer finished but whose postprocessing did not finish are labeled
**Processing incomplete** in Queue and Library. This includes unmerged video/audio streams and
media whose requested conversion or cover embedding failed. The label persists across restarts
and follows rename/recovery. Existing fragment files from retained failed tasks are recognized
using their `.f400.mp4` / `.f140.m4a` naming pattern; imported files are not labeled solely from
their names. Files remain available for inspection and are not automatically deleted.

![Library](images/library.jpg)

Search filenames, paths or titles; filter by media type, source site, file format. Sort by date,
name or size. Dates use the recorded download time, falling back to the file modification
time for older/imported files. Files without source metadata are labeled **Unknown source**.
The Library scan covers four directory levels and checks up to 20,000 entries. All discovered
media files are retained, with 25, 50 or 100 files per page after filtering/sorting. The footer
shows the visible range. Scanning reports checked entries and media counts; warnings explain
entry limits, depth limits and unreadable paths. Search and filters cover discovered files only
when a scan is incomplete. Hidden folders and symlink files are excluded. Click **Refresh** to
rescan files added or changed outside the app.

Choose **Images** in the media-type filter to see standalone images. Click an image thumbnail or
**Preview image** to open its preview, switch between fitted and original size, or download the
original file. Browser support determines whether a format can be displayed. Images retain
the same source-page, folder, rename and recovery actions as videos and audio.

Existing same-stem images beside video/audio files are treated as cover companions and stay
grouped with their media instead of appearing as separate Library cards. Images downloaded using
the new modes are explicitly recorded as standalone images, even if their names match a video.
Imported images with matching video names should be moved to a separate folder to make their
standalone role unambiguous.

**Rename** changes the filename only and preserves the extension. It refuses invalid Windows
filenames and existing destinations. Source metadata persists separately from task history,
so clearing completed tasks does not erase the source information for new downloads.
**Original page** opens the saved source URL when available.

**Move to recovery** requires confirmation and moves the media file into the hidden
`.grab-trash` directory inside the download folder. This is application-managed recovery,
not the Windows Recycle Bin. Files still occupy disk space and are not automatically purged.
After a single or batch move, click **Undo** in the notification to restore the successfully moved
files and their companions. Undo stays until used or dismissed. Failed restores remain available
for retry; existing files are never overwritten. Permanent deletion has no Undo.
Library displays long filenames with up to 24 title characters followed by an ellipsis and the
original extension. Hover to see the full name. Files on disk and download names remain unchanged.

Open **Recovery** to permanently delete an item and its matching subtitles/covers after confirmation,
or restore an item to its original location; if that location is occupied,
rename or move the conflicting file first. The app never overwrites it. Keep
`.grab-library.json` with the download folder so recovery records and source metadata remain
available. Same-stem cover files and same-stem subtitles (including language suffixes such as
`.en.srt`) are renamed, moved and restored with the media. A destination conflict or locked file
blocks the operation; completed moves are rolled back on failure. If multiple media files share
the same stem and companions, management is blocked to avoid taking another file's attachments;
give those files unique names and organize their companions in the file manager first.
Permanent deletion cannot be undone. If deletion fails partway through, the recovery record remains
so you can retry; already deleted companions cannot be restored.

File-changing actions are blocked while downloads are running. Pause the queue and wait for
running downloads to finish before editing files. A player holding a file open may also need
to be closed. Recovery contents are not served through the media playback endpoint.

## Batch management and local repair

### Library organizer

Open **Library > Library organizer > Check Library**. The check runs in a background worker,
reports inventory/hash/content-verification progress and can be cancelled. Closing the panel
keeps the check running. Only one check runs at a time. Wait for active downloads to finish;
if a download starts during the check, the check stops and can be run again afterward.

The three space totals cover recognized media main files, covers/subtitles and regular files
stored in `.grab-trash`, respectively. Each discovered file belongs to only one category.
Totals describe file sizes rather than filesystem allocation; hard links, compression and
allocation units can differ. Extra-copy totals cover main files only. Recovery still occupies
disk space. App settings, unrelated file types and other hidden working directories are excluded.

Duplicate checking groups non-empty files by size, hashes candidates and compares matching
content byte-for-byte. Different encodings or resolutions are not considered duplicates unless
their bytes are identical. Recognized companion images/subtitles and known incomplete outputs
are excluded from duplicate groups. Multiple hard-linked paths to the same physical file are
not counted as separate reclaimable copies. Checks do not write hashes or edit library records.

Nothing is preselected. Select copies to recycle, review the confirmation and keep at least one
file in every group. Up to 200 copies can be processed per review. Before moving, the backend
revalidates the selected groups, including their retained copies. Changed/missing files or
expired results require a new check. The existing companion rules apply; ambiguous/shared
companions can block an individual move. Each copy keeps its own annotations rather than
merging them with another file. Successful moves offer **Undo** using the normal group restore
workflow. After any successful move, run a new check before making another reviewed selection.
When some moves fail, only the successful recovery IDs are offered for Undo; technical details
remain available under the error message. Files are never permanently deleted by this assistant.

Missing results list only previously recorded main files that cannot be found after a complete
inventory. Their favorites, collections, tags and notes are kept. Put a file back in its original
location and run a new check to clear the finding. Never-recorded deleted files cannot be inferred.
Permission errors, links/junctions, scan limits, incomplete outputs and files that change during
checking appear separately as unconfirmed findings. Results from partial inventory never label
absent records as missing. Inventory limits match Library's configured entry/depth bounds.
Download-history entries already moved to Recovery are excluded from missing findings.
If library records cannot be read, checking and reviewed recycling stop; restore folder access
or a valid metadata backup before trying again. The assistant does not reset those records.

Results are a snapshot, kept only in the running app. Switching libraries hides old results and
restarting requires a new check. Large groups and finding lists are paginated in the panel.

### Batch actions and repair

Select individual files or **Select this page** in Library, then **Move selected to recovery**.
Selections carry across pages. The confirmation includes the selected main-file size; companions
move with each file. Recovery supports **Select all**, **Restore selected**, and **Delete selected
permanently**. Its size includes stored companions. Permanent deletion requires confirmation.
Partial failures leave unsuccessful items selected for retry and report the success/failure counts.
Bulk moves save their recovery records together before moving files. If the app stops partway
through, restart and use **Restore** in Recovery to return the affected groups and their organization.
Some files may still be at their original locations; these are accepted only if their recorded
identity, size and modification time still match. Changed or replacement files are not overwritten.
If a rollback or its metadata save fails, the recovery record is retained for this same restore
workflow. Undo includes only groups reported as successfully moved.

For a known unfinished download, **Repair** adds an offline task to Queue using the original saved
MP4/MP3, cover and subtitle settings. It checks local video/audio streams, works on temporary
copies, and verifies the output before replacing it. It does not contact the source site.
Successful merges/conversions move superseded inputs into Recovery. Cancellation or a processing
failure keeps originals intact. Missing/ambiguous inputs or missing requested covers/subtitles
require downloading the original item again. A completed output is never overwritten.

## Language and connectivity

English, Simplified Chinese, Traditional Chinese and Japanese are available from **Language**.
Site-provided titles, logs and some diagnostic details retain their original language.
Use a valid HTTP/SOCKS proxy address only when you have a proxy service listening there;
the application's own UI port is not a proxy. Diagnostics never changes system DNS settings.

Download only content you have permission to download. Site rate limits, authentication,
network restrictions and DRM remain outside the application's guarantees.
