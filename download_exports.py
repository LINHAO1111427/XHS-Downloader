from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from shutil import copy2, rmtree
from threading import RLock
from uuid import uuid4


class DownloadExportError(ValueError):
    pass


def _safe_name(value: str, fallback: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(" ._")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return (cleaned or fallback)[:80]


def _resolve_source(root: Path, value: str) -> Path:
    target = (root / value).resolve()
    try:
        target.relative_to(root)
    except ValueError as error:
        raise DownloadExportError("导出文件不在下载工作区内") from error
    if not target.is_file():
        raise DownloadExportError(f"导出文件不存在：{value}")
    return target


class DownloadExporter:
    """Persist a local export directory and copy completed assets into it."""

    def __init__(
        self,
        settings_path: Path,
        default_directory: Path,
        *,
        require_non_c_drive: bool = True,
    ) -> None:
        self.settings_path = settings_path.resolve()
        self.default_directory = default_directory.resolve()
        self.require_non_c_drive = require_non_c_drive
        self._lock = RLock()

    def _validate_directory(self, value: str | Path) -> Path:
        raw = Path(value).expanduser()
        if not raw.is_absolute():
            raise DownloadExportError("下载目录必须填写绝对路径")
        directory = raw.resolve()
        if (
            self.require_non_c_drive
            and os.name == "nt"
            and directory.drive.casefold() == "c:"
        ):
            raise DownloadExportError(f"下载目录不能位于 C 盘：{directory}")
        if directory.exists() and not directory.is_dir():
            raise DownloadExportError("下载目录不能指向文件")
        probe: Path | None = None
        try:
            directory.mkdir(parents=True, exist_ok=True)
            probe = directory / f".xhs-write-test-{uuid4().hex}.tmp"
            probe.write_bytes(b"")
            probe.unlink()
        except OSError as error:
            if probe is not None:
                try:
                    probe.unlink(missing_ok=True)
                except OSError:
                    pass
            raise DownloadExportError(f"下载目录无法创建：{error}") from error
        return directory

    def directory(self) -> Path:
        with self._lock:
            value = ""
            if self.settings_path.is_file():
                try:
                    value = str(
                        json.loads(self.settings_path.read_text(encoding="utf-8")).get(
                            "directory", ""
                        )
                    ).strip()
                except (OSError, ValueError, TypeError):
                    value = ""
            return self._validate_directory(value or self.default_directory)

    def public_config(self) -> dict:
        return {"directory": str(self.directory())}

    def configure(self, value: str) -> dict:
        directory = self._validate_directory(value.strip())
        with self._lock:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.settings_path.with_name(
                f".{self.settings_path.name}.{uuid4().hex}.tmp"
            )
            try:
                temporary.write_text(
                    json.dumps(
                        {"directory": str(directory)}, ensure_ascii=False, indent=2
                    ),
                    encoding="utf-8",
                )
                temporary.replace(self.settings_path)
            finally:
                temporary.unlink(missing_ok=True)
        return {"directory": str(directory)}

    @staticmethod
    def _available_path(directory: Path, name: str) -> Path:
        candidate = directory / name
        counter = 2
        while candidate.exists():
            candidate = directory / f"{Path(name).stem}_{counter}{Path(name).suffix}"
            counter += 1
        return candidate

    def export(
        self,
        source_root: Path,
        paths: list[str],
        *,
        title: str,
        kind: str,
        text: str | None = None,
        text_filename: str = "文案.txt",
    ) -> dict:
        source_root = source_root.resolve()
        selected = [
            _resolve_source(source_root, value) for value in dict.fromkeys(paths)
        ]
        if not selected and text is None:
            raise DownloadExportError("没有可导出的内容")

        kind_names = {
            "text": "文案",
            "graphic": "图文",
            "live_photo": "实况图",
            "file": "文件",
        }
        kind_name = kind_names.get(kind)
        if kind_name is None:
            raise DownloadExportError("不支持的导出类型")
        folder_name = "_".join(
            (
                datetime.now().strftime("%Y%m%d-%H%M%S"),
                kind_name,
                _safe_name(title, "未命名"),
            )
        )
        with self._lock:
            export_root = self.directory()
            destination = self._available_path(export_root, folder_name)
            destination.mkdir(parents=False)
            exported: list[str] = []
            try:
                for source in selected:
                    target = self._available_path(destination, source.name)
                    copy2(source, target)
                    exported.append(target.name)
                if text is not None:
                    target = self._available_path(
                        destination, _safe_name(text_filename, "文案.txt")
                    )
                    if not target.suffix:
                        target = target.with_suffix(".txt")
                    target.write_text(text, encoding="utf-8")
                    exported.append(target.name)
            except Exception:
                rmtree(destination, ignore_errors=True)
                raise
        return {
            "ok": True,
            "kind": kind,
            "directory": str(destination),
            "files": exported,
            "count": len(exported),
        }
