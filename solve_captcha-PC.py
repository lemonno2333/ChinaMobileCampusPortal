#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
from PIL import Image

TEMPLATE_DIR = "templates"
SIZE = (24, 32)
PADDING = 3
EXPECTED_CHARS = 4


def load_image(path):
    img = Image.open(path)

    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img)
        img = img.convert("L")
    else:
        img = img.convert("L")

    return img


def auto_threshold(img):
    hist = img.histogram()

    total = sum(hist)
    if total == 0:
        return 128

    # 计算平均灰度
    mean = sum(i * hist[i] for i in range(256)) / total

    # 找最暗和最亮的有效区间
    low = 0
    while low < 255 and hist[low] == 0:
        low += 1

    high = 255
    while high > 0 and hist[high] == 0:
        high -= 1

    # 如果图像对比度很低，保守一点
    if high - low < 40:
        return int(mean)

    # 用暗亮中点偏亮一点，尽量保住数字主体
    t = int((low + high) / 2)

    # 再向亮端偏移一点，避免背景发黑
    t = min(220, t + 10)

    return t


def ensure_binary(img, threshold=None):
    if threshold is None:
        threshold = auto_threshold(img)
    return img.point(lambda p: 0 if p < threshold else 255, mode="L")


def find_foreground_bbox(img):
    pixels = img.load()
    w, h = img.size

    min_x, min_y = w, h
    max_x, max_y = -1, -1

    for y in range(h):
        for x in range(w):
            if pixels[x, y] < 128:
                if x < min_x:
                    min_x = x
                if y < min_y:
                    min_y = y
                if x > max_x:
                    max_x = x
                if y > max_y:
                    max_y = y

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
        return Image.new("L", size, 255)

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

    # 只在太大时缩小，不主动放大
    if iw > max_w or ih > max_h:
        scale = min(max_w / iw, max_h / ih)
        nw = max(1, int(round(iw * scale)))
        nh = max(1, int(round(ih * scale)))
        img = img.resize((nw, nh), Image.Resampling.NEAREST)
        iw, ih = img.size

    canvas = Image.new("L", size, 255)
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
    out = Image.new("L", img.size, 255)
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

            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < w and 0 <= ny < h and not visited[ny][nx] and is_white(nx, ny):
                    visited[ny][nx] = True
                    stack.append((nx, ny))

        return touches_border

    holes = 0
    for y in range(h):
        for x in range(w):
            if not visited[y][x] and is_white(x, y):
                touches_border = flood_fill(x, y)
                if not touches_border:
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
        cnt = 0
        for y in range(h):
            if pixels[x, y] < 128:
                cnt += 1
        proj.append(cnt)

    return proj


def split_by_projection(img, expected=4):
    proj = vertical_projection(img)
    w, h = img.size

    bbox = find_foreground_bbox(img)
    if bbox is None:
        avg_w = w // expected
        return [(i * avg_w, (i + 1) * avg_w if i < expected - 1 else w) for i in range(expected)]

    left, _, right, _ = bbox
    total_w = right - left

    # 先按整体宽度均分出理论分界点
    base_cuts = [left + total_w * i // expected for i in range(1, expected)]

    cuts = []

    for c in base_cuts:
        # 在理论分界点附近搜索“最低谷”
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

    # 防止切出来太窄
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

    preview = preprocessed.convert("RGB")
    px = preview.load()
    w, h = preview.size
    for a, b in spans:
        for y in range(h):
            if 0 <= a < w:
                px[a, y] = (255, 0, 0)
            if 0 <= b - 1 < w:
                px[b - 1, y] = (0, 0, 255)
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

    save_debug(preprocessed, spans, chars, normalized_chars)

    return "".join(result), infos


def remove_small_noise(img, min_neighbors=2):
    pixels = img.load()
    w, h = img.size
    out = img.copy()
    out_px = out.load()

    for y in range(1, h - 1):
        for x in range(1, w - 1):
            if pixels[x, y] < 128:
                black_neighbors = 0
                for yy in (-1, 0, 1):
                    for xx in (-1, 0, 1):
                        if xx == 0 and yy == 0:
                            continue
                        if pixels[x + xx, y + yy] < 128:
                            black_neighbors += 1

                # 孤立黑点去掉
                if black_neighbors <= min_neighbors:
                    out_px[x, y] = 255

    return out


def clean_char(img):
    # 不要用固定 128，改成自动阈值
    img = ensure_binary(img)

    # 轻度去噪
    img = remove_small_noise(img, min_neighbors=2)

    # 再裁边
    img = crop_to_foreground(img, margin=1)
    return img


def extract_features(img):
    pixels = img.load()
    w, h = img.size

    black = []
    for y in range(h):
        for x in range(w):
            if pixels[x, y] < 128:
                black.append((x, y))

    total_black = len(black)
    if total_black == 0:
        return {
            "holes": 0,
            "top": 0.0,
            "bottom": 0.0,
            "left": 0.0,
            "right": 0.0,
        }

    top = sum(1 for x, y in black if y < h / 2) / total_black
    bottom = sum(1 for x, y in black if y >= h / 2) / total_black
    left = sum(1 for x, y in black if x < w / 2) / total_black
    right = sum(1 for x, y in black if x >= w / 2) / total_black

    return {
        "holes": count_holes(img),
        "top": top,
        "bottom": bottom,
        "left": left,
        "right": right,
    }


def feature_score(f1, f2):
    score = 0.0

    if f1["holes"] == f2["holes"]:
        score += 1.0
    else:
        score -= 0.5 * abs(f1["holes"] - f2["holes"])

    score += 1.0 - abs(f1["top"] - f2["top"])
    score += 1.0 - abs(f1["bottom"] - f2["bottom"])
    score += 1.0 - abs(f1["left"] - f2["left"])
    score += 1.0 - abs(f1["right"] - f2["right"])

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
    print("调试文件已保存到 debug/ 目录")


if __name__ == "__main__":
    main()