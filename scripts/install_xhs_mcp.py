"""Install a pinned native service, verifying the upstream release SHA256."""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path

from curl_cffi import CurlHttpVersion
from curl_cffi.requests import Session

VERSION = "v2.5.0"
RELEASES = {
    "windows-amd64": ("xiaohongshu-mcp-windows-amd64.exe", "3578c9fcf3e7be0b79564aeceef8c4f38e0072d9357ca1f911ee14cd37bd454c"),
    "linux-amd64": ("xiaohongshu-mcp-linux-amd64", "2695820af3a924412c0e555042b81a2598d144342539d4ebea18b17d56c85fbf"),
    "darwin-arm64": ("xiaohongshu-mcp-darwin-arm64", "3e32e08c3403d22a5efef2f06aa52630b458819fc54474cba23e896c7092c38e"),
}


def install(root, target_platform=None):
    if target_platform is None:
        machine = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}.get(platform.machine().lower(), "unknown")
        target_platform = f"{platform.system().lower()}-{machine}"
    filename, digest = RELEASES[target_platform]
    url = f"https://github.com/xpzouying/xiaohongshu-mcp/releases/download/{VERSION}/{filename}"
    directory = root / "tools" / "xhs-mcp"
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / filename
    verified = target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == digest
    if verified and (directory / "LICENSE").is_file():
        print("MCP_BINARY_ALREADY_VERIFIED")
        return
    with Session(timeout=60, impersonate="chrome", http_version=CurlHttpVersion.V1_1) as client:
        if not verified:
            temporary = target.with_suffix(".download")
            for attempt in range(4):
                offset = temporary.stat().st_size if temporary.exists() else 0
                headers = {"Range": f"bytes={offset}-"} if offset else {}
                response = None
                try:
                    response = client.get(url, headers=headers, stream=True)
                    response.raise_for_status()
                    append = offset and response.status_code == 206
                    if append and not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                        raise RuntimeError("Unexpected release download range")
                    with temporary.open("ab" if append else "wb") as output:
                        for chunk in response.iter_content(chunk_size=64 * 1024):
                            output.write(chunk)
                    break
                except Exception:
                    if attempt == 3:
                        raise
                    print(f"DOWNLOAD_RETRY {attempt + 1}; partial bytes retained", flush=True)
                finally:
                    if response is not None:
                        response.close()
            if hashlib.sha256(temporary.read_bytes()).hexdigest() != digest:
                temporary.unlink()
                raise RuntimeError("MCP release SHA256 mismatch")
            temporary.replace(target)
        if target_platform != "windows-amd64":
            target.chmod(0o755)
        license_response = client.get(f"https://raw.githubusercontent.com/xpzouying/xiaohongshu-mcp/{VERSION}/LICENSE", timeout=30)
        license_response.raise_for_status()
    (directory / "LICENSE").write_text(license_response.text, encoding="utf-8")
    (directory / f"release-{target_platform}.json").write_text(json.dumps({"version": VERSION, "url": url, "sha256": digest}, indent=2), encoding="utf-8")
    print("MCP_BINARY_INSTALLED_AND_SHA256_VERIFIED")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=Path(__file__).resolve().parents[1] / "Volume")
    parser.add_argument("--platform", choices=sorted(RELEASES))
    args = parser.parse_args()
    install(args.data_root.resolve(), args.platform)
