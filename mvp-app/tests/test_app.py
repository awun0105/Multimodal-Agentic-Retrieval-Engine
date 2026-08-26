import inspect
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import trake
from app import (
    SearchController,
    _configured_model_device,
    _detail_markdown,
    _generate_preview_text,
    _keyframe_directory,
    _timestamp,
    build_app,
    create_app,
    create_search_mechanism,
    create_trake_searcher,
    search_keyframes_gpu,
    search_keyframes_gpu_v2,
)
from schemas import KeyframeDetails, PreparedQuery, SearchOutcome, SearchResult


class FakeSearchMechanism:
    def __init__(self):
        self.clip_searcher = object()
        self.translator = object()

    def filter_options(self):
        return {
            "collections": ["C01"],
            "videos": ["V01"],
            "objects": ["Person"],
            "authors": ["Alice"],
        }

    def get_keyframe_details(self, _keyframe_id):
        return KeyframeDetails({}, {})


class FakeTrakeSearcher:
    """Stand-in for TrakeSearcher — build_trake_tab only wires callbacks, never calls it."""


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
    assert components_by_label["Keyframes"]["height"] == "auto"
    assert components_by_label["Keyframes"]["allow_preview"] is False
    assert components_by_label["Keyframes"]["object_fit"] == "contain"
    assert components_by_label["Selected keyframe"]["height"] == 420
    assert build_app.__kwdefaults__["page_size"] == 10
    assert any(
        component["props"].get("elem_id") == "app-title" for component in config["components"]
    )
    assert "#keyframe-gallery .grid-wrap" in config["css"]
    assert "overflow-y: visible !important" in config["css"]
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
            "CLIP_DEVICE": "auto",
            "TRANSLATION_MODEL_ID": "translation-model",
            "TRANSLATION_MODEL_REVISION": "translation-revision",
            "TRANSLATION_DEVICE": "auto",
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

    clip_class.assert_called_once_with(
        model_id="text-model",
        revision="text-revision",
        device=None,
    )
    clip_class.return_value.load.assert_called_once_with()
    translator_class.assert_called_once_with(
        model_id="translation-model",
        revision="translation-revision",
        device=None,
    )
    translator_class.return_value._ensure_loaded.assert_not_called()
    indexer_class.assert_called_once_with("index.faiss", nprobe=16)
    assert result is mechanism_class.return_value


@pytest.mark.parametrize("value", ["gpu", "cuda:0"])
def test_runtime_rejects_invalid_model_device(value):
    with pytest.raises(ValueError, match="MODEL_DEVICE must be one of"):
        _configured_model_device(value, "MODEL_DEVICE")


@pytest.mark.parametrize(("value", "expected"), [("auto", None), ("", None), ("cpu", "cpu")])
def test_runtime_normalizes_model_device(value, expected):
    assert _configured_model_device(value, "MODEL_DEVICE") == expected


def test_create_app_reuses_runtime_models_during_gradio_reload():
    runtime = SimpleNamespace(
        data_root=SimpleNamespace(),
        environment={"RESULTS_PER_PAGE": "10"},
    )
    search_mechanism = FakeSearchMechanism()
    trake_searcher = FakeTrakeSearcher()
    first_app = object()
    second_app = object()

    with (
        patch("app._runtime", None),
        patch("app._search_mechanism", None),
        patch("app._trake_searcher", None),
        patch("app._keyframes_root", None),
        patch("app.prepare_runtime", return_value=runtime) as prepare_runtime,
        patch("app.create_search_mechanism", return_value=search_mechanism) as create_search,
        patch("app.create_trake_searcher", return_value=trake_searcher) as create_trake,
        patch("app._keyframe_directory", return_value=SimpleNamespace()),
        patch("app.build_app", side_effect=[first_app, second_app]) as build,
    ):
        assert create_app() is first_app
        assert create_app() is second_app

    prepare_runtime.assert_called_once_with()
    create_search.assert_called_once_with(runtime)
    create_trake.assert_called_once_with(runtime, search_mechanism)
    assert build.call_count == 2


def test_build_app_without_trake_searcher_keeps_single_tab():
    app = build_app(FakeSearchMechanism())
    config = app.get_config_file()
    # gradio 5.x also reports the nested Image/Player tabs as tabitem components,
    # so count only the top-level query tabs by label.
    top_tabs = {
        component["props"].get("label")
        for component in config["components"]
        if component["type"] == "tabitem"
        and component["props"].get("label") in {"Query Text", "Query TRAKE"}
    }
    assert top_tabs == {"Query Text"}


def test_build_app_with_trake_searcher_adds_second_tab():
    app = build_app(FakeSearchMechanism(), trake_searcher=FakeTrakeSearcher())
    config = app.get_config_file()
    top_tabs = {
        component["props"].get("label")
        for component in config["components"]
        if component["type"] == "tabitem"
        and component["props"].get("label") in {"Query Text", "Query TRAKE"}
    }
    assert top_tabs == {"Query Text", "Query TRAKE"}


def test_trake_tab_does_not_change_kis_endpoints():
    without_trake = build_app(FakeSearchMechanism())
    with_trake = build_app(FakeSearchMechanism(), trake_searcher=FakeTrakeSearcher())

    endpoints_without = set(without_trake.get_api_info()["named_endpoints"])
    endpoints_with = set(with_trake.get_api_info()["named_endpoints"])

    assert endpoints_with - endpoints_without == {"/search_trake"}
    assert endpoints_without <= endpoints_with


def test_create_trake_searcher_reuses_loaded_models():
    search_mechanism = FakeSearchMechanism()
    runtime = SimpleNamespace(
        sqlite_file="runtime.sqlite",
        embeddings_file="embeddings.npy",
        data_root="release",
    )
    with patch("app.TrakeSearcher") as trake_searcher_class:
        result = create_trake_searcher(runtime, search_mechanism)

    trake_searcher_class.assert_called_once_with(
        clip_searcher=search_mechanism.clip_searcher,
        translator=search_mechanism.translator,
        sqlite_file="runtime.sqlite",
        embeddings_file="embeddings.npy",
        data_root="release",
    )
    assert result is trake_searcher_class.return_value


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


def test_select_keyframe_allows_pinning_without_local_video(tmp_path):
    class DetailSearchMechanism(FakeSearchMechanism):
        def get_keyframe_details(self, _keyframe_id):
            return KeyframeDetails(
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
                video={},
                detections=(),
            )

    controller = SearchController(DetailSearchMechanism(), page_size=10)
    row = _result_row(tmp_path, "V01_001", "V01", "C01", "Alice", 1.0, 1, 90)

    with patch("app.get_video_path", return_value=None):
        result = controller.select_keyframe([row], SimpleNamespace(index=0))

    previous_frame_update, next_frame_update, pin_update = result[4:7]
    assert previous_frame_update["interactive"] is False
    assert next_frame_update["interactive"] is False
    assert pin_update["interactive"] is True
    assert result[-1] == 90


def test_generate_preview_text_caps_at_submission_max(tmp_path):
    """Top K up to 200 is allowed; the contest file accepts at most 100 rows."""
    rows = [
        _result_row(tmp_path, f"KF_{index:03d}", f"V{index:03d}", "C01", "Alice", 0.9, index, index)
        for index in range(120)
    ]

    preview = _generate_preview_text(rows)
    lines = preview.splitlines()
    assert len(lines) == trake.SUBMISSION_MAX_ROWS


def test_generate_preview_text_promotes_pinned_frames_to_top(tmp_path):
    rows = [
        _result_row(tmp_path, "KF_001", "V01", "C01", "Alice", 0.9, 1, 30),
        _result_row(tmp_path, "KF_002", "V02", "C01", "Alice", 0.8, 2, 60),
    ]
    preview = _generate_preview_text(rows, pinned={"V02": 999})

    # The pin REPLACES V02's prediction and leads the file — one line per video,
    # always in `videoID, frameID` shape.
    assert preview.splitlines() == ["V02,999", "V01,30"]


def test_generate_preview_text_accepts_pin_for_video_outside_results(tmp_path):
    rows = [_result_row(tmp_path, "KF_001", "V01", "C01", "Alice", 0.9, 1, 30)]
    preview = _generate_preview_text(rows, pinned={"L26_V306": 4321})

    assert preview.splitlines() == ["L26_V306,4321", "V01,30"]


# --- Inline metadata parsing in _run_search ---


class RecordingMechanism(FakeSearchMechanism):
    """Records what the controller passes down and serves canned rows."""

    def __init__(self):
        super().__init__()
        self.seen_query = None
        self.seen_filters = None
        self.listed_videos = []
        self.listed_collections = []
        self.exact_lookups = []

    @staticmethod
    def _canned_result(video_id="V01", number=1, vector_id=0):
        return SearchResult(
            vector_id,
            f"{video_id}_{number:03d}",
            video_id,
            "C01",
            number,
            "/tmp/x.jpg",
            "keyframes/C01/x.jpg",
            1.0,
            1.0,
            30,
            30.0,
            640,
            360,
            "Title",
            "Alice",
        )

    def search_by_text(self, query, top_k, language, filters, *, translate_vietnamese=None):
        self.seen_query = query
        self.seen_filters = filters
        prepared = PreparedQuery(query, query, "auto", "english", translation_enabled=False)
        return SearchOutcome((self._canned_result(),), prepared)

    def get_video_keyframes(self, video_id):
        self.listed_videos.append(video_id)
        return [self._canned_result()]

    def get_collection_keyframes(self, collection_id):
        self.listed_collections.append(collection_id)
        return [self._canned_result(video_id="V02", number=1, vector_id=1)]

    def find_exact_keyframe(self, video_id, keyframe_no):
        self.exact_lookups.append((video_id, keyframe_no))
        if keyframe_no == 999:
            return None
        return self._canned_result(number=keyframe_no)


def _run(mechanism, query, **overrides):
    controller = SearchController(mechanism, page_size=10)
    arguments = {
        "collections": (),
        "video_id": "",
        "object_entities": (),
        "object_match_mode": "any",
        "minimum_object_confidence": 0.3,
        "author": None,
        "publish_date_from": None,
        "publish_date_to": None,
    }
    arguments.update(overrides)
    return controller._run_search(query, 100, "auto", **arguments)


def test_run_search_scopes_semantic_query_to_inline_video():
    mechanism = RecordingMechanism()
    rows, status = _run(mechanism, "con ca, L26_V306", translate_vietnamese=False)

    assert mechanism.seen_query == "con ca"
    assert mechanism.seen_filters.video_ids == ("L26_V306",)
    assert len(rows) == 1
    assert "Scope: video L26_V306" in status


def test_run_search_merges_inline_scope_with_dropdown_selections():
    mechanism = RecordingMechanism()
    _run(
        mechanism,
        "con ca, L26",
        collections=("C02",),
        video_id="L28_V009",
        translate_vietnamese=False,
    )

    assert mechanism.seen_filters.collections == ("C02", "L26")
    assert mechanism.seen_filters.video_ids == ("L28_V009",)


def test_run_search_lists_whole_video_without_clip():
    mechanism = RecordingMechanism()
    rows, status = _run(mechanism, "L26_V306")

    assert mechanism.listed_videos == ["L26_V306"]
    assert mechanism.seen_query is None  # embedding path never invoked
    assert len(rows) == 1 and rows[0]["score"] == 1.0
    assert status.startswith("Metadata: video L26_V306")


def test_run_search_resolves_exact_keyframe_pair():
    mechanism = RecordingMechanism()
    rows, status = _run(mechanism, "L26_V306, 49")

    assert mechanism.exact_lookups == [("L26_V306", 49)]
    assert rows[0]["keyframe_id"] == "V01_049"
    assert status.startswith("Metadata: đúng keyframe")


def test_run_search_resolves_multiple_exact_keyframes_in_order():
    mechanism = RecordingMechanism()
    rows, status = _run(mechanism, "L26_V306_049, L27_V001_007")

    assert mechanism.exact_lookups == [
        ("L26_V306", 49),
        ("L27_V001", 7),
    ]
    assert [row["keyframe_id"] for row in rows] == ["V01_049", "V01_007"]
    assert "V01_049, V01_007" in status


def test_run_search_reports_missing_exact_keyframes():
    mechanism = RecordingMechanism()
    rows, status = _run(mechanism, "L26_V306_049, L27_V001_999")

    assert [row["keyframe_id"] for row in rows] == ["V01_049"]
    assert "Không tìm thấy: L27_V001_999" in status


def test_run_search_dedupes_video_inside_typed_collection():
    """Typing a video plus its own collection must not duplicate its frames."""
    mechanism = RecordingMechanism()

    def video_rows(video_id):
        return [mechanism._canned_result(video_id="L26_V306", number=3, vector_id=10)]

    def collection_rows(collection_id):
        return [
            mechanism._canned_result(video_id="L26_V306", number=3, vector_id=10),
            mechanism._canned_result(video_id="L26_V307", number=1, vector_id=11),
            mechanism._canned_result(video_id="L26_V308", number=1, vector_id=12),
        ]

    mechanism.get_video_keyframes = video_rows
    mechanism.get_collection_keyframes = collection_rows

    rows, status = _run(mechanism, "L26_V306, L26")

    assert [row["vector_id"] for row in rows] == [10, 11, 12]
    assert status.endswith("— 3 keyframes")


# --- KIS pin callback and player source resolution ---


def test_process_pin_kis_uses_browser_frame_and_copies_dict():
    from app import process_pin_kis

    pins = {"V01": 10}
    # Runtime argument order: (video_id, kf_frame, pins, calc_frame, accuracy)
    out, status = process_pin_kis("V01", 55, pins, 777, "calculated")
    assert out == {"V01": 777}
    assert out is not pins
    assert "Calculated" in status

    out2, status2 = process_pin_kis("V02", 42, pins, None, "")
    assert out2 == {"V01": 10, "V02": 42}
    assert "Keyframe 42" in status2

    out3, _s = process_pin_kis("V03", 9, {}, "-4", "estimated")
    assert out3 == {"V03": 9}

    unchanged, message = process_pin_kis("", 5, pins, 1, "calculated")
    assert unchanged is pins
    assert "Không có video" in message


class _DetailFake(FakeSearchMechanism):
    def __init__(self, details):
        super().__init__()
        self._details = details

    def get_keyframe_details(self, _keyframe_id):
        return self._details


def test_select_keyframe_reads_fps_from_keyframe_row(tmp_path):
    """The videos row carries no per-frame fps; the silent 25 FPS fallback is gone."""
    from player import resolve_player_source

    image = tmp_path / "kf.jpg"
    image.write_bytes(b"jpeg")
    details = KeyframeDetails(
        keyframe={
            "keyframe_id": "L26_V306_049",
            "video_id": "L26_V306",
            "collection_id": "L26",
            "keyframe_no": 49,
            "pts_time_sec": 3.0,
            "fps": 30.0,
            "frame_idx": 90,
            "width": 640,
            "height": 360,
        },
        video={"watch_url": f"https://youtu.be/{'dQw4w9WgXcQ'}"},
        detections=(),
    )
    controller = SearchController(_DetailFake(details), page_size=10)
    row = {"keyframe_id": details.keyframe["keyframe_id"], "image_path": str(image)}
    event = SimpleNamespace(index=0)

    result = controller.select_keyframe([row], event)

    fps, video_id, kf_frame = result[-3], result[-2], result[-1]
    assert fps == 30.0
    assert video_id == "L26_V306"
    assert kf_frame == 90

    player_html = result[1]
    assert 'data-player=' in player_html
    assert "dQw4w9WgXcQ" in player_html
    kind, source = resolve_player_source(local_path=None, watch_url=details.video["watch_url"])
    assert (kind, source) == ("youtube", "dQw4w9WgXcQ")


def test_select_keyframe_without_any_source_keeps_pin_available(tmp_path, monkeypatch):
    from player import resolve_player_source

    monkeypatch.setattr("app.get_video_path", lambda _video_id: None)
    image = tmp_path / "kf.jpg"
    image.write_bytes(b"jpeg")
    details = KeyframeDetails(
        keyframe={
            "keyframe_id": "L26_V306_049",
            "video_id": "L26_V306",
            "collection_id": "L26",
            "keyframe_no": 49,
            "pts_time_sec": 3.0,
            "fps": 25.0,
            "frame_idx": 75,
            "width": 640,
            "height": 360,
        },
        video={},
        detections=(),
    )
    controller = SearchController(_DetailFake(details), page_size=10)
    row = {"keyframe_id": details.keyframe["keyframe_id"], "image_path": str(image)}
    event = SimpleNamespace(index=0)

    result = controller.select_keyframe([row], event)

    pin_update = result[6]
    prev_update, next_update = result[4], result[5]
    assert pin_update["interactive"] is True
    assert prev_update["interactive"] is False
    assert next_update["interactive"] is False
    assert resolve_player_source(local_path=None, watch_url="") == ("none", None)


def test_player_head_ships_shared_runtime_once():
    from player import player_head_html

    head = player_head_html()
    for marker in (
        "__aiouPlayerBoot",
        "__aiouFrameSnapshot",
        "__aiouStep",
        "onYouTubeIframeAPIReady",
        "requestVideoFrameCallback",
    ):
        assert marker in head
