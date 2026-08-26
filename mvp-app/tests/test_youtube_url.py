import pytest

from youtube_url import extract_youtube_id, is_youtube_url

VALID_ID = "dQw4w9WgXcQ"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        (f"https://www.youtube.com/watch?v={VALID_ID}", VALID_ID),
        (f"https://youtube.com/watch?list=PL1&v={VALID_ID}", VALID_ID),
        (f"http://youtube.com/watch?v={VALID_ID}&t=30s", VALID_ID),
        (f"https://youtu.be/{VALID_ID}?t=5", VALID_ID),
        (f"https://www.youtube.com/embed/{VALID_ID}", VALID_ID),
        (f"https://www.youtube.com/shorts/{VALID_ID}", VALID_ID),
    ],
)
def test_extracts_id_from_supported_forms(url, expected):
    assert extract_youtube_id(url) == expected
    assert is_youtube_url(url)


@pytest.mark.parametrize(
    "url",
    [
        None,
        "",
        "   ",
        "L26_V306",
        "https://vimeo.com/123456789",
        f"https://www.youtube.com/watch?v=short-{VALID_ID[:9]}",
        "https://www.youtube.com/watch?list=PL1",
        f"youtube.com/watch?v={VALID_ID}",
        f"https://youtube.com/live/{VALID_ID}",
    ],
)
def test_rejects_invalid_or_unsupported_urls(url):
    assert extract_youtube_id(url) is None
    assert not is_youtube_url(url)
