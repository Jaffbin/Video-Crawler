"""Offline repair on temporary copies; never fetch media or overwrite complete outputs."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from grab_library import COVER_SUFFIXES, SUBTITLE_SUFFIXES

REPAIR_KEYS = ("mode", "abr", "cover", "keep_cover", "embed_subs")


def repair_options(options):
    return {key: options[key] for key in REPAIR_KEYS if key in options}


def base_stem(path):
    return re.sub(r"\.f[\w-]+$", "", path.stem)


def probe(path, executable):
    result = subprocess.run([str(executable), "-v", "error", "-protocol_whitelist", "file,pipe",
                             "-show_streams", "-show_format", "-of", "json", str(path)],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=15,
                            creationflags=0x08000000 if os.name == "nt" else 0)
    if result.returncode:
        raise ValueError("This file cannot be read. Download it again.")
    data = json.loads(result.stdout)
    streams = data.get("streams", [])
    return {"video": any(s.get("codec_type") == "video" and not s.get("disposition", {}).get("attached_pic") for s in streams),
            "audio": any(s.get("codec_type") == "audio" for s in streams),
            "cover_indexes": [s["index"] for s in streams if s.get("disposition", {}).get("attached_pic")],
            "subtitle_indexes": [s["index"] for s in streams if s.get("codec_type") == "subtitle"],
            "duration": float(data.get("format", {}).get("duration") or 0)}


def process(command, check, log):
    with subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                          text=True, encoding="utf-8", errors="replace",
                          creationflags=0x08000000 if os.name == "nt" else 0) as child:
        try:
            deadline = time.monotonic() + 1800
            while True:
                check()
                if time.monotonic() > deadline:
                    raise ValueError("Repair timed out. Your original files are unchanged.")
                try:
                    _, error = child.communicate(timeout=0.3)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if child.returncode:
                log(error[-2000:])
                raise ValueError("Repair could not finish. Your original files are unchanged. Try downloading again.")
        finally:
            if child.poll() is None:
                child.kill()
                child.communicate()


def repair(library, relative, records, options, ffmpeg, *, check, log):
    source = library.media_path(relative)
    record = records.get(relative, {})
    if record.get("complete") is not False or options.get("mode", "mp4") not in ("mp4", "mp3"):
        raise ValueError("Only unfinished video or audio files can be repaired.")
    base = base_stem(source)
    candidates = []
    for name, item in records.items():
        if not isinstance(item, dict) or item.get("complete") is not False or item.get("source_url") != record.get("source_url"):
            continue
        if not isinstance(name, str) or (library.root() / name).parent != source.parent or base_stem(Path(name)) != base:
            continue
        try:
            path = library.media_path(name)
        except FileNotFoundError:
            continue
        if path.parent == source.parent and base_stem(path) == base:
            candidates.append(path)
    if source not in candidates:
        raise ValueError("The original files are missing. Download this item again.")
    probe_exe = Path(ffmpeg).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
    details = {path: probe(path, probe_exe) for path in candidates}
    mode = options.get("mode", "mp4")
    whole = [path for path in candidates if details[path]["audio"] and (mode == "mp3" or details[path]["video"])]
    if whole:
        inputs = [source if source in whole else whole[0]]
    else:
        videos = [path for path in candidates if details[path]["video"]]
        audios = [path for path in candidates if details[path]["audio"]]
        if mode != "mp4" or len(videos) != 1 or len(audios) != 1:
            raise ValueError("Some video or audio files are missing or ambiguous. Download this item again.")
        inputs = [videos[0], audios[0]]
        durations = [details[path]["duration"] for path in inputs]
        if min(durations) <= 0 or max(durations) - min(durations) > max(2, max(durations) * 0.1):
            raise ValueError("The video and audio lengths do not match. Download this item again.")
    target = source.with_name(base + "." + mode)
    target_relative = target.relative_to(library.root()).as_posix()
    if target.exists() and (target not in inputs or records.get(target_relative, {}).get("complete") is not False):
        raise FileExistsError("A file already exists at the repaired location. Rename it before repairing.")
    attachments = []
    for path in source.parent.iterdir():
        if path.is_symlink() or not path.is_file():
            continue
        if path.suffix.lower() in COVER_SUFFIXES and path.stem in (base, source.stem):
            if library.is_attachment(path, records):
                attachments.append(path)
        elif path.suffix.lower() in SUBTITLE_SUFFIXES and (path.stem == base or re.fullmatch(re.escape(base) + r"\.[\w.-]+", path.stem)):
            attachments.append(path)
    covers = [path for path in attachments if path.suffix.lower() in COVER_SUFFIXES]
    subtitles = [path for path in attachments if path.suffix.lower() in SUBTITLE_SUFFIXES]
    existing_cover = details[inputs[0]].get("cover_indexes", [])
    existing_subtitles = details[inputs[0]].get("subtitle_indexes", [])
    if options.get("cover") and not covers and not existing_cover:
        raise ValueError("The cover file is missing. Download this item again to include its cover.")
    if options.get("embed_subs") and not subtitles and not existing_subtitles:
        raise ValueError("The subtitle file is missing. Download this item again to include subtitles.")
    originals = [*inputs, *attachments]
    signatures = {path: (path.stat().st_size, path.stat().st_mtime_ns) for path in originals}
    with tempfile.TemporaryDirectory(prefix=".repair-", dir=library.root()) as temporary:
        stage = Path(temporary)
        staged = {}
        for i, path in enumerate(originals):
            check()
            staged[path] = stage / (str(i) + path.suffix)
            shutil.copy2(path, staged[path])
        output = stage / ("repaired." + mode)
        command = [str(ffmpeg), "-nostdin", "-hide_banner", "-loglevel", "error", "-y"]
        for path in inputs:
            command += ["-protocol_whitelist", "file,pipe", "-i", str(staged[path])]
        command += ["-map", "0:v:0", "-map", f"{len(inputs) - 1}:a:0"] if mode == "mp4" else ["-map", "0:a:0"]
        # Input options must precede output options.
        maps = command[-4:] if mode == "mp4" else command[-2:]
        command = command[:-len(maps)]
        extras = []
        embed_cover = bool(options.get("cover") and covers)
        embed_subtitles = bool(options.get("embed_subs") and subtitles)
        if embed_cover:
            command += ["-protocol_whitelist", "file,pipe", "-i", str(staged[covers[0]])]
            extras += ["-map", f"{len(inputs)}:v:0"]
        elif existing_cover:
            extras += ["-map", f"0:{existing_cover[0]}"]
        if embed_subtitles:
            for i, path in enumerate(subtitles):
                command += ["-protocol_whitelist", "file,pipe", "-i", str(staged[path])]
                extras += ["-map", f"{len(inputs) + embed_cover + i}:s:0"]
        elif mode == "mp4":
            for index in existing_subtitles:
                extras += ["-map", f"0:{index}"]
        command += maps + extras
        if mode == "mp4":
            command += ["-c", "copy", "-movflags", "+faststart"]
            if embed_subtitles or existing_subtitles:
                command += ["-c:s", "mov_text"]
        else:
            abr = options.get("abr", 192)
            abr = abr if abr in (96, 128, 192, 256, 320) else 192
            command += ["-c:a", "libmp3lame", "-b:a", f"{abr}k", "-id3v2_version", "3"]
            if existing_cover and not embed_cover:
                command += ["-c:v", "copy"]
        if embed_cover:
            index = 1 if mode == "mp4" else 0
            command += [f"-c:v:{index}", "mjpeg", f"-disposition:v:{index}", "attached_pic"]
        command += ["-metadata", "title=" + str(record.get("title") or base)[:300], str(output)]
        process(command, check, log)
        verified = probe(output, probe_exe)
        if not verified["audio"] or (mode == "mp4" and not verified["video"]):
            raise ValueError("The repaired file is incomplete. Your originals are unchanged.")
        if (options.get("cover") and not verified["cover_indexes"]) or (options.get("embed_subs") and not verified["subtitle_indexes"]):
            raise ValueError("The cover or subtitles could not be included. Your original files are unchanged.")
        check()
        with library.lock:
            for path, signature in signatures.items():
                path.resolve().relative_to(library.root().resolve())
                if path.is_symlink() or not path.is_file():
                    raise ValueError("A file changed during repair. Please try again.")
                if (path.stat().st_size, path.stat().st_mtime_ns) != signature:
                    raise ValueError("A file changed during repair. Please try again.")
            data = library.load()
            if data["files"].get(target_relative, {}).get("complete") is True:
                raise FileExistsError("This file was already repaired. Refresh Library.")
            if target.exists() and target not in inputs:
                raise FileExistsError("A file already exists at the repaired location")
            backup = stage / "original-backup"
            replaced = target.exists()
            if replaced:
                os.replace(target, backup)
            try:
                os.replace(output, target)
                # Classification may change while ffmpeg processes the temporary copy.
                current = data["files"].get(relative, {})
                classification = {key: current[key] for key in ("favorite", "collections", "tags", "note", "playback") if key in current}
                data["files"][target_relative] = {**record, **classification, "complete": True,
                                                  "repair_options": repair_options(options)}
                library.store.save(data)
            except BaseException:
                if target.exists():
                    target.unlink()
                if replaced:
                    os.replace(backup, target)
                raise
            for path in inputs:
                if path != target:
                    try:
                        # The completed output now owns same-stem covers/subtitles.
                        library.trash(path.relative_to(library.root()).as_posix(), complete=False, include_companions=False)
                    except (OSError, ValueError) as error:
                        log(f"Repair succeeded, but an original remains in Library: {error}")
        return target_relative
