#!/usr/bin/env python3
"""Импорт товаров из tools/catalog-auto.tsv в PRODUCTS (src/index.html).
Строки 'old' — уже добавленные товары (по порядку): им дописываются code и img2 (фото с vamzid.md).
Остальные строки — новые товары. Запуск: python3 tools/import_auto.py  (один раз; повторный запуск ничего не дублирует)."""
import re, json, sys
from urllib.parse import quote
R = "Автомобильная тематика"
CAT = {"K": ("Музыка и звук", "Авто-колонки"), "S": ("Музыка и звук", "Звуковой сигнал"),
       "PR": ("Музыка и звук", "Предохранители"), "CH": ("Обустройство салона", "Автомобильные чехлы"),
       "PD": ("Обустройство салона", "Подушки"), "PT": ("Свет и фары", "Противотуманки"),
       "HM": ("Уход за автомобилем", "Автомобильная химия"), "SM": ("Уход за автомобилем", "Герметики и смазки"),
       "TN": ("Уход за автомобилем", "Тонировка"), "US": ("Аксессуары", "Зарядки и бусты")}
REPL = [("ОСВЕЖИТ. ", "ОСВЕЖИТЕЛЬ "), ("ПОЛИРОЛЬ-ОЧ.ПЛАСТИКА", "ПОЛИРОЛЬ-ОЧИСТИТЕЛЬ ПЛАСТИКА"),
        ("ПОЛИР.ПАСТА", "ПОЛИРОВАЛЬНАЯ ПАСТА"), ("СИСТ.ВЕНТИЛЯЦИИ", "СИСТЕМЫ ВЕНТИЛЯЦИИ"),
        ("ТРИГЕР ПРОФ.", "ТРИГЕР ПРОФЕССИОНАЛЬНЫЙ "), ("ХОЛОД.ВОСК", "ХОЛОДНЫЙ ВОСК"),
        ("ПЕНА-ОГНЕТУШ", "ПЕНА-ОГНЕТУШИТЕЛЬ"), ("СР-ВО", "СРЕДСТВО"), ("ПАЛОЧКИ РЕЗИН.2ШТ", "ПАЛОЧКИ РЕЗИНОВЫЕ 2ШТ"),
        ("ПОДУШКА ОТРОПЕДИЧ.НА", "ПОДУШКА ОРТОПЕДИЧЕСКАЯ НА"), ("ПОДУШКА ОТРОПЕДИЧ.", "ПОДУШКА ОРТОПЕДИЧЕСКАЯ"),
        ("КОНЦ.", "КОНЦЕНТРАТ "), ("СИЛИК.SILICONE", "СИЛИКОНОВАЯ SILICONE"), ("УНИВЕРС.PG", "УНИВЕРСАЛЬНАЯ PG"),
        ("В ЖЕЛ.КОР.", "В ЖЕЛЕЗНОЙ КОРОБКЕ "), ("НОВАЯ.МАШИНА", "НОВАЯ МАШИНА"), ("ПЛЕНКА АМЕРИКАНКА 75СМ3М", "ПЛЕНКА АМЕРИКАНКА 75СМ×3М"),
        ("ОЧИСТИТЕЛЬ ШИН И РЕЗИНЫ", "ОЧИСТИТЕЛЬ ШИН И РЕЗИНЫ")]
UNIT = {"МЛ": "мл", "Л": "л", "КГ": "кг", "Г": "г", "ШТ": "шт", "СМ": "см", "ММ": "мм"}
CT = re.compile(r"^[CС][TТ]\d{5,}$")

def nice(name):
    s = name
    for a, b in REPL: s = s.replace(a, b)
    out, art = [], None
    for tok in s.split():
        if CT.match(tok): art = tok; continue
        m = re.match(r"^(\d+(?:[.,]\d+)?)(МЛ|Л|КГ|Г|ШТ|СМ|ММ)$", tok)
        if m: out.append(m.group(1) + " " + UNIT[m.group(2)]); continue
        m = re.match(r"^(\d+)СМ×(\d+)М$", tok)
        if m: out.append(f"{m.group(1)} см × {m.group(2)} м"); continue
        if re.search(r"\d", tok): out.append(tok); continue      # коды и модели оставляем как есть
        if re.search("[А-Яа-яЁё]", tok): out.append(tok.lower()); continue
        if "-" in tok and not re.search(r"\d", tok): out.append("-".join(p.capitalize() if len(p) > 3 else p for p in tok.split("-"))); continue
        if re.search(r"\d", tok) or len(tok) <= 3: out.append(tok); continue
        out.append(tok.capitalize() if tok.isupper() else tok)
    t = " ".join(out)
    t = t[0].upper() + t[1:]
    return t, art

def url(folder, name, thumb=False):
    p = f"TOVARS/{folder}/{name}/" + ("1-228x228.png" if thumb else "1.png")
    return "https://vamzid.md/image/" + ("cache/" if thumb else "") + "catalog/" + quote(p, safe="/()+,.-_~")

rows = [l.rstrip("\n").split("|") for l in open("tools/catalog-auto.tsv", encoding="utf-8") if l.strip() and not l.startswith("#")]
old = [r for r in rows if r[4] == "old"]; new = [r for r in rows if r[4] != "old"]
s = open("src/index.html", encoding="utf-8").read()
i0 = s.index("const PRODUCTS=[") + len("const PRODUCTS=[")
i1 = s.index("\n];", i0)
lines = [l for l in s[i0:i1].split("\n") if l.strip()]
if any("code:" in l for l in lines): sys.exit("Уже импортировано (в PRODUCTS есть code:).")
assert len(lines) == len(old) == 99, (len(lines), len(old))
res = []
for l, r in zip(lines, old):
    l = l.rstrip(",")
    assert l.endswith("}")
    res.append(l[:-1] + f',code:"{r[0]}",img2:"{url(r[3], r[1])}"' + "}")
bad = []
for l, r in zip(lines, old):   # проверка: модель из названия сайта есть в нашем названии
    key = [t for t in r[1].split() if re.search(r"\d", t) and not CT.match(t)]
    n = re.search(r'n:"([^"]*)"', l).group(1).lower().replace("–", "-")
    if key and key[0].lower().replace(",", ",") not in n.replace(" ", "") and key[0].lower() not in n: bad.append((r[0], r[1], n))
for code, name, price, folder, k in new:
    g, x = CAT[k]; n, art = nice(name)
    d = (f"Арт. {art}." if art else "")
    thumb = url(folder, name, True) if folder != "-" else ""
    orig = url(folder, name) if folder != "-" else ""
    e = {"n": n, "r": R, "g": g, "x": x, "p": float(price) if "." in price else int(price)}
    parts = [f"n:{json.dumps(n, ensure_ascii=False)}", f'r:"{R}"', f'g:"{g}"', f'x:"{x}"', f"p:{e['p']}",
             f'img:""' if not orig else 'img:""', f'code:"{code}"']
    if orig: parts.append(f'img2:"{orig}"')
    if d: parts.append(f"d:{json.dumps(d, ensure_ascii=False)}")
    res.append("{" + ",".join(parts) + "}")
s = s[:i0] + "\n" + ",\n".join(res) + s[i1:]
open("src/index.html", "w", encoding="utf-8").write(s)
print("old", len(old), "new", len(new), "всего", len(res)); print("не прошли сверку:", bad)
