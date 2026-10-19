"""Dump StringTable entries (id -> localized value) from a localization bundle."""
import sys, UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION = "6000.0.75f1"
env = UnityPy.load(sys.argv[1])
for obj in env.objects:
    if obj.type.name != "MonoBehaviour": continue
    try: tt = obj.read_typetree()
    except Exception: continue
    if "m_TableData" not in tt: continue
    for e in tt["m_TableData"]:
        print(tt["m_Name"], e["m_Id"], repr(e["m_Localized"]), sep="\t")
