"""Windows tray and small download window, sharing the existing local service."""
from __future__ import annotations

import logging
import sys
import threading
from urllib.parse import urldefrag

from grab_storage import JsonStore
from grab_notifications import CompletionBatch, WindowsNotifier, completion_content

LOG = logging.getLogger(__name__)
LABELS = {
    "en": ("Open Video Grabber", "Quick download", "Exit", "Downloads continue in the background. Use this icon to reopen the app."),
    "zh-CN": ("打开 Video Grabber", "快捷下载", "退出", "下载将在后台继续。点击此图标可以重新打开软件。"),
    "zh-TW": ("開啟 Video Grabber", "快捷下載", "結束", "下載會在背景繼續。點擊此圖示可以重新開啟軟體。"),
    "ja": ("Video Grabber を開く", "クイックダウンロード", "終了", "ダウンロードはバックグラウンドで続行します。このアイコンから再表示できます。"),
}


def reopen(window):
    window.show()
    # Restoring an already maximized WinForms window would discard its size.
    if str(window.native.WindowState) == "Minimized":
        window.restore()


def make_tray(controller):
    import pystray
    from PIL import Image, ImageDraw

    image = Image.new("RGBA", (64, 64))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((2, 2, 62, 62), radius=14, fill="#f4f4f5")
    draw.line([(32, 13), (32, 42)], fill="#18181b", width=6)
    draw.line([(20, 31), (32, 43), (44, 31)], fill="#18181b", width=6)
    draw.line([(17, 51), (47, 51)], fill="#18181b", width=5)
    menu = pystray.Menu(
        pystray.MenuItem(lambda item: controller.labels[0], lambda icon, item: controller.show_main(), default=True),
        pystray.MenuItem(lambda item: controller.labels[1], lambda icon, item: controller.show_quick()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(lambda item: controller.labels[2], lambda icon, item: controller.request_exit()),
    )
    return pystray.Icon("video-grabber", image, "Video Grabber", menu)


class DesktopController:
    def __init__(self, webview, main_window, url: str, tray_factory=make_tray, preferences_path=None,
                 pending_downloads=lambda: 0, notification_jobs=lambda since: [],
                 notification_action=lambda action, path: None, notifier_factory=WindowsNotifier):
        self.webview = webview
        self.main_window = main_window
        self.url = urldefrag(url)[0]
        self.quick_window = None
        self.icon = None
        self.ready = threading.Event()
        self.exiting = threading.Event()
        self.locale = "en"
        self._tray_factory = tray_factory
        self._quick_lock = threading.Lock()
        self._notified = False
        self._behavior_lock = threading.RLock()
        self._preferences = (JsonStore(lambda: preferences_path, threading.Lock())
                             if preferences_path is not None else None)
        saved = self._preferences.load({}) if self._preferences else {}
        behavior = saved.get("close_behavior") if isinstance(saved, dict) else None
        self.close_behavior = behavior if isinstance(behavior, str) and behavior in {"background", "exit"} else "ask"
        self.pending_downloads = pending_downloads
        self.notifications_enabled = not isinstance(saved, dict) or saved.get("notifications_enabled") is not False
        self.notifications_available = False
        self._notification_jobs = notification_jobs
        self._notification_action = notification_action
        self._notifier_factory = notifier_factory
        self._notification_batch = CompletionBatch()
        self._notification_stop = threading.Event()
        self._notification_thread = None
        self.ui_ready = threading.Event()
        self._close_pending = threading.Event()

    @property
    def labels(self):
        return LABELS[self.locale]

    def start(self):
        """Runs in pywebview's startup worker; the GUI loop stays on its main thread."""
        try:
            self.icon = self._tray_factory(self)
            self._notification_thread = threading.Thread(target=self._watch_completions,
                                                         name="completion-notifications", daemon=True)
            self._notification_thread.start()
            self.icon.run(setup=self._on_ready)
        except ModuleNotFoundError as exc:
            if exc.name in {"pystray", "PIL"}:
                LOG.warning(
                    'System tray dependencies are missing for %s.\n'
                    'Install with this Python: & "%s" -m pip install "pystray>=0.19.5,<0.20" "Pillow>=10,<13"\n'
                    'Background running is unavailable until these dependencies are installed.',
                    sys.executable, sys.executable,
                )
            else:
                LOG.exception("System tray could not start. Background running is unavailable.")
        except Exception:
            LOG.exception("System tray could not start. Background running is unavailable.")
        finally:
            self._notification_stop.set()
            if self._notification_thread is not None:
                self._notification_thread.join(timeout=2)
            self.ready.clear()
            if not self.exiting.is_set():
                # A failed tray must not leave the application hidden and unreachable.
                self.main_window.show()

    def _on_ready(self, icon):
        if self.exiting.is_set():
            icon.stop()
            return
        icon.visible = True
        self.ready.set()

    def close_main(self):
        if self.exiting.is_set():
            return True
        pending = self.pending_downloads()
        if self.close_behavior == "exit" and pending == 0:
            # Destroy both windows outside the synchronous GUI closing callback.
            threading.Thread(target=self.quit, daemon=True).start()
            return False
        if self.close_behavior == "background" and self.ready.is_set():
            self.background()
        elif not self.ui_ready.is_set():
            # The UI may still be loading. Never silently hide or discard a close request.
            self._confirm_exit(pending)
        elif not self._close_pending.is_set():
            self._close_pending.set()
            # Closing runs on the GUI thread. JavaScript evaluation must not block that thread.
            threading.Thread(target=self._request_close, daemon=True).start()
        return False

    def _confirm_exit(self, pending):
        message = {"en": "Exit Video Grabber?", "zh-CN": "完全退出 Video Grabber？",
                   "zh-TW": "完全結束 Video Grabber？", "ja": "Video Grabber を終了しますか？"}[self.locale]
        if pending:
            message += "\n" + {"en": f"Unfinished downloads: {pending}.", "zh-CN": f"还有 {pending} 项下载未完成。",
                               "zh-TW": f"還有 {pending} 項下載未完成。", "ja": f"未完了のダウンロードが {pending} 件あります。"}[self.locale]
        if self.main_window.create_confirmation_dialog("Video Grabber", message):
            threading.Thread(target=self.quit, daemon=True).start()

    def request_exit(self):
        """An explicit tray exit still protects unfinished work, regardless of close preference."""
        if self.exiting.is_set():
            return
        pending = self.pending_downloads()
        if pending == 0:
            self.quit()
            return
        self.show_main()
        if not self.ui_ready.is_set():
            self._confirm_exit(pending)
            return
        if not self._close_pending.is_set():
            self._close_pending.set()
            self._request_close()

    def _request_close(self):
        try:
            acknowledged = self.main_window.evaluate_js(
                "!window.dispatchEvent(new Event('grab-close-request', {cancelable: true}))")
            if not acknowledged:
                self.ui_ready.clear()
                self._close_pending.clear()
                LOG.warning("The close dialog is not ready. Close again to confirm exit, or use the tray menu.")
        except Exception:
            self._close_pending.clear()
            LOG.exception("Could not show the close dialog. Use Exit in the tray menu.")

    def set_close_behavior(self, behavior):
        if behavior not in {"ask", "background", "exit"}:
            raise ValueError("Choose a valid close behavior.")
        with self._behavior_lock:
            if self._preferences:
                self._preferences.path().parent.mkdir(parents=True, exist_ok=True)
                saved = self._preferences.load({})
                self._preferences.save({**(saved if isinstance(saved, dict) else {}), "close_behavior": behavior})
            self.close_behavior = behavior

    def set_notifications(self, enabled):
        if not isinstance(enabled, bool):
            raise ValueError("Choose whether completion notifications are enabled.")
        with self._behavior_lock:
            if self._preferences:
                self._preferences.path().parent.mkdir(parents=True, exist_ok=True)
                saved = self._preferences.load({})
                self._preferences.save({**(saved if isinstance(saved, dict) else {}), "notifications_enabled": enabled})
            self.notifications_enabled = enabled

    @property
    def preferences_lock(self):
        return self._behavior_lock

    def reload_preferences(self):
        with self._behavior_lock:
            saved = self._preferences.load({}) if self._preferences else {}
            if isinstance(saved, dict):
                behavior = saved.get("close_behavior")
                if isinstance(behavior, str) and behavior in {"ask", "background", "exit"}:
                    self.close_behavior = behavior
                if isinstance(saved.get("notifications_enabled"), bool):
                    self.notifications_enabled = saved["notifications_enabled"]

    def _foreground(self):
        try:
            import ctypes
            foreground = ctypes.windll.user32.GetForegroundWindow
            foreground.restype = ctypes.c_void_p
            return foreground() == self.main_window.native.Handle.ToInt64()
        except (AttributeError, OSError):
            return False

    def _activate_notification(self, action, path):
        if self.exiting.is_set() or not self.notifications_enabled:
            return
        try:
            if action == "queue":
                self.show_main("queue")
            elif action in {"play", "folder"} and path:
                self._notification_action(action, path)
        except Exception:
            LOG.exception("Could not open the completed download. It may have been moved or removed.")
            self.show_main("queue")

    def _notification_fallback(self, batch):
        if self.ready.is_set() and not self.exiting.is_set() and self.notifications_enabled:
            try:
                title, summary, _, _, _ = completion_content(batch, self.locale)
                self.icon.notify(summary, title)
            except Exception:
                LOG.warning("Windows could not display the download completion reminder.")

    def _watch_completions(self):
        notifier = None
        try:
            try:
                notifier = self._notifier_factory()
                self.notifications_available = True
            except Exception:
                LOG.warning('Native notification buttons are unavailable. Install desktop dependencies with '
                            '"%s" -m pip install -e ".[desktop]" and restart. Tray reminders remain available.', sys.executable)
            enabled = self.notifications_enabled
            while not self._notification_stop.wait(1):
                try:
                    if enabled and not self.notifications_enabled and notifier:
                        notifier.clear()
                    enabled = self.notifications_enabled
                    batch = self._notification_batch.update(self._notification_jobs(self._notification_batch.started))
                    if not batch or not self.notifications_enabled or self._foreground() or self.exiting.is_set():
                        continue
                    if notifier:
                        try:
                            notifier.show(batch, self.locale, self._activate_notification,
                                          lambda batch=batch: self._notification_fallback(batch))
                        except Exception:
                            LOG.exception("Windows could not show the actionable completion notification.")
                            self._notification_fallback(batch)
                    else:
                        self._notification_fallback(batch)
                except Exception:
                    LOG.exception("Could not check download completion notifications.")
        finally:
            self.notifications_available = False
            if notifier:
                try:
                    notifier.close()
                except Exception:
                    LOG.warning("Could not clear Windows completion notifications on exit.")

    def background(self):
        if not self.ready.is_set() or self.exiting.is_set():
            raise ValueError("The tray is unavailable. Keep the window open or exit the app.")
        self.main_window.hide()
        if not self._notified:
            self._notified = True
            try:
                self.icon.notify(self.labels[3], "Video Grabber")
            except Exception:
                LOG.warning("The app is still running in the tray; Windows could not show its notification.")

    def show_main(self, view=""):
        if self.exiting.is_set():
            return
        reopen(self.main_window)
        if view in {"new", "queue", "library"}:
            self.main_window.evaluate_js(f"location.hash = '#/{view}'")

    def show_quick(self):
        if self.exiting.is_set() or not self.ready.is_set():
            return
        with self._quick_lock:
            if self.exiting.is_set():
                return
            if self.quick_window is None:
                window = self.webview.create_window(
                    "Video Grabber — Quick download", self.url + "#/quick", js_api=DesktopBridge(self),
                    width=460, height=650, min_size=(360, 460), background_color="#0b0d10", text_select=True,
                )
                if window is None:
                    return
                self.quick_window = window
                window.events.closing += self.close_quick
            else:
                reopen(self.quick_window)

    def close_quick(self):
        if self.exiting.is_set():
            return True
        if self.quick_window is not None:
            self.quick_window.hide()
        return False

    def stop(self):
        self.exiting.set()
        self._notification_stop.set()
        self.ready.clear()
        if self.icon is not None:
            # Remove it synchronously too: service restarts use os._exit afterwards.
            self.icon.visible = False
            self.icon.stop()
        if self._notification_thread is not None and self._notification_thread is not threading.current_thread():
            self._notification_thread.join(timeout=2)

    def quit(self):
        if self.exiting.is_set():
            return
        self.stop()
        with self._quick_lock:
            quick = self.quick_window
        if quick is not None:
            quick.destroy()
        self.main_window.destroy()


class DesktopBridge:
    """Only fixed window actions are exposed to the trusted local UI."""
    def __init__(self, controller):
        self._controller = controller

    def show_main(self, view=""):
        self._controller.show_main(view)

    def hide_quick(self):
        self._controller.close_quick()

    def close_settings(self):
        self._controller.ui_ready.set()
        return {"behavior": self._controller.close_behavior, "tray_ready": self._controller.ready.is_set(),
                "pending_downloads": self._controller.pending_downloads()}

    def set_close_behavior(self, behavior):
        self._controller.set_close_behavior(behavior)
        return self.close_settings()

    def close_action(self, action, remember=False):
        if action not in {"cancel", "background", "exit"}:
            raise ValueError("Choose a valid close action.")
        if action == "background":
            if not self._controller.ready.is_set():
                raise ValueError("The tray is unavailable. Keep the window open or exit the app.")
            if remember is True:
                self._controller.set_close_behavior("background")
            self._controller.background()
        elif action == "exit":
            self._controller.quit()
        self._controller._close_pending.clear()

    def sync_locale(self, locale):
        if locale in LABELS:
            self._controller.locale = locale
            if self._controller.icon is not None and self._controller.ready.is_set():
                self._controller.icon.update_menu()
