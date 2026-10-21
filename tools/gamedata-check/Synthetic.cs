using System;
using System.Buffers.Binary;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;

/// <summary>UnityFS bundles made from scratch for the bundle reader's checks: no game data. One directory entry per
/// (name, flags, bytes), the entries' bytes laid end to end and cut into blocks of blockSize, each LZ4-compressed
/// (block flag 3) or stored (flag 0); the block table stored uncompressed after the header, as Unity 2019+ writes
/// it.</summary>
sealed class SyntheticBundle
{
    public byte[] Bytes;
    public long DataOffset;
    public List<(uint Decompressed, uint Compressed, ushort Flags)> Blocks = new List<(uint, uint, ushort)>();
    public byte[] Data;

    /// <summary>overclaim is added to the last entry's size in the directory, to make one that runs past the
    /// data.</summary>
    public static SyntheticBundle Make(IReadOnlyList<(string Name, uint Flags, byte[] Bytes)> entries, int blockSize, bool lz4,
                                       long overclaim = 0)
    {
        var b = new SyntheticBundle { Data = entries.SelectMany(e => e.Bytes).ToArray() };
        var blocks = new MemoryStream();
        for (int at = 0; at < b.Data.Length; at += blockSize)
        {
            int n = Math.Min(blockSize, b.Data.Length - at);
            var raw = b.Data.AsSpan(at, n).ToArray();
            var packed = lz4 ? LZ4ps.LZ4Codec.Encode32HC(raw, 0, raw.Length) : raw;
            b.Blocks.Add(((uint)n, (uint)packed.Length, (ushort)(lz4 ? 3 : 0)));
            blocks.Write(packed, 0, packed.Length);
        }
        var info = new MemoryStream();
        info.Write(new byte[16], 0, 16);                                    // Hash128, unused
        WriteBE(info, b.Blocks.Count);
        foreach (var (d, c, f) in b.Blocks)
        {
            WriteBE(info, (int)d);
            WriteBE(info, (int)c);
            info.WriteByte((byte)(f >> 8));
            info.WriteByte((byte)f);
        }
        WriteBE(info, entries.Count);
        long offset = 0;
        for (int i = 0; i < entries.Count; i++)
        {
            var (name, flags, bytes) = entries[i];
            WriteBE(info, offset);
            WriteBE(info, bytes.Length + (i == entries.Count - 1 ? overclaim : 0));
            WriteBE(info, (int)flags);
            var n = Encoding.ASCII.GetBytes(name + "\0");
            info.Write(n, 0, n.Length);
            offset += bytes.Length;
        }
        var infoBytes = info.ToArray();

        var head = new MemoryStream();
        var sig = Encoding.ASCII.GetBytes("UnityFS\0");
        head.Write(sig, 0, sig.Length);
        WriteBE(head, 8);                                                   // format version
        var versions = Encoding.ASCII.GetBytes("5.x.x\0" + "6000.0.75f1\0");
        head.Write(versions, 0, versions.Length);
        long headerEnd = 64;                                                // 50 bytes of header, aligned to 16
        b.DataOffset = headerEnd + infoBytes.Length;
        long total = b.DataOffset + blocks.Length;
        WriteBE(head, total);
        WriteBE(head, infoBytes.Length);                                    // block table: compressed size
        WriteBE(head, infoBytes.Length);                                    // and decompressed (stored)
        WriteBE(head, 0x40);                                                // HasDirectoryInfo, table uncompressed
        while (head.Length < headerEnd) head.WriteByte(0);
        head.Write(infoBytes, 0, infoBytes.Length);
        blocks.Position = 0;
        blocks.CopyTo(head);
        b.Bytes = head.ToArray();
        return b;
    }

    /// <summary>The header's total file size, rewritten (it sits at byte 30).</summary>
    public static void SetTotalSize(byte[] bundle, long total) => BinaryPrimitives.WriteInt64BigEndian(bundle.AsSpan(30), total);

    public AssetsTools.NET.AssetBundleBlockInfo[] BlockInfos() =>
        Blocks.Select(x => new AssetsTools.NET.AssetBundleBlockInfo { DecompressedSize = x.Decompressed, CompressedSize = x.Compressed, Flags = x.Flags })
              .ToArray();

    static void WriteBE(Stream s, int v)
    {
        var b = new byte[4];
        BinaryPrimitives.WriteInt32BigEndian(b, v);
        s.Write(b, 0, 4);
    }

    static void WriteBE(Stream s, long v)
    {
        var b = new byte[8];
        BinaryPrimitives.WriteInt64BigEndian(b, v);
        s.Write(b, 0, 8);
    }
}
