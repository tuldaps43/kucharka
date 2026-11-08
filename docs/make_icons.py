import os
import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ICONS_DIR = ROOT / 'icons'
ICONS_DIR.mkdir(exist_ok=True)


def write_png(path: Path, width: int, height: int, pixels):
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            r, g, b, a = pixels[y][x]
            raw.extend((r, g, b, a))

    def chunk(tag, data):
        return (
            struct.pack('>I', len(data))
            + tag
            + data
            + struct.pack('>I', zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(bytes(raw), 9))
    png += chunk(b'IEND', b'')
    path.write_bytes(png)


def draw_round_square(size: int, radius: int = 28):
    pixels = [[(255, 255, 255, 0) for _ in range(size)] for _ in range(size)]
    red = (192, 57, 43, 255)
    for y in range(size):
        for x in range(size):
            if x < radius and y < radius:
                if (x - radius) ** 2 + (y - radius) ** 2 <= radius ** 2:
                    pixels[y][x] = red
            elif x > size - radius - 1 and y < radius:
                if (x - (size - radius - 1)) ** 2 + (y - radius) ** 2 <= radius ** 2:
                    pixels[y][x] = red
            elif x < radius and y > size - radius - 1:
                if (x - radius) ** 2 + (y - (size - radius - 1)) ** 2 <= radius ** 2:
                    pixels[y][x] = red
            elif x > size - radius - 1 and y > size - radius - 1:
                if (x - (size - radius - 1)) ** 2 + (y - (size - radius - 1)) ** 2 <= radius ** 2:
                    pixels[y][x] = red
            elif x >= radius and x <= size - radius - 1 and y >= radius and y <= size - radius - 1:
                pixels[y][x] = red

    # white plate
    plate_color = (255, 255, 255, 255)
    cx = size * 0.5
    cy = size * 0.6
    plate_r = size * 0.23
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            if dx * dx + dy * dy <= plate_r * plate_r:
                pixels[y][x] = plate_color

    # white chef hat
    hat_color = (255, 255, 255, 255)
    for y in range(size):
        for x in range(size):
            if y < size * 0.35 and x > size * 0.2 and x < size * 0.8:
                if (y < size * 0.16) and abs(x - cx) < size * 0.24:
                    pixels[y][x] = hat_color
                if y >= size * 0.16 and y <= size * 0.3 and abs(x - cx) <= size * 0.26:
                    pixels[y][x] = hat_color

    # red plate inner circle to make it look like a serving plate
    for y in range(size):
        for x in range(size):
            dx = x - cx
            dy = y - cy
            if dx * dx + dy * dy <= (plate_r * 0.72) ** 2:
                pixels[y][x] = (192, 57, 43, 255)

    return pixels


for size in (192, 512):
    pixels = draw_round_square(size)
    write_png(ICONS_DIR / f'{size}.png', size, size, pixels)

print(f'Ikony vytvořeny v {ICONS_DIR}')
