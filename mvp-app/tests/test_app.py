import inspect
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app import (
    SearchController,
    _detail_markdown,
    _keyframe_directory,
    _timestamp,
    build_app,
    create_search_mechanism,
    search_keyframes_gpu,
    search_keyframes_gpu_v2,
)
from schemas import KeyframeDetails, SearchResult


class FakeSearchMechanism:
    def filter_options(self):
        return {
            "collections": ["C01"],
            "videos": ["V01"],
            "objects": ["Person"],
            "authors": ["Alice"],
        }

    def get_keyframe_details(self, _keyframe_id):
        return KeyframeDetails({}, {})


def test_build_app_exposes_keyframe_endpoints_and_filters():
    app = build_app(FakeSearchMechanism())
    endpoints = app.get_api_info()["named_endpoints"]
    assert "/search_keyframes" in endpoints
    assert "/search_keyframes_v2" in endpoints
    assert "/get_keyframe_details" in endpoints
    assert len(endpoints["/search_keyframes"]["parameters"]) == 11
    assert len(endpoints["/search_keyframes_v2"]["parameters"]) == 11

    config = app.get_config_file()
    labels = {
        component["props"].get("label")
        for component in config["components"]
        if component.get("props", {}).get("label")
    }
    assert {
        "Query",
        "Translate Vietnamese query to English",
        "Top K",
        "Collections",
        "Video ID",
        "Objects",
        "Search within results",
        "Detected objects",
    } <= labels

    components_by_label = {
        component["props"].get("label"): component["props"]
        for component in config["components"]
        if component.get("props", {}).get("label")
    }
    assert components_by_label["Video ID"]["value"] == ""
    assert components_by_label["Author / Channel"]["value"] == ""
    assert components_by_label["Translate Vietnamese query to English"]["value"] is True
    assert components_by_label["Translate Vietnamese query to English"]["info"] == (
        "Off: direct multilingual search. On: NLLB translation before search."
    )
    assert components_by_label["Top K"]["value"] == 100
    assert components_by_label["Top K"]["maximum"] == 200
    assert components_by_label["Keyframes"]["columns"] == 5
    assert components_by_label["Keyframes"]["rows"] == 2
    assert components_by_label["Keyframes"]["height"] == 320
    assert components_by_label["Keyframes"]["allow_preview"] is False
    assert components_by_label["Keyframes"]["object_fit"] == "contain"
    assert components_by_label["Selected keyframe"]["height"] == 420
    assert build_app.__kwdefaults__["page_size"] == 10
    assert any(
        component["props"].get("elem_id") == "app-title" for component in config["components"]
    )
    assert "#keyframe-gallery .grid-wrap" in config["css"]
    assert "overflow-y: hidden !important" in config["css"]
    assert "@media (max-width: 600px)" in config["css"]

    component_ids = {
        component["props"].get("label"): component["id"]
        for component in config["components"]
        if component.get("props", {}).get("label")
    }
    refine_accordion_id = next(
        component["id"]
        for component in config["components"]
        if component["type"] == "accordion"
        and component["props"].get("label") == "Refine current Top K results"
    )

    def find_layout_node(node, component_id):
        if node["id"] == component_id:
            return node
        for child in node.get("children", []):
            match = find_layout_node(child, component_id)
            if match is not None:
                return match
        return None

    def descendant_ids(node):
        return {
            child_id
            for child in node.get("children", [])
            for child_id in ({child["id"]} | descendant_ids(child))
        }

    refine_layout = find_layout_node(config["layout"], refine_accordion_id)
    assert refine_layout is not None
    assert component_ids["Search within results"] in descendant_ids(refine_layout)


def test_zerogpu_entrypoint_does_not_serialize_controller_instance():
    assert next(iter(inspect.signature(search_keyframes_gpu).parameters)) == "query"
    assert "@spaces.GPU" not in inspect.getsource(SearchController.search_keyframes)
    assert "@spaces.GPU" in inspect.getsource(search_keyframes_gpu)
    assert "@spaces.GPU" in inspect.getsource(search_keyframes_gpu_v2)


def test_click_and_enter_use_the_same_zerogpu_entrypoint():
    app = build_app(FakeSearchMechanism())
    callback_names = [
        getattr(block_function.fn, "__name__", "") for block_function in app.fns.values()
    ]

    assert callback_names.count("search_keyframes_gpu_v2") == 2
    assert callback_names.count("search_keyframes_gpu") == 1
    assert "search_keyframes" not in callback_names


def test_runtime_preloads_only_multilingual_text_model():
    runtime = SimpleNamespace(
        environment={
            "MODEL_ID": "text-model",
            "MODEL_REVISION": "text-revision",
            "TRANSLATION_MODEL_ID": "translation-model",
            "TRANSLATION_MODEL_REVISION": "translation-revision",
            "FAISS_NPROBE": "16",
        },
        index_file="index.faiss",
        sqlite_file="runtime.sqlite",
        embeddings_file="embeddings.npy",
        data_root="release",
    )
    with (
        patch("app.CLIPSearcher") as clip_class,
        patch("app.QueryTranslator") as translator_class,
        patch("app.ImageIndexer") as indexer_class,
        patch("app.SearchMechanism") as mechanism_class,
    ):
        result = create_search_mechanism(runtime)

    clip_class.assert_called_once_with(model_id="text-model", revision="text-revision")
    clip_class.return_value.load.assert_called_once_with()
    translator_class.assert_called_once_with(
        model_id="translation-model",
        revision="translation-revision",
    )
    translator_class.return_value._ensure_loaded.assert_not_called()
    indexer_class.assert_called_once_with("index.faiss", nprobe=16)
    assert result is mechanism_class.return_value


def test_allowed_file_directory_is_limited_to_keyframes(tmp_path):
    assert _keyframe_directory(tmp_path) == (tmp_path / "keyframes").resolve()


def test_detail_markdown_contains_required_metadata():
    details = KeyframeDetails(
        keyframe={
            "keyframe_id": "V01_001",
            "video_id": "V01",
            "collection_id": "C01",
            "keyframe_no": 1,
            "frame_idx": 90,
            "pts_time_sec": 3.0,
            "fps": 30.0,
            "width": 1280,
            "height": 720,
        },
        video={
            "title": "Title",
            "author": "Alice",
            "channel_id": "channel",
            "publish_date_iso": "2024-01-01",
            "watch_url": "https://example.com/watch?v=1",
        },
    )
    markdown = _detail_markdown(details)
    for expected in ["V01_001", "Frame index", "00:00:03.000", "30", "1280 x 720"]:
        assert expected in markdown
    assert "t=3s" in markdown
    assert 'target="_blank"' in markdown
    assert 'rel="noopener noreferrer"' in markdown


def test_timestamp_and_search_result_serialization():
    assert _timestamp(3661.125) == "01:01:01.125"
    result = SearchResult(
        0,
        "V01_001",
        "V01",
        "C01",
        1,
        "/data/keyframes/C01/V01/001.jpg",
        "keyframes/C01/V01/001.jpg",
        0.75,
        3.0,
        90,
        30.0,
        1280,
        720,
        "Title",
        "Alice",
    )
    assert result.to_dict()["keyframe_id"] == "V01_001"
    assert result.to_dict()["author"] == "Alice"


def _result_row(tmp_path, keyframe_id, video_id, collection, author, score, number, frame):
    image_path = tmp_path / f"{keyframe_id}.jpg"
    image_path.write_bytes(b"jpeg")
    return {
        "keyframe_id": keyframe_id,
        "video_id": video_id,
        "collection_id": collection,
        "title": f"Title {video_id}",
        "author": author,
        "score": score,
        "keyframe_no": number,
        "frame_idx": frame,
        "pts_time_sec": float(number),
        "image_path": str(image_path),
    }


def test_result_refinement_combines_dynamic_fields_and_numeric_search(tmp_path):
    controller = SearchController(FakeSearchMechanism(), page_size=2)
    rows = [
        _result_row(tmp_path, "KF_001", "V01", "C01", "Alice", 0.9, 1, 30),
        _result_row(tmp_path, "KF_002", "V01", "C01", "Alice", 0.7, 2, 60),
        _result_row(tmp_path, "KF_003", "V02", "C02", "Bob", 0.8, 1, 90),
    ]

    refined = controller._refined_rows(
        rows,
        "title v01",
        "title",
        ["C01"],
        [],
        ["Alice"],
        0.75,
    )
    assert [row["keyframe_id"] for row in refined] == ["KF_001"]

    numeric = controller._refined_rows(rows, "1", "keyframe_no", [], [], [], -1.0)
    assert [row["keyframe_id"] for row in numeric] == ["KF_001", "KF_003"]

    with pytest.raises(ValueError, match="integer"):
        controller._refined_rows(rows, "not-a-number", "frame_idx", [], [], [], -1.0)


def test_page_payload_uses_ten_result_pages_and_rendered_row_mapping(tmp_path):
    controller = SearchController(FakeSearchMechanism(), page_size=10)
    rows = [
        _result_row(tmp_path, f"KF_{index:03d}", "V01", "C01", "Alice", 0.9, index, index)
        for index in range(21)
    ]

    gallery, page_rows, page, label, previous, next_ = controller.page_payload(rows, 2)

    assert len(gallery) == 1
    assert [row["keyframe_id"] for row in page_rows] == ["KF_020"]
    assert page == 2
    assert label == "Page 3 / 3 | 21 results"
    assert previous["interactive"] is True
    assert next_["interactive"] is False
