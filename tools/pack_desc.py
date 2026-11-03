#!/usr/bin/env python3
"""Собирает desc.json: сначала сгенерированные описания, поверх них — описания из интернета (desc_web.json: {код: [текст, "Параметр: знач; ...", "источник"]})."""
import json, os
g = json.load(open("tools/desc_generated.json", encoding="utf-8"))
w = json.load(open("tools/desc_web.json", encoding="utf-8")) if os.path.exists("tools/desc_web.json") else {}
g.update(w)
json.dump(g, open("desc.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print("desc.json:", len(g), "описаний,", len(w), "из интернета,", os.path.getsize("desc.json") // 1024, "КБ")
