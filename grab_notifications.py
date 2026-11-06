"""Queue completion summaries and optional Windows notifications with fixed actions."""
from __future__ import annotations

import datetime
import logging
from pathlib import Path
import time

LOG = logging.getLogger(__name__)
AUMID = "VideoGrabber.Local.Desktop"

COPY = {
    "en": ("Downloads finished", "Completed {ok}, failed {bad}", "Download complete", "{ok} downloads completed",
           "Play", "Open image", "Open folder", "View queue", "Play latest file", "Open latest folder"),
    "zh-CN": ("下载已结束", "已完成 {ok} 项，失败 {bad} 项", "下载完成", "{ok} 项下载已完成",
              "播放", "查看图片", "打开文件夹", "查看队列", "播放最新文件", "打开最新文件夹"),
    "zh-TW": ("下載已結束", "已完成 {ok} 項，失敗 {bad} 項", "下載完成", "{ok} 項下載已完成",
              "播放", "檢視圖片", "開啟資料夾", "檢視佇列", "播放最新檔案", "開啟最新資料夾"),
    "ja": ("ダウンロード終了", "完了 {ok} 件、失敗 {bad} 件", "ダウンロード完了", "{ok} 件のダウンロードが完了",
           "再生", "画像を開く", "フォルダーを開く", "キューを表示", "最新のファイルを再生", "最新のフォルダーを開く"),
}
IMAGES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif"}


class CompletionBatch:
    """Observe completed work even when it finishes entirely between two polls."""
    def __init__(self, started=None):
        self.started = time.time() if started is None else started
        self.seen = set()
        self.ok = self.bad = 0
        self.latest = None

    def update(self, jobs):
        active = False
        present = set()
        for job in jobs:
            key = (job["id"], job["finished"])
            present.add(key)
            status = job["status"]
            if status in {"queued", "running"} or (status in {"done", "error"} and not job["finished"]):
                active = True
            if key in self.seen or job["finished"] <= self.started:
                continue
            if status == "done":
                self.ok += 1
                if self.latest is None or job["finished"] > self.latest["finished"]:
                    self.latest = job
            elif status == "error":
                self.bad += 1
            if status in {"done", "error", "canceled"}:
                self.seen.add(key)
        self.seen.intersection_update(present)
        if active or not self.ok + self.bad:
            return None
        result = {"ok": self.ok, "bad": self.bad, "latest": self.latest}
        self.ok = self.bad = 0
        self.latest = None
        return result


def completion_content(batch, locale):
    text = COPY.get(locale, COPY["en"])
    latest = batch["latest"]
    summary = (text[1] if batch["bad"] else text[2] if batch["ok"] == 1 else text[3]).format(**batch)
    files = [file for file in latest["files"] if file.get("complete") is not False] if latest else []
    # Video covers and subtitles must never become the play target.
    mode = latest.get("mode", "mp4") if latest else ""
    if mode not in {"cover", "image"}:
        files = [file for file in files if Path(file["path"]).suffix.lower() not in IMAGES | {".srt", ".vtt", ".ass"}]
    path = files[-1]["path"] if files else ""
    multiple = batch["ok"] > 1 or len(files) > 1
    actions = []
    if path:
        image = Path(path).suffix.lower() in IMAGES
        actions = [(text[5] if image else text[8] if multiple else text[4], "play"),
                   (text[9] if multiple else text[6], "folder")]
    actions.append((text[7], "queue"))
    detail = Path(path).name if path else ""
    return text[0], summary, detail, path, actions


class WindowsNotifier:
    """Created and closed on the desktop notification thread (WinRT apartment owner)."""
    def __init__(self):
        import winreg
        from winrt.runtime import ApartmentType, init_apartment, uninit_apartment
        from windows_toasts import InteractableWindowsToaster, Toast, ToastButton

        init_apartment(ApartmentType.MULTI_THREADED)
        self._uninit = uninit_apartment
        try:
            # A dedicated per-user identity makes actions work from Notification Center too.
            with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, rf"SOFTWARE\Classes\AppUserModelId\{AUMID}") as key:
                winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, "Video Grabber")
            self.toaster = InteractableWindowsToaster("Video Grabber", notifierAUMID=AUMID)
            self.toaster.clear_toasts()
        except Exception:
            self.toaster = None
            self._uninit()
            raise
        self.Toast, self.Button = Toast, ToastButton
        self.toast = None

    def show(self, batch, locale, activate, failed):
        title, summary, detail, path, actions = completion_content(batch, locale)
        allowed = {action for _, action in actions}
        def clicked(event):
            action = event.arguments if event.arguments in allowed else "queue"
            activate(action, path)

        toast = self.Toast([title, summary, detail] if detail else [title, summary],
                           group="downloads", expiration_time=datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1))
        toast.tag = "completion"
        for label, action in actions:
            toast.AddAction(self.Button(label, action))
        toast.on_activated = clicked
        toast.on_failed = lambda event: failed()
        self.toast = toast  # Keep callback owners alive while Windows retains the notification.
        self.toaster.show_toast(toast)

    def clear(self):
        self.toaster.clear_toasts()
        self.toast = None

    def close(self):
        if self.toaster is None:
            return
        try:
            self.clear()
        finally:
            # Release apartment-bound WinRT objects before uninitializing COM.
            self.toast = None
            self.toaster = None
            self._uninit()
