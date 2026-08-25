from __future__ import annotations

import math
from pathlib import Path

import torch
import torchvision.transforms as T
from PIL import Image


def build_vintern_transform(image_size: int):
    mean = (0.48145466, 0.4578275, 0.40821073)
    std = (0.26862954, 0.26130258, 0.27577711)
    return T.Compose(
        [
            T.ToTensor(),
            T.Normalize(mean=mean, std=std),
        ]
    )


def choose_tile_grid(
    *,
    width: int,
    height: int,
    max_tiles: int,
) -> tuple[int, int]:
    """Choose an optimal grid (columns, rows) for the image aspect ratio up to max_tiles."""
    ratio = width / height
    best_grid = (1, 1)
    best_diff = float("inf")

    for cols in range(1, max_tiles + 1):
        for rows in range(1, max_tiles + 1):
            if cols * rows > max_tiles:
                continue

            grid_ratio = cols / rows
            diff = abs(grid_ratio - ratio)

            if diff < best_diff:
                best_diff = diff
                best_grid = (cols, rows)
            elif diff == best_diff and cols * rows > best_grid[0] * best_grid[1]:
                best_grid = (cols, rows)

    return best_grid


def split_dynamic_tiles(
    image: Image.Image,
    *,
    image_size: int,
    max_tiles: int,
    use_thumbnail: bool,
) -> list[Image.Image]:
    """Split image into dynamic 448x448 patches and optionally include a global thumbnail."""
    width, height = image.size
    cols, rows = choose_tile_grid(
        width=width,
        height=height,
        max_tiles=max_tiles,
    )

    resized_width = cols * image_size
    resized_height = rows * image_size
    resized_image = image.resize((resized_width, resized_height), resample=Image.Resampling.BICUBIC)

    tiles: list[Image.Image] = []
    for row in range(rows):
        for col in range(cols):
            box = (
                col * image_size,
                row * image_size,
                (col + 1) * image_size,
                (row + 1) * image_size,
            )
            tiles.append(resized_image.crop(box))

    if use_thumbnail:
        thumbnail = image.resize((image_size, image_size), resample=Image.Resampling.BICUBIC)
        tiles.append(thumbnail)

    return tiles


def load_vintern_reasoning_image(
    path: Path,
    *,
    image_size: int,
    max_tiles: int,
    use_thumbnail: bool,
) -> torch.Tensor:
    """Load image, split into dynamic tiles, and normalize to a batched tensor."""
    with Image.open(path) as img:
        img = img.convert("RGB")

    tiles = split_dynamic_tiles(
        img,
        image_size=image_size,
        max_tiles=max_tiles,
        use_thumbnail=use_thumbnail,
    )

    transform = build_vintern_transform(image_size)
    tensors = [transform(tile) for tile in tiles]

    return torch.stack(tensors)
