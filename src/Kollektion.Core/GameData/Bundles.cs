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

    /// <summary>A bundle opened by <see cref="Bundles.Load"/>: its file name and serialized files, in the bundle's
    /// order.</summary>
    public sealed class Bundle
    {
        public string Name { get; }
        public IReadOnlyList<AssetsFileInstance> Files { get; }

        public Bundle(string name, IReadOnlyList<AssetsFileInstance> files)
        {
            Name = name;
            Files = files;
        }
    }

    /// <summary>The game's Addressables bundles, read with AssetsTools.NET from the type trees they carry (no class
    /// database), as UnityPy reads them for tools/export_*.py. Every bundle loaded resolves references into the others.
    /// Blocks are decompressed on demand and strictly (<see cref="BundleBlockStream"/>), so a 670 MB scene bundle costs
    /// only what is read from it and a damaged one fails instead of reading as zeros.
    /// <para>Objects reached through references (<see cref="Deref"/>) are kept until <see cref="Forget"/>, because the
    /// prefab walks visit them again and again; objects a scan lists (<see cref="OfTypes"/>) are read afresh and not
    /// kept. One thread at a time per instance: the bundle streams, the cache and AssetsTools.NET's readers are
    /// shared.</para></summary>
    public sealed class Bundles : IDisposable
    {
        readonly AssetsManager am = new AssetsManager { UseTemplateFieldCache = true, UseQuickLookup = true };
        readonly Dictionary<(string, long), Asset> cache = new Dictionary<(string, long), Asset>();
        readonly Dictionary<(string, int, long), string> scriptNames = new Dictionary<(string, int, long), string>();
        readonly Dictionary<string, Bundle> loaded = new Dictionary<string, Bundle>();
        readonly Dictionary<string, (long Length, DateTime Written)> stamps = new Dictionary<string, (long, DateTime)>();
        readonly List<Stream> streams = new List<Stream>();

        /// <summary>A file's size and last write time, to tell whether it changed while it was read (Steam may
        /// replace a bundle the reader holds open).</summary>
        public static (long Length, DateTime Written) Stamp(string path)
        {
            var fi = new FileInfo(path);
            return fi.Exists ? (fi.Length, fi.LastWriteTimeUtc) : (-1, DateTime.MinValue);
        }

        /// <summary>Each bundle loaded, by full path, with its stamp from just before it was opened.</summary>
        public IReadOnlyDictionary<string, (long Length, DateTime Written)> Stamps => stamps;

        /// <summary>Opens a bundle for reading only, sharing it with any process that holds it (the game, on Windows),
        /// and checks it is whole (<see cref="BundleBlockStream.Attach"/>). A path loaded before returns the same
        /// bundle.</summary>
        public Bundle Load(string path)
        {
            var full = Path.GetFullPath(path);
            if (loaded.TryGetValue(full, out var known)) return known;
            var name = Path.GetFileName(full);
            var stamp = Stamp(full);
            var stream = new FileStream(full, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete);
            streams.Add(stream);
            BundleFileInstance bun;
            try
            {
                bun = am.LoadBundleFile(stream, full, false);
            }
            catch (Exception e) when (GameDataException.IsDamage(e))
            {
                throw new GameDataException($"{name}: not a bundle this reader understands ({e.GetType().Name}: {e.Message})", e);
            }
            BundleBlockStream.Attach(bun, stream, name);
            var files = new List<AssetsFileInstance>();
            var entries = bun.file.BlockAndDirInfo.DirectoryInfos;
            for (int i = 0; i < entries.Count; i++)
            {
                var entry = entries[i];
                try
                {
                    bool assets = bun.file.IsAssetsFile(i);
                    if (entry.IsSerialized && !assets)
                        throw new GameDataException($"{name}: {entry.Name} is marked a serialized file but doesn't read as one");
                    if (assets) files.Add(am.LoadAssetsFileFromBundle(bun, i, false));
                }
                catch (Exception e) when (GameDataException.IsDamage(e))
                {
                    throw new GameDataException($"{name}: {entry.Name} can't be read ({e.GetType().Name}: {e.Message})", e);
                }
            }
            stamps[full] = stamp;
            return loaded[full] = new Bundle(name, files);
        }

        /// <summary>Throws when a bundle loaded here has changed size or write time since it was opened.</summary>
        public void CheckUnchanged()
        {
            foreach (var kv in stamps)
                if (Stamp(kv.Key) != kv.Value)
                    throw new GameDataException($"{Path.GetFileName(kv.Key)} changed while it was read (is Steam updating the game?)");
        }

        /// <summary>Drops the objects kept from references, once a walk is done with them.</summary>
        public void Forget() => cache.Clear();

        public void Dispose()
        {
            cache.Clear();
            am.UnloadAll(true);
            foreach (var s in streams)
                s.Dispose();
            streams.Clear();
        }

        static string Where(AssetsFileInstance inst) => inst.parentBundle?.name ?? inst.name;

        /// <summary>An object's value tree, read afresh.</summary>
        Asset Read(AssetsFileInstance inst, AssetFileInfo info)
        {
            try
            {
                return new Asset(inst, info, am.GetBaseField(inst, info));
            }
            catch (Exception e) when (GameDataException.IsDamage(e))
            {
                throw new GameDataException($"{Where(inst)}: object {info.PathId} in {inst.name} can't be read ({e.GetType().Name}: {e.Message})", e);
            }
        }

        /// <summary>An object's value tree, kept until <see cref="Forget"/>.</summary>
        Asset Get(AssetsFileInstance inst, AssetFileInfo info)
        {
            var key = (inst.name, info.PathId);
            if (!cache.TryGetValue(key, out var a))
                cache[key] = a = Read(inst, info);
            return a;
        }

        /// <summary>The object a PPtr field points at; null for a null pointer, an exception when it can't be
        /// resolved (UnityPy's deref raises there too).</summary>
        public Asset Deref(Asset from, AssetTypeValueField pptr)
        {
            if (pptr["m_PathID"].AsLong == 0) return null;
            AssetExternal ext;
            try
            {
                ext = am.GetExtAsset(from.Inst, pptr, true);
            }
            catch (Exception e) when (GameDataException.IsDamage(e))
            {
                throw new GameDataException($"{Where(from.Inst)}: a reference from object {from.PathId} can't be followed ({e.GetType().Name}: {e.Message})", e);
            }
            if (ext.info == null)
                throw new UnresolvedReferenceException(
                    $"{Where(from.Inst)}: unresolved reference (file {pptr["m_FileID"].AsInt}, object {pptr["m_PathID"].AsLong}) from {from.Inst.name}");
            return Get(ext.file, ext.info);
        }

        /// <summary>A GameObject's components, in order.</summary>
        public IEnumerable<Asset> Components(Asset go) =>
            go.F["m_Component"]["Array"].Children.Select(c => Deref(go, c["component"]));

        /// <summary>A MonoBehaviour's script class name: its m_Script followed through the file's externals to the
        /// MonoScript's m_ClassName (null for no script). This is the resolver to use;
        /// <see cref="NodeFacts.ScriptsByPathId"/> keeps the Python's own lookup by path id alone, for nodes.json's
        /// sake.</summary>
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
        /// lists them), read afresh and not kept; with accept, only those whose name it accepts.</summary>
        public IEnumerable<Asset> OfTypes(IReadOnlyCollection<AssetClassID> types, Func<string, bool> accept, params Bundle[] within)
        {
            var ids = new HashSet<int>(types.Select(t => (int)t));
            foreach (var bundle in within)
                foreach (var f in bundle.Files)
                    foreach (var info in f.file.AssetInfos)
                    {
                        if (!ids.Contains(info.TypeId) || (accept != null && !accept(PeekName(f, info))))
                            continue;
                        yield return Read(f, info);
                    }
        }

        /// <summary>A named object's m_Name straight from its bytes: Meshes, Textures and Sprites store it first,
        /// GameObjects after their components and layer.</summary>
        public static string PeekName(AssetsFileInstance f, AssetFileInfo info)
        {
            lock (f.LockReader)
            {
                try
                {
                    return PeekName(f.file.Reader, info.GetAbsoluteByteOffset(f.file), info.ByteSize, (AssetClassID)info.TypeId);
                }
                catch (Exception e) when (GameDataException.IsDamage(e) && !(e is NotSupportedException))
                {
                    throw new GameDataException($"{Where(f)}: object {info.PathId} in {f.name} can't be read ({e.GetType().Name}: {e.Message})", e);
                }
            }
        }

        /// <summary>PeekName on an object's bytes at offset (size bytes long) in r, for a Mesh, Texture2D, Sprite or
        /// GameObject; an InvalidDataException when the name doesn't fit inside the object.</summary>
        public static string PeekName(AssetsFileReader r, long offset, long size, AssetClassID type)
        {
            if (type != AssetClassID.GameObject && type != AssetClassID.Mesh && type != AssetClassID.Texture2D && type != AssetClassID.Sprite)
                throw new NotSupportedException($"names of {type} objects aren't read from their bytes");
            long end = offset + size;
            r.Position = offset;
            if (type == AssetClassID.GameObject)
            {
                int n = r.ReadInt32();
                if (n < 0 || n > (end - r.Position) / 12) throw new InvalidDataException($"{n} components don't fit in the GameObject");
                r.Position += n * 12L;     // ComponentPair: PPtr (int file id, long path id)
                r.ReadUInt32();            // m_Layer
            }
            int length = r.ReadInt32();
            if (length < 0 || length > end - r.Position) throw new InvalidDataException($"a {length}-byte name doesn't fit in the object");
            return System.Text.Encoding.UTF8.GetString(r.ReadBytes(length));
        }

        /// <summary>The root Transforms (no parent) of GameObjects with this name, in file order.</summary>
        public List<Asset> FindRoots(string name, params Bundle[] within) =>
            RootsWhere(name.Equals, within).Select(r => r.Root).ToList();

        /// <summary>The root Transforms (no parent) of GameObjects whose name accept takes, with their names, in file
        /// order.</summary>
        public List<(string Name, Asset Root)> RootsWhere(Func<string, bool> accept, params Bundle[] within)
        {
            var roots = new List<(string, Asset)>();
            foreach (var go in OfTypes(new[] { AssetClassID.GameObject }, accept, within))
            {
                var t = Components(go).FirstOrDefault(c => c.Type == AssetClassID.Transform);
                if (t != null && t.F["m_Father"]["m_PathID"].AsLong == 0)
                    roots.Add((go.Name, t));
            }
            return roots;
        }

        public string NodeName(Asset transform) =>
            (Deref(transform, transform.F["m_GameObject"]) ?? throw new InvalidDataException($"transform {transform.PathId} has no GameObject")).Name;

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
            if (idx < 0) throw new GameDataException($"{bun.name}: no bundle entry {entry}");
            bun.file.GetFileRange(idx, out long start, out long length);
            if (offset < 0 || size < 0 || offset + size > length)
                throw new GameDataException($"{bun.name}: {entry}: {size} bytes at {offset} run past its {length}");
            var r = bun.file.DataReader;
            lock (r)
            {
                r.Position = start + offset;
                var bytes = r.ReadBytes(size);
                if (bytes.Length != size) throw new GameDataException($"{bun.name}: {entry}: short read");
                return bytes;
            }
        }
    }

    /// <summary>A reference that leads to no object: UnityPy's deref raises here too, and some exporters skip such a
    /// reference as the Python does (a script in another bundle, a part with no reference).</summary>
    public sealed class UnresolvedReferenceException : GameDataException
    {
        public UnresolvedReferenceException(string message) : base(message)
        {
        }
    }
}
