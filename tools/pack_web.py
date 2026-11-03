import json, runpy, os
W = runpy.run_path("tools/desc_web_src.py")["W"]
for f in ["tools/desc_web_src2.py"]:
    if os.path.exists(f): W.update(runpy.run_path(f)["W"])
json.dump(W, open("tools/desc_web.json", "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
print(len(W), "записей из интернета")
