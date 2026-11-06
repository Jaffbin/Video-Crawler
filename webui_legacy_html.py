"""Legacy single-page fallback interface when webui_dist/ is not built."""

INDEX_HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Video Grabber WebUI</title>
<link rel="icon" href="data:,">
<style>
:root{
  --bg:#E7EBEE; --panel:#F6F8F9; --field:#FFFFFF; --ink:#16202A; --muted:#566573; --line:#C5CDD4;
  --fill:#0E7A66; --on-fill:#FFFFFF; --fill-soft:rgba(14,122,102,.15);
  --bad:#B3372B; --warn:#8A5300; --bad-soft:rgba(179,55,43,.12); --idle-soft:rgba(86,101,115,.12);
  --sans:"Noto Sans SC","PingFang SC","Microsoft YaHei UI","Segoe UI",system-ui,sans-serif;
  color-scheme:light dark;
}
@media (prefers-color-scheme:dark){
  :root{
    --bg:#10161B; --panel:#172027; --field:#0E1418; --ink:#E5EBF0; --muted:#94A2AE; --line:#2B3641;
    --fill:#3FCFA9; --on-fill:#08201A; --fill-soft:rgba(63,207,169,.16);
    --bad:#F08A7E; --warn:#F2B84B; --bad-soft:rgba(240,138,126,.14); --idle-soft:rgba(148,162,174,.12);
  }
}
*{box-sizing:border-box}
[hidden]{display:none!important}
html{background:var(--bg)}
body{margin:0;color:var(--ink);font:15px/1.55 var(--sans);-webkit-font-smoothing:antialiased}
button,input,select,textarea{font:inherit;color:inherit}
:focus-visible{outline:2px solid var(--fill);outline-offset:2px}
.muted{color:var(--muted)} .small{font-size:13px}

.top{display:flex;align-items:center;gap:16px;max-width:1180px;margin:0 auto;padding:22px 24px 6px}
.top h1{margin:0;font-size:24px;font-weight:700;letter-spacing:.04em;flex:1}
.banner{max-width:1180px;margin:8px auto 0;padding:10px 24px;background:var(--bad-soft);color:var(--bad);font-weight:600}
.banner p{margin:0}

.layout{display:grid;grid-template-columns:minmax(320px,380px) 1fr;gap:28px;max-width:1180px;margin:0 auto;padding:16px 24px 48px;align-items:start}
@media (max-width:860px){.layout{grid-template-columns:1fr;padding:12px 16px 40px}.top{padding:18px 16px 4px}}

.panel{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:18px;position:sticky;top:16px}
@media (max-width:860px){.panel{position:static}}
h2{margin:0 0 10px;font-size:16px;font-weight:700}
.queue h2{margin-top:0}
.queue section+section{margin-top:34px}
.sec-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px}
.sec-head h2{margin:0}

textarea,input[type=text],input[type=number],input[type=search],select{width:100%;background:var(--field);border:1px solid var(--line);border-radius:6px;padding:8px 10px}
textarea{resize:vertical;min-height:112px;line-height:1.5}
label.f{display:block;margin:12px 0 4px;font-weight:600;font-size:14px}
.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.check{display:flex;align-items:center;gap:8px;margin:8px 0;cursor:pointer}
.check input{width:16px;height:16px;accent-color:var(--fill)}
.sub{margin:2px 0 0 24px}
.group{margin-top:14px;padding-top:12px;border-top:1px solid var(--line)}
details.adv{margin-top:14px;padding-top:12px;border-top:1px solid var(--line)}
details.adv summary{cursor:pointer;font-weight:600}

.seg{display:grid;grid-template-columns:1fr 1fr;border:1px solid var(--line);border-radius:6px;overflow:hidden;background:var(--field);margin-top:14px;position:relative}
.seg input{position:absolute;opacity:0;pointer-events:none}
.seg label{padding:9px 10px;text-align:center;cursor:pointer;font-weight:600}
.seg input:checked+label{background:var(--fill);color:var(--on-fill)}
.seg input:focus-visible+label{outline:2px solid var(--ink);outline-offset:-3px}
body[data-mode="mp3"] .only-mp4{display:none}
body:not([data-mode="mp3"]) .only-mp3{display:none}

.btn{border:1px solid var(--line);background:var(--field);border-radius:6px;padding:8px 14px;cursor:pointer;font-weight:600}
.btn:hover{border-color:var(--muted)}
.btn.primary{background:var(--fill);border-color:var(--fill);color:var(--on-fill)}
.btn.primary:hover{filter:brightness(1.06)}
.btn.small{padding:4px 10px;font-size:13px}
.btn:disabled{opacity:.5;cursor:default}
.actions{display:flex;gap:10px;margin-top:18px}
.actions .primary{flex:1}

#probe{margin-top:10px;padding:10px 12px;background:var(--field);border:1px solid var(--line);border-radius:6px;font-size:14px}
#probe p{margin:0}
.pr-head{display:flex;gap:10px;align-items:flex-start}
.pr-head img{width:96px;height:54px;object-fit:cover;border-radius:4px;flex:none;background:var(--idle-soft)}
.chips{display:flex;flex-wrap:wrap;gap:6px;align-items:center;margin-top:8px}
.chip{border:1px solid var(--line);background:var(--panel);border-radius:999px;padding:1px 10px;cursor:pointer;font-size:13px}
.chip:hover{border-color:var(--fill);color:var(--fill)}
#probe ul{margin:6px 0 0;padding-left:18px}
#probe li{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.err{color:var(--bad)}

.list{border:1px solid var(--line);border-radius:8px;background:var(--panel);overflow:hidden}
.empty{padding:18px 16px;color:var(--muted)}
.job{position:relative;padding:14px 16px;border-top:1px solid var(--line);display:grid;grid-template-columns:1fr auto;gap:2px 16px;isolation:isolate}
.job.first{border-top:0}
.job::before{content:"";position:absolute;inset:0 auto 0 0;width:var(--p,0%);background:var(--fill-soft);transition:width .8s linear;z-index:-1}
.job[data-status="error"]::before{width:100%;background:var(--bad-soft)}
.job[data-status="canceled"]::before,.job[data-status="queued"]::before{width:100%;background:var(--idle-soft)}
.job[data-status="done"]::before{width:100%}
.job-title{font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.job-meta{display:flex;flex-wrap:wrap;gap:2px 14px;font-size:13px;color:var(--muted);min-height:20px}
.job-err{color:var(--bad);font-size:14px;margin-top:4px}
.job-files{display:flex;flex-direction:column;gap:2px;margin-top:4px;font-size:14px}
.job-files a,.file a{color:var(--fill);font-weight:600;text-decoration:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.job-files a:hover,.file a:hover{text-decoration:underline}
.job-side{grid-column:2;grid-row:1 / span 3;display:flex;flex-direction:column;align-items:flex-end;justify-content:space-between;gap:8px}
.pct{font-size:28px;font-weight:600;line-height:1;font-variant-numeric:tabular-nums;min-width:3ch;text-align:right}
.pct.word{font-size:15px;font-weight:600;color:var(--muted)}
.job[data-status="error"] .pct{color:var(--bad)}
.job[data-status="done"] .pct{color:var(--fill)}
.job-btns{display:flex;gap:6px}
.job-log{grid-column:1 / -1;margin-top:6px;font-size:13px}
.job-log summary{cursor:pointer;color:var(--muted);width:max-content}
.job-log pre{margin:6px 0 0;padding:10px;max-height:240px;overflow:auto;background:var(--field);border:1px solid var(--line);border-radius:6px;font:12px/1.5 ui-monospace,"Cascadia Mono",Consolas,monospace;white-space:pre-wrap;word-break:break-all}

.file{display:flex;align-items:center;gap:14px;padding:10px 16px;border-top:1px solid var(--line)}
.file:first-child{border-top:0}
.file a{flex:1;min-width:0}
.file span{font-size:13px;color:var(--muted);white-space:nowrap;font-variant-numeric:tabular-nums}

.top{flex-wrap:wrap}
.top h1{white-space:nowrap}
.btn.attn{border-color:var(--fill);color:var(--fill)}
.ta-tools{display:flex;align-items:center;gap:10px;margin-top:6px}
.ta-tools span{flex:1;min-width:0}
textarea.flash{animation:flash 1.2s ease-out}
@keyframes flash{0%{box-shadow:0 0 0 3px var(--fill)}100%{box-shadow:0 0 0 0 transparent}}
.upd{grid-column:1 / -1;background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:12px 16px}
.upd-row{display:flex;flex-wrap:wrap;align-items:center;gap:10px}
.upd-row p{margin:0;flex:1;min-width:220px;font-weight:600}
.upd pre{margin:10px 0 0;max-height:200px;overflow:auto;padding:10px;background:var(--field);border:1px solid var(--line);border-radius:6px;font:12px/1.5 ui-monospace,"Cascadia Mono",Consolas,monospace;white-space:pre-wrap;word-break:break-all}
.filters{display:flex;gap:10px;align-items:center;margin-bottom:8px}
.filters input{flex:1;min-width:0}
.filters select{width:auto}
.sec-tools{display:flex;gap:8px;align-items:center}
#drop{position:fixed;inset:0;z-index:20;display:flex;align-items:center;justify-content:center;background:rgba(14,122,102,.86);color:#fff;font-size:22px;font-weight:700;pointer-events:none}
.banner.row{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.banner.row p{flex:1;min-width:220px}
.banner.warnb{background:rgba(180,120,0,.14);color:var(--warn)}
.badge{display:inline-block;min-width:66px;text-align:center;padding:1px 8px;border-radius:999px;font-size:12px;font-weight:700;border:1px solid var(--line);color:var(--muted);height:fit-content}
.badge.ok{color:var(--fill);border-color:var(--fill)}
.badge.warn{color:var(--warn);border-color:var(--warn)}
.badge.error{color:var(--bad);border-color:var(--bad)}
.doc-list{margin-top:8px}
.doc-row{display:grid;grid-template-columns:72px 1fr;gap:4px 12px;padding:10px 0;border-top:1px solid var(--line)}
.doc-row:first-child{border-top:0}
.doc-row .lbl{font-weight:600}
.doc-row .det{font-size:14px;color:var(--muted);overflow-wrap:anywhere}
.doc-fix{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:4px}
.doc-fix code{background:var(--field);border:1px solid var(--line);border-radius:6px;padding:2px 8px;font:12px ui-monospace,"Cascadia Mono",Consolas,monospace;overflow-wrap:anywhere}
.job-note{color:var(--warn);font-size:13px;margin-top:4px;white-space:pre-line}
.cookie-box{margin-top:6px;padding:8px 10px;background:var(--field);border:1px solid var(--line);border-radius:6px}
.cookie-box p{margin:0 0 6px}
.cookie-actions{display:flex;gap:8px;align-items:center;margin-bottom:6px}
#toast{position:fixed;left:50%;bottom:22px;transform:translateX(-50%);background:var(--ink);color:var(--bg);padding:9px 16px;border-radius:6px;font-weight:600;max-width:90vw;z-index:10}
#toast.bad{background:var(--bad);color:#fff}
@media (prefers-reduced-motion:reduce){.job::before{transition:none}}
</style>
</head>
<body data-mode="mp4">
<header class="top">
  <h1>Video Grabber WebUI</h1>
  <span id="ver" class="muted small"></span>
  <button class="btn small" id="docBtn" type="button">Diagnostics</button>
  <button class="btn small" id="updBtn" type="button">Check for Updates</button>
  <button class="btn small" id="notifyBtn" type="button">Enable Completion Notifications</button>
  <button class="btn small" id="openDir" type="button">Open Download Folder</button>
</header>
<div class="banner" id="notice" hidden><p>ffmpeg not found: merging audio/video and MP3 conversion will fail. Please restart after installing.</p></div>
<div class="banner warnb row" id="envNotice" hidden>
  <p id="envMsg"></p>
  <button class="btn small" id="envOpen" type="button">Open Diagnostics</button>
  <button class="btn small" id="envDismiss" type="button">Dismiss</button>
</div>
<div class="banner" id="offline" hidden><p>Disconnected from local service, please ensure webui.py is running.</p></div>

<main class="layout">
  <section class="upd" id="upd" hidden aria-label="Update yt-dlp">
    <div class="upd-row">
      <p id="updMsg"></p>
      <button class="btn small primary" id="updDo" type="button" hidden>Update</button>
      <button class="btn small primary" id="updRestart" type="button" hidden>Restart Service</button>
      <button class="btn small" id="updClose" type="button">Collapse</button>
    </div>
    <pre id="updLog" hidden></pre>
  </section>
  <section class="upd" id="doctor" hidden aria-label="Diagnostics">
    <div class="upd-row">
      <p>Diagnostics</p>
      <button class="btn small" id="docRecheck" type="button">Re-check</button>
      <button class="btn small" id="docNet" type="button">Test network</button>
      <button class="btn small" id="docCopy" type="button">Copy report</button>
      <button class="btn small" id="docClose" type="button">Close</button>
    </div>
    <div class="doc-list" id="docList"></div>
    <p class="muted small" style="margin:8px 0 0">The report hides your home folder and proxy passwords, but it includes your most recent failed links and log lines. Read it before sharing.</p>
  </section>
  <section class="panel" aria-label="New Download">
    <h2>New Download</h2>
    <textarea id="urls" placeholder="Paste URLs, one per line. Supports video pages, playlists, mp4 and m3u8 direct links" spellcheck="false"></textarea>
    <div class="ta-tools">
      <button class="btn small" id="pasteBtn" type="button">Read Clipboard</button>
      <span class="muted small">Or press Ctrl+V, or drag and drop txt files/links into the page</span>
    </div>
    <div id="probe" hidden></div>

    <div class="seg" role="radiogroup" aria-label="Output Format">
      <input type="radio" name="mode" id="m-mp4" value="mp4" checked><label for="m-mp4">MP4 Video</label>
      <input type="radio" name="mode" id="m-mp3" value="mp3"><label for="m-mp3">MP3 Audio</label>
    </div>

    <div class="only-mp4">
      <label class="f" for="quality">Max Quality</label>
      <select id="quality">
        <option value="best">Best Quality</option><option value="2160">2160p (4K)</option><option value="1440">1440p</option>
        <option value="1080">1080p</option><option value="720">720p</option><option value="480">480p</option><option value="360">360p</option>
      </select>
    </div>
    <div class="only-mp3">
      <label class="f" for="abr">Audio Quality</label>
      <select id="abr">
        <option value="320">320 kbps</option><option value="256">256 kbps</option><option value="192" selected>192 kbps</option>
        <option value="128">128 kbps</option><option value="96">96 kbps</option>
      </select>
    </div>

    <div class="group">
      <label class="check"><input type="checkbox" id="subs">Download Subtitles</label>
      <div class="sub" id="subOpts" hidden>
        <label class="f" for="subLangs" style="margin-top:4px">Subtitle Languages</label>
        <input type="text" id="subLangs" value="zh-Hans,zh-Hant,zh,en" spellcheck="false">
        <label class="check"><input type="checkbox" id="autoSubs">Use auto-generated if manual subtitles are unavailable</label>
        <label class="check only-mp4"><input type="checkbox" id="embedSubs">Embed into MP4 (keep .srt)</label>
      </div>
      <label class="check"><input type="checkbox" id="cover">Download cover and embed into file</label>
      <label class="check sub" id="keepCoverRow" hidden><input type="checkbox" id="keepCover">Keep an extra jpg cover file</label>
    </div>

    <div class="group">
      <label class="check"><input type="checkbox" id="noPlaylist">If URL contains a playlist, download only this video</label>
      <label class="f" for="items" style="margin-top:6px">Playlist range (leave empty for all)</label>
      <input type="text" id="items" placeholder="e.g., 1-5,8" spellcheck="false">
    </div>

    <details class="adv">
      <summary>Advanced Settings</summary>
      <label class="f" for="cookieSrc">Cookies (for logged-in or member-only videos)</label>
      <select id="cookieSrc">
        <option value="">None</option>
        <option value="file" disabled>Uploaded cookies.txt</option>
        <optgroup label="Read from a browser">
          <option>chrome</option><option>edge</option><option>firefox</option><option>brave</option>
          <option>chromium</option><option>opera</option><option>vivaldi</option><option>safari</option>
        </optgroup>
      </select>
      <div class="cookie-box">
        <p class="muted small" id="cookieStatus">No cookies.txt uploaded.</p>
        <div class="cookie-actions">
          <button class="btn small" id="cookieUp" type="button">Upload cookies.txt</button>
          <button class="btn small" id="cookieDel" type="button" hidden>Remove</button>
          <input type="file" id="cookieFile" accept=".txt,text/plain" hidden>
        </div>
        <p class="muted small">Reading cookies straight from Chrome or Edge can fail on Windows while the browser is open; an exported cookies.txt avoids that. YouTube rotates account cookies, so export from a private window and do not reuse that window afterwards
          (<a href="https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies" target="_blank" rel="noopener">how to export</a>). The file is stored outside your download folder and every run works on its own copy.</p>
      </div>
      <label class="f" for="referer">Referer (for hotlink protection)</label>
      <input type="text" id="referer" placeholder="https://example.com/" spellcheck="false">
      <label class="f" for="proxy">Proxy</label>
      <input type="text" id="proxy" placeholder="http://127.0.0.1:7890" spellcheck="false">
      <div class="row">
        <div><label class="f" for="limit">Rate Limit</label><input type="text" id="limit" placeholder="e.g., 2M" spellcheck="false"></div>
        <div><label class="f" for="threads">Concurrent Fragments</label><input type="number" id="threads" min="1" max="16" value="4"></div>
      </div>
      <label class="f" for="sleep">Wait between downloads (seconds)</label>
      <input type="number" id="sleep" min="0" max="60" step="0.5" value="0">
      <label class="check"><input type="checkbox" id="archive">Skip already downloaded videos</label>
      <label class="check"><input type="checkbox" id="allSniffed">Download all when multiple video URLs are found on the page</label>
      <label class="check"><input type="checkbox" id="jsRender" disabled>If no video is found, render page with headless browser to grab</label>
      <p class="muted small sub" id="jsHint" style="margin-top:0"></p>
    </details>

    <div class="actions">
      <button class="btn" id="probeBtn" type="button">Parse URL</button>
      <button class="btn primary" id="start" type="button">Start Download</button>
    </div>
  </section>

  <div class="queue">
    <section aria-label="Queue">
      <div class="sec-head"><h2>Queue</h2><div class="sec-tools"><span id="count" class="muted small"></span><button class="btn small" id="clearBtn" type="button">Clear Finished</button></div></div>
      <div class="filters">
        <input type="search" id="q" placeholder="Search title, URL, or filename" spellcheck="false">
        <select id="flt" aria-label="Filter by status">
          <option value="all">All</option><option value="active">Active</option><option value="done">Done</option><option value="bad">Failed or Canceled</option>
        </select>
      </div>
      <div class="list">
        <div id="jobsEmpty" class="empty">Queue is empty. Paste a URL and click 'Start Download'.</div>
        <div id="jobsNoMatch" class="empty" hidden>No matching tasks.</div>
        <div id="jobs"></div>
      </div>
    </section>
    <section aria-label="Downloaded Files">
      <div class="sec-head"><h2>Downloaded Files</h2><button class="btn small" id="refreshFiles" type="button">Refresh</button></div>
      <div class="list">
        <div id="filesEmpty" class="empty">No completed files yet.</div>
        <div id="files"></div>
      </div>
    </section>
  </div>
</main>
<div id="drop" hidden>Release mouse to add links inside</div>
<div id="toast" hidden></div>

<script>
const TOKEN = "__TOKEN__";
const $ = s => document.querySelector(s);
const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

async function api(path, body) {
  const r = await fetch(path, {
    method: body === undefined ? "GET" : "POST",
    headers: {"X-Token": TOKEN, "Content-Type": "application/json"},
    body: body === undefined ? undefined : JSON.stringify(body)
  });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.error || r.statusText);
  return data;
}

let toastTimer;
function toast(msg, bad) {
  const t = $("#toast");
  t.textContent = msg; t.className = bad ? "bad" : ""; t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { t.hidden = true; }, 3200);
}

const fmtSize = n => n >= 1073741824 ? (n / 1073741824).toFixed(2) + " GB" : n >= 1048576 ? (n / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(n / 1024)) + " KB";
const fmtDur = s => { s = Math.round(s); const h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60), x = s % 60; return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(x).padStart(2, "0"); };
const fileUrl = p => "/files/" + p.split("/").map(encodeURIComponent).join("/") + "?t=" + encodeURIComponent(TOKEN);

// ── Form ──
function readOptions() {
  return {
    mode: document.querySelector("input[name=mode]:checked").value,
    quality: $("#quality").value, abr: +$("#abr").value,
    subs: $("#subs").checked, sub_langs: $("#subLangs").value.trim(),
    auto_subs: $("#autoSubs").checked, embed_subs: $("#embedSubs").checked,
    cover: $("#cover").checked, keep_cover: $("#keepCover").checked,
    no_playlist: $("#noPlaylist").checked, items: $("#items").value.trim(),
    archive: $("#archive").checked, cookies_from_browser: ["", "file"].includes($("#cookieSrc").value) ? "" : $("#cookieSrc").value,
    use_cookies_file: $("#cookieSrc").value === "file",
    referer: $("#referer").value.trim(), proxy: $("#proxy").value.trim(),
    limit_rate: $("#limit").value.trim(), threads: +$("#threads").value || 4,
    sleep: +$("#sleep").value || 0, all_sniffed: $("#allSniffed").checked,
    js_render: $("#jsRender").checked && !$("#jsRender").disabled
  };
}
function syncForm() {
  document.body.dataset.mode = document.querySelector("input[name=mode]:checked").value;
  $("#subOpts").hidden = !$("#subs").checked;
  $("#keepCoverRow").hidden = !$("#cover").checked;
}
function saveOptions() { try { localStorage.setItem("grab-options", JSON.stringify(readOptions())); } catch (e) {} }
function setQuality(v) {
  const sel = $("#quality");
  v = String(v);
  if (![...sel.options].some(o => o.value === v)) {
    const o = el("option", null, v + "p"); o.value = v; sel.append(o);
  }
  sel.value = v;
}
function restoreOptions() {
  let o = null;
  try { o = JSON.parse(localStorage.getItem("grab-options") || "null"); } catch (e) {}
  if (!o) return;
  const set = (id, v) => { if (v !== undefined && v !== null) $(id).value = v; };
  const chk = (id, v) => { if (v !== undefined) $(id).checked = !!v; };
  (document.querySelector("input[name=mode][value=" + (o.mode === "mp3" ? "mp3" : "mp4") + "]")).checked = true;
  if (o.quality) setQuality(o.quality);
  set("#abr", o.abr); set("#subLangs", o.sub_langs); set("#items", o.items); wantFileCookies = !!o.use_cookies_file; set("#cookieSrc", o.use_cookies_file ? "" : o.cookies_from_browser);
  set("#referer", o.referer); set("#proxy", o.proxy); set("#limit", o.limit_rate); set("#threads", o.threads); set("#sleep", o.sleep);
  chk("#subs", o.subs); chk("#autoSubs", o.auto_subs); chk("#embedSubs", o.embed_subs); chk("#cover", o.cover);
  chk("#keepCover", o.keep_cover); chk("#noPlaylist", o.no_playlist); chk("#archive", o.archive); chk("#allSniffed", o.all_sniffed);
  chk("#jsRender", o.js_render);
}
document.querySelectorAll("input,select").forEach(e => e.addEventListener("change", () => { syncForm(); saveOptions(); }));

const readUrls = () => $("#urls").value.split("\n").map(s => s.trim()).filter(s => s && !s.startsWith("#"));

$("#start").onclick = async () => {
  const urls = readUrls();
  if (!urls.length) return toast("Paste at least one URL first", true);
  try {
    const r = await api("/api/jobs", {urls, options: readOptions()});
    $("#urls").value = ""; $("#probe").hidden = true;
    toast("Added to queue: " + r.ids.length + " links");
    poll();
  } catch (e) { toast(e.message, true); }
};

$("#probeBtn").onclick = async () => {
  const urls = readUrls();
  if (!urls.length) return toast("Paste a URL first", true);
  const box = $("#probe"); box.hidden = false;
  box.replaceChildren(el("p", "muted", "Parsing " + (urls.length > 1 ? "the first link " : "") + "..." + (readOptions().js_render ? " (Page rendering enabled, this may take a few seconds)" : "")));
  $("#probeBtn").disabled = true;
  try { renderProbe(await api("/api/probe", {url: urls[0], options: readOptions()})); }
  catch (e) { box.replaceChildren(el("p", "err", e.message)); }
  finally { $("#probeBtn").disabled = false; }
};

function renderProbe(r) {
  const box = $("#probe"); box.replaceChildren();
  if (r.error) { box.append(el("p", "err", r.error)); return; }
  if (r.kind === "video") {
    const head = el("div", "pr-head");
    if (r.thumbnail) { const im = el("img"); im.src = r.thumbnail; im.alt = ""; im.referrerPolicy = "no-referrer"; head.append(im); }
    const t = el("div"); t.append(el("strong", null, r.title || "(No title)"));
    const meta = [r.uploader, r.duration ? fmtDur(r.duration) : "", r.extractor].filter(Boolean).join("   ");
    if (meta) t.append(el("div", "muted small", meta));
    head.append(t); box.append(head);
    if (r.heights && r.heights.length) {
      const row = el("div", "chips"); row.append(el("span", "muted small", "Quality Options"));
      r.heights.slice(0, 6).forEach(h => {
        const b = el("button", "chip", h + "p"); b.type = "button";
        b.onclick = () => { setQuality(h); $("#m-mp4").checked = true; syncForm(); saveOptions(); toast("Max quality set to " + h + "p"); };
        row.append(b);
      });
      box.append(row);
    }
  } else if (r.kind === "playlist") {
    box.append(el("strong", null, r.title || "Playlist"));
    box.append(el("div", "muted small", "Total " + r.count + " items. You can limit the range in 'Playlist range' below."));
    if (r.items && r.items.length) { const ul = el("ul"); r.items.forEach(x => ul.append(el("li", null, x))); box.append(ul); }
  } else if (r.kind === "page") {
    box.append(el("strong", null, r.title || "Webpage"));
    box.append(el("div", "muted small", r.rendered
      ? "Captured " + r.count + " media requests when loading page with headless browser, will try each sequentially when downloading."
      : "yt-dlp lacks a dedicated extractor, but found " + r.count + " media URLs in the page, will try each sequentially when downloading."));
    const ul = el("ul"); r.sources.forEach(x => ul.append(el("li", null, x))); box.append(ul);
  }
}

// ── Queue ──
const nodes = new Map(), openLogs = new Set();

function makeJob(j) {
  const n = el("article", "job"); n.dataset.id = j.id;
  const main = el("div"); main.style.minWidth = "0";
  main.append(el("div", "job-title"), el("div", "job-meta"), el("div", "job-files"), el("div", "job-err"), el("div", "job-note"));
  const side = el("div", "job-side"); side.append(el("div", "pct"), el("div", "job-btns"));
  const log = el("details", "job-log"); log.append(el("summary", null, "Log"), el("pre"));
  log.addEventListener("toggle", () => { if (log.open) { openLogs.add(j.id); refreshLog(j.id); } else openLogs.delete(j.id); });
  n.append(main, side, log);
  return n;
}
async function refreshLog(id) {
  const n = nodes.get(id); if (!n) return;
  try {
    const r = await api("/api/jobs/" + id + "/log");
    const pre = n.querySelector("pre");
    const atEnd = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 8;
    pre.textContent = r.lines.join("\n");
    if (atEnd) pre.scrollTop = pre.scrollHeight;
  } catch (e) {}
}
async function act(id, what, msg) {
  try { await api("/api/jobs/" + id + "/" + what, {}); if (msg) toast(msg); poll(); } catch (e) { toast(e.message, true); }
}
const fmtTime = t => new Date(t * 1000).toLocaleString([], {month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit"});
function updateJob(n, j) {
  n._job = j;
  n.dataset.status = j.status;
  n.style.setProperty("--p", (j.status === "done" ? 100 : j.percent) + "%");
  const title = n.querySelector(".job-title"); title.textContent = j.title || j.url; title.title = j.url;

  const meta = n.querySelector(".job-meta"); meta.replaceChildren();
  const bits = j.status === "running" ? [j.stage, j.item && "Item " + j.item, j.speed, j.eta && "ETA " + j.eta]
    : [j.status === "queued" ? "Queued" : j.item && "Total " + j.item.split("/")[1], j.stage === "Last incomplete" && j.stage, j.finished && fmtTime(j.finished)];
  bits.filter(Boolean).forEach(t => meta.append(el("span", null, t)));

  const pct = n.querySelector(".pct");
  const word = {queued: "Wait", done: "Done", error: "Failed", canceled: "Canceled"}[j.status];
  pct.textContent = word || Math.round(j.percent) + "%";
  pct.classList.toggle("word", !!word && j.status !== "done");

  n.querySelector(".job-err").textContent = j.status === "error" ? j.error : "";
  n.querySelector(".job-note").textContent = (j.notes || []).map(t => "Note: " + t).join("\n");

  const fk = JSON.stringify(j.files), files = n.querySelector(".job-files");
  if (files.dataset.k !== fk) {
    files.dataset.k = fk; files.replaceChildren();
    j.files.forEach(f => { const a = el("a", null, f.name); a.href = fileUrl(f.path); a.target = "_blank"; a.rel = "noopener"; a.title = "Play in new tab"; files.append(a); });
  }

  const btns = n.querySelector(".job-btns"), bk = j.status + (j.stage === "Canceling…" ? "!" : "");
  if (btns.dataset.k !== bk) {
    btns.dataset.k = bk; btns.replaceChildren();
    const add = (label, fn, dis) => { const b = el("button", "btn small", label); b.type = "button"; b.disabled = !!dis; b.onclick = fn; btns.append(b); };
    if (j.status === "queued" || j.status === "running") add(j.stage === "Canceling…" ? "Canceling" : "Cancel", () => act(j.id, "cancel"), j.stage === "Canceling…");
    if (j.status === "done" && j.files.length) add("Open Folder", () => api("/api/open-folder", {path: j.files[0].path}).catch(e => toast(e.message, true)));
    if (j.status === "error" || j.status === "canceled") add("Retry", () => act(j.id, "retry", "Re-added to queue"));
    if (["done", "error", "canceled"].includes(j.status)) add("Remove", () => act(j.id, "remove"));
  }
}
function renderJobs(list) {
  const wrap = $("#jobs");
  const seen = new Set(list.map(j => j.id));
  list.forEach(j => { let n = nodes.get(j.id); if (!n) { n = makeJob(j); nodes.set(j.id, n); } updateJob(n, j); });
  for (const [id, n] of nodes) if (!seen.has(id)) { n.remove(); nodes.delete(id); openLogs.delete(id); }
  let ref = wrap.firstElementChild;
  for (const j of list) { const n = nodes.get(j.id); if (n === ref) ref = ref.nextElementSibling; else wrap.insertBefore(n, ref); }
  openLogs.forEach(refreshLog);
  applyFilter();
}
let filterQ = "", filterS = "all", lastFiles = [];
function renderFiles(list) { lastFiles = list; renderFileRows(); }
function renderFileRows() {
  const box = $("#files"); box.replaceChildren();
  const q = filterQ.trim().toLowerCase();
  const list = q ? lastFiles.filter(f => f.path.toLowerCase().includes(q)) : lastFiles;
  const empty = $("#filesEmpty");
  empty.hidden = list.length > 0;
  empty.textContent = lastFiles.length && !list.length ? "No matching files." : "No completed files yet.";
  list.forEach(f => {
    const row = el("div", "file"); const a = el("a", null, f.path); a.href = fileUrl(f.path); a.target = "_blank"; a.rel = "noopener"; a.title = "Play in new tab";
    row.append(a, el("span", null, fmtSize(f.size)), el("span", null, new Date(f.mtime * 1000).toLocaleString()));
    box.append(row);
  });
}

let rev = -1, restarting = false, lastPw = null;
async function poll() {
  if (restarting) return;
  try {
    const s = await api("/api/state?rev=" + rev);
    $("#ver").textContent = "yt-dlp " + s.version;
    $("#openDir").title = s.root;
    $("#notice").hidden = s.ffmpeg;
    $("#offline").hidden = true;
    if (lastPw !== s.playwright) {
      lastPw = s.playwright;
      $("#jsRender").disabled = !s.playwright;
      $("#jsHint").textContent = s.playwright
        ? "Playwright detected. On Windows, system built-in Edge will be prioritized, no need to download additional browser."
        : "Playwright not detected. Run pip install playwright and restart to enable (No need to download browser if Edge is installed on Windows).";
    }
    renderJobs(s.jobs);
    trackCompletion(s.jobs);
    if (s.files) renderFiles(s.files);
    rev = s.rev;
  } catch (e) { $("#offline").hidden = false; }
}

$("#openDir").onclick = () => api("/api/open-folder", {}).catch(e => toast(e.message, true));
$("#clearBtn").onclick = async () => { try { await api("/api/clear", {}); poll(); } catch (e) { toast(e.message, true); } };


// ── Search & Filters ──
const matches = j => {
  const q = filterQ.trim().toLowerCase();
  if (q && !((j.title || "").toLowerCase().includes(q) || j.url.toLowerCase().includes(q))) return false;
  if (filterS === "active") return j.status === "queued" || j.status === "running";
  if (filterS === "done") return j.status === "done";
  if (filterS === "bad") return j.status === "error" || j.status === "canceled";
  return true;
};
function applyFilter() {
  let shown = 0, first = null;
  for (const n of $("#jobs").children) {
    const ok = !n._job || matches(n._job);
    n.hidden = !ok; n.classList.remove("first");
    if (ok) { shown++; if (!first) first = n; }
  }
  if (first) first.classList.add("first");
  const total = nodes.size;
  $("#jobsEmpty").hidden = total > 0;
  $("#jobsNoMatch").hidden = !(total > 0 && shown === 0);
  $("#count").textContent = !total ? "" : shown === total ? total + " tasks" : "Showing " + shown + " / " + total;
  renderFileRows();
}
$("#q").addEventListener("input", e => { filterQ = e.target.value; applyFilter(); });
$("#flt").addEventListener("change", e => { filterS = e.target.value; applyFilter(); });
$("#refreshFiles").onclick = () => { rev = -1; poll(); };

// ── Paste & Drag-Drop ──
const extractUrls = text => [...new Set((String(text).match(/https?:\/\/[^\s"'<>\\)\]，。）】]+/gi) || []).map(u => u.replace(/[.,;、]+$/, "")))];
function addUrls(list, source) {
  if (!list.length) { toast("No links found", true); return 0; }
  const have = new Set(readUrls()), fresh = list.filter(u => !have.has(u));
  if (!fresh.length) { toast("These links are already in the input box"); return 0; }
  const ta = $("#urls");
  ta.value = (ta.value.trim() ? ta.value.replace(/\s*$/, "\n") : "") + fresh.join("\n") + "\n";
  ta.classList.remove("flash"); void ta.offsetWidth; ta.classList.add("flash");
  toast("Added " + fresh.length + " link(s)" + (source ? " (" + source + ")" : ""));
  return fresh.length;
}
document.addEventListener("paste", e => {
  const t = e.target;
  if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
  const urls = extractUrls((e.clipboardData && e.clipboardData.getData("text")) || "");
  if (urls.length) { e.preventDefault(); addUrls(urls, "from clipboard"); }
});
$("#pasteBtn").onclick = async () => {
  try { addUrls(extractUrls(await navigator.clipboard.readText()), "from clipboard"); }
  catch (e) { toast("Browser clipboard access denied, please press Ctrl+V directly", true); }
};
let dragDepth = 0;
const hasPayload = e => e.dataTransfer && [...e.dataTransfer.types].some(t => t === "Files" || t === "text/uri-list" || t === "text/plain");
window.addEventListener("dragenter", e => { if (!hasPayload(e)) return; e.preventDefault(); dragDepth++; $("#drop").hidden = false; });
window.addEventListener("dragover", e => { if (hasPayload(e)) e.preventDefault(); });
window.addEventListener("dragleave", e => { if (!hasPayload(e)) return; dragDepth = Math.max(0, dragDepth - 1); if (!dragDepth) $("#drop").hidden = true; });
window.addEventListener("drop", async e => {
  if (!hasPayload(e)) return;
  e.preventDefault(); dragDepth = 0; $("#drop").hidden = true;
  const dt = e.dataTransfer, urls = [];
  for (const f of [...dt.files].slice(0, 20)) {
    if (!(f.type.startsWith("text/") || /\.(txt|csv|md|list|url|webloc|json|html?)$/i.test(f.name))) { toast(f.name + " is not a text file, skipped", true); continue; }
    if (f.size > 2e6) { toast(f.name + " is too large, skipped", true); continue; }
    try { urls.push(...extractUrls(await f.text())); } catch (_) {}
  }
  if (!dt.files.length) urls.push(...extractUrls(dt.getData("text/uri-list") + "\n" + dt.getData("text/plain")));
  if (dt.files.length || urls.length) addUrls([...new Set(urls)], dt.files.length ? "from dropped files" : "from dropped links");
});

// ── Notifications ──
const lastStatus = new Map();
let wasActive = false, batch = {ok: 0, bad: 0, title: ""}, doneMark = false;
const notifyState = () => ("Notification" in window) ? Notification.permission : "unsupported";
function refreshNotifyBtn() {
  const b = $("#notifyBtn"), st = notifyState();
  if (st === "unsupported") { b.hidden = true; return; }
  b.textContent = st === "granted" ? "Notifications: Enabled" : st === "denied" ? "Notifications Blocked by Browser" : "Enable Completion Notifications";
  b.disabled = st === "denied";
}
$("#notifyBtn").onclick = async () => {
  if (notifyState() === "granted") return toast("Already enabled: you'll be notified when queue finishes and page is not in foreground");
  try { await Notification.requestPermission(); } catch (e) {}
  refreshNotifyBtn();
  if (notifyState() === "granted") { try { new Notification("Video Grabber WebUI", {body: "Notifications Enabled"}); } catch (e) {} }
};
function announceDone(b) {
  const msg = b.bad ? "Completed " + b.ok + ", failed " + b.bad : b.ok === 1 ? "Download complete: " + b.title : b.ok + " downloads completed";
  const away = document.hidden || !document.hasFocus();
  if (away) doneMark = true;
  toast(msg, !!b.bad && !b.ok);
  if (away && notifyState() === "granted") {
    try { const n = new Notification("Video Grabber WebUI", {body: msg, tag: "grab-done"}); n.onclick = () => { window.focus(); n.close(); }; } catch (e) {}
  }
}
function trackCompletion(jobs) {
  let active = 0;
  for (const j of jobs) {
    const prev = lastStatus.get(j.id), was = prev === "queued" || prev === "running";
    if (was && j.status === "done") { batch.ok++; batch.title = j.title || j.url; }
    if (was && j.status === "error") batch.bad++;
    lastStatus.set(j.id, j.status);
    if (j.status === "queued" || j.status === "running") active++;
  }
  if (wasActive && !active && batch.ok + batch.bad > 0) { announceDone(batch); batch = {ok: 0, bad: 0, title: ""}; }
  wasActive = active > 0;
  document.title = active ? "Downloading (" + active + ") - Video Grabber WebUI" : doneMark ? "Done - Video Grabber WebUI" : "Video Grabber WebUI";
}
window.addEventListener("focus", () => { doneMark = false; });

// ── Update yt-dlp ──
function showUpd(text, o) {
  o = o || {};
  $("#upd").hidden = false; $("#updMsg").textContent = text;
  $("#updDo").hidden = !o.canUpdate; $("#updRestart").hidden = !o.canRestart;
}
async function checkUpdate(force, silent) {
  try {
    const r = await api("/api/ytdlp/check" + (force ? "?force=1" : ""));
    const b = $("#updBtn");
    b.classList.toggle("attn", !!(r.newer || r.needs_restart));
    b.textContent = r.needs_restart ? "Restart to complete update" : r.newer ? "Update yt-dlp (new version available)" : "Check for Updates";
    if (r.needs_restart) { if (!silent) showUpd("yt-dlp updated to " + r.installed + ", restart service to apply. A new terminal window may pop up, you can close the old one.", {canRestart: true}); }
    else if (r.error) { if (!silent) showUpd(r.error); }
    else if (r.newer) { if (!silent) showUpd("New version " + r.latest + " available (current " + r.installed + "). Updating often fixes download issues due to site changes.", {canUpdate: true}); }
    else if (!silent) showUpd("Already on the latest version (" + r.installed + ").");
    return r;
  } catch (e) { if (!silent) toast(e.message, true); }
}
$("#updBtn").onclick = () => checkUpdate(true, false);
$("#updClose").onclick = () => { $("#upd").hidden = true; };
let updTimer = null;
async function pollUpdate() {
  clearTimeout(updTimer);
  let s;
  try { s = await api("/api/ytdlp/update-status"); } catch (e) { return; }
  const log = $("#updLog"); log.hidden = false; log.textContent = s.lines.join("\n"); log.scrollTop = log.scrollHeight;
  if (s.status === "running") { updTimer = setTimeout(pollUpdate, 800); return; }
  $("#updDo").disabled = false;
  if (s.status === "error") { showUpd(s.error || "Update failed"); return; }
  if (s.extras && s.extras.includes("deno")) {
    showUpd("Components installed. Restart the service so yt-dlp picks them up.", {canRestart: true});
    loadDoctor(false, true);
    return;
  }
  await checkUpdate(true, false);
  loadDoctor(false, true);
}
async function runUpdate(extras) {
  try { await api("/api/ytdlp/update", extras ? {extras} : {}); } catch (e) { return toast(e.message, true); }
  $("#upd").hidden = false; $("#updDo").hidden = true; $("#updRestart").hidden = true; $("#updDo").disabled = true;
  $("#updMsg").textContent = extras ? "Installing components…" : "Updating yt-dlp…";
  $("#updLog").textContent = ""; $("#updLog").hidden = false;
  pollUpdate();
}
$("#updDo").onclick = () => runUpdate();
$("#updRestart").onclick = async () => {
  try { await api("/api/restart", {}); } catch (e) { return toast(e.message, true); }
  restarting = true; $("#offline").hidden = true; toast("Restarting, please wait a few seconds...");
  setTimeout(() => {
    const t = setInterval(async () => {
      try { const r = await fetch("/", {cache: "no-store"}); if (r.ok) { clearInterval(t); location.reload(); } } catch (e) {}
    }, 1000);
  }, 1500);
};


// ── Cookies (uploaded cookies.txt) ──
let wantFileCookies = false;
function applyCookieStatus(st, select) {
  $("#cookieSrc option[value=file]").disabled = !st.present;
  $("#cookieDel").hidden = !st.present;
  const box = $("#cookieStatus");
  if (!st.present) {
    box.textContent = "No cookies.txt uploaded.";
    if ($("#cookieSrc").value === "file") { $("#cookieSrc").value = ""; saveOptions(); }
    return;
  }
  const bits = [st.cookies + (st.cookies === 1 ? " cookie" : " cookies") + " for " + st.domain_count + (st.domain_count === 1 ? " site" : " sites")];
  if (st.expired) bits.push(st.expired + " already expired");
  if (st.has_youtube) bits.push(st.youtube_login ? "YouTube sign-in found" : "no YouTube sign-in cookies");
  if (st.has_bilibili) bits.push(st.bilibili_login ? "Bilibili sign-in found" : "no Bilibili sign-in cookie");
  box.textContent = bits.join("; ") + ".";
  if (select || wantFileCookies) { $("#cookieSrc").value = "file"; wantFileCookies = false; saveOptions(); }
}
async function loadCookies() { try { applyCookieStatus(await api("/api/cookies")); } catch (e) {} }
$("#cookieUp").onclick = () => $("#cookieFile").click();
$("#cookieFile").addEventListener("change", async e => {
  const f = e.target.files[0]; e.target.value = "";
  if (!f) return;
  if (f.size > 3e6) return toast("That file is larger than 3 MB, so it is probably not a cookies.txt.", true);
  try { applyCookieStatus(await api("/api/cookies", {text: await f.text()}), true); toast("cookies.txt uploaded"); }
  catch (err) { toast(err.message, true); }
});
$("#cookieDel").onclick = async () => {
  try { applyCookieStatus(await api("/api/cookies/delete", {})); toast("cookies.txt removed"); } catch (e) { toast(e.message, true); }
};

// ── Diagnostics ──
let lastDoctor = null;
const STATUS_TEXT = {ok: "OK", info: "Info", warn: "Warning", error: "Problem"};
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch (e) {}
  const ta = el("textarea"); ta.value = text; ta.style.cssText = "position:fixed;opacity:0";
  document.body.append(ta); ta.select();
  let ok = false; try { ok = document.execCommand("copy"); } catch (e) {}
  ta.remove(); return ok;
}
function renderDoctor(d) {
  const list = $("#docList"); list.replaceChildren();
  d.checks.forEach(c => {
    const row = el("div", "doc-row"), main = el("div");
    main.append(el("div", "lbl", c.label), el("div", "det", c.detail));
    if (c.fix || c.action) {
      const fix = el("div", "doc-fix");
      if (c.fix) {
        fix.append(el("code", null, c.fix));
        const cp = el("button", "btn small", "Copy"); cp.type = "button";
        cp.onclick = async () => toast((await copyText(c.fix)) ? "Copied" : "Could not copy", false);
        fix.append(cp);
      }
      if (c.action) {
        const go = el("button", "btn small primary", "Install now"); go.type = "button";
        go.onclick = () => runUpdate(c.action === "install_components" ? "default,deno" : "default");
        fix.append(go);
      }
      main.append(fix);
    }
    row.append(el("span", "badge " + c.status, STATUS_TEXT[c.status] || c.status), main);
    list.append(row);
  });
}
async function loadDoctor(net, silent) {
  if (!silent) { $("#doctor").hidden = false; $("#docList").replaceChildren(el("p", "muted", net ? "Testing the network…" : "Checking…")); }
  try {
    const d = await api("/api/doctor?" + (net ? "net=1" : silent ? "" : "force=1"));
    lastDoctor = d;
    if (!$("#doctor").hidden) renderDoctor(d);
    updateEnvNotice(d);
    return d;
  } catch (e) { if (!silent) $("#docList").replaceChildren(el("p", "err", e.message)); }
}
function updateEnvNotice(d) {
  const bad = d.checks.filter(c => (c.id === "js_runtime" || c.id === "ejs") && (c.status === "warn" || c.status === "error"));
  const sig = bad.map(c => c.id).join(",");
  let dismissed = ""; try { dismissed = localStorage.getItem("grab-env-dismissed") || ""; } catch (e) {}
  if (!bad.length || dismissed === sig) { $("#envNotice").hidden = true; return; }
  $("#envMsg").textContent = "YouTube setup incomplete: " + bad.map(c => c.label).join(" and ") + " not detected. Some YouTube formats may be unavailable.";
  $("#envNotice").dataset.sig = sig; $("#envNotice").hidden = false;
}
$("#docBtn").onclick = () => loadDoctor(false, false);
$("#docRecheck").onclick = () => loadDoctor(false, false);
$("#docNet").onclick = () => loadDoctor(true, false);
$("#docCopy").onclick = async () => {
  if (!lastDoctor) return toast("Run a check first", true);
  toast((await copyText(lastDoctor.report)) ? "Report copied. Read it before you share it." : "Could not copy", false);
};
$("#docClose").onclick = () => { $("#doctor").hidden = true; };
$("#envOpen").onclick = () => loadDoctor(false, false);
$("#envDismiss").onclick = () => {
  try { localStorage.setItem("grab-env-dismissed", $("#envNotice").dataset.sig || ""); } catch (e) {}
  $("#envNotice").hidden = true;
};

restoreOptions(); syncForm(); refreshNotifyBtn(); poll(); checkUpdate(false, true); loadCookies(); loadDoctor(false, true);
setInterval(() => { if (!document.hidden) poll(); }, 1000);
</script>
</body>
</html>
"""

