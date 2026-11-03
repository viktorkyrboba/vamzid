import json, runpy
W = runpy.run_path("tools/desc_web_src.py")["W"]
json.dump(W, open("tools/desc_web.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(len(W), "записей из интернета")
