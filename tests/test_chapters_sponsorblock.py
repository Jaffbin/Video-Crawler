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


# ── Clips ──
@pytest.mark.parametrize("value, expected", [
    ("1:20-3:45", (80.0, 225.0)),
    ("01:02:03-01:02:13.5", (3723.0, 3733.5)),
    ("80-225", (80.0, 225.0)),
    ("1:20-", (80.0, float("inf"))),
    ("-0:30", (0.0, 30.0)),
    ("", None),
    (None, None),
])
def test_clip_ranges_are_parsed(value, expected):
    assert grab.parse_section(value) == expected


@pytest.mark.parametrize("value", ["3:45-1:20", "1:20", "1:20-2:00-3:00", "a-b", "1:2:3:4-5", "1:20-1:20",
                                   "25:00:00-26:00:00", 80])
def test_bad_clip_ranges_are_rejected(value):
    with pytest.raises(ValueError):
        grab.parse_section(value)


def test_clip_labels_are_safe_for_filenames():
    assert grab.section_label((80.0, 225.0)) == "1m20s-3m45s"
    assert grab.section_label((3723.0, float("inf"))) == "1h2m3s-end"
    assert grab.section_label((5.9, 9.0)) == "5s-9s"


def test_a_clip_gets_its_own_name_exact_cuts_and_no_skip_list(tmp_path):
    args = args_for(tmp_path, mode="mp4", section="1:20-3:45", archive=True)
    assert args.section == (80.0, 225.0) and args.archive is None
    opts = grab.build_opts(args)
    assert opts["outtmpl"].endswith("[%(id)s] [1m20s-3m45s].%(ext)s")
    assert opts["force_keyframes_at_cuts"] is True and opts["download_ranges"] is not None
    assert "section" not in grab.build_opts(args_for(tmp_path, mode="cover", section="1:20-3:45"))
    assert args_for(tmp_path, mode="mp4", section="garbage").section is None
    assert webui.download_profile(args)["section"] == "1m20s-3m45s"


@pytest.fixture
def range_site(tmp_path):
    """Serves files with HTTP Range support, like real sites; ffmpeg seeks with it to cut a clip."""
    import http.server
    import threading

    site = tmp_path / "site"
    site.mkdir()

    class Handler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(site), **kwargs)

        def log_message(self, *args):
            pass

        def do_GET(self):
            path = site / self.path.lstrip("/")
            data = path.read_bytes()
            ranged = self.headers.get("Range", "").replace("bytes=", "")
            start, end = 0, len(data) - 1
            if ranged:
                first, _, last = ranged.partition("-")
                start = int(first or 0)
                end = int(last) if last else end
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{len(data)}")
            else:
                self.send_response(200)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            self.wfile.write(data[start:end + 1])

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield site, f"http://127.0.0.1:{server.server_port}"
    server.shutdown()
    server.server_close()


@pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg is not installed")
def test_real_run_saves_only_the_requested_part(tmp_path, range_site):
    site, base = range_site
    subprocess.run([str(FFMPEG_EXE), "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=25",
                    "-f", "lavfi", "-i", "sine=frequency=440", "-t", "6", "-g", "25", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", "-movflags", "+faststart",
                    str(site / "six.mp4")], check=True)
    out = tmp_path / "dl"
    opts = grab.build_opts(args_for(out, mode="mp4", section="0:01.5-0:04"))
    opts.update(quiet=True, noprogress=True)
    info = {"id": "abc123", "title": "Demo", "extractor": "generic", "extractor_key": "Generic",
            "webpage_url": f"{base}/six.mp4", "duration": 6.0,
            "url": f"{base}/six.mp4", "ext": "mp4", "protocol": "http"}
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.process_ie_result(info, download=True)
    saved = out / "Demo [abc123] [1s-4s].mp4"
    assert saved.is_file() and duration(saved) == pytest.approx(2.5, abs=0.4)


def test_the_job_route_rejects_a_bad_range_and_drops_the_skip_list(tmp_path, monkeypatch):
    import threading
    import json
    import urllib.request
    import urllib.error

    root = (tmp_path / "dl").resolve()
    root.mkdir()
    monkeypatch.setattr(webui, "ROOT", root)
    monkeypatch.setattr(webui, "CONFIG_DIR", tmp_path / "cfg")
    webui.JOB_MANAGER.reset()
    srv = webui.Server(("127.0.0.1", 0), webui.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"

    def post(body):
        request = urllib.request.Request(base + "/api/jobs", data=json.dumps(body).encode(),
                                         headers={"Content-Type": "application/json", "X-Token": webui.TOKEN})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    try:
        status, body = post({"urls": ["https://example.com/v"], "options": {"section": "3:00-1:00"}})
        assert status == 400 and "after its start" in body["error"]
        status, body = post({"urls": ["https://example.com/v"], "options": {"section": "1:00-2:00", "archive": True}})
        assert status == 200 and webui.JOB_MANAGER.get(body["ids"][0]).options["archive"] is False
    finally:
        srv.shutdown()
        srv.server_close()
        webui.JOB_MANAGER.reset()
