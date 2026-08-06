import json

import pytest

from h3_local import FPS, fill_h3_graph, frames_for_seconds


# --- frame count is a hard model constraint -----------------------------


def test_frame_count_satisfies_the_modulo_rule():
    for seconds in (6, 8, 10, 12, 15):
        assert frames_for_seconds(seconds) % 17 == 5


def test_frame_count_stays_in_the_trained_range():
    for seconds in (6, 8, 10, 12, 15):
        assert 124 <= frames_for_seconds(seconds) <= 362


def test_frame_count_is_near_the_request():
    # 8s at 24fps is 192 frames; nearest valid is within one 17-frame step
    assert abs(frames_for_seconds(8) - 8 * FPS) <= 17


def test_below_trained_range_raises():
    with pytest.raises(ValueError, match="124"):
        frames_for_seconds(3)


def test_above_trained_range_raises():
    with pytest.raises(ValueError, match="362"):
        frames_for_seconds(20)


# --- graph filling against the real workflow ----------------------------


@pytest.fixture
def flf_graph(workflows_dir):
    return json.loads((workflows_dir / "h3_flf.api.json").read_text(encoding="utf-8"))


@pytest.fixture
def i2v_graph(workflows_dir):
    return json.loads((workflows_dir / "h3_i2v.api.json").read_text(encoding="utf-8"))


def _h3_node(graph):
    return next(n for n in graph.values() if n.get("class_type") == "MiniMaxH3ImageToVideo")


def test_fill_sets_length_on_the_h3_node(flf_graph):
    out = fill_h3_graph(flf_graph, {"prompt": "p"}, ["a.png", "b.png"], frames=192 - 4, seed=1)
    assert _h3_node(out)["inputs"]["length"] == 188


def test_fill_sets_prompt_on_the_h3_node(flf_graph):
    out = fill_h3_graph(flf_graph, {"prompt": "she leaps"}, ["a.png", "b.png"], 141, 1)
    assert _h3_node(out)["inputs"]["prompt"] == "she leaps"


def test_fill_sets_seed_on_the_sampler(flf_graph):
    out = fill_h3_graph(flf_graph, {"prompt": "p"}, ["a.png", "b.png"], 141, seed=777)
    sampler = next(n for n in out.values() if n.get("class_type") == "KSampler")
    assert sampler["inputs"]["seed"] == 777


def test_fill_binds_images_in_first_then_last_order(flf_graph):
    out = fill_h3_graph(flf_graph, {"prompt": "p"}, ["first.png", "last.png"], 141, 1)
    h3 = _h3_node(out)
    first_node = h3["inputs"]["first_frame"][0]
    last_node = h3["inputs"]["last_frame"][0]
    assert out[first_node]["inputs"]["image"] == "first.png"
    assert out[last_node]["inputs"]["image"] == "last.png"


def test_i2v_graph_has_no_last_frame(i2v_graph):
    assert "last_frame" not in _h3_node(i2v_graph)["inputs"]


def test_fill_i2v_binds_only_the_first_frame(i2v_graph):
    out = fill_h3_graph(i2v_graph, {"prompt": "p"}, ["only.png"], 141, 1)
    h3 = _h3_node(out)
    assert out[h3["inputs"]["first_frame"][0]]["inputs"]["image"] == "only.png"


def test_fill_sets_dimensions(flf_graph):
    out = fill_h3_graph(flf_graph, {"prompt": "p"}, ["a.png", "b.png"], 141, 1, width=1280, height=704)
    h3 = _h3_node(out)
    assert (h3["inputs"]["width"], h3["inputs"]["height"]) == (1280, 704)


def test_fill_does_not_mutate_the_template(flf_graph):
    before = json.dumps(flf_graph, sort_keys=True)
    fill_h3_graph(flf_graph, {"prompt": "p"}, ["a.png", "b.png"], 141, 1)
    assert json.dumps(flf_graph, sort_keys=True) == before


def test_fill_never_emits_a_negative_prompt(flf_graph):
    out = fill_h3_graph(flf_graph, {"prompt": "p", "negative_prompt": "blurry"}, ["a.png", "b.png"], 141, 1)
    assert "blurry" not in json.dumps(out)


def test_too_many_images_rejected(flf_graph):
    with pytest.raises(ValueError, match="two"):
        fill_h3_graph(flf_graph, {"prompt": "p"}, ["a.png", "b.png", "c.png"], 141, 1)


def test_missing_h3_node_raises():
    with pytest.raises(RuntimeError, match="MiniMaxH3ImageToVideo"):
        fill_h3_graph({"1": {"class_type": "KSampler", "inputs": {}}}, {"prompt": "p"}, ["a.png"], 141, 1)
