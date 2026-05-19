import re, pathlib
root = pathlib.Path(r"g:/SNEC-RESEARCH")
for f in root.glob("chunk*.js"):
    t = f.read_text(encoding="utf-8", errors="ignore")
    apis = sorted(set(re.findall(r"/api/[A-Za-z0-9_]+", t)))
    if apis:
        print(f"--- {f.name} ---")
        for a in apis: print(a)
