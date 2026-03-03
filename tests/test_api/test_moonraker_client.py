from packages.api.moonraker_client import MoonrakerClient


def test_moonraker_client_import():
    client = MoonrakerClient("http://127.0.0.1:7125")
    assert client.base_url == "http://127.0.0.1:7125"


def test_cache_key_generation():
    client = MoonrakerClient("http://127.0.0.1:7125")
    key = client._cache_key("/printer/objects/query", {"print_stats": ""})
    assert isinstance(key, str)
    assert len(key) > 0


def test_cache_expiry():
    client = MoonrakerClient("http://127.0.0.1:7125", cache_ttl=0.0)
    client._cache["test_key"] = (0, {"data": True})
    assert client._get_cached("test_key") is None  # expired
