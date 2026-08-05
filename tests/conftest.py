from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).parent.parent


@pytest.fixture
def workflows_dir(repo_root: Path) -> Path:
    return repo_root / "skills" / "director-storyboard" / "workflows"
