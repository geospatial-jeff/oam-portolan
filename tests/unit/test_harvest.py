from oam_mirror.harvest import dedupe, year_slices


def test_year_slices_cover_open_ended_bounds():
    slices = year_slices(2015, 2016)
    assert (slices[0][0], slices[-1][1]) == ("..", "..")


def test_year_slices_one_per_year_plus_two_open_ends():
    assert len(year_slices(2015, 2026)) == 14


def test_dedupe_keeps_one_item_per_id():
    merged = dedupe([[{"id": "b"}, {"id": "a"}], [{"id": "a"}]])
    assert [item["id"] for item in merged] == ["a", "b"]
