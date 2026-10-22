using System;
using System.IO;
using AssetsTools.NET;
using AssetsTools.NET.Extra;
using SevenZip.Compression.LZMA;

namespace Kollektion.Core.GameData
{
    /// <summary>The game's files aren't what the reader expects: a damaged, truncated or changed bundle, or data the
    /// exporters can't take. The message names the bundle; verifying the game's files in Steam is the cure.</summary>
    public class GameDataException : IOException
    {
        public GameDataException(string message, Exception inner = null) : base(message, inner)
        {
        }

        /// <summary>Whether an exception thrown while reading game data should become a GameDataException naming
        /// where it happened: not one already, and not running out of memory, which says nothing about the
        /// files.</summary>
        public static bool IsDamage(Exception e) => !(e is GameDataException || e is OutOfMemoryException);
    }

    /// <summary>LZ4 block decoding (the raw block format, no frame) that refuses anything but a well-formed block of
    /// exactly the expected size: AssetsTools.NET's decoder leaves the rest of the block zero when the input ends early
    /// and garbles it when the input is damaged, where Python's lz4 raises.</summary>
    public static class Lz4
    {
        /// <summary>Decodes src into all of dst; an InvalidDataException when src isn't one well-formed block that
        /// decodes to exactly dst.Length bytes.</summary>
        public static void Decode(ReadOnlySpan<byte> src, Span<byte> dst)
        {
            int ip = 0, op = 0;
            while (true)
            {
                if (ip >= src.Length) throw new InvalidDataException("LZ4 block ends inside a sequence");
                int token = src[ip++];
                int literals = token >> 4;
                if (literals == 15) literals += ExtraLength(src, ref ip);
                if (literals > src.Length - ip) throw new InvalidDataException("LZ4 literals run past the end of the block");
                if (literals > dst.Length - op) throw new InvalidDataException($"LZ4 block decodes past its {dst.Length} bytes");
                src.Slice(ip, literals).CopyTo(dst.Slice(op));
                ip += literals;
                op += literals;
                if (ip == src.Length) break;          // the last sequence has literals only
                if (src.Length - ip < 2) throw new InvalidDataException("LZ4 block ends inside a match offset");
                int offset = src[ip] | src[ip + 1] << 8;
                ip += 2;
                if (offset == 0 || offset > op) throw new InvalidDataException($"LZ4 match offset {offset} points before the block's start");
                int length = token & 15;
                if (length == 15) length += ExtraLength(src, ref ip);
                length += 4;
                if (length > dst.Length - op) throw new InvalidDataException($"LZ4 block decodes past its {dst.Length} bytes");
                if (offset >= length)
                    dst.Slice(op - offset, length).CopyTo(dst.Slice(op));
                else
                    for (int k = 0; k < length; k++) dst[op + k] = dst[op - offset + k];   // overlapping: a repeat
                op += length;
            }
            if (op != dst.Length) throw new InvalidDataException($"LZ4 block decodes to {op} bytes, not {dst.Length}");
        }

        static int ExtraLength(ReadOnlySpan<byte> src, ref int ip)
        {
            int n = 0, b;
            do
            {
                if (ip >= src.Length) throw new InvalidDataException("LZ4 block ends inside a length");
                b = src[ip++];
                n += b;
                if (n > 1 << 30) throw new InvalidDataException("LZ4 length out of range");
            } while (b == 255);
            return n;
        }
    }

    /// <summary>A UnityFS bundle's data, decompressed block by block as it is read (a 670 MB scene bundle costs only
    /// what is read from it), strictly: every block must lie inside the file and decode to exactly the size the block
    /// table gives, or reading fails with a <see cref="GameDataException"/>. Replaces AssetsTools.NET's LZ4BlockStream,
    /// which returns zero-filled or garbled blocks for a truncated or damaged file. One thread at a time.</summary>
    public sealed class BundleBlockStream : Stream
    {
        const int CacheSize = 4;

        readonly Stream file;
        readonly string name;
        readonly AssetBundleBlockInfo[] blocks;
        readonly long[] start;     // each block's first byte in the decompressed data
        readonly long[] at;        // each block's first byte in the file
        readonly long length;
        readonly int[] cachedIndex = { -1, -1, -1, -1 };
        readonly byte[][] cached = new byte[CacheSize][];
        int nextSlot;

        /// <summary>The blocks of a bundle file whose data starts at dataOffset; name is the bundle's, for
        /// errors.</summary>
        public BundleBlockStream(Stream file, long dataOffset, AssetBundleBlockInfo[] blocks, string name)
        {
            this.file = file;
            this.name = name;
            this.blocks = blocks;
            start = new long[blocks.Length];
            at = new long[blocks.Length];
            long d = 0, c = dataOffset;
            for (int i = 0; i < blocks.Length; i++)
            {
                var b = blocks[i];
                int type = b.GetCompressionType();
                if (type > 3) throw new GameDataException($"{name}: block {i} has compression type {type}, which no Unity bundle uses");
                if (type == 0 && b.CompressedSize != b.DecompressedSize)
                    throw new GameDataException($"{name}: stored block {i} is {b.CompressedSize} bytes in the file and {b.DecompressedSize} decompressed");
                if (b.DecompressedSize > int.MaxValue / 2)
                    throw new GameDataException($"{name}: block {i} claims {b.DecompressedSize} bytes");
                start[i] = d;
                at[i] = c;
                d += b.DecompressedSize;
                c += b.CompressedSize;
                if (c > file.Length)
                    throw new GameDataException($"{name}: block {i} ends at byte {c} of a {file.Length}-byte file (the file is cut short or its block table is damaged)");
            }
            length = d;
        }

        public override bool CanRead => true;
        public override bool CanSeek => true;
        public override bool CanWrite => false;
        public override long Length => length;
        public override long Position { get; set; }

        public override int Read(byte[] buffer, int offset, int count)
        {
            int done = 0;
            while (done < count && Position < length)
            {
                int i = BlockAt(Position);
                var data = Block(i);
                int from = (int)(Position - start[i]);
                int n = Math.Min(count - done, data.Length - from);
                Buffer.BlockCopy(data, from, buffer, offset + done, n);
                done += n;
                Position += n;
            }
            return done;
        }

        int BlockAt(long position)
        {
            int lo = 0, hi = start.Length - 1;
            while (lo < hi)
            {
                int mid = (lo + hi + 1) / 2;
                if (start[mid] <= position) lo = mid;
                else hi = mid - 1;
            }
            return lo;      // the last block starting at or before it: an empty block before it is passed over
        }

        byte[] Block(int i)
        {
            for (int s = 0; s < CacheSize; s++)
                if (cachedIndex[s] == i) return cached[s];
            var data = Decode(i);
            cachedIndex[nextSlot] = i;
            cached[nextSlot] = data;
            nextSlot = (nextSlot + 1) % CacheSize;
            return data;
        }

        byte[] Decode(int i)
        {
            var b = blocks[i];
            var raw = new byte[b.CompressedSize];
            file.Position = at[i];
            int got = 0;
            while (got < raw.Length)
            {
                int r = file.Read(raw, got, raw.Length - got);
                if (r == 0) throw new GameDataException($"{name}: block {i} is cut short ({got} of {raw.Length} bytes)");
                got += r;
            }
            int type = b.GetCompressionType();
            if (type == 0) return raw;
            var data = new byte[b.DecompressedSize];
            try
            {
                if (type == 1)
                {
                    using var lzma = SevenZipHelper.StreamDecompress(new MemoryStream(raw), data.Length);
                    if (lzma.Length != data.Length) throw new InvalidDataException($"LZMA block decodes to {lzma.Length} bytes, not {data.Length}");
                    lzma.Read(data, 0, data.Length);
                }
                else
                    Lz4.Decode(raw, data);
            }
            catch (Exception e) when (GameDataException.IsDamage(e))
            {
                throw new GameDataException($"{name}: block {i} is damaged ({e.Message})", e);
            }
            return data;
        }

        public override long Seek(long offset, SeekOrigin origin)
        {
            long p = origin switch
            {
                SeekOrigin.Begin => offset,
                SeekOrigin.Current => Position + offset,
                _ => length + offset,
            };
            if (p < 0) throw new IOException("seek before the start of the bundle data");
            return Position = p;
        }

        public override void Flush()
        {
        }

        public override void SetLength(long value) => throw new NotSupportedException();
        public override void Write(byte[] buffer, int offset, int count) => throw new NotSupportedException();

        /// <summary>Checks a bundle AssetsTools.NET has just opened (without unpacking) and makes it read strictly: the
        /// header's total size must be the file's, the block table is decoded again strictly and replaces the one
        /// AssetsTools.NET decoded leniently, every directory entry must lie inside the data, and the data is read
        /// through a BundleBlockStream.</summary>
        public static void Attach(BundleFileInstance bundle, Stream file, string name)
        {
            var bf = bundle.file;
            var header = bf.Header ?? throw new GameDataException($"{name}: not a UnityFS bundle");
            var fs = header.FileStreamHeader;
            if (fs.TotalFileSize != file.Length)
                throw new GameDataException($"{name}: its header gives {fs.TotalFileSize} bytes, the file has {file.Length} (cut short or changed)");

            long infoAt = header.GetBundleInfoOffset();
            if (infoAt < 0 || infoAt + fs.CompressedSize > file.Length)
                throw new GameDataException($"{name}: its block table lies outside the file");
            var raw = new byte[fs.CompressedSize];
            file.Position = infoAt;
            int got = 0;
            while (got < raw.Length)
            {
                int r = file.Read(raw, got, raw.Length - got);
                if (r == 0) throw new GameDataException($"{name}: its block table is cut short");
                got += r;
            }
            byte[] info;
            int type = header.GetCompressionType();
            try
            {
                switch (type)
                {
                    case 0:
                        info = raw;
                        break;
                    case 1:
                        using (var lzma = SevenZipHelper.StreamDecompress(new MemoryStream(raw), fs.DecompressedSize))
                            info = lzma.ToArray();
                        if (info.Length != fs.DecompressedSize) throw new InvalidDataException("LZMA block table decodes short");
                        break;
                    case 2:
                    case 3:
                        info = new byte[fs.DecompressedSize];
                        Lz4.Decode(raw, info);
                        break;
                    default:
                        throw new InvalidDataException($"compression type {type}");
                }
                var table = new AssetBundleBlockAndDirInfo();
                table.Read(new AssetsFileReader(new MemoryStream(info)) { BigEndian = true });
                bf.BlockAndDirInfo = table;
            }
            catch (Exception e) when (GameDataException.IsDamage(e))
            {
                throw new GameDataException($"{name}: its block table is damaged ({e.Message})", e);
            }

            var data = new BundleBlockStream(file, header.GetFileDataOffset(), bf.BlockAndDirInfo.BlockInfos, name);
            foreach (var entry in bf.BlockAndDirInfo.DirectoryInfos)
                if (entry.Offset < 0 || entry.DecompressedSize < 0 || entry.Offset + entry.DecompressedSize > data.Length)
                    throw new GameDataException($"{name}: entry {entry.Name} lies outside the bundle's {data.Length} bytes of data");
            bf.DataReader = new AssetsFileReader(data);
            bf.DataIsCompressed = false;
        }
    }
}
