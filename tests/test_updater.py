from pet_shelf.updater import version_tuple


def test_version_tuple_accepts_release_tag():
    assert version_tuple("v1.2.3") == (1, 2, 3)


def test_version_tuple_handles_missing_parts():
    assert version_tuple("2") == (2,)
