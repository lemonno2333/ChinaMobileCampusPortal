#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 纯标准库版本，无需任何第三方依赖
# JPEG 解码依赖 djpeg（libjpeg-turbo-utils），PNG 用纯标准库解析

import os
import sys
import zlib
import struct
import subprocess
import tempfile

TEMPLATE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
SIZE = (24, 32)
PADDING = 3
EXPECTED_CHARS = 4


# ─────────────────────────────────────────────
# Image 类：替代 PIL.Image
# ─────────────────────────────────────────────

class Image:
    """轻量图像对象，内部用二维列表存储灰度值 (0-255)"""

    def __init__(self, width, height, pixels=None):
        self.width = width
        self.height = height
        # pixels[y][x] = 灰度值 0-255
        if pixels is not None:
            self.pixels = pixels
        else:
            self.pixels = [[255] * width for _ in range(height)]

    @property
    def size(self):
        return (self.width, self.height)

    def load(self):
        """兼容 PIL 的 pixels[x, y] 访问方式"""
        return _PixelAccessor(self.pixels, self.width, self.height)

    def copy(self):
        return Image(self.width, self.height,
                     [row[:] for row in self.pixels])

    def crop(self, box):
        x1, y1, x2, y2 = box
        x1 = max(0, x1)
        y1 = max(0, y1)
        x2 = min(self.width, x2)
        y2 = min(self.height, y2)
        w = max(1, x2 - x1)
        h = max(1, y2 - y1)
        new_pixels = [self.pixels[y][x1:x2] for y in range(y1, y2)]
        return Image(w, h, new_pixels)

    def paste(self, src, offset):
        dx, dy = offset
        for y in range(src.height):
            for x in range(src.width):
                nx, ny = x + dx, y + dy
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    self.pixels[ny][nx] = src.pixels[y][x]

    def point(self, func):
        new_pixels = [[func(self.pixels[y][x])
                       for x in range(self.width)]
                      for y in range(self.height)]
        return Image(self.width, self.height, new_pixels)

    def histogram(self):
        hist = [0] * 256
        for row in self.pixels:
            for v in row:
                hist[v] += 1
        return hist

    def resize_nearest(self, new_w, new_h):
        new_pixels = []
        for y in range(new_h):
            row = []
            for x in range(new_w):
                sx = int(x * self.width / new_w)
                sy = int(y * self.height / new_h)
                sx = min(sx, self.width - 1)
                sy = min(sy, self.height - 1)
                row.append(self.pixels[sy][sx])
            new_pixels.append(row)
        return Image(new_w, new_h, new_pixels)

    def save(self, path):
        """保存为灰度 PNG（调试用）"""
        _write_png_gray(path, self.pixels, self.width, self.height)

    def convert_rgb(self):
        """返回 RGBImage，用于 save_debug 画分割线"""
        rgb = RGBImage(self.width, self.height)
        for y in range(self.height):
            for x in range(self.width):
                v = self.pixels[y][x]
                rgb.pixels[y][x] = (v, v, v)
        return rgb


class RGBImage:
    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.pixels = [[(255, 255, 255)] * width for _ in range(height)]

    @property
    def size(self):
        return (self.width, self.height)

    def load(self):
        return _RGBPixelAccessor(self.pixels, self.width, self.height)

    def save(self, path):
        _write_png_rgb(path, self.pixels, self.width, self.height)


class _PixelAccessor:
    def __init__(self, pixels, w, h):
        self._pixels = pixels
        self._w = w
        self._h = h

    def __getitem__(self, key):
        x, y = key
        return self._pixels[y][x]

    def __setitem__(self, key, value):
        x, y = key
        self._pixels[y][x] = value


class _RGBPixelAccessor:
    def __init__(self, pixels, w, h):
        self._pixels = pixels

    def __getitem__(self, key):
        x, y = key
        return self._pixels[y][x]

    def __setitem__(self, key, value):
        x, y = key
        self._pixels[y][x] = value


# ─────────────────────────────────────────────
# PNG 读写（纯标准库）
# ─────────────────────────────────────────────

def _read_png(path):
    """读取 PNG，返回 Image（灰度）"""
    with open(path, "rb") as f:
        data = f.read()

    assert data[:8] == b'\x89PNG\r\n\x1a\n', "不是有效的 PNG 文件"

    pos = 8
    width = height = 0
    bit_depth = color_type = 0
    idat_chunks = []
    palette = []

    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos+4])[0]
        chunk_type = data[pos+4:pos+8]
        chunk_data = data[pos+8:pos+8+length]
        pos += 12 + length

        if chunk_type == b"IHDR":
            width = struct.unpack(">I", chunk_data[0:4])[0]
            height = struct.unpack(">I", chunk_data[4:8])[0]
            bit_depth = chunk_data[8]
            color_type = chunk_data[9]
        elif chunk_type == b"PLTE":
            for i in range(0, len(chunk_data), 3):
                palette.append((chunk_data[i], chunk_data[i+1], chunk_data[i+2]))
        elif chunk_type == b"IDAT":
            idat_chunks.append(chunk_data)
        elif chunk_type == b"IEND":
            break

    raw = zlib.decompress(b"".join(idat_chunks))

    # 根据颜色类型计算每像素字节数
    # color_type: 0=灰度, 2=RGB, 3=索引, 4=灰度+Alpha, 6=RGBA
    if color_type == 0:   # 灰度
        cpp = 1
    elif color_type == 2: # RGB
        cpp = 3
    elif color_type == 3: # 索引（调色板）
        cpp = 1
    elif color_type == 4: # 灰度+Alpha
        cpp = 2
    elif color_type == 6: # RGBA
        cpp = 4
    else:
        cpp = 3

    stride = width * cpp + 1  # +1 for filter byte
    pixels = []

    prev_row = [0] * (width * cpp)

    for y in range(height):
        offset = y * stride
        filter_type = raw[offset]
        row_raw = list(raw[offset+1:offset+1+width*cpp])

        # PNG 滤波器还原
        if filter_type == 0:  # None
            row = row_raw
        elif filter_type == 1:  # Sub
            row = row_raw[:]
            for i in range(cpp, len(row)):
                row[i] = (row[i] + row[i-cpp]) & 0xFF
        elif filter_type == 2:  # Up
            row = [(row_raw[i] + prev_row[i]) & 0xFF for i in range(len(row_raw))]
        elif filter_type == 3:  # Average
            row = row_raw[:]
            for i in range(len(row)):
                a = row[i-cpp] if i >= cpp else 0
                b = prev_row[i]
                row[i] = (row[i] + (a + b) // 2) & 0xFF
        elif filter_type == 4:  # Paeth
            row = row_raw[:]
            for i in range(len(row)):
                a = row[i-cpp] if i >= cpp else 0
                b = prev_row[i]
                c = prev_row[i-cpp] if i >= cpp else 0
                p = a + b - c
                pa = abs(p - a)
                pb = abs(p - b)
                pc = abs(p - c)
                if pa <= pb and pa <= pc:
                    pr = a
                elif pb <= pc:
                    pr = b
                else:
                    pr = c
                row[i] = (row[i] + pr) & 0xFF
        else:
            row = row_raw

        prev_row = row

        # 转换为灰度
        gray_row = []
        for x in range(width):
            base = x * cpp
            if color_type == 0:   # 灰度
                gray_row.append(row[base])
            elif color_type == 2: # RGB
                r, g, b = row[base], row[base+1], row[base+2]
                gray_row.append(int(0.299*r + 0.587*g + 0.114*b))
            elif color_type == 3: # 索引
                idx = row[base]
                if idx < len(palette):
                    r, g, b = palette[idx]
                else:
                    r = g = b = 0
                gray_row.append(int(0.299*r + 0.587*g + 0.114*b))
            elif color_type == 4: # 灰度+Alpha：合成到白底
                gray = row[base]
                alpha = row[base+1]
                gray_row.append((gray * alpha + 255 * (255 - alpha)) // 255)
            elif color_type == 6: # RGBA：合成到白底
                r, g, b, a = row[base], row[base+1], row[base+2], row[base+3]
                r = (r * a + 255 * (255 - a)) // 255
                g = (g * a + 255 * (255 - a)) // 255
                b = (b * a + 255 * (255 - a)) // 255
                gray_row.append(int(0.299*r + 0.587*g + 0.114*b))
            else:
                gray_row.append(128)

        pixels.append(gray_row)

    return Image(width, height, pixels)


def _write_png_gray(path, pixels, width, height):
    def make_chunk(chunk_type, data):
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    raw = b""
    for row in pixels:
        raw += b"\x00" + bytes(row)
    idat = zlib.compress(raw)

    png = b'\x89PNG\r\n\x1a\n'
    png += make_chunk(b"IHDR", ihdr)
    png += make_chunk(b"IDAT", idat)
    png += make_chunk(b"IEND", b"")

    with open(path, "wb") as f:
        f.write(png)


def _write_png_rgb(path, pixels, width, height):
    def make_chunk(chunk_type, data):
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    raw = b""
    for row in pixels:
        raw += b"\x00"
        for r, g, b in row:
            raw += bytes([r, g, b])
    idat = zlib.compress(raw)

    png = b'\x89PNG\r\n\x1a\n'
    png += make_chunk(b"IHDR", ihdr)
    png += make_chunk(b"IDAT", idat)
    png += make_chunk(b"IEND", b"")

    with open(path, "wb") as f:
        f.write(png)


# ─────────────────────────────────────────────
# 以下逻辑与原版完全一致，仅替换 PIL API
# ─────────────────────────────────────────────

def _read_ppm(data):
    """解析 PPM/PGM 二进制数据，返回 Image（灰度）"""
    # 跳过注释行，解析头部
    pos = 0

    def skip_whitespace_and_comments():
        nonlocal pos
        while pos < len(data):
            if data[pos:pos+1] == b'#':
                while pos < len(data) and data[pos:pos+1] != b'\n':
                    pos += 1
            elif data[pos:pos+1] in (b' ', b'\t', b'\n', b'\r'):
                pos += 1
            else:
                break

    def read_token():
        nonlocal pos
        skip_whitespace_and_comments()
        token = b''
        while pos < len(data) and data[pos:pos+1] not in (b' ', b'\t', b'\n', b'\r'):
            token += data[pos:pos+1]
            pos += 1
        return token.decode()

    magic = read_token()   # P5=灰度PGM, P6=彩色PPM
    width = int(read_token())
    height = int(read_token())
    maxval = int(read_token())
    pos += 1  # 跳过头部后的一个空白字节

    pixels = []
    if magic == 'P5':  # 灰度 PGM
        for y in range(height):
            row = list(data[pos:pos+width])
            pixels.append(row)
            pos += width
    elif magic == 'P6':  # 彩色 PPM，转灰度
        for y in range(height):
            row = []
            for x in range(width):
                r = data[pos]
                g = data[pos+1]
                b = data[pos+2]
                row.append(int(0.299*r + 0.587*g + 0.114*b))
                pos += 3
            pixels.append(row)
    else:
        raise ValueError(f"不支持的 PPM 格式: {magic}")

    return Image(width, height, pixels)


def _read_jpeg(path):
    """用 djpeg 把 JPEG 转成灰度 PPM，再解析"""
    result = subprocess.run(
        ['djpeg', '-grayscale', '-pnm', path],
        capture_output=True
    )
    if result.returncode != 0:
        raise RuntimeError(f"djpeg 失败: {result.stderr.decode()}")
    return _read_ppm(result.stdout)


def load_image(path):
    """自动识别 JPEG 或 PNG 并解码"""
    with open(path, 'rb') as f:
        header = f.read(4)
    if header[:2] == b'\xff\xd8':
        return _read_jpeg(path)
    elif header[:4] == b'\x89PNG':
        return _read_png(path)
    else:
        raise ValueError(f"不支持的图片格式: {header.hex()}")


def auto_threshold(img):
    hist = img.histogram()
    total = sum(hist)
    if total == 0:
        return 128

    mean = sum(i * hist[i] for i in range(256)) / total

    low = 0
    while low < 255 and hist[low] == 0:
        low += 1
    high = 255
    while high > 0 and hist[high] == 0:
        high -= 1

    if high - low < 40:
        return int(mean)

    t = int((low + high) / 2)
    t = min(220, t + 10)
    return t


def ensure_binary(img, threshold=None):
    if threshold is None:
        threshold = auto_threshold(img)
    return img.point(lambda p: 0 if p < threshold else 255)


def find_foreground_bbox(img):
    pixels = img.load()
    w, h = img.size
    min_x, min_y = w, h
    max_x, max_y = -1, -1

    for y in range(h):
        for x in range(w):
            if pixels[x, y] < 128:
                if x < min_x: min_x = x
                if y < min_y: min_y = y
                if x > max_x: max_x = x
                if y > max_y: max_y = y

    if max_x == -1:
        return None
    return (min_x, min_y, max_x + 1, max_y + 1)


def crop_to_foreground(img, margin=0):
    bbox = find_foreground_bbox(img)
    if bbox is None:
        return img.copy()
    min_x, min_y, max_x, max_y = bbox
    min_x = max(0, min_x - margin)
    min_y = max(0, min_y - margin)
    max_x = min(img.size[0], max_x + margin)
    max_y = min(img.size[1], max_y + margin)
    return img.crop((min_x, min_y, max_x, max_y))


def normalize(img, size=SIZE, padding=PADDING):
    img = ensure_binary(img)
    bbox = find_foreground_bbox(img)
    if bbox is None:
        return Image(size[0], size[1])

    min_x, min_y, max_x, max_y = bbox
    min_x = max(0, min_x - 1)
    min_y = max(0, min_y - 1)
    max_x = min(img.size[0], max_x + 1)
    max_y = min(img.size[1], max_y + 1)
    img = img.crop((min_x, min_y, max_x, max_y))

    iw, ih = img.size
    target_w, target_h = size
    max_w = target_w - padding * 2
    max_h = target_h - padding * 2

    if iw > max_w or ih > max_h:
        scale = min(max_w / iw, max_h / ih)
        nw = max(1, int(round(iw * scale)))
        nh = max(1, int(round(ih * scale)))
        img = img.resize_nearest(nw, nh)
        iw, ih = img.size

    canvas = Image(target_w, target_h)
    x = (target_w - iw) // 2
    y = (target_h - ih) // 2
    canvas.paste(img, (x, y))
    return canvas


def get_black_pixels(img):
    pixels = img.load()
    w, h = img.size
    pts = set()
    for y in range(h):
        for x in range(w):
            if pixels[x, y] < 128:
                pts.add((x, y))
    return pts


def shift_image(img, dx=0, dy=0):
    out = Image(img.width, img.height)
    out.paste(img, (dx, dy))
    return out


def overlap_score(img1, img2):
    s1 = get_black_pixels(img1)
    s2 = get_black_pixels(img2)
    if not s1 or not s2:
        return 0.0
    inter = len(s1 & s2)
    union = len(s1 | s2)
    iou = inter / union if union else 0.0
    dice = 2 * inter / (len(s1) + len(s2))
    return 0.5 * iou + 0.5 * dice


def similarity(img1, img2):
    best = 0.0
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            shifted = shift_image(img1, dx=dx, dy=dy)
            score = overlap_score(shifted, img2)
            if score > best:
                best = score
    return best


def count_holes(img):
    pixels = img.load()
    w, h = img.size
    visited = [[False] * w for _ in range(h)]

    def is_white(x, y):
        return pixels[x, y] >= 128

    def flood_fill(sx, sy):
        stack = [(sx, sy)]
        visited[sy][sx] = True
        touches_border = False
        while stack:
            x, y = stack.pop()
            if x == 0 or y == 0 or x == w - 1 or y == h - 1:
                touches_border = True
            for nx, ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if 0 <= nx < w and 0 <= ny < h and not visited[ny][nx] and is_white(nx, ny):
                    visited[ny][nx] = True
                    stack.append((nx, ny))
        return touches_border

    holes = 0
    for y in range(h):
        for x in range(w):
            if not visited[y][x] and is_white(x, y):
                if not flood_fill(x, y):
                    holes += 1
    return holes


def load_templates(template_dir=TEMPLATE_DIR):
    templates = {str(i): [] for i in range(10)}

    for name in os.listdir(template_dir):
        if not name.lower().endswith(".png"):
            continue
        digit = name[0]
        if digit not in templates:
            continue
        path = os.path.join(template_dir, name)
        img = load_image(path)
        img = normalize(img)
        templates[digit].append({
            "img": img,
            "feat": extract_features(img),
        })

    for digit in "0123456789":
        if not templates[digit]:
            raise FileNotFoundError(f"缺少数字 {digit} 的模板")

    return templates


def recognize_char_img(img, templates):
    norm = normalize(img)
    feat = extract_features(norm)
    scores = []

    for digit, tpl_list in templates.items():
        best_for_digit = -1.0
        for tpl in tpl_list:
            s_img = similarity(norm, tpl["img"])
            s_feat = feature_score(feat, tpl["feat"])
            score = 0.75 * s_img + 0.25 * s_feat
            if score > best_for_digit:
                best_for_digit = score
        scores.append((digit, best_for_digit))

    scores.sort(key=lambda x: x[1], reverse=True)
    best_digit, best_score = scores[0]
    return best_digit, best_score, scores, norm


def vertical_projection(img):
    pixels = img.load()
    w, h = img.size
    proj = []
    for x in range(w):
        cnt = sum(1 for y in range(h) if pixels[x, y] < 128)
        proj.append(cnt)
    return proj


def split_by_projection(img, expected=4):
    proj = vertical_projection(img)
    w, h = img.size
    bbox = find_foreground_bbox(img)

    if bbox is None:
        avg_w = w // expected
        return [(i * avg_w, (i+1) * avg_w if i < expected-1 else w) for i in range(expected)]

    left, _, right, _ = bbox
    total_w = right - left
    base_cuts = [left + total_w * i // expected for i in range(1, expected)]
    cuts = []

    for c in base_cuts:
        search_left = max(left + 1, c - 4)
        search_right = min(right - 1, c + 4)
        best_x = c
        best_val = proj[c] if 0 <= c < len(proj) else 999999
        for x in range(search_left, search_right + 1):
            if proj[x] < best_val:
                best_val = proj[x]
                best_x = x
        cuts.append(best_x)

    spans = []
    prev = left
    for c in cuts:
        spans.append((prev, c))
        prev = c
    spans.append((prev, right))

    fixed = []
    for a, b in spans:
        if b - a < 2:
            b = a + 2
        fixed.append((a, b))

    return fixed


def split_captcha(img):
    img = ensure_binary(img, threshold=150)
    img = crop_to_foreground(img, margin=0)
    spans = split_by_projection(img, expected=EXPECTED_CHARS)

    chars = []
    h = img.size[1]
    for a, b in spans:
        a2 = max(0, a)
        b2 = min(img.size[0], b)
        ch = img.crop((a2, 0, b2, h))
        ch = clean_char(ch)
        chars.append(ch)

    return img, spans, chars


def save_debug(preprocessed, spans, chars, normalized_chars):
    os.makedirs("debug", exist_ok=True)
    preprocessed.save("debug/1_preprocessed.png")

    preview = preprocessed.convert_rgb()
    px = preview.load()
    w, h = preview.size
    for a, b in spans:
        for y in range(h):
            if 0 <= a < w:
                px[a, y] = (255, 0, 0)
            if 0 <= b-1 < w:
                px[b-1, y] = (0, 0, 255)
    preview.save("debug/2_split_preview.png")

    for i, ch in enumerate(chars):
        ch.save(f"debug/3_char_{i}.png")
    for i, ch in enumerate(normalized_chars):
        ch.save(f"debug/4_char_norm_{i}.png")


def solve_captcha(path):
    templates = load_templates()
    raw = load_image(path)
    preprocessed, spans, chars = split_captcha(raw)

    result = []
    infos = []
    normalized_chars = []

    for ch in chars:
        digit, score, scores, norm = recognize_char_img(ch, templates)
        result.append(digit)
        infos.append((digit, score, scores))
        normalized_chars.append(norm)

    # save_debug(preprocessed, spans, chars, normalized_chars)
    return "".join(result), infos


def remove_small_noise(img, min_neighbors=2):
    pixels = img.load()
    w, h = img.size
    out = img.copy()
    out_px = out.load()

    for y in range(1, h - 1):
        for x in range(1, w - 1):
            if pixels[x, y] < 128:
                black_neighbors = sum(
                    1 for yy in (-1, 0, 1) for xx in (-1, 0, 1)
                    if not (xx == 0 and yy == 0) and pixels[x+xx, y+yy] < 128
                )
                if black_neighbors <= min_neighbors:
                    out_px[x, y] = 255
    return out


def clean_char(img):
    img = ensure_binary(img)
    img = remove_small_noise(img, min_neighbors=2)
    img = crop_to_foreground(img, margin=1)
    return img


def extract_features(img):
    pixels = img.load()
    w, h = img.size
    black = [(x, y) for y in range(h) for x in range(w) if pixels[x, y] < 128]
    total_black = len(black)

    if total_black == 0:
        return {"holes": 0, "top": 0.0, "bottom": 0.0, "left": 0.0, "right": 0.0}

    top    = sum(1 for x, y in black if y < h / 2) / total_black
    bottom = sum(1 for x, y in black if y >= h / 2) / total_black
    left   = sum(1 for x, y in black if x < w / 2) / total_black
    right  = sum(1 for x, y in black if x >= w / 2) / total_black

    return {"holes": count_holes(img), "top": top, "bottom": bottom, "left": left, "right": right}


def feature_score(f1, f2):
    score = 0.0
    if f1["holes"] == f2["holes"]:
        score += 1.0
    else:
        score -= 0.5 * abs(f1["holes"] - f2["holes"])
    score += 1.0 - abs(f1["top"]    - f2["top"])
    score += 1.0 - abs(f1["bottom"] - f2["bottom"])
    score += 1.0 - abs(f1["left"]   - f2["left"])
    score += 1.0 - abs(f1["right"]  - f2["right"])
    return score / 5.0


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python solve_captcha.py captcha.png")
        sys.exit(1)

    path = sys.argv[1]
    result, infos = solve_captcha(path)

    for i, (digit, score, scores) in enumerate(infos, 1):
        print(f"[第{i}位]")
        print(f"  识别结果: {digit}")
        print(f"  最高相似度: {score:.4f}")
        print(f"  前3名: {scores[:3]}")

    print("最终结果:", result)


if __name__ == "__main__":
    main()