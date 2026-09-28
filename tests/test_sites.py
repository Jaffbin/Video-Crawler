import grab_sites


def test_hanime1_download_page_accepts_only_the_expected_watch_url():
    assert grab_sites.hanime1_download_page("https://hanime1.me/watch?v=93338") == (
        "https://hanime1.me/download?v=93338"
    )
    assert grab_sites.hanime1_download_page("https://www.hanime1.me/watch/?v=a_B-9") == (
        "https://www.hanime1.me/download?v=a_B-9"
    )
    assert grab_sites.hanime1_download_page("https://evil.example/watch?v=93338") is None
    assert grab_sites.hanime1_download_page("https://hanime1.me/watch?v=../../secret") is None
    assert grab_sites.hanime1_download_page("https://hanime1.me/download?v=93338") is None


def test_parse_hanime1_download_table_deduplicates_and_orders_quality():
    document = """
    <a href="https://outside.example/ad.mp4">not a video option</a>
    <table class="table download-table striped">
      <tr><td><a href="//cdn.example/v-1080p.mp4" download="Episode 01.mp4">1080P</a></td></tr>
      <tr><td><a href="https://cdn.example/v-720p.mp4" download="Episode 01.mp4">720p</a></td></tr>
      <tr><td><a href="https://cdn.example/v-720p.mp4">duplicate</a></td></tr>
      <tr><td><a href="/media/source.mp4" download="Episode 01.mp4">Source</a></td></tr>
    </table>
    """
    page = "https://hanime1.me/download?v=abc"
    best = grab_sites.parse_hanime1_downloads(document, page)
    assert [item.height for item in best] == [None, 1080, 720]
    assert best[0].title == "Episode 01"
    assert best[0].url == "https://hanime1.me/media/source.mp4"

    capped = grab_sites.parse_hanime1_downloads(document, page, "720")
    assert [item.height for item in capped] == [720, None, 1080]


def test_parse_hanime1_downloads_ignores_links_outside_the_download_table():
    assert grab_sites.parse_hanime1_downloads(
        '<a href="https://cdn.example/video.mp4">ad</a>', "https://hanime1.me/download?v=x"
    ) == []
