"""Summarize every car-definition ScriptableObject (same script as Mammoth) in a bundle."""
import sys, UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION = "6000.0.75f1"
env = UnityPy.load(sys.argv[1])
CAR_SCRIPT = 7795854033978393654
rows = []
for obj in env.objects:
    if obj.type.name != "MonoBehaviour": continue
    try: tt = obj.read_typetree()
    except Exception: continue
    if tt.get("m_Script", {}).get("m_PathID") != CAR_SCRIPT: continue
    s = tt["suspensionSetup"]; b = tt["carColliderBounds"]
    rows.append((tt["m_Name"], tt["ItemId"], tt["Name"]["m_TableEntryReference"]["m_KeyId"], tt["Type"], tt["Price"], tt["RequiredDlc"], tt["CountryCode"], tt["hasBed"], round(b["z"],2), s["radius"], s["suspensionTravel"]))
for r in sorted(rows): print(*r, sep="\t")
