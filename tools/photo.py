#!/usr/bin/env python3
"""Подготовка фото товара: python3 tools/photo.py вход.(jpg|png) выход.jpg [размер=800]
Обрезает пустые поля, убирает шум/артефакты JPEG, увеличивает, добавляет резкость,
выравнивает белый фон и ставит товар по центру квадрата. Оригинал не меняется."""
import sys, cv2, numpy as np

def flat_bg_to_white(img, tol=26):
    """Если у фото ровный серый/бежевый фон (не белый) — заменяет его на белый.
    Фото-сцены с неоднородным фоном не трогаем."""
    h, w = img.shape[:2]
    ring = np.concatenate([img[:3].reshape(-1, 3), img[-3:].reshape(-1, 3),
                           img[:, :3].reshape(-1, 3), img[:, -3:].reshape(-1, 3)]).astype(np.float32)
    med = np.median(ring, axis=0)
    if med.min() >= 247 or np.abs(ring - med).max(axis=1).mean() > 9:
        return img
    dist = np.abs(img.astype(np.float32) - med).max(axis=2)
    bg = (dist <= tol).astype(np.uint8)
    n, lab = cv2.connectedComponents(bg, connectivity=4)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))) - {0}
    m = np.isin(lab, list(edge)).astype(np.uint8) * 255
    if m.mean() < 40:      # фон занимает мало — это не студийное фото, не трогаем
        return img
    m = cv2.dilate(m, np.ones((3, 3), np.uint8))
    a = cv2.GaussianBlur(m, (0, 0), 1.0).astype(np.float32)[..., None] / 255
    return (img * (1 - a) + 255 * a).astype(np.uint8)

def enhance(img, size=800, fill=0.9):
    img = img[..., :3] if img.ndim == 3 and img.shape[2] == 4 else img
    # обрезка белых полей
    mask = (img.min(axis=2) < 236).astype(np.uint8)
    ys, xs = np.where(mask)
    if len(xs):
        img = img[max(ys.min()-2, 0):ys.max()+3, max(xs.min()-2, 0):xs.max()+3]
    img = cv2.fastNlMeansDenoisingColored(img, None, 4, 4, 5, 15)
    img = flat_bg_to_white(img)
    h, w = img.shape[:2]
    k = size * fill / max(h, w)
    out = cv2.resize(img, (max(1, round(w*k)), max(1, round(h*k))),
                     interpolation=cv2.INTER_LANCZOS4 if k > 1 else cv2.INTER_AREA)
    blur = cv2.GaussianBlur(out, (0, 0), 1.6)
    out = cv2.addWeighted(out, 1.7, blur, -0.7, 0)          # резкость (unsharp mask)
    f = out.astype(np.float32)
    f = np.clip(f * (255.0 / 246.0), 0, 255)                # почти белое -> чисто белое
    out = f.astype(np.uint8)
    canvas = np.full((size, size, 3), 255, np.uint8)
    oh, ow = out.shape[:2]
    y, x = (size-oh)//2, (size-ow)//2
    canvas[y:y+oh, x:x+ow] = out
    return canvas

if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    size = int(sys.argv[3]) if len(sys.argv) > 3 else 800
    im = cv2.imread(src, cv2.IMREAD_UNCHANGED)
    if im is None: sys.exit("не удалось открыть " + src)
    if im.ndim == 3 and im.shape[2] == 4:                    # прозрачный фон -> белый
        a = im[..., 3:4].astype(np.float32)/255
        im = (im[..., :3]*a + 255*(1-a)).astype(np.uint8)
    cv2.imwrite(dst, enhance(im, size), [cv2.IMWRITE_JPEG_QUALITY, 90])
