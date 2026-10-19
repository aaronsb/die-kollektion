"""Dump MonoBehaviour typetrees whose m_Name matches any argument (substring)."""
import sys, json, UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION = "6000.0.75f1"
env = UnityPy.load(sys.argv[1])
pats = sys.argv[2:]
exact = [p[1:] for p in pats if p.startswith("=")]
subs = [p for p in pats if not p.startswith("=")]
for obj in env.objects:
    if obj.type.name != "MonoBehaviour": continue
    try:
        tt = obj.read_typetree()
    except Exception as e:
        continue
    n = tt.get("m_Name", "")
    if n in exact or any(s in n for s in subs):
        print(f"##### {n} (path_id={obj.path_id})")
        print(json.dumps(tt, indent=1, default=str)[:20000])
