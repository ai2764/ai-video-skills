import shutil
import subprocess

import pytest

from thumbnails import contact_sheet, pair_sheet, thumbnail

pytestmark = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")


def _size(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip().rstrip(",")
    width, height = (int(value) for value in out.split(",")[:2])
    return width, height


@pytest.fixture
def source_images(tmp_path):
    paths = []
    for index, color in enumerate(("red", "blue", "green")):
        path = tmp_path / f"src{index}.png"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=1344x768",
             "-frames:v", "1", str(path)],
            check=True, capture_output=True,
        )
        paths.append(path)
    return paths


def test_thumbnail_shrinks_to_long_edge(source_images, tmp_path):
    out = thumbnail(source_images[0], tmp_path / "thumbs", long_edge=512)
    assert out.exists()
    assert max(_size(out)) == 512


def test_thumbnail_preserves_aspect_ratio(source_images, tmp_path):
    width, height = _size(thumbnail(source_images[0], tmp_path / "thumbs", long_edge=512))
    assert abs(width / height - 1344 / 768) < 0.02


def test_thumbnail_is_much_smaller_than_source(source_images, tmp_path):
    out = thumbnail(source_images[0], tmp_path / "thumbs", long_edge=512)
    assert out.stat().st_size < source_images[0].stat().st_size


def test_pair_sheet_is_two_frames_wide(source_images, tmp_path):
    out = pair_sheet(source_images[0], source_images[1], tmp_path / "pairs", long_edge=512)
    width, _ = _size(out)
    assert width == 1024


def test_pair_sheet_names_carry_both_sources(source_images, tmp_path):
    out = pair_sheet(source_images[0], source_images[1], tmp_path / "pairs")
    assert "src0" in out.name and "src1" in out.name


def test_contact_sheet_tiles_all_inputs(source_images, tmp_path):
    out = contact_sheet(source_images, tmp_path / "sheets", columns=3, long_edge=320)
    assert out.exists()
    width, _ = _size(out)
    assert width == 960


def test_contact_sheet_wraps_to_a_second_row(source_images, tmp_path):
    out = contact_sheet(source_images, tmp_path / "sheets", columns=2, long_edge=320)
    width, height = _size(out)
    assert width == 640
    # two rows: ceil(3/2)
    assert height > 320


def test_missing_source_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        thumbnail(tmp_path / "nope.png", tmp_path / "thumbs")


def test_pair_sheet_missing_source_raises(source_images, tmp_path):
    with pytest.raises(FileNotFoundError):
        pair_sheet(source_images[0], tmp_path / "nope.png", tmp_path / "pairs")
