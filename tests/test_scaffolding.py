def test_fixtures_dir_exists(fixtures_dir):
    assert fixtures_dir.is_dir()
    assert fixtures_dir.name == "fixtures"
