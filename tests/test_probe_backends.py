import json

from probe_backends import H3_NODES, probe_comfyui


def _clip(*types):
    return {"input": {"required": {"type": [list(types)]}}}


def test_ltx_available_from_real_object_info(fixtures_dir):
    info = json.loads((fixtures_dir / "object_info_ltx.json").read_text(encoding="utf-8"))
    result = probe_comfyui(info)
    assert result["timeline"] is True
    assert result["i2v"] is True
    assert result["flf"] is True


def test_timeline_false_without_director_node():
    result = probe_comfyui({})
    assert result["timeline"] is False
    assert "LTXDirector" in result["reasons"]["timeline"]


def test_h3_local_false_when_nodes_absent():
    result = probe_comfyui({"LTXDirector": {}})
    assert result["h3_local"] is False
    assert "MiniMaxH3ImageToVideo" in result["reasons"]["h3_local"]


def test_h3_local_false_when_weights_missing():
    info = {name: {} for name in H3_NODES}
    info["CLIPLoader"] = _clip("stable_diffusion", "ltxv")
    result = probe_comfyui(info)
    assert result["h3_local"] is False
    assert "minimax" in result["reasons"]["h3_local"]


def test_h3_local_true_when_nodes_and_weights_present():
    info = {name: {} for name in H3_NODES}
    info["CLIPLoader"] = _clip("stable_diffusion", "minimax")
    result = probe_comfyui(info)
    assert result["h3_local"] is True
    assert "h3_local" not in result["reasons"]


def test_h3_local_reason_lists_every_missing_node():
    info = {"MiniMaxH3ImageToVideo": {}}
    reason = probe_comfyui(info)["reasons"]["h3_local"]
    assert "EmptyMiniMaxH3LatentAV" in reason
    assert "MiniMaxH3ImageToVideo" not in reason


def test_real_object_info_reports_h3_weights_installed(fixtures_dir):
    """The captured CLIPLoader really does offer the minimax type."""
    info = json.loads((fixtures_dir / "object_info_ltx.json").read_text(encoding="utf-8"))
    types = info["CLIPLoader"]["input"]["required"]["type"][0]
    assert "minimax" in types
