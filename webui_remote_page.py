"""The phone page served by the remote access listener (docs/adr/0009-remote-access-listener.md).

Static HTML, CSS and JavaScript with no build step and no third-party code, served with a CSP of
default-src 'self'. Site-provided text (titles, errors) is only ever inserted with textContent.
"""

HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="dark light">
<meta name="referrer" content="no-referrer">
<title>Video Grabber</title>
<link rel="stylesheet" href="/remote.css">
</head>
<body>
<div id="app" class="app" aria-live="polite"></div>
<script src="/remote.js"></script>
</body>
</html>
"""

CSS = r"""
:root {
  --canvas: #0b0d10;
  --panel: #111318;
  --input: #18181b;
  --line: rgba(255, 255, 255, 0.09);
  --text: #f4f4f5;
  --muted: #a1a1aa;
  --focus: #7dd3fc;
  --primary: #fafafa;
  --primary-text: #09090b;
  --danger: #fca5a5;
  --ok: #86efac;
  color-scheme: dark;
}
@media (prefers-color-scheme: light) {
  :root {
    --canvas: #f5f6f8;
    --panel: #ffffff;
    --input: #ffffff;
    --line: rgba(24, 24, 27, 0.12);
    --text: #18181b;
    --muted: #52525b;
    --focus: #0369a1;
    --primary: #27272a;
    --primary-text: #ffffff;
    --danger: #b91c1c;
    --ok: #15803d;
    color-scheme: light;
  }
}
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; }
body {
  background: var(--canvas);
  color: var(--text);
  font: 16px/1.45 system-ui, -apple-system, "Segoe UI", "PingFang SC", "Hiragino Sans", "Microsoft YaHei", sans-serif;
  -webkit-text-size-adjust: 100%;
}
button, input, select, textarea { font: inherit; color: inherit; }
button { cursor: pointer; }
:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; }
.app { display: flex; flex-direction: column; min-height: 100%; max-width: 640px; margin: 0 auto; }

.top {
  display: flex; align-items: baseline; gap: 12px;
  padding: calc(14px + env(safe-area-inset-top)) 16px 10px;
}
.top h1 { margin: 0; font-size: 1.125rem; font-weight: 650; letter-spacing: -0.01em; }
.top .who { flex: 1; min-width: 0; color: var(--muted); font-size: 0.875rem;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.link { background: none; border: 0; padding: 8px 0; color: var(--muted); font-size: 0.875rem; }

.scroll { flex: 1; padding: 0 16px 16px; }
.empty { color: var(--muted); padding: 32px 4px; max-width: 32ch; }

/* Queue: one row per task, like delivery receipts for links sent from this phone. */
.task { padding: 12px 0; border-bottom: 1px solid var(--line); display: grid; gap: 6px; }
.task .row { display: flex; gap: 12px; align-items: flex-start; }
.task .title { flex: 1; min-width: 0; overflow-wrap: anywhere; font-weight: 550; }
.task .stage { color: var(--muted); font-size: 0.875rem; font-variant-numeric: tabular-nums; }
.task .stage.error { color: var(--danger); }
.task .stage.done { color: var(--ok); }
.bar { height: 3px; border-radius: 3px; background: var(--line); overflow: hidden; }
.bar > i { display: block; height: 100%; background: var(--focus); transition: width 0.4s ease; }
.small { flex: none; min-height: 36px; padding: 0 12px; border-radius: 999px;
  border: 1px solid var(--line); background: transparent; font-size: 0.875rem; }

/* Library */
.tools { display: grid; grid-template-columns: 1fr auto; gap: 8px; padding: 4px 0 8px;
  position: sticky; top: 0; background: var(--canvas); z-index: 1; }
.field { min-height: 44px; padding: 0 12px; border-radius: 12px; border: 1px solid var(--line);
  background: var(--input); width: 100%; }
.item { display: flex; gap: 12px; align-items: center; width: 100%; padding: 10px 0; text-align: left;
  background: none; border: 0; border-bottom: 1px solid var(--line); }
.thumb { flex: none; width: 72px; aspect-ratio: 16 / 10; border-radius: 8px; background: var(--panel);
  object-fit: cover; display: grid; place-items: center; color: var(--muted); font-size: 0.75rem; }
.item .text { min-width: 0; display: grid; gap: 2px; }
.item .name { overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2;
  -webkit-box-orient: vertical; }
.item .meta { color: var(--muted); font-size: 0.8125rem; font-variant-numeric: tabular-nums; }
.more { width: 100%; margin-top: 12px; }

/* Bottom dock: the composer sends a link to the computer, then the tabs. */
.dock { position: sticky; bottom: 0; background: var(--panel); border-top: 1px solid var(--line);
  padding: 10px 12px calc(6px + env(safe-area-inset-bottom)); display: grid; gap: 8px; }
.composer { display: grid; grid-template-columns: 1fr auto; gap: 8px; align-items: end; }
.composer textarea { resize: none; min-height: 44px; max-height: 120px; padding: 11px 14px;
  border-radius: 22px; border: 1px solid var(--line); background: var(--input); line-height: 1.3; }
.send { min-height: 44px; padding: 0 18px; border-radius: 22px; border: 0; font-weight: 650;
  background: var(--primary); color: var(--primary-text); }
.send:disabled { opacity: 0.45; cursor: default; }
.options { display: flex; gap: 8px; align-items: center; }
.seg { display: inline-flex; border: 1px solid var(--line); border-radius: 999px; padding: 2px; }
.seg button { border: 0; background: none; min-height: 32px; padding: 0 12px; border-radius: 999px;
  color: var(--muted); font-size: 0.875rem; }
.seg button[aria-pressed="true"] { background: var(--primary); color: var(--primary-text); }
.note { color: var(--muted); font-size: 0.8125rem; flex: 1; min-width: 0; }
.note.error { color: var(--danger); }
.tabs { display: grid; grid-template-columns: 1fr 1fr; }
.tabs button { border: 0; background: none; min-height: 44px; color: var(--muted); font-weight: 550; }
.tabs button[aria-selected="true"] { color: var(--text); box-shadow: inset 0 2px 0 var(--focus); }

/* Pairing */
.pair { flex: 1; display: grid; align-content: center; gap: 16px; padding: 24px 20px; max-width: 420px;
  margin: 0 auto; width: 100%; }
.pair h1 { margin: 0; font-size: 1.75rem; line-height: 1.15; letter-spacing: -0.02em; }
.pair p { margin: 0; color: var(--muted); }
.pair label { display: grid; gap: 6px; font-size: 0.875rem; color: var(--muted); }
.code { font-size: 1.75rem; letter-spacing: 0.18em; text-transform: uppercase; text-align: center;
  font-variant-numeric: tabular-nums; min-height: 60px; }
.pair .send { width: 100%; }

/* Player sheet */
.sheet { position: fixed; inset: 0; background: var(--canvas); z-index: 10; display: flex; flex-direction: column; }
.sheet header { display: flex; gap: 12px; align-items: center; padding: calc(10px + env(safe-area-inset-top)) 16px 10px; }
.sheet header span { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.sheet .media { flex: 1; display: grid; place-items: center; padding: 0 0 env(safe-area-inset-bottom); min-height: 0; }
.sheet video, .sheet img { max-width: 100%; max-height: 100%; }
.sheet audio { width: calc(100% - 32px); }
.hidden { display: none !important; }
@media (prefers-reduced-motion: reduce) { .bar > i { transition: none; } }
"""

JS = r"""
'use strict';
(() => {
  const MESSAGES = {
    'zh-CN': {
      'Pair this phone': '配对这部手机',
      'In Video Grabber on your computer, open Settings and help, then Remote access, and choose Pair a phone. Enter the code it shows.': '在电脑上的 Video Grabber 中打开“设置与帮助”→“远程访问”，选择“配对手机”，然后输入显示的配对码。',
      'Pairing code': '配对码', 'Name for this phone': '这部手机的名称', 'Pair': '配对', 'Pairing…': '正在配对…',
      'Queue': '队列', 'Library': '资料库', 'Paste a link': '粘贴链接', 'Send': '发送', 'Video': '视频', 'MP3': 'MP3',
      'Sent to your computer.': '已发送到电脑。', 'Already in the queue.': '已在队列中。',
      'Nothing in the queue. Paste a link below to send it to your computer.': '队列是空的。在下方粘贴链接，发送到电脑下载。',
      'Cancel': '取消', 'Retry': '重试', 'Done': '完成', 'Failed': '失败', 'Canceled': '已取消', 'Waiting': '等待中',
      'Queue paused on the computer.': '电脑上的队列已暂停。',
      'Search the Library': '搜索资料库', 'All': '全部', 'Audio': '音频', 'Images': '图片',
      'No matching files.': '没有匹配的文件。', 'Show more': '显示更多', 'Close': '关闭',
      'Forget this phone': '取消配对', 'Forget this phone? You will need a new pairing code to connect again.': '要取消这部手机的配对吗？之后需要新的配对码才能再次连接。',
      'Video Grabber is not reachable. Check that the app is running and remote access is on.': '无法连接 Video Grabber。请确认电脑上的应用正在运行，并已打开远程访问。',
      'This phone is no longer paired.': '这部手机已不再配对。', 'Paired as {name}': '已配对：{name}'
    },
    'zh-TW': {
      'Pair this phone': '配對這支手機',
      'In Video Grabber on your computer, open Settings and help, then Remote access, and choose Pair a phone. Enter the code it shows.': '在電腦上的 Video Grabber 中開啟「設定與說明」→「遠端存取」，選擇「配對手機」，然後輸入顯示的配對碼。',
      'Pairing code': '配對碼', 'Name for this phone': '這支手機的名稱', 'Pair': '配對', 'Pairing…': '正在配對…',
      'Queue': '佇列', 'Library': '資料庫', 'Paste a link': '貼上連結', 'Send': '傳送', 'Video': '影片', 'MP3': 'MP3',
      'Sent to your computer.': '已傳送到電腦。', 'Already in the queue.': '已在佇列中。',
      'Nothing in the queue. Paste a link below to send it to your computer.': '佇列是空的。在下方貼上連結，傳送到電腦下載。',
      'Cancel': '取消', 'Retry': '重試', 'Done': '完成', 'Failed': '失敗', 'Canceled': '已取消', 'Waiting': '等待中',
      'Queue paused on the computer.': '電腦上的佇列已暫停。',
      'Search the Library': '搜尋資料庫', 'All': '全部', 'Audio': '音訊', 'Images': '圖片',
      'No matching files.': '沒有符合的檔案。', 'Show more': '顯示更多', 'Close': '關閉',
      'Forget this phone': '取消配對', 'Forget this phone? You will need a new pairing code to connect again.': '要取消這支手機的配對嗎？之後需要新的配對碼才能再次連線。',
      'Video Grabber is not reachable. Check that the app is running and remote access is on.': '無法連線 Video Grabber。請確認電腦上的應用程式正在執行，並已開啟遠端存取。',
      'This phone is no longer paired.': '這支手機已不再配對。', 'Paired as {name}': '已配對：{name}'
    },
    ja: {
      'Pair this phone': 'このスマートフォンをペアリング',
      'In Video Grabber on your computer, open Settings and help, then Remote access, and choose Pair a phone. Enter the code it shows.': 'パソコンの Video Grabber で「設定とヘルプ」→「リモートアクセス」を開き、「スマートフォンをペアリング」を選んで、表示されたコードを入力してください。',
      'Pairing code': 'ペアリングコード', 'Name for this phone': 'このスマートフォンの名前', 'Pair': 'ペアリング', 'Pairing…': 'ペアリング中…',
      'Queue': 'キュー', 'Library': 'ライブラリ', 'Paste a link': 'リンクを貼り付け', 'Send': '送信', 'Video': '動画', 'MP3': 'MP3',
      'Sent to your computer.': 'パソコンに送信しました。', 'Already in the queue.': 'すでにキューにあります。',
      'Nothing in the queue. Paste a link below to send it to your computer.': 'キューは空です。下にリンクを貼り付けてパソコンに送信してください。',
      'Cancel': 'キャンセル', 'Retry': '再試行', 'Done': '完了', 'Failed': '失敗', 'Canceled': 'キャンセル済み', 'Waiting': '待機中',
      'Queue paused on the computer.': 'パソコンのキューは一時停止中です。',
      'Search the Library': 'ライブラリを検索', 'All': 'すべて', 'Audio': '音声', 'Images': '画像',
      'No matching files.': '一致するファイルはありません。', 'Show more': 'さらに表示', 'Close': '閉じる',
      'Forget this phone': 'ペアリングを解除', 'Forget this phone? You will need a new pairing code to connect again.': 'このスマートフォンのペアリングを解除しますか？再接続には新しいペアリングコードが必要です。',
      'Video Grabber is not reachable. Check that the app is running and remote access is on.': 'Video Grabber に接続できません。パソコンでアプリが起動し、リモートアクセスがオンになっているか確認してください。',
      'This phone is no longer paired.': 'このスマートフォンのペアリングは解除されています。', 'Paired as {name}': 'ペアリング済み：{name}'
    }
  };
  const lang = (navigator.languages || [navigator.language || 'en']).map((l) => {
    const v = String(l).toLowerCase();
    if (v.startsWith('zh')) return /tw|hk|mo|hant/.test(v) ? 'zh-TW' : 'zh-CN';
    return v.startsWith('ja') ? 'ja' : v.startsWith('en') ? 'en' : '';
  }).find(Boolean) || 'en';
  document.documentElement.lang = lang;
  const t = (key, vars) => {
    let text = (MESSAGES[lang] && MESSAGES[lang][key]) || key;
    for (const [name, value] of Object.entries(vars || {})) text = text.replace('{' + name + '}', value);
    return text;
  };

  const app = document.getElementById('app');
  const state = { device: '', tab: 'queue', mode: 'mp4', jobs: [], paused: false, note: '', noteError: false,
                  q: '', kind: '', items: [], total: 0, timer: 0 };

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === undefined || value === null || value === false) continue;
      if (key === 'text') node.textContent = value;
      else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? '' : value);
    }
    for (const child of [].concat(children || [])) if (child) node.append(child);
    return node;
  }

  async function call(method, path, body) {
    const init = { method, credentials: 'same-origin', headers: {} };
    if (body !== undefined) {
      init.headers['Content-Type'] = 'application/json';
      init.headers['X-VG-Remote'] = '1';
      init.body = JSON.stringify(body);
    }
    let response;
    try {
      response = await fetch(path, init);
    } catch {
      throw new Error(t('Video Grabber is not reachable. Check that the app is running and remote access is on.'));
    }
    const data = await response.json().catch(() => ({}));
    if (response.status === 401 && path !== '/pair') {
      const wasPaired = Boolean(state.device);
      state.device = '';
      renderPair(wasPaired ? t('This phone is no longer paired.') : '');
      throw new Error('unpaired');
    }
    if (!response.ok) throw new Error(data.error || String(response.status));
    return data;
  }

  // ── Pairing ──
  function renderPair(message) {
    stopPolling();
    const code = el('input', { class: 'field code', id: 'code', autocomplete: 'one-time-code', autocapitalize: 'characters',
                               spellcheck: 'false', maxlength: '9', inputmode: 'text', required: true });
    const name = el('input', { class: 'field', id: 'name', maxlength: '40', value: guessName() });
    const status = el('p', { class: 'note' + (message ? ' error' : ''), role: 'status', text: message || '' });
    const button = el('button', { class: 'send', type: 'submit', text: t('Pair') });
    const form = el('form', { class: 'pair', onsubmit: async (event) => {
      event.preventDefault();
      button.disabled = true;
      button.textContent = t('Pairing…');
      try {
        const result = await call('POST', '/pair', { code: code.value, name: name.value });
        state.device = result.device;
        renderMain();
      } catch (error) {
        status.className = 'note error';
        status.textContent = error.message;
        button.disabled = false;
        button.textContent = t('Pair');
      }
    } }, [
      el('h1', { text: t('Pair this phone') }),
      el('p', { text: t('In Video Grabber on your computer, open Settings and help, then Remote access, and choose Pair a phone. Enter the code it shows.') }),
      el('label', { for: 'code' }, [t('Pairing code'), code]),
      el('label', { for: 'name' }, [t('Name for this phone'), name]),
      button, status,
    ]);
    app.replaceChildren(form);
    code.focus();
  }

  function guessName() {
    const ua = navigator.userAgent;
    return /iPhone/.test(ua) ? 'iPhone' : /iPad/.test(ua) ? 'iPad' : /Android/.test(ua) ? 'Android' : 'Phone';
  }

  // ── Main ──
  function renderMain() {
    const main = el('main', { class: 'scroll', id: 'main' });
    const header = el('header', { class: 'top' }, [
      el('h1', { text: 'Video Grabber' }),
      el('span', { class: 'who', text: t('Paired as {name}', { name: state.device }) }),
      el('button', { class: 'link', type: 'button', text: t('Forget this phone'), onclick: forget }),
    ]);
    const tabs = el('nav', { class: 'tabs', role: 'tablist' }, [
      tabButton('queue', t('Queue')), tabButton('library', t('Library')),
    ]);
    const dock = el('div', { class: 'dock' }, [state.tab === 'queue' ? composer() : null, tabs]);
    app.replaceChildren(header, main, dock);
    if (state.tab === 'queue') {
      drawQueue();
      startPolling();
    } else {
      stopPolling();
      drawLibrary(true);
    }
  }

  function tabButton(id, label) {
    return el('button', { type: 'button', role: 'tab', 'aria-selected': String(state.tab === id), text: label,
                          onclick: () => { state.tab = id; state.note = ''; renderMain(); } });
  }

  function composer() {
    const input = el('textarea', { rows: '1', placeholder: t('Paste a link'), 'aria-label': t('Paste a link'),
                                   autocapitalize: 'off', autocomplete: 'off', spellcheck: 'false', inputmode: 'url' });
    input.value = sharedLink();
    const send = el('button', { class: 'send', type: 'submit', text: t('Send') });
    const sync = () => {
      send.disabled = !/https?:\/\//i.test(input.value);
      input.style.height = 'auto';
      input.style.height = Math.min(input.scrollHeight, 120) + 'px';
    };
    input.addEventListener('input', sync);
    const note = el('span', { class: 'note' + (state.noteError ? ' error' : ''), role: 'status', text: state.note });
    const seg = el('div', { class: 'seg', role: 'group', 'aria-label': 'Format' }, [
      ['mp4', t('Video')], ['mp3', t('MP3')],
    ].map(([mode, label]) => el('button', { type: 'button', 'aria-pressed': String(state.mode === mode), text: label,
      onclick: (event) => {
        state.mode = mode;
        for (const b of seg.children) b.setAttribute('aria-pressed', String(b === event.currentTarget));
      } })));
    const form = el('form', { class: 'composer', onsubmit: async (event) => {
      event.preventDefault();
      const urls = input.value.split(/\s+/).filter((u) => /^https?:\/\//i.test(u)).slice(0, 50);
      if (!urls.length) return;
      send.disabled = true;
      try {
        const result = await call('POST', '/api/downloads', { urls, mode: state.mode });
        setNote(result.ids.length ? t('Sent to your computer.') : t('Already in the queue.'), false, note);
        input.value = '';
        history.replaceState(null, '', '/');
        await refreshJobs();
      } catch (error) {
        if (error.message !== 'unpaired') setNote(error.message, true, note);
      } finally {
        sync();
      }
    } }, [input, send]);
    setTimeout(sync);
    return el('div', {}, [form, el('div', { class: 'options' }, [seg, note])]);
  }

  // Links can arrive from a share shortcut as /?url=... or /?text=...; they still need a tap on Send.
  function sharedLink() {
    const params = new URLSearchParams(location.search);
    const value = params.get('url') || params.get('text') || '';
    const match = value.match(/https?:\/\/\S+/i);
    return match ? match[0] : '';
  }

  function setNote(text, error, node) {
    state.note = text;
    state.noteError = error;
    if (node) {
      node.textContent = text;
      node.className = 'note' + (error ? ' error' : '');
    }
  }

  // ── Queue ──
  async function refreshJobs() {
    try {
      const data = await call('GET', '/api/jobs');
      state.jobs = data.jobs;
      state.paused = data.paused;
      if (state.tab === 'queue') drawQueue();
    } catch (error) {
      if (error.message !== 'unpaired') setNote(error.message, true, document.querySelector('.note'));
    }
  }

  function startPolling() {
    stopPolling();
    refreshJobs();
    state.timer = setInterval(() => { if (!document.hidden) refreshJobs(); }, 3000);
  }

  function stopPolling() {
    clearInterval(state.timer);
    state.timer = 0;
  }

  function drawQueue() {
    const main = document.getElementById('main');
    if (!main) return;
    const rows = [];
    if (state.paused) rows.push(el('p', { class: 'empty', text: t('Queue paused on the computer.') }));
    if (!state.jobs.length) rows.push(el('p', { class: 'empty', text: t('Nothing in the queue. Paste a link below to send it to your computer.') }));
    for (const job of state.jobs) rows.push(taskRow(job));
    main.replaceChildren(...rows);
  }

  function taskRow(job) {
    const label = { done: t('Done'), error: t('Failed'), canceled: t('Canceled'), queued: t('Waiting') }[job.status];
    const stage = job.status === 'error' && job.error ? job.error
      : job.status === 'running' ? `${job.stage} · ${Math.round(job.percent)}%` : label || job.stage;
    let action = null;
    if (job.status === 'queued' || job.status === 'running') action = actionButton(job.id, 'cancel', t('Cancel'));
    if (job.status === 'error' || job.status === 'canceled') action = actionButton(job.id, 'retry', t('Retry'));
    return el('div', { class: 'task' }, [
      el('div', { class: 'row' }, [el('span', { class: 'title', text: job.title || job.url }), action]),
      job.status === 'running' ? el('div', { class: 'bar', role: 'progressbar', 'aria-valuemin': '0', 'aria-valuemax': '100',
        'aria-valuenow': String(Math.round(job.percent)) }, [progressFill(job.percent)]) : null,
      el('span', { class: 'stage ' + job.status, text: stage }),
    ]);
  }

  // The CSP blocks style attributes, so set the width through the CSSOM instead.
  function progressFill(percent) {
    const fill = el('i');
    fill.style.width = Math.max(2, Math.min(100, percent)) + '%';
    return fill;
  }

  function actionButton(id, action, label) {
    return el('button', { class: 'small', type: 'button', text: label, onclick: async (event) => {
      event.currentTarget.disabled = true;
      try {
        await call('POST', `/api/jobs/${id}/${action}`, {});
      } catch (error) {
        if (error.message !== 'unpaired') setNote(error.message, true, document.querySelector('.note'));
      }
      refreshJobs();
    } });
  }

  // ── Library ──
  async function drawLibrary(reset) {
    const main = document.getElementById('main');
    if (!main) return;
    if (reset) {
      state.items = [];
      const search = el('input', { class: 'field', type: 'search', placeholder: t('Search the Library'),
                                   'aria-label': t('Search the Library'), value: state.q });
      let wait = 0;
      search.addEventListener('input', () => {
        clearTimeout(wait);
        wait = setTimeout(() => { state.q = search.value; drawLibrary(true); }, 300);
      });
      const kind = el('select', { class: 'field', 'aria-label': 'Type', onchange: (event) => {
        state.kind = event.currentTarget.value;
        drawLibrary(true);
      } }, [['', t('All')], ['video', t('Video')], ['audio', t('Audio')], ['image', t('Images')]].map(
        ([value, label]) => el('option', { value, text: label, selected: state.kind === value })));
      main.replaceChildren(el('div', { class: 'tools' }, [search, kind]), el('div', { id: 'items' }));
      if (state.q) { search.focus(); search.setSelectionRange(search.value.length, search.value.length); }
    }
    const params = new URLSearchParams({ q: state.q, kind: state.kind, offset: String(state.items.length), limit: '30' });
    let data;
    try {
      data = await call('GET', '/api/library?' + params);
    } catch (error) {
      if (error.message !== 'unpaired') document.getElementById('items').replaceChildren(el('p', { class: 'empty', text: error.message }));
      return;
    }
    state.items = state.items.concat(data.items);
    state.total = data.total;
    const list = document.getElementById('items');
    if (!list) return;
    const nodes = state.items.length ? state.items.map(libraryRow) : [el('p', { class: 'empty', text: t('No matching files.') })];
    if (state.items.length < state.total) {
      nodes.push(el('button', { class: 'small more', type: 'button', text: t('Show more'), onclick: () => drawLibrary(false) }));
    }
    list.replaceChildren(...nodes);
  }

  function fileUrl(path) {
    return '/files/' + path.split('/').map(encodeURIComponent).join('/');
  }

  function libraryRow(item) {
    const cover = item.kind === 'image' ? item.path : item.thumbnail;
    const thumb = cover ? el('img', { class: 'thumb', src: fileUrl(cover), alt: '', loading: 'lazy' })
      : el('span', { class: 'thumb', 'aria-hidden': 'true', text: item.kind === 'audio' ? '♪' : '▶' });
    const date = new Date((item.downloaded || 0) * 1000).toLocaleDateString(lang);
    return el('button', { class: 'item', type: 'button', onclick: () => openPlayer(item) }, [
      thumb,
      el('span', { class: 'text' }, [
        el('span', { class: 'name', text: item.title || item.name }),
        el('span', { class: 'meta', text: `${formatSize(item.size)} · ${date}` }),
      ]),
    ]);
  }

  function formatSize(bytes) {
    const units = ['B', 'KB', 'MB', 'GB'];
    let value = Number(bytes) || 0;
    let unit = 0;
    while (value >= 1024 && unit < units.length - 1) { value /= 1024; unit += 1; }
    return `${value.toFixed(unit && value < 10 ? 1 : 0)} ${units[unit]}`;
  }

  function openPlayer(item) {
    const src = fileUrl(item.path);
    const media = item.kind === 'image' ? el('img', { src, alt: item.title || item.name })
      : el(item.kind === 'audio' ? 'audio' : 'video', { src, controls: true, autoplay: true, playsinline: true, preload: 'metadata' });
    const close = el('button', { class: 'small', type: 'button', text: t('Close') });
    const sheet = el('div', { class: 'sheet', role: 'dialog', 'aria-modal': 'true', 'aria-label': item.title || item.name }, [
      el('header', {}, [el('span', { text: item.title || item.name }), close]),
      el('div', { class: 'media' }, [media]),
    ]);
    const previous = document.activeElement;
    const shut = () => {
      if (media.pause) media.pause();
      sheet.remove();
      document.removeEventListener('keydown', onKey);
      if (previous) previous.focus();
    };
    const onKey = (event) => { if (event.key === 'Escape') shut(); };
    close.addEventListener('click', shut);
    document.addEventListener('keydown', onKey);
    document.body.append(sheet);
    close.focus();
  }

  async function forget() {
    if (!confirm(t('Forget this phone? You will need a new pairing code to connect again.'))) return;
    try {
      await call('POST', '/api/forget', {});
    } catch {
      /* Already unpaired or unreachable: show the pairing screen either way. */
    }
    state.device = '';
    renderPair('');
  }

  // ── Start ──
  call('GET', '/api/me').then((me) => { state.device = me.device; renderMain(); }).catch((error) => {
    if (error.message !== 'unpaired') renderPair(error.message);
  });
})();
"""

ASSETS = {
    "/": (HTML.encode("utf-8"), "text/html; charset=utf-8"),
    "/remote.css": (CSS.encode("utf-8"), "text/css; charset=utf-8"),
    "/remote.js": (JS.encode("utf-8"), "text/javascript; charset=utf-8"),
}
