import base64
import http.server
import threading
import json
import urllib.request
from pathlib import Path

import pytest
import yt_dlp
from yt_dlp.extractor.common import InfoExtractor
from yt_dlp.utils import DownloadCancelled

import grab
import grab_images
import webui
from grab_download import tracking_downloader
from grab_models import Job

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jf1sAAAAASUVORK5CYII=')


@pytest.fixture
def image_site():
    requests = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append((self.path, dict(self.headers)))
            if self.path == '/temporary' and sum(path == '/temporary' for path, _ in requests) == 1:
                self.send_response(503)
                self.end_headers()
                return
            body, mime, size = PNG, 'image/png', len(PNG)
            if self.path == '/page':
                body, mime = b'<html>Sign in</html>', 'text/html'
                size = len(body)
            elif self.path == '/fake.jpg':
                body, mime = b'<html>Not an image</html>', 'image/jpeg'
                size = len(body)
            elif self.path == '/huge':
                size = grab_images.IMAGE_MAX_BYTES + 1
            elif self.path in ('/large', '/unknown-size'):
                body = PNG + bytes(150000)
                size = len(body)
            elif self.path == '/image?token=private':
                mime = 'application/octet-stream'
            self.send_response(200)
            self.send_header('Content-Type', mime)
            if self.path != '/unknown-size':
                self.send_header('Content-Length', str(size))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{server.server_port}', requests
    server.shutdown()
    server.server_close()


def client(**options):
    return yt_dlp.YoutubeDL({'quiet': True, 'socket_timeout': 2, **options})


def test_direct_image_preserves_bytes_sniffs_extension_and_keeps_auth_headers(image_site, tmp_path):
    base, requests = image_site
    progress = []
    with client(http_headers={'Referer': base + '/page'}) as ydl:
        path = grab_images.download_image(ydl, base + '/image?token=private', tmp_path, progress=progress.append)
    assert path.suffix == '.png' and path.parent == tmp_path / 'images'
    assert path.read_bytes() == PNG and 'private' not in path.name
    assert requests[0][1]['Referer'] == base + '/page'
    assert not list(path.parent.glob('.image-*'))


@pytest.mark.parametrize('route,message', [('/page', 'page instead'), ('/fake.jpg', 'not a supported'), ('/huge', '100 MiB')])
def test_non_images_and_oversized_responses_never_publish_files(image_site, tmp_path, route, message):
    base, _ = image_site
    with client() as ydl, pytest.raises(ValueError, match=message):
        grab_images.download_image(ydl, base + route, tmp_path)
    assert not list(tmp_path.rglob('*.png')) and not list(tmp_path.rglob('*.part'))


def test_probe_checks_image_without_writing_files(image_site, tmp_path):
    base, _ = image_site
    with client() as ydl:
        result = grab_images.probe_image(ydl, base + '/image')
    assert result['kind'] == 'image' and result['image_format'] == 'PNG'
    assert result['size']['bytes'] == len(PNG) and list(tmp_path.iterdir()) == []


def test_cookie_file_is_used_by_image_requests(image_site, tmp_path):
    base, requests = image_site
    cookiefile = tmp_path / 'cookies.txt'
    cookiefile.write_text('# Netscape HTTP Cookie File\n127.0.0.1\tFALSE\t/\tFALSE\t2147483647\tsession\tfixture-only\n')
    with client(cookiefile=str(cookiefile)) as ydl:
        grab_images.download_image(ydl, base + '/image', tmp_path)
    assert requests[0][1]['Cookie'] == 'session=fixture-only'


def test_cli_image_list_formats_does_not_download(image_site, tmp_path, capsys):
    base, _ = image_site
    args = grab.parse_args(['-m', 'image', '--list-formats', '-o', str(tmp_path), '--referer', base + '/page'])
    assert grab.process(base + '/image', args)
    assert 'Original image format: PNG' in capsys.readouterr().out
    assert not list(tmp_path.iterdir())


def test_streaming_limit_without_content_length_removes_partial_file(image_site, tmp_path, monkeypatch):
    base, _ = image_site
    monkeypatch.setattr(grab_images, 'IMAGE_MAX_BYTES', 128)
    with client() as ydl:
        assert grab_images.probe_image(ydl, base + '/unknown-size')['size']['bytes'] is None
        with pytest.raises(ValueError, match='100 MiB'):
            grab_images.download_image(ydl, base + '/unknown-size', tmp_path)
    assert not list(tmp_path.rglob('*.png')) and not list(tmp_path.rglob('*.part'))


def test_cancellation_removes_temporary_file_and_keeps_existing_image(image_site, tmp_path):
    base, _ = image_site
    destination = tmp_path / 'existing.png'
    destination.write_bytes(PNG)
    canceled = threading.Event()

    def check():
        if canceled.is_set():
            raise DownloadCancelled('Canceled')

    with client() as ydl, pytest.raises(DownloadCancelled):
        grab_images.download_image(ydl, base + '/large', tmp_path, base=tmp_path / 'existing',
                                   check=check, progress=lambda _: canceled.set())
    assert destination.read_bytes() == PNG and not list(tmp_path.glob('*.part'))


def test_transient_response_is_retried(image_site, tmp_path, monkeypatch):
    base, requests = image_site
    monkeypatch.setattr(grab_images, 'wait', lambda seconds, check: check())
    with client() as ydl:
        path = grab_images.download_image(ydl, base + '/temporary', tmp_path)
    assert path.read_bytes() == PNG
    assert [path for path, _ in requests] == ['/temporary', '/temporary']


@pytest.mark.parametrize('message', ['Certificate verify failed', 'Permission denied'])
def test_permanent_image_request_failure_is_not_retried(tmp_path, message):
    from yt_dlp.networking.exceptions import RequestError
    from types import SimpleNamespace
    requests = []

    def urlopen(request):
        requests.append(request)
        raise RequestError(message)

    with pytest.raises(RequestError):
        grab_images.download_image(SimpleNamespace(params={}, urlopen=urlopen), 'https://example.invalid/image.png', tmp_path)
    assert len(requests) == 1


@pytest.mark.parametrize('data,extension', [
    (PNG, '.png'), (b'\xff\xd8\xff\xe0' + bytes(60), '.jpg'),
    (b'GIF89a' + bytes(58), '.gif'), (b'RIFF' + bytes(4) + b'WEBP' + bytes(52), '.webp'),
    (b'\x00\x00\x00\x20ftypavif' + bytes(52), '.avif'),
])
def test_original_format_detection(data, extension):
    assert grab_images.image_extension(data) == extension


def test_cover_only_playlist_downloads_images_without_formats_or_ffmpeg(image_site, tmp_path):
    base, requests = image_site
    job = Job('https://coverfixture.invalid/list', {'mode': 'cover'})
    args = grab.parse_args(['-m', 'cover', '-o', str(tmp_path), '--subs', '--cover'])
    options = grab.build_opts(args)
    assert options['skip_download'] and options['writethumbnail']
    assert options['postprocessors'] == [] and not options.get('writesubtitles')
    downloaded = []

    class CoverIE(InfoExtractor):
        _VALID_URL = r'https://coverfixture.invalid/(?P<id>list|1|2)'

        def _real_extract(self, url):
            item = self._match_id(url)
            if item == 'list':
                return self.playlist_result([self.url_result(f'https://coverfixture.invalid/{i}', ie=CoverIE)
                                             for i in (1, 2)], 'list', 'Album')
            # No downloadable video formats are provided: covers should still work.
            return {'id': item, 'title': f'Cover {item}',
                    'thumbnails': [{'url': base + '/image'}] if item == '1' else []}

    downloader = grab_images.thumbnail_downloader(tracking_downloader(yt_dlp.YoutubeDL, job), tmp_path,
                                                   on_image=lambda path, info: downloaded.append((path, dict(info))))
    with downloader({**options, 'quiet': True}, auto_init=False) as ydl:
        ydl.add_info_extractor(CoverIE())
        assert ydl.download([job.url]) != 0  # Second entry has no cover.
    assert len(downloaded) == 1
    path, info = downloaded[0]
    assert Path(path).read_bytes() == PNG
    assert info['playlist_index'] == 1 and '/covers/' in path.replace('\\', '/')
    assert [path for path, _ in requests] == ['/image']
    assert len(job.failed_items) == 1 and job.failed_items[0]['index'] == 2


@pytest.fixture
def image_app(tmp_path, monkeypatch):
    root = tmp_path / 'downloads'
    root.mkdir()
    monkeypatch.setattr(webui, 'ROOT', root)
    monkeypatch.setattr(webui, 'CONFIG_DIR', tmp_path / 'config')
    monkeypatch.setattr(webui, 'FILES_CACHE', {'rev': None, 'ts': 0, 'data': []})
    webui.JOB_MANAGER.reset()
    webui.SUBSCRIPTION_MANAGER.reset()
    server = webui.Server(('127.0.0.1', 0), webui.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{server.server_port}'
    server.shutdown()
    server.server_close()
    webui.JOB_MANAGER.reset()
    webui.SUBSCRIPTION_MANAGER.reset()


def api(base, path, body=None):
    headers = {'X-Token': webui.TOKEN, 'Content-Type': 'application/json'}
    request = urllib.request.Request(base + path, headers=headers,
                                     data=None if body is None else json.dumps(body).encode())
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


def test_image_job_probe_library_file_serving_and_recovery(image_site, image_app):
    base, _ = image_site
    preview = api(image_app, '/api/probe', {'url': base + '/image', 'options': {'mode': 'image'}})
    assert preview['kind'] == 'image' and not list(webui.ROOT.glob('images/*'))
    result = api(image_app, '/api/jobs', {'urls': [base + '/image'], 'options': {'mode': 'image'}})
    job = webui.JOB_MANAGER.get(result['ids'][0])
    webui.run_job(job)
    assert job.status == 'done' and len(job.files) == 1
    item = api(image_app, '/api/state?rev=-1')['files'][0]
    assert item['kind'] == 'image' and item['source_url'] == base + '/image'
    request = urllib.request.Request(image_app + '/files/' + urllib.parse.quote(item['path']), headers={'X-Token': webui.TOKEN})
    with urllib.request.urlopen(request) as response:
        assert response.read() == PNG
        assert response.headers['Content-Type'] == 'image/png'
        assert response.headers['X-Content-Type-Options'] == 'nosniff'
    renamed = api(image_app, '/api/library/rename', {'path': item['path'], 'name': 'renamed.png'})['path']
    recovery = api(image_app, '/api/library/trash', {'path': renamed})['id']
    assert api(image_app, '/api/state?rev=-1')['files'] == []
    api(image_app, '/api/library/restore', {'id': recovery})
    assert api(image_app, '/api/state?rev=-1')['files'][0]['path'] == renamed


def test_scan_hides_attached_covers_and_keeps_independent_images(image_app):
    (webui.ROOT / 'video.mp4').write_bytes(b'video')
    (webui.ROOT / 'video.jpg').write_bytes(b'\xff\xd8\xff')
    (webui.ROOT / 'standalone.png').write_bytes(PNG)
    assert {item['name'] for item in webui.list_files(force=True)} == {'video.mp4', 'standalone.png'}
    webui.LIBRARY.remember({'video.jpg': {'role': 'image', 'source_url': 'https://example.com/image'}})
    assert {item['name'] for item in webui.list_files(force=True)} == {'video.mp4', 'video.jpg', 'standalone.png'}


def test_image_options_remain_valid_after_history_reload(image_app):
    for mode in ('cover', 'image'):
        job_id = webui.create_jobs([f'https://example.com/{mode}'], {'mode': mode})[0]
        assert webui.make_args(webui.JOB_MANAGER.get(job_id).options).mode == mode
    webui.JOB_MANAGER.reset()
    webui.load_history()
    assert {job.options['mode'] for job in webui.JOB_MANAGER.snapshot()} == {'cover', 'image'}
