using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using AssetsTools.NET;
using AssetsTools.NET.Extra;

namespace Kollektion.Core.GameData
{
    /// <summary>One object of a serialized file, with its value tree (read from the file's own type tree).</summary>
    public sealed class Asset
    {
        public AssetsFileInstance Inst { get; }
        public AssetFileInfo Info { get; }
        public AssetTypeValueField F { get; }

        public Asset(AssetsFileInstance inst, AssetFileInfo info, AssetTypeValueField field)
        {
            Inst = inst;
            Info = info;
            F = field;
        }

        public long PathId => Info.PathId;
        public AssetClassID Type => (AssetClassID)Info.TypeId;
        public string Name => F["m_Name"].IsDummy ? "" : F["m_Name"].AsString;
    }

    /// <summary>A bundle opened by <see cref="Bundles.Load"/>: its serialized files, in the bundle's order.</summary>
    public sealed class Bundle
    {
        public string Path { get; }
        public BundleFileInstance Instance { get; }
        public IReadOnlyList<AssetsFileInstance> Files { get; }

        public Bundle(string path, BundleFileInstance instance, IReadOnlyList<AssetsFileInstance> files)
        {
            Path = path;
            Instance = instance;
            Files = files;
        }
    }

    /// <summary>The game's Addressables bundles, read with AssetsTools.NET from the type trees they carry (no class
    /// database), as UnityPy reads them for tools/export_*.py. Every bundle loaded resolves references into the others.
    /// Blocks are decompressed on demand, so a 670 MB scene bundle costs only what is read from it.</summary>
    public sealed class Bundles : IDisposable
    {
        readonly AssetsManager am = new AssetsManager { UseTemplateFieldCache = true, UseQuickLookup = true };
        readonly Dictionary<(string, long), Asset> cache = new Dictionary<(string, long), Asset>();
        readonly Dictionary<(string, int, long), string> scriptNames = new Dictionary<(string, int, long), string>();
        readonly List<Stream> streams = new List<Stream>();

        /// <summary>Opens a bundle for reading only, sharing it with any process that holds it (the game, on
        /// Windows).</summary>
        public Bundle Load(string path)
        {
            var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            streams.Add(stream);
            var bun = am.LoadBundleFile(stream, path, true);
            var files = new List<AssetsFileInstance>();
            var names = bun.file.GetAllFileNames();
            for (int i = 0; i < names.Count; i++)
                if (bun.file.IsAssetsFile(i))
                    files.Add(am.LoadAssetsFileFromBundle(bun, i, false));
            return new Bundle(path, bun, files);
        }

        public void Dispose()
        {
            cache.Clear();
            am.UnloadAll(true);
            foreach (var s in streams)
                s.Dispose();
            streams.Clear();
        }

        public Asset Get(AssetsFileInstance inst, AssetFileInfo info)
        {
            var key = (inst.name, info.PathId);
            if (!cache.TryGetValue(key, out var a))
                cache[key] = a = new Asset(inst, info, am.GetBaseField(inst, info));
            return a;
        }

        /// <summary>The object a PPtr field points at; null for a null pointer, an exception when it can't be
        /// resolved (UnityPy's deref raises there too).</summary>
        public Asset Deref(Asset from, AssetTypeValueField pptr)
        {
            if (pptr["m_PathID"].AsLong == 0) return null;
            var ext = am.GetExtAsset(from.Inst, pptr, true);
            if (ext.info == null)
                throw new InvalidDataException(
                    $"unresolved reference (file {pptr["m_FileID"].AsInt}, object {pptr["m_PathID"].AsLong}) from {from.Inst.name}");
            return Get(ext.file, ext.info);
        }

        /// <summary>A GameObject's components, in order.</summary>
        public IEnumerable<Asset> Components(Asset go) =>
            go.F["m_Component"]["Array"].Children.Select(c => Deref(go, c["component"]));

        /// <summary>A MonoBehaviour's script class name (its MonoScript's m_ClassName), or null for no script.</summary>
        public string ScriptName(Asset mb)
        {
            var p = mb.F["m_Script"];
            var key = (mb.Inst.name, p["m_FileID"].AsInt, p["m_PathID"].AsLong);
            if (!scriptNames.TryGetValue(key, out var n))
                scriptNames[key] = n = Deref(mb, p)?.F["m_ClassName"].AsString;
            return n;
        }

        /// <summary>Every object of a type in the given bundles, in file order; with names, only those whose name
        /// is one of them (read without building the value tree).</summary>
        public IEnumerable<Asset> OfType(AssetClassID type, ISet<string> names, params Bundle[] within) =>
            OfTypes(new[] { type }, names == null ? (Func<string, bool>)null : names.Contains, within);

        /// <summary>Every object of any of the types in the given bundles, in file order (as UnityPy's env.objects
        /// lists them); with accept, only those whose name it accepts.</summary>
        public IEnumerable<Asset> OfTypes(IReadOnlyCollection<AssetClassID> types, Func<string, bool> accept, params Bundle[] within)
        {
            var ids = new HashSet<int>(types.Select(t => (int)t));
            foreach (var bundle in within)
                foreach (var f in bundle.Files)
                    foreach (var info in f.file.AssetInfos)
                    {
                        if (!ids.Contains(info.TypeId) || (accept != null && !accept(PeekName(f, info))))
                            continue;
                        yield return Get(f, info);
                    }
        }

        /// <summary>A named object's m_Name straight from its bytes: named objects store it first, GameObjects after
        /// their components and layer.</summary>
        public static string PeekName(AssetsFileInstance f, AssetFileInfo info)
        {
            var r = f.file.Reader;
            lock (f.LockReader)
            {
                r.Position = info.GetAbsoluteByteOffset(f.file);
                if (info.TypeId == (int)AssetClassID.GameObject)
                {
                    int n = r.ReadInt32();
                    r.Position += n * 12L;     // ComponentPair: PPtr (int file id, long path id)
                    r.ReadUInt32();            // m_Layer
                }
                return r.ReadCountStringInt32();
            }
        }

        /// <summary>The root Transforms (no parent) of GameObjects with this name, in file order.</summary>
        public List<Asset> FindRoots(string name, params Bundle[] within)
        {
            var roots = new List<Asset>();
            foreach (var go in OfType(AssetClassID.GameObject, new HashSet<string> { name }, within))
            {
                var t = Components(go).FirstOrDefault(c => c.Type == AssetClassID.Transform);
                if (t != null && t.F["m_Father"]["m_PathID"].AsLong == 0)
                    roots.Add(t);
            }
            return roots;
        }

        public string NodeName(Asset transform) => Deref(transform, transform.F["m_GameObject"]).Name;

        public IEnumerable<Asset> Children(Asset transform) =>
            transform.F["m_Children"]["Array"].Children.Select(c => Deref(transform, c));

        /// <summary>The Transform at a path of child names below t, or null when a name is missing.</summary>
        public Asset TryFindChild(Asset t, string path)
        {
            foreach (var part in path.Split('/'))
            {
                t = Children(t).FirstOrDefault(c => NodeName(c) == part);
                if (t == null) return null;
            }
            return t;
        }

        public Asset FindChild(Asset t, string path) =>
            TryFindChild(t, path) ?? throw new InvalidDataException($"{path}: no such node under {NodeName(t)}");

        /// <summary>Bytes from a resource entry (CAB-….resS) of the bundle that holds `from`.</summary>
        public byte[] ReadResource(Asset from, string path, long offset, int size)
        {
            var bun = from.Inst.parentBundle ?? throw new InvalidDataException($"{from.Inst.name} is not in a bundle");
            var entry = path.Split('/').Last();
            int idx = bun.file.GetFileIndex(entry);
            if (idx < 0) throw new InvalidDataException($"no bundle entry {entry}");
            bun.file.GetFileRange(idx, out long start, out long length);
            if (offset < 0 || size < 0 || offset + size > length)
                throw new InvalidDataException($"{entry}: {size} bytes at {offset} run past its {length}");
            var r = bun.file.DataReader;
            lock (r)
            {
                r.Position = start + offset;
                var bytes = r.ReadBytes(size);
                if (bytes.Length != size) throw new InvalidDataException($"{entry}: short read");
                return bytes;
            }
        }
    }
}
