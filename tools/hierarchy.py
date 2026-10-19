"""Print the transform hierarchy of a root GameObject with component types and local positions."""
import sys, UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION = "6000.0.75f1"
env = UnityPy.load(sys.argv[1])
root_name, maxdepth = sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 99
scripts = {}
def comp_desc(c):
    o = c.deref()
    t = o.type.name
    if t == "MonoBehaviour":
        try:
            tt = o.read_typetree()
            sp = tt["m_Script"]
            s = sp.get("m_PathID")
            return f"MB:{scripts.get(s, s)}"
        except Exception: return "MB:?"
    return t
# build monoscript name map from the monoscripts bundle next to the target bundle
import glob, os
for obj in UnityPy.load(glob.glob(os.path.join(os.path.dirname(sys.argv[1]), "*monoscripts*.bundle"))[0]).objects:
    if obj.type.name == "MonoScript":
        d = obj.read(); scripts[obj.path_id] = d.m_ClassName
roots = []
for obj in env.objects:
    if obj.type.name == "GameObject":
        go = obj.read()
        if go.m_Name == root_name:
            tr = go.m_Transform.read() if hasattr(go, "m_Transform") else None
            for c in go.m_Component:
                co = c.component.deref()
                if co.type.name == "Transform":
                    t = co.read()
                    while t.m_Father and t.m_Father.path_id != 0:
                        t = t.m_Father.read()
                    roots.append(t)
def walk(t, d):
    go = t.m_GameObject.read()
    comps = [comp_desc(c.component) for c in go.m_Component if c.component.deref().type.name != "Transform"]
    p = t.m_LocalPosition
    print("  " * d + f"{go.m_Name}  ({p.x:.2f},{p.y:.2f},{p.z:.2f})  [{', '.join(comps)}]")
    if d >= maxdepth: return
    for ch in t.m_Children: walk(ch.read(), d + 1)
print(f"{len(roots)} root(s)")
for r in roots[:1]: walk(r, 0)
