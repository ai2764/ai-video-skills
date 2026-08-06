import pytest

from routing import estimate_cost, route_segment, route_storyboard, split_for_h3

ALL = {"ltx": True, "h3_local": True, "h3_api": True}
NO_LOCAL = {"ltx": True, "h3_local": False, "h3_api": True}
NO_H3 = {"ltx": True, "h3_local": False, "h3_api": False}


def seg(n_keys, duration, fast):
    return {
        "keyframes": [f"k{i}.png" for i in range(n_keys)],
        "duration_s": duration,
        "fast_camera": fast,
    }


# --- Rule 1: keyframe count picks the row -------------------------------


def test_one_keyframe_is_i2v():
    assert route_segment(seg(1, 8, False), ALL)[0] == "i2v"


def test_two_keyframes_is_flf():
    assert route_segment(seg(2, 8, False), ALL)[0] == "flf"


def test_three_keyframes_is_timeline():
    assert route_segment(seg(3, 8, False), ALL)[0] == "timeline"


def test_zero_keyframes_still_routes_as_i2v():
    assert route_segment({"keyframes": [], "duration_s": 8}, ALL)[0] == "i2v"


# --- Rule 2: fast camera movement picks the column ----------------------


def test_slow_segment_stays_on_ltx():
    assert route_segment(seg(2, 8, False), ALL)[1] == "ltx"


def test_fast_segment_goes_to_h3():
    assert route_segment(seg(2, 8, True), ALL)[1] in {"h3_local", "h3_api"}


def test_local_h3_preferred_over_api_when_both_present():
    assert route_segment(seg(2, 8, True), ALL)[1] == "h3_local"


def test_h3_api_used_when_local_unavailable():
    assert route_segment(seg(2, 8, True), NO_LOCAL)[1] == "h3_api"


def test_falls_back_to_ltx_when_no_h3_at_all():
    assert route_segment(seg(2, 8, True), NO_H3) == ("flf", "ltx")


# --- Rule 3: sub-4s vetoes H3 regardless of camera movement -------------


def test_short_fast_segment_forced_back_to_ltx():
    assert route_segment(seg(2, 3.0, True), ALL) == ("flf", "ltx")


def test_exactly_four_seconds_is_allowed_on_h3():
    assert route_segment(seg(2, 4.0, True), ALL)[1] != "ltx"


def test_over_ceiling_fast_segment_stays_on_ltx():
    assert route_segment(seg(2, 16.0, True), ALL) == ("flf", "ltx")


# --- Rule 4: >=3 keyframes + fast camera splits into adjacent pairs -----


def test_timeline_with_fast_camera_splits_into_pairs():
    run = {"segments": [seg(4, 12, True)]}
    pairs = split_for_h3(run, [0])
    assert len(pairs) == 3
    assert all(len(p["keyframes"]) == 2 for p in pairs)


def test_split_preserves_total_duration():
    run = {"segments": [seg(4, 12, True)]}
    assert sum(p["duration_s"] for p in split_for_h3(run, [0])) == pytest.approx(12)


def test_split_pairs_are_adjacent():
    run = {"segments": [seg(4, 12, True)]}
    pairs = split_for_h3(run, [0])
    assert [p["keyframes"] for p in pairs] == [
        ["k0.png", "k1.png"], ["k1.png", "k2.png"], ["k2.png", "k3.png"]
    ]


def test_split_leaves_two_keyframe_segments_alone():
    run = {"segments": [seg(2, 8, True)]}
    assert len(split_for_h3(run, [0])) == 1


def test_split_records_the_source_segment():
    run = {"segments": [seg(3, 10, True)]}
    assert all(p["source_index"] == 0 for p in split_for_h3(run, [0]))


# --- H3 never routes to timeline ---------------------------------------


def test_h3_is_never_paired_with_timeline():
    for duration in (5, 10, 15):
        mode, backend = route_segment(seg(5, duration, True), ALL)
        if backend != "ltx":
            assert mode != "timeline"


def test_no_backend_available_raises():
    with pytest.raises(ValueError, match="no backend"):
        route_segment(seg(2, 8, True), {"ltx": False, "h3_local": False, "h3_api": False})


# --- route_storyboard reports a reason ---------------------------------


def test_storyboard_plan_explains_each_choice():
    run = {"segments": [seg(2, 8, True), seg(2, 8, False), seg(2, 3, True)]}
    plan = route_storyboard(run, ALL)
    assert [p["cell"][1] for p in plan] == ["h3_local", "ltx", "ltx"]
    assert "fast camera" in plan[0]["reason"]
    assert "no fast camera" in plan[1]["reason"]
    assert "floor" in plan[2]["reason"]


# --- Cost ---------------------------------------------------------------


def test_cost_768p():
    plan = [
        {"duration_s": 8, "cell": ("flf", "h3_api")},
        {"duration_s": 10, "cell": ("flf", "h3_api")},
    ]
    cost = estimate_cost(plan, "768P", image_count=2)
    assert cost["seconds"] == 18
    assert cost["video_usd"] == pytest.approx(1.44)
    assert cost["image_usd"] == 0.0
    assert cost["total_usd"] == pytest.approx(1.44)


def test_cost_2k_and_extra_images():
    plan = [{"duration_s": 10, "cell": ("flf", "h3_api")}]
    cost = estimate_cost(plan, "2K", image_count=7)
    assert cost["video_usd"] == pytest.approx(1.30)
    assert cost["image_usd"] == pytest.approx(0.08)


def test_cost_ignores_ltx_segments():
    plan = [{"duration_s": 100, "cell": ("timeline", "ltx")}]
    assert estimate_cost(plan)["total_usd"] == 0.0


def test_cost_ignores_local_h3_segments():
    plan = [{"duration_s": 100, "cell": ("flf", "h3_local")}]
    assert estimate_cost(plan)["total_usd"] == 0.0


def test_unknown_resolution_rejected():
    with pytest.raises(ValueError, match="resolution"):
        estimate_cost([], "1080p")


def test_act3_scale_estimate():
    """The real act3 plan: 1847 frames at 24fps ~= 77s, all on H3 API."""
    plan = [{"duration_s": 1847 / 24, "cell": ("flf", "h3_api")}]
    assert estimate_cost(plan, "768P")["total_usd"] == pytest.approx(6.16, abs=0.1)
