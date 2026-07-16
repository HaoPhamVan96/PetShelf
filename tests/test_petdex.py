from pathlib import Path

from PySide6.QtCore import QUrlQuery

from pet_shelf.petdex import PetDexClient, PetDexPet, resolve_petdex_cli


def test_petdex_payload_is_normalized():
    pet = PetDexPet.from_payload(
        {
            "slug": "boba",
            "displayName": "Boba",
            "description": "A cozy companion",
            "submittedBy": {"name": "Crafter"},
            "metrics": {"installCount": 123},
        }
    )
    assert pet.slug == "boba"
    assert pet.creator == "Crafter"
    assert pet.install_count == 123
    assert pet.thumbnail_url == "https://petdex.dev/api/pets/boba/thumb"


def test_petdex_rejects_unsafe_slug():
    assert PetDexPet.from_payload({"slug": "../../oops"}).slug == ""


def test_search_url_encodes_query_and_pagination():
    url = PetDexClient.search_url("school girl", cursor=40, limit=500)
    query = QUrlQuery(url)
    assert query.queryItemValue("q") == "school girl"
    assert query.queryItemValue("cursor") == "40"
    assert query.queryItemValue("limit") == "50"
    assert query.queryItemValue("includeMeta") == "0"


def test_cli_resolution_prefers_installed_petdex():
    found = {"petdex": "/tools/petdex", "npx": "/tools/npx"}
    assert resolve_petdex_cli(found.get, []) == ("/tools/petdex", [])


def test_cli_resolution_falls_back_to_npx():
    found = {"npx": "/tools/npx"}
    assert resolve_petdex_cli(found.get, []) == ("/tools/npx", ["--yes", "petdex"])


def test_cli_resolution_checks_common_paths(tmp_path):
    candidate = tmp_path / "npx"
    candidate.write_text("launcher")
    assert resolve_petdex_cli(lambda _name: None, [Path(candidate)]) == (
        str(candidate),
        ["--yes", "petdex"],
    )
