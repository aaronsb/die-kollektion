using System.Collections.Generic;
using System.Globalization;
using System.IO;
using UnityEngine;
using UnityEngine.Rendering;

namespace VehicleMods;

/// <summary>
/// Builds Unity meshes from the OBJ files tools/export_car_mesh.py and build_vehicle.py write:
/// car-root space, metres, x negated with reversed winding (right-handed). Loading undoes both
/// and maps the result into the target node's local space. Skinned meshes carry two extensions:
/// "bw i0 i1 i2 i3 w0 w1 w2 w3" per vertex (parallel to v) and "bp" bind poses (row-major),
/// which the game's meshes do not expose at runtime.
/// </summary>
static class ObjMesh
{
    public static Mesh Build(string path, Matrix4x4 rootToNode, string name)
    {
        var positions = new List<Vector3>();
        var skin = new List<BoneWeight>();
        var bindposes = new List<Matrix4x4>();
        var outSkin = new List<BoneWeight>();
        var normals = new List<Vector3>();
        var uvs = new List<Vector2>();
        var corners = new Dictionary<(int v, int t, int n), int>();
        var outPositions = new List<Vector3>();
        var outNormals = new List<Vector3>();
        var outUvs = new List<Vector2>();
        var triangles = new List<int>();

        foreach (var line in File.ReadLines(path))
        {
            var parts = line.Split(' ', System.StringSplitOptions.RemoveEmptyEntries);
            if (parts.Length == 0) continue;
            switch (parts[0])
            {
                case "v":
                    positions.Add(new Vector3(-F(parts[1]), F(parts[2]), F(parts[3])));
                    break;
                case "vn":
                    normals.Add(new Vector3(-F(parts[1]), F(parts[2]), F(parts[3])));
                    break;
                case "bw":
                    skin.Add(new BoneWeight
                    {
                        boneIndex0 = I(parts[1]), boneIndex1 = I(parts[2]), boneIndex2 = I(parts[3]), boneIndex3 = I(parts[4]),
                        weight0 = F(parts[5]), weight1 = F(parts[6]), weight2 = F(parts[7]), weight3 = F(parts[8]),
                    });
                    break;
                case "bp":
                    bindposes.Add(new Matrix4x4
                    {
                        m00 = F(parts[1]), m01 = F(parts[2]), m02 = F(parts[3]), m03 = F(parts[4]),
                        m10 = F(parts[5]), m11 = F(parts[6]), m12 = F(parts[7]), m13 = F(parts[8]),
                        m20 = F(parts[9]), m21 = F(parts[10]), m22 = F(parts[11]), m23 = F(parts[12]),
                        m30 = F(parts[13]), m31 = F(parts[14]), m32 = F(parts[15]), m33 = F(parts[16]),
                    });
                    break;
                case "vt":
                    uvs.Add(new Vector2(F(parts[1]), F(parts[2])));
                    break;
                case "f":
                    // Restore Unity's winding: the file reversed it for the mirrored x axis.
                    var face = new int[parts.Length - 1];
                    for (var i = 1; i < parts.Length; i++) face[i - 1] = Corner(parts[i]);
                    for (var i = 1; i + 1 < face.Length; i++)
                    {
                        triangles.Add(face[0]);
                        triangles.Add(face[i + 1]);
                        triangles.Add(face[i]);
                    }
                    break;
            }
        }

        var mesh = new Mesh { name = name };
        if (outPositions.Count > 65535) mesh.indexFormat = IndexFormat.UInt32;
        mesh.vertices = outPositions.ToArray();
        if (outNormals.Count == outPositions.Count) mesh.normals = outNormals.ToArray();
        if (outUvs.Count == outPositions.Count) mesh.uv = outUvs.ToArray();
        mesh.triangles = triangles.ToArray();
        if (outSkin.Count == outPositions.Count && bindposes.Count > 0)
        {
            mesh.boneWeights = outSkin.ToArray();
            mesh.bindposes = bindposes.ToArray();
        }
        if (outNormals.Count != outPositions.Count) mesh.RecalculateNormals();
        mesh.RecalculateTangents();
        mesh.RecalculateBounds();
        return mesh;

        int Corner(string token)
        {
            var ids = token.Split('/');
            var key = (Index(ids, 0), Index(ids, 1), Index(ids, 2));
            if (corners.TryGetValue(key, out var index)) return index;
            index = outPositions.Count;
            corners[key] = index;
            outPositions.Add(rootToNode.MultiplyPoint3x4(positions[key.Item1]));
            if (key.Item3 >= 0) outNormals.Add(rootToNode.MultiplyVector(normals[key.Item3]).normalized);
            if (key.Item2 >= 0) outUvs.Add(uvs[key.Item2]);
            if (skin.Count == positions.Count) outSkin.Add(skin[key.Item1]);
            return index;
        }
    }

    static int Index(string[] ids, int slot) => slot < ids.Length && ids[slot].Length > 0 ? int.Parse(ids[slot], CultureInfo.InvariantCulture) - 1 : -1;

    static int I(string text) => int.Parse(text, CultureInfo.InvariantCulture);

    static float F(string text) => float.Parse(text, CultureInfo.InvariantCulture);
}
