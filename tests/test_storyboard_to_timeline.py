import json

import pytest

from director_timeline import storyboard_to_timeline


@pytest.fixture
def storyboard():
    return {
        "global_prompt": "A continuous cinematic shot.",
        "negative_prompt": "blurry",
        "width": 1280,
        "height": 704,
        "seed": 42,
        "segments": [
            {"id": "s1", "image": "a.png", "prompt": "first beat", "duration": 4.0, "strength": 0.82},
            {"id": "s2", "image": "b.png", "prompt": "second beat", "duration": 3.0, "strength": 0.80},
            {"id": "s3", "image": "c.png", "prompt": "third beat", "duration": 2.0, "strength": 0.85},
        ],
    }


def test_durations_become_frame_counts(storyboard):
    timeline = storyboard_to_timeline(storyboard)
    assert [s["frames"] for s in timeline["segments"]] == [96, 72, 48]


def test_start_frames_are_cumulative(storyboard):
    timeline = storyboard_to_timeline(storyboard)
    assert [s["start_frame"] for s in timeline["segments"]] == [0, 96, 168]
    assert [s["guide_frame"] for s in timeline["segments"]] == [0, 96, 168]


def test_totals_match_the_sum(storyboard):
    timeline = storyboard_to_timeline(storyboard)
    assert timeline["duration_frames"] == 216
    assert timeline["duration_seconds"] == 9.0
    assert timeline["fps"] == 24


def test_local_prompts_joined_with_pipe(storyboard):
    timeline = storyboard_to_timeline(storyboard)
    assert timeline["local_prompts"] == "first beat|second beat|third beat"


def test_segment_lengths_joined_with_comma(storyboard):
    timeline = storyboard_to_timeline(storyboard)
    assert timeline["segment_lengths"] == "96,72,48"


def test_image_becomes_image_path(storyboard):
    timeline = storyboard_to_timeline(storyboard)
    assert timeline["segments"][0]["image_path"] == "a.png"
    assert timeline["segments"][0]["type"] == "image"


def test_image_path_alias_is_accepted(storyboard):
    storyboard["segments"][0] = {"id": "s1", "image_path": "z.png", "prompt": "p", "duration": 4.0}
    timeline = storyboard_to_timeline(storyboard)
    assert timeline["segments"][0]["image_path"] == "z.png"


def test_segment_without_image_is_text(storyboard):
    storyboard["segments"][1].pop("image")
    timeline = storyboard_to_timeline(storyboard)
    assert timeline["segments"][1]["type"] == "text"
    assert timeline["segments"][1]["image_path"] == ""


def test_strength_defaults_to_one(storyboard):
    storyboard["segments"][0].pop("strength")
    timeline = storyboard_to_timeline(storyboard)
    assert timeline["segments"][0]["strength"] == 1.0


def test_pipe_in_a_prompt_is_rejected(storyboard):
    storyboard["segments"][0]["prompt"] = "she turns | he runs"
    with pytest.raises(ValueError, match=r"\|"):
        storyboard_to_timeline(storyboard)


def test_empty_segments_rejected():
    with pytest.raises(ValueError, match="at least one segment"):
        storyboard_to_timeline({"global_prompt": "x", "segments": []})


def test_length_seconds_alias_is_accepted(storyboard):
    storyboard["segments"][0] = {"id": "s1", "image": "a.png", "prompt": "p", "length_seconds": 4.0}
    assert storyboard_to_timeline(storyboard)["segments"][0]["frames"] == 96


def test_local_prompt_alias_is_accepted(storyboard):
    storyboard["segments"][0] = {"id": "s1", "image": "a.png", "local_prompt": "aliased", "duration": 4.0}
    assert storyboard_to_timeline(storyboard)["local_prompts"].startswith("aliased|")


def test_roundtrip_feeds_build_director_inputs(storyboard):
    from director_timeline import build_director_inputs

    timeline = storyboard_to_timeline(storyboard)
    inputs = build_director_inputs(timeline, {1: "a.png", 2: "b.png", 3: "c.png"}, 1280, 704)
    assert inputs["segment_lengths"] == "96,72,48"
    assert inputs["duration_frames"] == 216
    segments = json.loads(inputs["timeline_data"])["segments"]
    assert [s["start"] for s in segments] == [0, 96, 168]
    assert [s["length"] for s in segments] == [96, 72, 48]
