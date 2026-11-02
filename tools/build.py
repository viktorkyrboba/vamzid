#!/usr/bin/env python3
"""Сборка сайта «Все Для Дома».

Исходник: src/index.html (читаемый, картинки — файлы в img/).
  python3 tools/build.py all      -> всё сразу (gh + cf)
  python3 tools/build.py gh       -> index.html в корне для GitHub Pages
  python3 tools/build.py cf       -> папка dist/ для Cloudflare Pages (основной хостинг)
  python3 tools/build.py single X -> один самодостаточный HTML-файл X (картинки встроены)
Во всех вариантах строгий CSP: скрипты разрешены только по их хешам.
"""
import base64, hashlib, re, sys, pathlib, shutil
ROOT = pathlib.Path(__file__).resolve().parent.parent
# основной адрес сайта: для canonical и превью в соцсетях
SITE_CF = "https://vamzid.pages.dev/"
SITE_GH = "https://viktorkyrboba.github.io/vamzid/"
SRC = (ROOT / "src/index.html").read_text(encoding="utf-8")

def order_origin():
    """Адрес сервера заказов из const ORDER_ENDPOINT — разрешаем подключение только к нему."""
    m = re.search(r'const ORDER_ENDPOINT="([^"]*)"', SRC)
    url = m.group(1) if m else ""
    if not url:
        return "'none'"
    o = re.match(r"(https://[^/]+)", url)
    if not o:
        sys.exit("ORDER_ENDPOINT должен начинаться с https://")
    return o.group(1)

def csp(script_src):
    return ("<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; "
            f"script-src {script_src}; style-src 'unsafe-inline'; img-src 'self' data:; "
            f"connect-src {order_origin()}; media-src 'none'; frame-src 'none'; font-src 'none'; object-src 'none'; "
            "manifest-src 'none'; worker-src 'none'; base-uri 'none'; form-action 'none'\">")

def inline_hashes(html):
    out = []
    for m in re.finditer(r"<script(?![^>]*ld\+json)[^>]*>(.*?)</script>", html, re.S):
        out.append("'sha256-" + base64.b64encode(hashlib.sha256(m.group(1).encode()).digest()).decode() + "'")
    return " ".join(out)

def page(site):
    html = SRC.replace("__SITE__", site).replace("<!--PRELOAD-->", '<link rel="preload" as="image" href="img/p1.jpg" fetchpriority="high">')
    return html.replace("<!--CSP-->", csp(inline_hashes(html)))

def build_gh():
    html = page(SITE_CF)  # canonical указывает на основной адрес (Cloudflare)
    (ROOT / "index.html").write_text(html, encoding="utf-8")
    print("index.html", len(html) // 1024, "KB")

def build_cf():
    d = ROOT / "dist"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir()
    (d / "index.html").write_text(page(SITE_CF), encoding="utf-8")
    shutil.copytree(ROOT / "img", d / "img")
    for f in ["404.html", "robots.txt", "og.jpg", "_headers"]:
        shutil.copy(ROOT / f, d / f)
    print("dist/", sum(p.stat().st_size for p in d.rglob("*") if p.is_file()) // 1024, "KB")

def build_single(dst):
    vars_block = re.search(r'<style id="img-vars">(.*?)</style>', SRC).group(1)
    def inline(m):
        data = (ROOT / m.group(1)).read_bytes()
        return 'url("data:image/jpeg;base64,' + base64.b64encode(data).decode() + '")'
    inlined = re.sub(r"url\((img/[^)]+)\)", inline, vars_block)
    html = SRC.replace("__SITE__", SITE_CF).replace(f'<style id="img-vars">{vars_block}</style>', "").replace("<!--PRELOAD-->\n", "")
    # тяжёлые встроенные картинки — в конец страницы, чтобы не блокировать первый показ текста
    html = html.replace("</body>", f'<style id="img-vars">{inlined}</style>\n</body>')
    # во встроенной версии хост может добавлять свои скрипты, поэтому без хешей
    html = html.replace("<!--CSP-->", csp("'unsafe-inline'"))
    pathlib.Path(dst).write_text(html, encoding="utf-8")
    print(dst, len(html) // 1024, "KB")

if __name__ == "__main__":
    if sys.argv[1:2] == ["all"]: build_gh(); build_cf()
    elif sys.argv[1:2] == ["gh"]: build_gh()
    elif sys.argv[1:2] == ["cf"]: build_cf()
    elif sys.argv[1:2] == ["single"]: build_single(sys.argv[2])
    else: print(__doc__)
