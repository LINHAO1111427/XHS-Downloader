from __future__ import annotations

from io import BytesIO
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Sequence

from PIL import Image, ImageOps, UnidentifiedImageError


NINE_GRID_COUNT = 9
NINE_GRID_COLUMNS = 3
NINE_GRID_ROWS = 3
DEFAULT_TILE_SIZE = 1024
DEFAULT_GAP = 8
DEFAULT_BACKGROUND = "#ffffff"


class NineGridError(ValueError):
    """Raised when a nine-grid source set cannot be composed."""


def _square_tile(path: Path, size: int) -> Image.Image:
    try:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
    except (OSError, UnidentifiedImageError) as error:
        raise NineGridError(f"\u56fe\u7247\u65e0\u6cd5\u8bfb\u53d6\uff1a{path.name}") from error
    width, height = image.size
    if not width or not height:
        raise NineGridError(f"\u56fe\u7247\u5c3a\u5bf8\u65e0\u6548\uff1a{path.name}")
    scale = max(size / width, size / height)
    resized = image.resize(
        (max(size, round(width * scale)), max(size, round(height * scale))),
        Image.Resampling.LANCZOS,
    )
    left = (resized.width - size) // 2
    top = (resized.height - size) // 2
    return resized.crop((left, top, left + size, top + size))


def compose_nine_grid(
    paths: Sequence[Path],
    *,
    tile_size: int = DEFAULT_TILE_SIZE,
    gap: int = DEFAULT_GAP,
    background: str = DEFAULT_BACKGROUND,
) -> bytes:
    """Compose exactly nine images into a row-major 3x3 square PNG."""
    if len(paths) != NINE_GRID_COUNT:
        raise NineGridError("\u4e5d\u5bab\u683c\u5fc5\u987b\u6b63\u597d\u9009\u62e9 9 \u5f20\u56fe\u7247")
    if tile_size < 64 or tile_size > 4096:
        raise NineGridError("\u4e5d\u5bab\u683c\u5355\u683c\u5c3a\u5bf8\u5fc5\u987b\u5728 64 \u81f3 4096 \u4e4b\u95f4")
    if gap < 0 or gap > tile_size:
        raise NineGridError("\u4e5d\u5bab\u683c\u95f4\u8ddd\u65e0\u6548")

    canvas_size = tile_size * NINE_GRID_COLUMNS + gap * (NINE_GRID_COLUMNS - 1)
    canvas = Image.new("RGB", (canvas_size, canvas_size), background)
    for index, raw_path in enumerate(paths):
        path = Path(raw_path)
        if not path.is_file():
            raise NineGridError(f"\u56fe\u7247\u4e0d\u5b58\u5728\uff1a{path.name}")
        tile = _square_tile(path, tile_size)
        row, column = divmod(index, NINE_GRID_COLUMNS)
        canvas.paste(tile, (column * (tile_size + gap), row * (tile_size + gap)))

    output = BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    return output.getvalue()


def write_nine_grid(
    paths: Sequence[Path],
    output_path: Path,
    *,
    tile_size: int = DEFAULT_TILE_SIZE,
    gap: int = DEFAULT_GAP,
    background: str = DEFAULT_BACKGROUND,
) -> Path:
    """Write a nine-grid atomically and return its resolved output path."""
    data = compose_nine_grid(
        paths, tile_size=tile_size, gap=gap, background=background
    )
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        dir=output_path.parent,
        prefix=f".{output_path.stem}.",
        suffix=".tmp",
        delete=False,
    ) as temporary:
        temporary.write(data)
        temporary_path = Path(temporary.name)
    temporary_path.replace(output_path)
    return output_path
