import json

import pytest

from director_timeline import align_dimension, build_director_inputs, build_segments


def test_align_dimension_matches_camera_lab():
    # halve, align to 32, double back
    assert align_dimension(720) == 704
    assert align_dimension(736) == 768
    assert align_dimension(1280) == 1280
    assert align_dimension(704) == 704


@pytest.fixture
def golden(fixtures_dir):
    timeline = json.loads((fixtures_dir / "golden_director_timeline.json").read_text(encoding="utf-8"))
    api = json.loads((fixtures_dir / "golden_director_api_prompt.json").read_text(encoding="utf-8"))
    director = next(n for n in api.values() if n.get("class_type") == "LTXDirector")
    return timeline, director["inputs"]


@pytest.fixture
def golden_image_names(golden):
    _, inputs = golden
    return {
        index: segment["imageFile"]
        for index, segment in enumerate(json.loads(inputs["timeline_data"])["segments"], start=1)
        if segment.get("imageFile")
    }


def test_segments_carry_frames_and_start(golden):
    timeline, inputs = golden
    expected = json.loads(inputs["timeline_data"])["segments"]
    got = build_segments(timeline)
    assert len(got) == len(expected)
    for a, b in zip(got, expected):
        assert a["id"] == b["id"]
        assert a["start"] == b["start"]
        assert a["length"] == b["length"]
        assert a["prompt"] == b["prompt"]
        assert a["label"] == b["label"]


def test_timeline_data_segments_match_golden_exactly(golden, golden_image_names):
    timeline, inputs = golden
    got = build_director_inputs(timeline, golden_image_names, width=1280, height=704)
    assert json.loads(got["timeline_data"]) == json.loads(inputs["timeline_data"])


@pytest.mark.parametrize(
    "key",
    [
        "global_prompt",
        "local_prompts",
        "segment_lengths",
        "guide_strength",
        "duration_frames",
        "duration_seconds",
        "start_frame",
        "end_frame",
        "start_second",
        "end_second",
        "frame_rate",
        "custom_width",
        "custom_height",
        "display_mode",
        "resize_method",
        "divisible_by",
        "img_compression",
        "inpaint_audio",
        "overrideAudio",
        "use_custom_audio",
    ],
)
def test_director_input_matches_golden(golden, golden_image_names, key):
    timeline, expected = golden
    got = build_director_inputs(timeline, golden_image_names, width=1280, height=704)
    assert got[key] == expected[key]


def test_local_prompts_use_pipe_separator(golden, golden_image_names):
    timeline, _ = golden
    got = build_director_inputs(timeline, golden_image_names, width=1280, height=704)
    assert got["local_prompts"].count("|") == len(timeline["segments"]) - 1


def test_width_is_passed_through_not_realigned(golden, golden_image_names):
    timeline, _ = golden
    got = build_director_inputs(timeline, golden_image_names, width=1280, height=704)
    assert got["custom_width"] == 1280
    assert got["custom_height"] == 704


def test_missing_image_name_leaves_segment_without_guide(golden):
    timeline, _ = golden
    got = build_director_inputs(timeline, {}, width=1280, height=704)
    segments = json.loads(got["timeline_data"])["segments"]
    assert all("imageFile" not in segment for segment in segments)
    assert got["guide_strength"] == ""
