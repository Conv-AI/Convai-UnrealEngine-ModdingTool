"""Offline validation of the published native groom target and package inventory."""
import json
from pathlib import Path


def test_groom_target_and_inventory():
    root = Path(__file__).resolve().parents[1]
    version = json.loads((root / "Version.json").read_text())
    declaration = version["runtime-content-contract"]
    inventory = json.loads((root / declaration["inventory"]).read_text())
    for field in ("id", "product", "assets_root", "engine", "platform"):
        assert declaration[field] == inventory[field]
    assert declaration["engine"] == version["current-ue-version"] == "5.8"
    assert declaration["platform"] == "Windows"
    assert declaration["assets_root"] == "https://beta.convai.com/assets"
    assert set(inventory["native_solver_roots"]) == {
        "/HairStrands/Emitters/StableSpringsSystem",
        "/HairStrands/Emitters/StableRodsSystem",
    }
    packages = inventory["packages"]
    assert len({package["package"] for package in packages}) == len(packages) == 8
    for package in packages:
        assert package["cooked_header"].endswith(".uasset")
        assert package["cooked_header"] in package["cooked_payloads"]
        assert str(Path(package["cooked_header"]).with_suffix(".uexp")).replace("\\", "/") in package["cooked_payloads"]
    assert inventory["audit"]["production"]["verified_packages"] == len(packages)
    settings = json.loads((root / "resources/modding_tool_config.json").read_text())["project_settings"]
    assert settings["uploader_utility_plugins"] == ["Interchange"]
    assert "Interchange" not in settings["required_plugins"]  # Older SDKs reject new names in this legacy list.
