import sys, collections, UnityPy
UnityPy.config.FALLBACK_UNITY_VERSION = "6000.0.75f1"
env = UnityPy.load(sys.argv[1])
counts = collections.Counter()
names = collections.defaultdict(list)
for obj in env.objects:
    t = obj.type.name
    counts[t] += 1
    if t in sys.argv[2:] :
        try:
            d = obj.peek_name() if hasattr(obj,'peek_name') else obj.read().m_Name
        except Exception as e:
            d = f"<{e}>"
        names[t].append(d)
print(counts.most_common())
for t, ns in names.items():
    print(f"== {t} ({len(ns)})")
    for n in sorted(set(ns)): print("  ", n)
