"""Assemble an explicitly labeled walkthrough from actual browser captures, not mockups."""

from pathlib import Path

from PIL import Image, ImageOps


def main() -> None:
    root = Path("docs")
    frames = []
    for name in ("operator", "executive", "bearing", "procedures"):
        with Image.open(root / f"{name}.jpg") as image:
            frames.append(ImageOps.pad(image.convert("RGB"), (1000, 1000), color="white"))
    frames[0].save(
        root / "demo.gif",
        save_all=True,
        append_images=frames[1:],
        duration=7500,
        loop=0,
        optimize=True,
    )


if __name__ == "__main__":
    main()
