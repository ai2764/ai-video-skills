import json

import pytest

from comfy_backend import fill_director_graph, stage_images


@pytest.fixture
def timeline(fixtures_dir):
    return json.loads((fixtures_dir / "golden_director_timeline.json").read_text(encoding="utf-8"))


@pytest.fixture
def golden_inputs(fixtures_dir):
    api = json.loads((fixtures_dir / "golden_director_api_prompt.json").read_text(encoding="utf-8"))
    return next(n for n in api.values() if n.get("class_type") == "LTXDirector")["inputs"]


@pytest.fixture
def template(workflows_dir):
    return json.loads((workflows_dir / "ltx_director_2.api.json").read_text(encoding="utf-8"))


@pytest.fixture
def image_names(golden_inputs):
    return {
        index: segment["imageFile"]
        for index, segment in enumerate(json.loads(golden_inputs["timeline_data"])["segments"], start=1)
        if segment.get("imageFile")
    }


def test_fill_reproduces_golden_director_inputs(template, timeline, image_names, golden_inputs):
    filled = fill_director_graph(template, timeline, image_names, width=1280, height=704)
    got = next(n for n in filled.values() if n.get("class_type") == "LTXDirector")["inputs"]
    assert got["local_prompts"] == golden_inputs["local_prompts"]
    assert got["segment_lengths"] == golden_inputs["segment_lengths"]
    assert got["guide_strength"] == golden_inputs["guide_strength"]
    assert json.loads(got["timeline_data"]) == json.loads(golden_inputs["timeline_data"])


def test_fill_preserves_wired_inputs(template, timeline, image_names):
    """model/clip/audio_vae are node links, not widgets — filling must not
    clobber them."""
    filled = fill_director_graph(template, timeline, image_names, width=1280, height=704)
    got = next(n for n in filled.values() if n.get("class_type") == "LTXDirector")["inputs"]
    for key in ("model", "clip", "audio_vae"):
        assert isinstance(got[key], list), key


def test_fill_does_not_mutate_the_template(template, timeline, image_names):
    before = json.dumps(template, sort_keys=True)
    fill_director_graph(template, timeline, image_names, width=1280, height=704)
    assert json.dumps(template, sort_keys=True) == before


def test_fill_sets_ic_lora_on_both_guide_nodes(template, timeline, image_names):
    filled = fill_director_graph(
        template, timeline, image_names, width=1280, height=704, ic_lora_name="thing.safetensors"
    )
    guides = [n for n in filled.values() if n.get("class_type") == "LTXDirectorGuide"]
    assert len(guides) == 2
    assert all(g["inputs"]["ic_lora_name"] == "thing.safetensors" for g in guides)


def test_fill_raises_without_director_node(timeline):
    with pytest.raises(RuntimeError, match="LTXDirector"):
        fill_director_graph(
            {"1": {"class_type": "KSampler", "inputs": {}}}, timeline, {}, width=1280, height=704
        )


def test_stage_images_uploads_each_segment_image(timeline, tmp_path):
    calls = []

    class FakeClient:
        def upload_image(self, path, subfolder=""):
            calls.append(path)
            return path.name

    staged = tmp_path / "a.png"
    staged.write_bytes(b"x")
    local = {**timeline, "segments": [{**s, "image_path": str(staged)} for s in timeline["segments"]]}
    names = stage_images(FakeClient(), local)
    assert sorted(names) == [1, 2, 3]
    assert len(calls) == 3


def test_stage_images_raises_on_missing_file(timeline, tmp_path):
    class FakeClient:
        def upload_image(self, path, subfolder=""):
            raise AssertionError("should not be reached")

    local = {**timeline, "segments": [{**timeline["segments"][0], "image_path": str(tmp_path / "gone.png")}]}
    with pytest.raises(FileNotFoundError):
        stage_images(FakeClient(), local)


def test_stage_images_skips_text_segments(timeline):
    class FakeClient:
        def upload_image(self, path, subfolder=""):
            raise AssertionError("should not be reached")

    local = {**timeline, "segments": [{"id": "t", "type": "text", "frames": 24, "image_path": ""}]}
    assert stage_images(FakeClient(), local) == {}


def test_fill_missing_required_adds_declared_defaults():
    from comfy_backend import fill_missing_required

    graph = {"37": {"class_type": "SaveVideo", "inputs": {"video": ["2", 0], "format": "auto"}}}
    info = {
        "SaveVideo": {
            "input": {
                "required": {
                    "video": ["VIDEO", {}],
                    "format": ["COMBO", {"default": "auto"}],
                    "codec": ["COMFY_DYNAMICCOMBO_V3", {"default": "auto"}],
                }
            }
        }
    }
    added = fill_missing_required(graph, info)
    assert graph["37"]["inputs"]["codec"] == "auto"
    assert added == ["37(SaveVideo).codec"]


def test_fill_missing_required_leaves_present_values_alone():
    from comfy_backend import fill_missing_required

    graph = {"1": {"class_type": "X", "inputs": {"a": "mine"}}}
    info = {"X": {"input": {"required": {"a": ["STRING", {"default": "theirs"}]}}}}
    assert fill_missing_required(graph, info) == []
    assert graph["1"]["inputs"]["a"] == "mine"


def test_fill_missing_required_skips_inputs_without_a_default():
    from comfy_backend import fill_missing_required

    graph = {"1": {"class_type": "X", "inputs": {}}}
    info = {"X": {"input": {"required": {"link_in": ["IMAGE", {}]}}}}
    assert fill_missing_required(graph, info) == []
    assert graph["1"]["inputs"] == {}


def test_fill_missing_required_ignores_unknown_node_types():
    from comfy_backend import fill_missing_required

    graph = {"1": {"class_type": "NotInObjectInfo", "inputs": {}}}
    assert fill_missing_required(graph, {}) == []
