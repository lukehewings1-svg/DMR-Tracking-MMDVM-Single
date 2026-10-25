"""Emergent object storage client for uploaded overlay images."""
import os

import requests

STORAGE_BASE = (os.environ.get("INTEGRATION_PROXY_URL") or "").strip() or "https://integrations.emergentagent.com"
STORAGE_URL = STORAGE_BASE.rstrip("/") + "/objstore/api/v1/storage"
APP_NAME = "dmr-tracker"
_storage_key = None


def init_storage(force: bool = False) -> str:
    global _storage_key
    if _storage_key and not force:
        return _storage_key
    resp = requests.post(f"{STORAGE_URL}/init", json={"emergent_key": os.environ["EMERGENT_LLM_KEY"]}, timeout=30)
    resp.raise_for_status()
    _storage_key = resp.json()["storage_key"]
    return _storage_key


def _request(method: str, path: str, headers: dict | None = None, **kwargs) -> requests.Response:
    url = f"{STORAGE_URL}/objects/{path}"
    resp = requests.request(method, url, headers={"X-Storage-Key": init_storage(), **(headers or {})}, **kwargs)
    if resp.status_code == 404 and method == "PUT":
        resp = requests.request(method, url, headers={"X-Storage-Key": init_storage(force=True), **(headers or {})}, **kwargs)
    resp.raise_for_status()
    return resp


def put_object(path: str, data: bytes, content_type: str) -> dict:
    return _request("PUT", path, data=data, headers={"Content-Type": content_type}, timeout=120).json()


def get_object(path: str) -> tuple[bytes, str]:
    resp = _request("GET", path, timeout=60)
    return resp.content, resp.headers.get("Content-Type", "application/octet-stream")
