using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using AssetsTools.NET;

namespace Kollektion.Core.GameData
{
    /// <summary>One vertex attribute's place in the vertex data (Unity's ChannelInfo).</summary>
    public readonly struct VertexChannel
    {
        public int Stream { get; }
        public int Offset { get; }
        public int Format { get; }
        public int Dimension { get; }

        public VertexChannel(int stream, int offset, int format, int dimension)
        {
            Stream = stream;
            Offset = offset;
            Format = format;
            Dimension = dimension;
        }
    }

    /// <summary>A range of the index buffer (Unity's SubMesh).</summary>
    public readonly struct SubMesh
    {
        public int FirstByte { get; }
        public int IndexCount { get; }
        public int Topology { get; }
        public int BaseVertex { get; }

        public SubMesh(int firstByte, int indexCount, int topology, int baseVertex)
        {
            FirstByte = firstByte;
            IndexCount = indexCount;
            Topology = topology;
            BaseVertex = baseVertex;
        }
    }

    /// <summary>A Unity 6 mesh decoded as UnityPy's MeshHandler decodes it for this game: uncompressed vertex streams
    /// (each starting 16-byte aligned), the data inline or in the bundle's .resS, 16- or 32-bit indices, triangle
    /// topology. Channels: 0 position, 1 normal, 4 UV0, 12 bone weights, 13 bone indices.</summary>
    public sealed class MeshData
    {
        // Bytes per component of each VertexFormat: Float, Float16, UNorm8, SNorm8, UNorm16, SNorm16, UInt8, SInt8,
        // UInt16, SInt16, UInt32, SInt32.
        static readonly int[] FormatSize = { 4, 2, 1, 1, 2, 2, 1, 1, 2, 2, 4, 4 };

        public string Name { get; }
        public int VertexCount { get; }
        public double[][] Vertices { get; private set; }
        public double[][] Normals { get; private set; }
        public double[][] UV0 { get; private set; }
        public double[][] BoneWeights { get; private set; }
        public double[][] BoneIndices { get; private set; }
        public IReadOnlyList<(int A, int B, int C)> Triangles { get; }

        MeshData(string name, int vertexCount, IReadOnlyList<(int, int, int)> triangles)
        {
            Name = name;
            VertexCount = vertexCount;
            Triangles = triangles;
        }

        /// <summary>A Mesh asset, or a Sprite's render data (m_RD), which has no compression, stream data or index
        /// format fields (its indices are 16-bit).</summary>
        public static MeshData Read(Bundles bundles, Asset owner, AssetTypeValueField f, string name)
        {
            var compression = f["m_MeshCompression"];
            if (!compression.IsDummy && compression.AsInt != 0)
                throw new NotSupportedException($"{name}: compressed mesh (m_MeshCompression {compression.AsInt}) not supported");
            var vd = f["m_VertexData"];
            int vertexCount = (int)vd["m_VertexCount"].AsUInt;
            byte[] data = vd["m_DataSize"].AsByteArray;
            var sd = f["m_StreamData"];
            if (!sd.IsDummy && sd["path"].AsString.Length > 0)
                data = bundles.ReadResource(owner, sd["path"].AsString, (long)sd["offset"].AsULong, (int)sd["size"].AsUInt);
            var channels = vd["m_Channels"]["Array"].Children
                .Select(c => new VertexChannel(c["stream"].AsByte, c["offset"].AsByte, c["format"].AsByte, c["dimension"].AsByte))
                .ToList();
            var ibField = f["m_IndexBuffer"]["Array"];
            byte[] indexBuffer = ibField.AsByteArray ?? ibField.Children.Select(c => c.AsByte).ToArray();
            var indexFormat = f["m_IndexFormat"];
            bool indices16 = indexFormat.IsDummy || indexFormat.AsInt == 0;
            var subMeshes = f["m_SubMeshes"]["Array"].Children
                .Select(s => new SubMesh((int)s["firstByte"].AsUInt, (int)s["indexCount"].AsUInt, s["topology"].AsInt,
                                         s["baseVertex"].IsDummy ? 0 : (int)s["baseVertex"].AsUInt))
                .ToList();
            return Decode(name, vertexCount, channels, data ?? Array.Empty<byte>(), indexBuffer, indices16, subMeshes);
        }

        public static MeshData Read(Bundles bundles, Asset mesh) => Read(bundles, mesh, mesh.F, mesh.Name);

        /// <summary>Decodes raw vertex and index bytes. baseVertex must be 0: UnityPy doesn't apply it, so a mesh
        /// using it would come out different from the Python pipeline's (and wrong in both); it fails here instead.</summary>
        public static MeshData Decode(string name, int vertexCount, IReadOnlyList<VertexChannel> channels, byte[] data,
                                      byte[] indexBuffer, bool indices16, IReadOnlyList<SubMesh> subMeshes)
        {
            int indexSize = indices16 ? 2 : 4;
            var indices = new uint[indexBuffer.Length / indexSize];
            for (int i = 0; i < indices.Length; i++)
                indices[i] = indices16 ? BitConverter.ToUInt16(indexBuffer, i * 2) : BitConverter.ToUInt32(indexBuffer, i * 4);
            var triangles = new List<(int, int, int)>();
            foreach (var sm in subMeshes)
            {
                if (sm.Topology != 0) throw new NotSupportedException($"{name}: submesh topology {sm.Topology} (only triangles)");
                if (sm.BaseVertex != 0) throw new NotSupportedException($"{name}: submesh baseVertex {sm.BaseVertex} (only 0)");
                int first = sm.FirstByte / indexSize;
                if (sm.FirstByte % indexSize != 0 || sm.IndexCount % 3 != 0 || first + sm.IndexCount > indices.Length)
                    throw new InvalidDataException($"{name}: submesh runs past the index buffer");
                for (int i = first; i < first + sm.IndexCount; i += 3)
                {
                    for (int k = 0; k < 3; k++)
                        if (indices[i + k] >= vertexCount)
                            throw new InvalidDataException($"{name}: index {indices[i + k]} of {vertexCount} vertices");
                    triangles.Add(((int)indices[i], (int)indices[i + 1], (int)indices[i + 2]));
                }
            }

            var mesh = new MeshData(name, vertexCount, triangles);
            if (channels.Count == 0 || vertexCount == 0) return mesh;
            int streamCount = 1 + channels.Max(c => c.Stream);
            var streamOffset = new int[streamCount];
            var stride = new int[streamCount];
            int off = 0;
            for (int s = 0; s < streamCount; s++)
            {
                foreach (var c in channels)
                    if (c.Stream == s && (c.Dimension & 0xF) > 0) stride[s] += (c.Dimension & 0xF) * Size(name, c.Format);
                streamOffset[s] = off;
                off += vertexCount * stride[s];
                off = (off + 15) & ~15;
            }
            for (int ch = 0; ch < channels.Count; ch++)
            {
                var c = channels[ch];
                int dim = c.Dimension & 0xF;
                if (dim == 0) continue;
                int size = Size(name, c.Format);
                int last = streamOffset[c.Stream] + (vertexCount - 1) * stride[c.Stream] + c.Offset + dim * size;
                if (last > data.Length) throw new InvalidDataException($"{name}: vertex data ends early (channel {ch})");
                var values = new double[vertexCount][];
                for (int v = 0; v < vertexCount; v++)
                {
                    var item = values[v] = new double[dim];
                    int p = streamOffset[c.Stream] + v * stride[c.Stream] + c.Offset;
                    for (int k = 0; k < dim; k++, p += size)
                        item[k] = c.Format switch
                        {
                            0 => BitConverter.ToSingle(data, p),
                            1 => (double)BitConverter.ToHalf(data, p),
                            2 or 6 => data[p],
                            3 or 7 => (sbyte)data[p],
                            4 or 8 => BitConverter.ToUInt16(data, p),
                            5 or 9 => BitConverter.ToInt16(data, p),
                            10 => BitConverter.ToUInt32(data, p),
                            _ => BitConverter.ToInt32(data, p),
                        };
                }
                switch (ch)
                {
                    case 0: mesh.Vertices = values; break;
                    case 1: mesh.Normals = values; break;
                    case 4: mesh.UV0 = values; break;
                    case 12: mesh.BoneWeights = values; break;
                    case 13: mesh.BoneIndices = values; break;
                }
            }
            return mesh;
        }

        static int Size(string name, int format) =>
            format >= 0 && format < FormatSize.Length ? FormatSize[format]
                : throw new NotSupportedException($"{name}: vertex format {format}");
    }
}
