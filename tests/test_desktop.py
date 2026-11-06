import types
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock
import pytest

from grab_desktop import DesktopBridge, DesktopController


class Event:
    def __init__(self):
        self.handlers = []

    def __iadd__(self, handler):
        self.handlers.append(handler)
        return self


def controller():
    main = Mock()
    main.create_confirmation_dialog.return_value = False
    quick = Mock(events=types.SimpleNamespace(closing=Event()))
    webview = Mock(create_window=Mock(return_value=quick))
    return DesktopController(webview, main, "http://127.0.0.1:8765/#/library", notifier_factory=Mock())


def test_notification_preferences_preserve_close_behavior_and_other_settings(tmp_path):
    import json
    prefs = tmp_path / "desktop.json"
    prefs.write_text(json.dumps({"other": "kept"}))
    desktop = DesktopController(Mock(), Mock(), "http://127.0.0.1:8765", preferences_path=prefs)
    desktop.set_notifications(False)
    desktop.set_close_behavior("background")
    assert json.loads(prefs.read_text()) == {"other": "kept", "notifications_enabled": False, "close_behavior": "background"}
    restored = DesktopController(Mock(), Mock(), "http://127.0.0.1:8765", preferences_path=prefs)
    assert not restored.notifications_enabled and restored.close_behavior == "background"
    restored.set_notifications(True)
    assert json.loads(prefs.read_text())["close_behavior"] == "background"
    with pytest.raises(ValueError):
        restored.set_notifications("yes")
    restored._preferences.save({"close_behavior": [], "notifications_enabled": "invalid"})
    restored.reload_preferences()
    assert restored.close_behavior == "background" and restored.notifications_enabled is True


@pytest.mark.parametrize("foreground,enabled,expected", [(False, True, 1), (True, True, 0), (False, False, 0)])
def test_background_completion_has_one_owner_and_does_not_replay_history(foreground, enabled, expected):
    from test_notifications import job
    desktop = controller()
    desktop.notifications_enabled = enabled
    desktop._notification_batch.started = 10
    desktop._foreground = Mock(return_value=foreground)
    desktop._notification_jobs = Mock(return_value=[job()])
    desktop._notification_stop = Mock(wait=Mock(side_effect=[False, False, True]))
    notifier = desktop._notifier_factory.return_value
    desktop._watch_completions()
    assert notifier.show.call_count == expected
    notifier.close.assert_called_once()
    assert not desktop.notifications_available


def test_missing_or_failed_notifier_falls_back_without_losing_the_app(caplog):
    from test_notifications import job
    desktop = controller()
    desktop.ready.set()
    desktop.icon = Mock()
    desktop._notifier_factory.side_effect = ModuleNotFoundError("windows_toasts")
    desktop._notification_batch.started = 10
    desktop._foreground = Mock(return_value=False)
    desktop._notification_jobs = lambda since: [job()]
    desktop._notification_stop = Mock(wait=Mock(side_effect=[False, True]))
    desktop._watch_completions()
    desktop.icon.notify.assert_called_once()
    assert "Tray reminders remain available" in caplog.text


def test_notification_actions_do_not_open_after_exit_or_when_disabled():
    desktop = controller()
    desktop._notification_action = Mock()
    desktop._activate_notification("play", "saved.mp4")
    desktop._notification_action.assert_called_once_with("play", "saved.mp4")
    desktop.notifications_enabled = False
    desktop._activate_notification("folder", "saved.mp4")
    desktop.notifications_enabled = True
    desktop.stop()
    desktop._activate_notification("play", "saved.mp4")
    assert desktop._notification_action.call_count == 1


def test_removed_notification_target_returns_to_the_queue():
    desktop = controller()
    desktop._notification_action = Mock(side_effect=FileNotFoundError())
    desktop.show_main = Mock()
    desktop._activate_notification("play", "gone.mp4")
    desktop.show_main.assert_called_once_with("queue")


def test_close_only_hides_after_the_tray_is_ready_and_notifies_once():
    desktop = controller()
    desktop.set_close_behavior("background")
    assert desktop.close_main() is False
    desktop.main_window.hide.assert_not_called()
    desktop.icon = Mock()
    desktop._on_ready(desktop.icon)
    assert desktop.icon.visible and desktop.ready.is_set()
    assert desktop.close_main() is False
    assert desktop.close_main() is False
    assert desktop.main_window.hide.call_count == 2
    desktop.icon.notify.assert_called_once()
    desktop.main_window.native.WindowState = "Minimized"
    desktop.show_main("queue")
    desktop.main_window.show.assert_called_once()
    desktop.main_window.restore.assert_called_once()
    desktop.main_window.evaluate_js.assert_called_once_with("location.hash = '#/queue'")
    desktop.main_window.native.WindowState = "Maximized"
    desktop.show_main()
    assert desktop.main_window.restore.call_count == 1


def test_close_asks_without_hiding_and_cancel_allows_another_prompt():
    desktop = controller()
    desktop.ready.set()
    bridge = DesktopBridge(desktop)
    assert bridge.close_settings()["behavior"] == "ask"
    observed = threading.Event()
    desktop._request_close = Mock(side_effect=observed.set)
    assert desktop.close_main() is False
    assert observed.wait(2)
    desktop.main_window.hide.assert_not_called()
    assert desktop._close_pending.is_set()
    desktop.close_main()
    desktop._request_close.assert_called_once()
    bridge.close_action("cancel")
    assert not desktop._close_pending.is_set()
    desktop.close_main()
    assert desktop._close_pending.is_set()


def test_missing_ui_listener_does_not_leave_close_requests_stuck():
    desktop = controller()
    desktop.ui_ready.set()
    desktop._close_pending.set()
    desktop.main_window.evaluate_js.return_value = False
    desktop._request_close()
    assert not desktop.ui_ready.is_set() and not desktop._close_pending.is_set()


def test_close_confirmation_still_appears_without_a_working_tray():
    desktop = controller()
    DesktopBridge(desktop).close_settings()
    observed = threading.Event()
    desktop._request_close = observed.set
    assert desktop.close_main() is False
    assert observed.wait(2)
    desktop.main_window.hide.assert_not_called()


def test_exit_summary_uses_the_latest_unfinished_count():
    desktop = controller()
    desktop.pending_downloads = Mock(side_effect=[3, 1, 0])
    bridge = DesktopBridge(desktop)
    assert [bridge.close_settings()["pending_downloads"] for _ in range(3)] == [3, 1, 0]


def test_tray_exit_checks_unfinished_work_even_with_background_preference():
    desktop = controller()
    desktop.ready.set()
    desktop.pending_downloads = lambda: 2
    desktop.set_close_behavior("background")
    DesktopBridge(desktop).close_settings()
    desktop._request_close = Mock()
    desktop.request_exit()
    desktop._request_close.assert_called_once()
    desktop.main_window.show.assert_called_once()
    desktop.main_window.destroy.assert_not_called()
    desktop.main_window.hide.assert_not_called()


def test_native_fallback_exit_includes_unfinished_count():
    desktop = controller()
    desktop.pending_downloads = lambda: 4
    desktop.close_main()
    assert "Unfinished downloads: 4" in desktop.main_window.create_confirmation_dialog.call_args.args[1]


def test_remembered_background_survives_restart_and_can_be_reset(tmp_path):
    path = tmp_path / "config" / "desktop.json"
    desktop = DesktopController(Mock(), Mock(), "http://127.0.0.1/", preferences_path=path)
    desktop.ready.set()
    desktop.icon = Mock()
    DesktopBridge(desktop).close_action("background", True)
    assert desktop.close_behavior == "background"
    desktop.main_window.hide.assert_called_once()
    restarted = DesktopController(Mock(), Mock(), "http://127.0.0.1/", preferences_path=path)
    assert restarted.close_behavior == "background"
    DesktopBridge(restarted).set_close_behavior("ask")
    assert DesktopController(Mock(), Mock(), "http://127.0.0.1/", preferences_path=path).close_behavior == "ask"
    with pytest.raises(ValueError):
        DesktopBridge(restarted).set_close_behavior("unknown")


def test_direct_exit_is_persisted_and_closes_both_windows_when_idle(tmp_path):
    path = tmp_path / "desktop.json"
    desktop = DesktopController(Mock(), Mock(), "http://127.0.0.1/", preferences_path=path,
                                pending_downloads=lambda: 0)
    desktop.set_close_behavior("exit")
    assert DesktopController(Mock(), Mock(), "http://127.0.0.1/", preferences_path=path).close_behavior == "exit"
    desktop.quick_window = Mock()
    closed = threading.Event()
    desktop.main_window.destroy.side_effect = closed.set
    assert desktop.close_main() is False
    assert closed.wait(2)
    desktop.main_window.destroy.assert_called_once()
    desktop.quick_window.destroy.assert_called_once()
    assert desktop.exiting.is_set()


@pytest.mark.parametrize("count", [1, 3])
def test_direct_exit_still_asks_when_downloads_are_unfinished(count):
    desktop = controller()
    desktop.pending_downloads = lambda: count
    desktop.set_close_behavior("exit")
    DesktopBridge(desktop).close_settings()
    prompted = threading.Event()
    desktop._request_close = prompted.set
    assert desktop.close_main() is False
    assert prompted.wait(2)
    desktop.main_window.destroy.assert_not_called()
    desktop.main_window.hide.assert_not_called()
    DesktopBridge(desktop).close_action("cancel")
    assert desktop.close_behavior == "exit" and not desktop.exiting.is_set()


def test_background_requires_tray_and_exit_ignores_remember_checkbox():
    desktop = controller()
    bridge = DesktopBridge(desktop)
    with pytest.raises(ValueError, match="tray"):
        bridge.close_action("background", True)
    assert desktop.close_behavior == "ask"
    desktop.main_window.hide.assert_not_called()
    bridge.close_action("exit", True)
    assert desktop.close_behavior == "ask" and desktop.exiting.is_set()
    desktop.main_window.destroy.assert_called_once()


def test_failed_preference_save_keeps_window_open(tmp_path, monkeypatch):
    desktop = DesktopController(Mock(), Mock(), "http://127.0.0.1/", preferences_path=tmp_path / "desktop.json")
    desktop.ready.set()
    monkeypatch.setattr(type(desktop._preferences), "save", Mock(side_effect=OSError("disk full")))
    with pytest.raises(OSError):
        DesktopBridge(desktop).close_action("background", True)
    assert desktop.close_behavior == "ask"
    desktop.main_window.hide.assert_not_called()


def test_quick_window_is_reused_and_close_does_not_destroy_the_session():
    desktop = controller()
    desktop.ready.set()
    with ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(lambda _: desktop.show_quick(), range(3)))
    desktop.webview.create_window.assert_called_once()
    args, kwargs = desktop.webview.create_window.call_args
    assert args[1] == "http://127.0.0.1:8765/#/quick"
    assert kwargs["width"] == 460 and kwargs["min_size"] == (360, 460)
    assert desktop.close_quick() is False
    desktop.quick_window.hide.assert_called_once()
    desktop.quick_window.destroy.assert_not_called()
    desktop.quit()
    desktop.quick_window.destroy.assert_called_once()
    desktop.main_window.destroy.assert_called_once()
    assert desktop.close_main() is True and desktop.close_quick() is True
    desktop.quit()
    desktop.main_window.destroy.assert_called_once()


def test_failed_tray_restores_main_window_instead_of_leaving_it_hidden(caplog):
    desktop = controller()
    desktop.icon = Mock()

    def run(setup):
        setup(desktop.icon)
        raise RuntimeError("tray unavailable")

    desktop.icon.run.side_effect = run
    desktop._tray_factory = lambda _: desktop.icon
    desktop.start()
    assert not desktop.ready.is_set()
    desktop.main_window.show.assert_called_once()
    assert desktop.close_main() is False
    assert "System tray could not start" in caplog.text


def test_stopping_before_tray_ready_does_not_leave_an_orphan_icon():
    desktop = controller()
    desktop.stop()
    icon = Mock()
    desktop._on_ready(icon)
    icon.stop.assert_called_once()
    assert not desktop.ready.is_set()
    desktop.show_quick()
    desktop.webview.create_window.assert_not_called()


@pytest.mark.parametrize("module", ["pystray", "PIL"])
def test_missing_dependency_names_the_current_python_and_keeps_normal_close(module, caplog):
    desktop = controller()
    desktop._tray_factory = Mock(side_effect=ModuleNotFoundError("missing dependency", name=module))
    desktop.start()
    assert "-m pip install" in caplog.text and "Pillow" in caplog.text
    assert all(record.exc_info is None for record in caplog.records)
    assert not desktop.ready.is_set() and desktop.close_main() is False
    desktop.main_window.show.assert_called_once()


def test_bridge_accepts_only_known_views_and_locales():
    desktop = controller()
    desktop.icon = Mock()
    desktop.ready.set()
    bridge = DesktopBridge(desktop)
    bridge.sync_locale("zh-CN")
    assert desktop.labels[1] == "快捷下载"
    desktop.icon.update_menu.assert_called_once()
    bridge.sync_locale("unknown")
    assert desktop.locale == "zh-CN"
    bridge.show_main("https://example.com/")
    desktop.main_window.evaluate_js.assert_not_called()

