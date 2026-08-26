import pytest

from query_parser import parse_search_query


def test_plain_text_stays_pure_semantic():
    parsed = parse_search_query("con ca vang")
    assert parsed.semantic_text == "con ca vang"
    assert not parsed.has_scope
    assert not parsed.is_exact_keyframe


@pytest.mark.parametrize("raw,expected", [("L26", "L26"), ("  L30  ", "L30")])
def test_single_collection_token(raw, expected):
    parsed = parse_search_query(raw)
    assert parsed.semantic_text == ""
    assert parsed.collections == (expected,)
    assert not parsed.is_exact_keyframe


def test_single_video_token():
    parsed = parse_search_query("L26_V306")
    assert parsed.video_ids == ("L26_V306",)
    assert parsed.collections == ()
    assert not parsed.is_exact_keyframe


@pytest.mark.parametrize(
    ("raw", "expected_no"),
    [
        ("L26_V306_049", 49),
        ("L26_V306_9", 9),
        ("L26_V306, 49", 49),
        ("L26_V306 ,49", 49),
    ],
)
def test_exact_keyframe_forms(raw, expected_no):
    parsed = parse_search_query(raw)
    assert parsed.is_exact_keyframe
    assert parsed.exact_video_id == "L26_V306"
    assert parsed.exact_keyframe_no == expected_no


def test_text_scoped_to_video_in_any_order():
    first = parse_search_query("con ca, L26_V306")
    second = parse_search_query("L26_V306, con ca")
    for parsed in (first, second):
        assert parsed.semantic_text == "con ca"
        assert parsed.video_ids == ("L26_V306",)
        assert not parsed.is_exact_keyframe


def test_text_scoped_to_collection():
    parsed = parse_search_query("con ca, L26")
    assert parsed.semantic_text == "con ca"
    assert parsed.collections == ("L26",)


def test_multiple_scope_tokens_are_kept_in_order_and_deduped():
    parsed = parse_search_query("con ca, L26_V001, L27, L26")
    assert parsed.semantic_text == "con ca"
    assert parsed.video_ids == ("L26_V001",)
    assert parsed.collections == ("L27", "L26")


def test_empty_input_yields_empty_parse():
    for raw in ["", "   ", ",,,,"]:
        parsed = parse_search_query(raw)
        assert parsed.semantic_text == ""
        assert not parsed.has_scope


def test_scope_label_and_description():
    assert parse_search_query("L26_V306").scope_label == "video L26_V306"
    combined = parse_search_query("L26, L27_V001")
    assert combined.scope_label == "video L27_V001 + collection L26"
    exact = parse_search_query("L26_V306, 7")
    assert exact.describe() == "đúng keyframe L26_V306_007"


def test_two_exact_numbers_rejected():
    with pytest.raises(ValueError, match="MỘT keyframe"):
        parse_search_query("L26_V306, 49, 50")


def test_number_without_exactly_one_video_rejected():
    with pytest.raises(ValueError, match="MỘT video ID"):
        parse_search_query("con ca, 49")
    with pytest.raises(ValueError, match="MỘT video ID"):
        parse_search_query("L26, 49")


def test_explicit_keyframe_with_other_tokens_rejected():
    with pytest.raises(ValueError, match="không được kết hợp"):
        parse_search_query("con ca, L26_V306_049")
    with pytest.raises(ValueError, match="không được kết hợp"):
        parse_search_query("L26_V306_049, L27_V001")
