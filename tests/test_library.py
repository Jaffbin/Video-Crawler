import pytest

from grab_library import MediaLibrary


@pytest.fixture
def library(tmp_path):
    return MediaLibrary(lambda: tmp_path, {".mp4", ".mp3"})


def media(library, relative="video.mp4"):
    path = library.root() / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"media content")
    return path


def test_organization_survives_remember_rename_recovery_and_restart(library):
    source = media(library)
    subtitle = source.with_suffix(".en.srt")
    subtitle.write_bytes(b"subtitles")
    first = library.change_collection("create", "学习")
    second = library.change_collection("create", "Music")
    library.organize([source.name], favorite=True, collection_id=first)
    library.organize([source.name], collection_id=second)
    library.remember({source.name: {"source_url": "https://example.com/v", "complete": True}})
    relative = library.rename(source.name, "renamed.mp4")
    recovery_id = library.trash(relative)
    restored = MediaLibrary(library.root, library.suffixes)
    assert restored.restore(recovery_id) == relative
    record = restored.load()["files"][relative]
    assert record["favorite"] is True and record["collections"] == [first, second]
    assert record["complete"] is True and record["source_url"] == "https://example.com/v"
    assert (library.root() / "renamed.mp4").read_bytes() == b"media content"
    assert (library.root() / "renamed.en.srt").read_bytes() == b"subtitles"


def test_collection_delete_keeps_files_favorites_and_cleans_recovery(library):
    first, second = media(library), media(library, "second.mp3")
    collection_id = library.change_collection("create", "Music")
    library.organize([first.name, second.name], favorite=True, collection_id=collection_id)
    recovery_id = library.trash(second.name)
    library.change_collection("rename", "Listen later", collection_id)
    assert library.collections() == [{"id": collection_id, "name": "Listen later"}]
    library.change_collection("delete", collection_id=collection_id)
    library.restore(recovery_id)
    assert first.is_file() and second.is_file() and library.collections() == []
    for record in library.load()["files"].values():
        assert record["favorite"] is True and record["collections"] == []


def test_organization_validates_paths_and_reports_partial_failure(library, tmp_path):
    source = media(library)
    outside = tmp_path.parent / "outside-organization.mp4"
    result = library.organize([source.name, source.name, "../outside-organization.mp4", "missing.mp4"], favorite=True)
    assert result["processed"] == [source.name]
    assert [item["item"] for item in result["failed"]] == ["../outside-organization.mp4", "missing.mp4"]
    assert not outside.exists()
    assert library.load()["files"][source.name]["favorite"] is True


@pytest.mark.parametrize("name", ["", "  ", "x" * 81, "bad\nname", None, []])
def test_collection_name_validation(library, name):
    with pytest.raises(ValueError):
        library.change_collection("create", name)
    assert library.collections() == []


def test_collection_names_are_unique_and_membership_changes_are_idempotent(library):
    source = media(library)
    key = library.change_collection("create", "Music")
    with pytest.raises(ValueError, match="already exists"):
        library.change_collection("create", " music ")
    library.organize([source.name], collection_id=key)
    library.organize([source.name], collection_id=key)
    assert library.load()["files"][source.name]["collections"] == [key]
    library.organize([source.name], collection_id=key, remove=True)
    assert library.load()["files"][source.name]["collections"] == []
    with pytest.raises(ValueError):
        library.organize([source.name], collection_id=[])


def test_organization_save_failure_keeps_persisted_metadata(library, monkeypatch):
    source = media(library)
    library.organize([source.name], favorite=False)
    before = library.store.path().read_bytes()
    monkeypatch.setattr(type(library.store), "save", lambda self, data: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        library.organize([source.name], favorite=True)
    assert library.store.path().read_bytes() == before


def test_purge_deletes_only_recovery_group(library):
    source = media(library)
    subtitle = library.root() / "video.en.srt"
    cover = library.root() / "video.jpg"
    subtitle.write_bytes(b"subtitle")
    cover.write_bytes(b"cover")
    recovery_id = library.trash(source.name)
    unrelated = media(library, "other.mp4")
    library.purge(recovery_id)
    assert list(library.trash_directory().iterdir()) == []
    assert library.trash_items() == []
    assert unrelated.read_bytes() == b"media content"
    with pytest.raises(FileNotFoundError):
        library.restore(recovery_id)


def test_purge_validates_entire_group_before_deleting(library):
    recovery_id = library.trash(media(library).name)
    data = library.load()
    outside = media(library, "other.mp4")
    data["trash"][recovery_id]["attachments"] = [{"path": "video.srt", "stored": "../other.mp4"}]
    library.store.save(data)
    with pytest.raises(ValueError):
        library.purge(recovery_id)
    assert library.trash_items() and outside.is_file()


def test_purge_can_retry_partial_failure(library, monkeypatch):
    subtitle = library.root() / "video.en.srt"
    subtitle.write_bytes(b"subtitle")
    recovery_id = library.trash(media(library).name)
    original = type(subtitle).unlink

    def fail_main(path, *args, **kwargs):
        if path.name == recovery_id + ".mp4":
            raise PermissionError("File locked")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(type(subtitle), "unlink", fail_main)
        with pytest.raises(PermissionError):
            library.purge(recovery_id)
    assert library.trash_items()
    library.purge(recovery_id)
    assert library.trash_items() == []


def test_purge_record_stays_visible_if_metadata_save_fails(library, monkeypatch):
    recovery_id = library.trash(media(library).name)
    with monkeypatch.context() as context:
        context.setattr(type(library.store), "save", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
        with pytest.raises(OSError):
            library.purge(recovery_id)
    assert library.trash_items()[0]["id"] == recovery_id
    library.purge(recovery_id)
    assert library.trash_items() == []


@pytest.mark.parametrize("recovery_id", ["../video.mp4", "unknown", "0" * 32])
def test_purge_rejects_unknown_or_invalid_id(library, recovery_id):
    source = media(library)
    with pytest.raises(FileNotFoundError):
        library.purge(recovery_id)
    assert source.is_file()


def test_rename_keeps_source_and_never_overwrites(library):
    source = media(library)
    library.remember({"video.mp4": {"source_url": "https://example.com/video", "title": "Video"}})
    assert library.rename("video.mp4", "renamed.mp4") == "renamed.mp4"
    assert not source.exists()
    assert library.load()["files"]["renamed.mp4"]["source_url"] == "https://example.com/video"
    target = media(library, "occupied.mp4")
    with pytest.raises(FileExistsError):
        library.rename("renamed.mp4", "occupied.mp4")
    assert target.read_bytes() == b"media content"
    assert (library.root() / "renamed.mp4").is_file()


@pytest.mark.parametrize("relative,name", [
    ("../outside.mp4", "safe.mp4"), ("video.mp4", "../unsafe.mp4"),
    ("video.mp4", "CON.mp4"), ("video.mp4", "changed.exe"), ("video.mp4", "bad?.mp4"),
])
def test_library_rejects_escape_and_invalid_names(library, relative, name):
    source = media(library)
    with pytest.raises((ValueError, FileNotFoundError)):
        library.rename(relative, name)
    assert source.is_file()


def test_recovery_preserves_bytes_metadata_and_reports_restore_collision(library):
    source = media(library, "playlist/video.mp4")
    library.remember({"playlist/video.mp4": {"source_url": "https://example.com/video"}})
    recovery_id = library.trash("playlist/video.mp4")
    assert not source.exists() and library.trash_items()[0]["path"] == "playlist/video.mp4"
    source.write_bytes(b"new download")
    with pytest.raises(FileExistsError):
        library.restore(recovery_id)
    assert source.read_bytes() == b"new download"
    source.unlink()
    assert library.restore(recovery_id) == "playlist/video.mp4"
    assert source.read_bytes() == b"media content" and library.trash_items() == []
    assert library.load()["files"]["playlist/video.mp4"]["source_url"] == "https://example.com/video"


def test_failed_metadata_save_leaves_original_file(library, monkeypatch):
    source = media(library)
    monkeypatch.setattr(type(library.store), "save", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        library.rename("video.mp4", "new.mp4")
    assert source.is_file() and not (library.root() / "new.mp4").exists()
    with pytest.raises(OSError):
        library.trash("video.mp4")
    assert source.is_file()


def test_malformed_recovery_records_are_not_exposed(library):
    library.store.save({"trash": {"a" * 32: {"stored": "../../outside.mp4"}, "bad": {"path": "x"}}})
    assert library.trash_items() == []
    with pytest.raises(ValueError):
        library.restore("a" * 32)


@pytest.mark.parametrize("extension", ["jpg", "gif", "avif"])
def test_subtitles_and_cover_follow_rename_trash_and_restore(library, extension):
    media(library)
    companions = [media(library, name) for name in ("video.zh-Hans.srt", "video.en.vtt", f"video.{extension}")]
    unrelated = media(library, "video-other.srt")
    assert library.rename("video.mp4", "renamed.mp4") == "renamed.mp4"
    assert all(not path.exists() for path in companions)
    names = ("renamed.mp4", "renamed.zh-Hans.srt", "renamed.en.vtt", f"renamed.{extension}")
    assert all((library.root() / name).is_file() for name in names)
    recovery_id = library.trash("renamed.mp4")
    assert all(not (library.root() / name).exists() for name in names)
    assert len(library.load()["trash"][recovery_id]["attachments"]) == 3
    assert library.restore(recovery_id) == "renamed.mp4"
    assert all((library.root() / name).read_bytes() == b"media content" for name in names)
    assert unrelated.exists()


def test_companion_collision_blocks_the_entire_group(library):
    source = media(library)
    cover = media(library, "video.jpg")
    occupied = media(library, "new.jpg")
    with pytest.raises(FileExistsError):
        library.rename("video.mp4", "new.mp4")
    assert source.exists() and cover.exists() and occupied.exists()
    assert not (library.root() / "new.mp4").exists()
    recovery_id = library.trash("video.mp4")
    media(library, "video.jpg")
    with pytest.raises(FileExistsError):
        library.restore(recovery_id)
    assert not source.exists() and len(library.trash_items()) == 1


def test_group_move_rolls_back_on_second_move_failure(library, monkeypatch):
    source = media(library)
    cover = media(library, "video.jpg")
    original = library.move_without_overwrite
    calls = []

    def move(src, dst):
        calls.append(src)
        if len(calls) == 2:
            raise OSError("file is locked")
        original(src, dst)

    monkeypatch.setattr(library, "move_without_overwrite", move)
    with pytest.raises(OSError):
        library.rename("video.mp4", "new.mp4")
    assert source.exists() and cover.exists()
    assert not (library.root() / "new.mp4").exists()
    calls.clear()
    with pytest.raises(OSError):
        library.trash("video.mp4")
    assert source.exists() and cover.exists() and library.load()["trash"] == {}


def test_metadata_save_failure_rolls_back_entire_rename_and_restore(library, monkeypatch):
    source = media(library)
    cover = media(library, "video.jpg")
    recovery_id = library.trash("video.mp4")
    original_save = type(library.store).save
    monkeypatch.setattr(type(library.store), "save", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        library.restore(recovery_id)
    assert not source.exists() and not cover.exists() and len(library.trash_items()) == 1
    monkeypatch.setattr(type(library.store), "save", original_save)
    library.restore(recovery_id)
    monkeypatch.setattr(type(library.store), "save", lambda *args: (_ for _ in ()).throw(OSError("disk full")))
    with pytest.raises(OSError):
        library.rename("video.mp4", "new.mp4")
    assert source.exists() and cover.exists() and not (library.root() / "new.jpg").exists()


def test_shared_companions_are_not_silently_taken_from_other_media(library):
    source = media(library)
    media(library, "video.mp3")
    cover = media(library, "video.jpg")
    with pytest.raises(ValueError, match="shared"):
        library.trash("video.mp4")
    assert source.exists() and cover.exists()


def test_recovery_attachment_records_cannot_escape_root(library, tmp_path):
    media(library)
    media(library, "video.jpg")
    recovery_id = library.trash("video.mp4")
    data = library.load()
    data["trash"][recovery_id]["attachments"][0]["path"] = "../outside.jpg"
    library.store.save(data)
    with pytest.raises(ValueError):
        library.restore(recovery_id)
    assert not (library.root() / "video.mp4").exists()


def test_independent_image_is_not_moved_with_same_named_video(tmp_path):
    from grab_images import IMAGE_SUFFIXES
    library = MediaLibrary(lambda: tmp_path, {".mp4", ".mp3"} | IMAGE_SUFFIXES)
    video = media(library)
    picture = media(library, "video.jpg")
    assert library.is_attachment(picture, library.load()["files"])
    library.remember({"video.jpg": {"role": "image", "source_url": "https://example.com/picture"}})
    assert not library.is_attachment(picture, library.load()["files"])
    library.rename("video.mp4", "new.mp4")
    assert picture.exists() and not video.exists()
    recovery_id = library.trash("video.jpg")
    assert not picture.exists()
    # Another same-named video must not prevent restoring an explicitly independent image.
    media(library)
    library.restore(recovery_id)
    assert picture.exists() and library.load()["files"]["video.jpg"]["role"] == "image"


def test_implicit_cover_cannot_be_managed_as_independent_image(tmp_path):
    from grab_images import IMAGE_SUFFIXES
    library = MediaLibrary(lambda: tmp_path, {".mp4", ".mp3"} | IMAGE_SUFFIXES)
    video = media(library)
    cover = media(library, "video.jpg")
    with pytest.raises(ValueError, match="together"):
        library.trash("video.jpg")
    library.rename("video.mp4", "new.mp4")
    assert not video.exists() and not cover.exists() and (tmp_path / "new.jpg").exists()
