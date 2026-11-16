"""Chapters and SponsorBlock: option parsing, the yt-dlp postprocessor chain, and a real ffmpeg run.

The real run feeds yt-dlp a local clip with chapters, posing as YouTube, and replaces only the
SponsorBlock network lookup, so no YouTube or SponsorBlock server is contacted.
"""
import subprocess
from pathlib import Path

import pytest
import yt_dlp
from yt_dlp.postprocessor.sponsorblock import SponsorBlockPP

import grab
from conftest import FFMPEG_EXE, HAVE_FFMPEG
from grab_models import Job
import webui


def args_for(tmp_path, **options):
    original = webui.ROOT
    webui.ROOT = tmp_path
    try:
        return webui.make_args(options)
    finally:
        webui.ROOT = original


def keys(opts):
    return [pp["key"] for pp in opts["postprocessors"]]


# ── Options ──
def test_options_are_parsed_strictly_and_only_for_video_or_audio(tmp_path):
    assert args_for(tmp_path, mode="mp4", sponsorblock="remove", split_chapters=True).sponsorblock == "remove"
    assert args_for(tmp_path, mode="mp3", sponsorblock="mark").sponsorblock == "mark"
    assert args_for(tmp_path, mode="mp4", sponsorblock="everything").sponsorblock == ""
    assert args_for(tmp_path, mode="mp4", split_chapters="yes").split_chapters is False
    cover = args_for(tmp_path, mode="cover", sponsorblock="remove", split_chapters=True)
    assert cover.sponsorblock == "" and cover.split_chapters is False


def test_off_by_default_leaves_the_chain_unchanged(tmp_path):
    opts = grab.build_opts(args_for(tmp_path, mode="mp4"))
    assert "SponsorBlock" not in keys(opts) and "FFmpegSplitChapters" not in keys(opts)
    assert isinstance(opts["outtmpl"], str)


def test_removal_runs_in_the_order_yt_dlp_requires(tmp_path):
    opts = grab.build_opts(args_for(tmp_path, mode="mp4", sponsorblock="remove", split_chapters=True))
    order = keys(opts)
    assert order[0] == "SponsorBlock"
    assert order.index("FFmpegVideoRemuxer") < order.index("ModifyChapters") < order.index("FFmpegMetadata")
    assert order[-1] == "FFmpegSplitChapters"
    sponsor = opts["postprocessors"][0]
    modify = next(pp for pp in opts["postprocessors"] if pp["key"] == "ModifyChapters")
    assert sponsor["categories"] == set(grab.SPONSORBLOCK_REMOVE) == modify["remove_sponsor_segments"]
    assert "intro" not in modify["remove_sponsor_segments"]  # intros can carry real content
    assert opts["outtmpl"]["chapter"].endswith(" chapters/%(section_number)02d. %(section_title).80B.%(ext)s")
    yt_dlp.YoutubeDL(opts).close()  # yt-dlp accepts the chain


def test_marking_only_adds_chapters(tmp_path):
    opts = grab.build_opts(args_for(tmp_path, mode="mp3", sponsorblock="mark"))
    modify = next(pp for pp in opts["postprocessors"] if pp["key"] == "ModifyChapters")
    assert modify["remove_sponsor_segments"] == set() and "intro" in opts["postprocessors"][0]["categories"]


def test_settings_are_remembered_only_when_used(tmp_path):
    plain = webui.download_profile(args_for(tmp_path, mode="mp4"))
    assert "sponsorblock" not in plain and "split_chapters" not in plain
    used = webui.download_profile(args_for(tmp_path, mode="mp4", sponsorblock="remove", split_chapters=True))
    assert used["sponsorblock"] == "remove" and used["split_chapters"] is True


def test_backups_keep_the_new_preferences():
    import grab_backup

    assert grab_backup.output_options({"sponsorblock": "remove", "split_chapters": True}) == {
        "sponsorblock": "remove", "split_chapters": True}
    with pytest.raises(ValueError):
        grab_backup.output_options({"sponsorblock": "all"})


def test_chapter_files_are_recorded_with_their_source(tmp_path):
    full = tmp_path / "Talk [abc].mp4"
    full.write_bytes(b"x")
    folder = grab.chapter_folder(full)
    folder.mkdir()
    for name in ("01. Intro.mp4", "02. Main.mp4", "notes.txt"):
        (folder / name).write_bytes(b"x")
    job = Job("https://www.youtube.com/watch?v=abc", {"mode": "mp4"})
    job.title = "Talk"
    job.seen_paths = [str(full)]
    job.media_metadata = {str(full): {"source_url": job.url, "title": "Talk", "download_profile": {"mode": "mp4"}}}
    webui.track_chapter_files(job)
    assert job.seen_paths == [str(full), str(folder / "01. Intro.mp4"), str(folder / "02. Main.mp4")]
    assert job.media_metadata[str(folder / "02. Main.mp4")]["title"] == "Talk - 02. Main"
    assert job.media_metadata[str(folder / "01. Intro.mp4")]["source_url"] == job.url


# ── Real pipeline ──
def duration(path):
    probe = Path(FFMPEG_EXE).with_name("ffprobe" + Path(FFMPEG_EXE).suffix)
    result = subprocess.run([str(probe), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                             str(path)], capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg is not installed")
def test_real_run_removes_a_sponsor_and_splits_chapters(tmp_path, media_site, monkeypatch):
    clip = media_site["root"] / "six.mp4"
    if not clip.exists():
        subprocess.run([str(FFMPEG_EXE), "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=25",
                        "-f", "lavfi", "-i", "sine=frequency=440", "-t", "6", "-g", "25", "-c:v", "libx264",
                        "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(clip)], check=True)
    monkeypatch.setattr(SponsorBlockPP, "_get_sponsor_segments",
                        lambda self, video_id, service: [{"segment": [2.0, 3.0], "category": "sponsor",
                                                          "actionType": "skip", "videoDuration": 6.0}])
    out = tmp_path / "dl"
    args = args_for(out, mode="mp4", sponsorblock="remove", split_chapters=True)
    opts = grab.build_opts(args)
    opts.update(quiet=True, noprogress=True)
    info = {"id": "abc123", "title": "Demo", "extractor": "youtube", "extractor_key": "Youtube",
            "webpage_url": "https://www.youtube.com/watch?v=abc123", "duration": 6.0,
            "url": f"{media_site['base']}/six.mp4", "ext": "mp4", "protocol": "http",
            "chapters": [{"start_time": 0, "end_time": 4, "title": "Part one"},
                         {"start_time": 4, "end_time": 6, "title": "Part two"}]}
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.process_ie_result(info, download=True)
    full = out / "Demo [abc123].mp4"
    assert full.is_file()
    assert duration(full) == pytest.approx(5.0, abs=0.6)  # the 1 s sponsor is gone, cut at keyframes
    parts = sorted(p.name for p in grab.chapter_folder(full).iterdir())
    assert parts == ["01. Part one.mp4", "02. Part two.mp4"]
