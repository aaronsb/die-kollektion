using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Kollektion.Core.GameData;

// Usage: dotnet run --project tools/gamedata-check [-f net6.0]
// Checks the pieces of `kollektion extract` that decide whether its files match the Python pipeline's, and that it
// refuses damaged game files instead of writing wrong ones, with no game files: every expected value below was printed
// by CPython 3.14, Pillow 13.0.0 and UnityPy 1.25.4 (the pipeline's own libraries; the longer ones are in Oracles.cs),
// and the bundles are made from scratch (Synthetic.cs). It builds for net10.0 (kollektion's runtime) and net6.0 (the
// game's, which the plugin shares).
//
// `... -- extract <game folder> <out dir> [<vehicles dir>]` runs the real extraction instead, to confirm it on the
// runtime the check was started on (the game's .NET 6, for one); it reads the game folder only.
Console.WriteLine($"runtime: .NET {Environment.Version}");
if (args.Length >= 3 && args[0] == "extract")
{
    Extraction.Run(args[1], args.Length > 3 ? args[3] : null, null, args[2], Console.WriteLine);
    Console.WriteLine($"extracted into {args[2]}");
    return 0;
}
var failed = 0;

void Check(bool ok, string what)
{
    Console.WriteLine($"{(ok ? "ok  " : "FAIL")} {what}");
    if (!ok) failed++;
}

void Throws<T>(Action action, string what) where T : Exception
{
    try
    {
        action();
        Check(false, $"{what}: accepted, should be refused");
    }
    catch (T)
    {
        Check(true, what);
    }
    catch (Exception e)
    {
        Check(false, $"{what}: refused with {e.GetType().Name} ({e.Message}), not {typeof(T).Name}");
    }
}

// Numbers: f"{x:.6f}", f"{x:.3f}", f"{x:.8f}", repr(x), round(x, 5), round(x, 6) + 0.0.
var numbers = new (double X, string F6, string F3, string F8, string Repr, string Round5, string Round6)[]
{
    (0.0, "0.000000", "0.000", "0.00000000", "0.0", "0.0", "0.0"),
    (-0.0, "-0.000000", "-0.000", "-0.00000000", "-0.0", "-0.0", "0.0"),
    (1.0, "1.000000", "1.000", "1.00000000", "1.0", "1.0", "1.0"),
    (-1.0, "-1.000000", "-1.000", "-1.00000000", "-1.0", "-1.0", "-1.0"),
    (0.0078125, "0.007812", "0.008", "0.00781250", "0.0078125", "0.00781", "0.007812"),
    (-0.0078125, "-0.007812", "-0.008", "-0.00781250", "-0.0078125", "-0.00781", "-0.007812"),
    (5e-07, "0.000000", "0.000", "0.00000050", "5e-07", "0.0", "0.0"),
    (1.0000005, "1.000001", "1.000", "1.00000050", "1.0000005", "1.0", "1.000001"),
    (2.5e-07, "0.000000", "0.000", "0.00000025", "2.5e-07", "0.0", "0.0"),
    (-1e-09, "-0.000000", "-0.000", "-0.00000000", "-1e-09", "-0.0", "0.0"),
    (0.1 + 0.2, "0.300000", "0.300", "0.30000000", "0.30000000000000004", "0.3", "0.3"),
    (1.0 / 3, "0.333333", "0.333", "0.33333333", "0.3333333333333333", "0.33333", "0.333333"),
    (2.0 / 3, "0.666667", "0.667", "0.66666667", "0.6666666666666666", "0.66667", "0.666667"),
    (123.4567895, "123.456789", "123.457", "123.45678950", "123.4567895", "123.45679", "123.456789"),
    (1e16, "10000000000000000.000000", "10000000000000000.000", "10000000000000000.00000000", "1e+16", "1e+16", "1e+16"),
    (1e15, "1000000000000000.000000", "1000000000000000.000", "1000000000000000.00000000", "1000000000000000.0", "1000000000000000.0", "1000000000000000.0"),
    (1e-05, "0.000010", "0.000", "0.00001000", "1e-05", "1e-05", "1e-05"),
    (0.0001, "0.000100", "0.000", "0.00010000", "0.0001", "0.0001", "0.0001"),
    (1.5e-07, "0.000000", "0.000", "0.00000015", "1.5e-07", "0.0", "0.0"),
    (3.4028234663852886e+38, "340282346638528859811704183484516925440.000000", "340282346638528859811704183484516925440.000",
     "340282346638528859811704183484516925440.00000000", "3.4028234663852886e+38", "3.4028234663852886e+38", "3.4028234663852886e+38"),
    (5e-324, "0.000000", "0.000", "0.00000000", "5e-324", "0.0", "0.0"),
    (0.30000001192092896, "0.300000", "0.300", "0.30000001", "0.30000001192092896", "0.3", "0.3"),
    (-0.071, "-0.071000", "-0.071", "-0.07100000", "-0.071", "-0.071", "-0.071"),
    (100.0, "100.000000", "100.000", "100.00000000", "100.0", "100.0", "100.0"),
    (1234567.0000005, "1234567.000000", "1234567.000", "1234567.00000050", "1234567.0000005", "1234567.0", "1234567.0"),
    (0.125, "0.125000", "0.125", "0.12500000", "0.125", "0.125", "0.125"),
    (2.675, "2.675000", "2.675", "2.67500000", "2.675", "2.675", "2.675"),
    (1.0000000000000002, "1.000000", "1.000", "1.00000000", "1.0000000000000002", "1.0", "1.0"),
    (1e23, "99999999999999991611392.000000", "99999999999999991611392.000", "99999999999999991611392.00000000", "1e+23", "1e+23", "1e+23"),
    (0.8, "0.800000", "0.800", "0.80000000", "0.8", "0.8", "0.8"),
    (1.5e-05, "0.000015", "0.000", "0.00001500", "1.5e-05", "2e-05", "1.5e-05"),
    (2.5e-05, "0.000025", "0.000", "0.00002500", "2.5e-05", "3e-05", "2.5e-05"),
};
var badNumbers = numbers.Where(n => PyFormat.Fixed(n.X, 6) != n.F6 || PyFormat.Fixed(n.X, 3) != n.F3 || PyFormat.Fixed(n.X, 8) != n.F8
                                    || PyFormat.Repr(n.X) != n.Repr || PyFormat.Repr(PyFormat.Round(n.X, 5)) != n.Round5
                                    || PyFormat.Repr(PyFormat.Round(n.X, 6) + 0.0) != n.Round6).ToList();
foreach (var n in badNumbers)
    Console.WriteLine($"     {n.Repr}: {PyFormat.Fixed(n.X, 6)} {PyFormat.Fixed(n.X, 3)} {PyFormat.Fixed(n.X, 8)} {PyFormat.Repr(n.X)} " +
                      $"{PyFormat.Repr(PyFormat.Round(n.X, 5))} {PyFormat.Repr(PyFormat.Round(n.X, 6) + 0.0)}");
Check(badNumbers.Count == 0, $"{numbers.Length} numbers formatted and rounded as Python does (ties to even, -0.000000, repr's exponents)");

// JSON: json.dumps(data, indent=1).
var data = new PyDict
{
    ["root"] = "Car_X", ["a"] = new List<object>(), ["b"] = new PyDict(),
    ["c"] = new List<object> { 1, -2, 3000000000L, 1.5, -0.0, true, false, null },
    ["d"] = new PyDict
    {
        ["nested"] = new List<object>
        {
            new PyDict { ["x"] = "quote \" back \\ nl \n tab \t", ["u"] = "Größe – ✓ 😀", ["ctl"] = "\u0001\u007f" },
        },
    },
    ["e"] = new List<object> { new List<object> { 0.30000001192092896, 1e-05, 1e16 } },
};
const string json = "{\n \"root\": \"Car_X\",\n \"a\": [],\n \"b\": {},\n \"c\": [\n  1,\n  -2,\n  3000000000,\n  1.5,\n  -0.0,\n  true,\n  false,\n  null\n ],\n \"d\": {\n  \"nested\": [\n   {\n    \"x\": \"quote \\\" back \\\\ nl \\n tab \\t\",\n    \"u\": \"Gr\\u00f6\\u00dfe \\u2013 \\u2713 \\ud83d\\ude00\",\n    \"ctl\": \"\\u0001\\u007f\"\n   }\n  ]\n },\n \"e\": [\n  [\n   0.30000001192092896,\n   1e-05,\n   1e+16\n  ]\n ]\n}";
Check(PyJson.Dump(data) == json, "JSON as json.dump(indent=1) writes it: layout, ASCII escapes, floats, empty containers");

// BC1 and BC3: two blocks each, decoded by Pillow's "bcn" decoder.
byte[] colour4 = { 0x00, 0xF8, 0x1F, 0x00, 0b11100100, 0b00011011, 0xAA, 0x55 };          // c0 > c1: four colours
byte[] colour3 = { 0x1F, 0x00, 0x00, 0xF8, 0b11100100, 0b11100100, 0b11100100, 0b11100100 }; // c0 <= c1: three + transparent
byte[] alphaHigh = { 200, 40, 0b10001000, 0b11000110, 0b11111010, 0b00000101, 0b00111001, 0b01110111 };  // a0 > a1
byte[] alphaLow = { 40, 200, 0b10001000, 0b11000110, 0b11111010, 0b00000101, 0b00111001, 0b01110111 };   // a0 <= a1
int[] bc1 =
{
    255, 0, 0, 255, 0, 0, 255, 255, 170, 0, 85, 255, 85, 0, 170, 255, 0, 0, 255, 255, 255, 0, 0, 255, 127, 0, 127, 255, 0, 0, 0, 0,
    85, 0, 170, 255, 170, 0, 85, 255, 0, 0, 255, 255, 255, 0, 0, 255, 0, 0, 255, 255, 255, 0, 0, 255, 127, 0, 127, 255, 0, 0, 0, 0,
    170, 0, 85, 255, 170, 0, 85, 255, 170, 0, 85, 255, 170, 0, 85, 255, 0, 0, 255, 255, 255, 0, 0, 255, 127, 0, 127, 255, 0, 0, 0, 0,
    0, 0, 255, 255, 0, 0, 255, 255, 0, 0, 255, 255, 0, 0, 255, 255, 0, 0, 255, 255, 255, 0, 0, 255, 127, 0, 127, 255, 0, 0, 0, 0,
};
int[] bc3 =
{
    255, 0, 0, 200, 0, 0, 255, 40, 170, 0, 85, 177, 85, 0, 170, 154, 0, 0, 255, 40, 255, 0, 0, 200, 85, 0, 170, 72, 170, 0, 85, 104,
    85, 0, 170, 131, 170, 0, 85, 108, 0, 0, 255, 85, 255, 0, 0, 62, 0, 0, 255, 136, 255, 0, 0, 168, 85, 0, 170, 0, 170, 0, 85, 255,
    170, 0, 85, 108, 170, 0, 85, 200, 170, 0, 85, 131, 170, 0, 85, 131, 0, 0, 255, 168, 255, 0, 0, 40, 85, 0, 170, 136, 170, 0, 85, 136,
    0, 0, 255, 154, 0, 0, 255, 85, 0, 0, 255, 108, 0, 0, 255, 154, 0, 0, 255, 104, 255, 0, 0, 0, 85, 0, 170, 168, 170, 0, 85, 104,
};
Check(Bcn.DecodeBc1(colour4.Concat(colour3).ToArray(), 8, 4).Select(b => (int)b).SequenceEqual(bc1),
      "BC1: both colour modes, transparent black, Pillow's rounding");
Check(Bcn.DecodeBc3(alphaHigh.Concat(colour4).Concat(alphaLow).Concat(colour3).ToArray(), 8, 4).Select(b => (int)b).SequenceEqual(bc3),
      "BC3: both alpha modes, four colours always, Pillow's rounding");
Throws<InvalidDataException>(() => Bcn.DecodeBc1(colour4, 8, 4), "BC1: too few bytes for the size");

// PNG: a file with each filter type (made with zlib, read back by Pillow), and round trips of each layout.
var fixture = Convert.FromBase64String(
    "iVBORw0KGgoAAAANSUhEUgAAAAMAAAAFCAIAAAAPE8H1AAAANklEQVR4nGNgYOXWYOUOYOVmZHfk1mBQBCImdhsGdhtFdhsnZr5qNgk5Jwm5YBaQGIMiO4MTAHPhBQhTWaY2AAAAAElFTkSuQmCC");
int[] fixturePixels =
{
    0, 5, 11, 40, 5, 11, 80, 5, 11, 7, 65, 11, 47, 65, 44, 87, 65, 77, 14, 125, 11, 54, 125, 77, 94, 125, 143, 21, 185, 11,
    61, 185, 110, 101, 185, 209, 28, 245, 11, 68, 245, 143, 108, 245, 19,
};
var read = Png.Read(new MemoryStream(fixture));
Check(read.Width == 3 && read.Height == 5 && read.Channels == 3 && read.Pixels.Select(b => (int)b).SequenceEqual(fixturePixels),
      "PNG read: filters None, Sub, Up, Average, Paeth");
var random = new Random(7);
foreach (var channels in new[] { 1, 2, 3, 4 })
{
    var img = new Image(37, 23, channels);
    for (int i = 0; i < img.Pixels.Length; i++)
        img.Pixels[i] = (byte)(i % 3 == 0 ? random.Next(256) : (i / 5) % 256);   // noise and gradients: every filter wins somewhere
    var stream = new MemoryStream();
    Png.Write(stream, img);
    var back = Png.Read(new MemoryStream(stream.ToArray()));
    Check(back.Width == 37 && back.Height == 23 && back.Channels == channels && back.Pixels.SequenceEqual(img.Pixels),
          $"PNG round trip, {channels} channel(s)");
}
var corrupt = (byte[])fixture.Clone();
corrupt[40] ^= 1;
Throws<InvalidDataException>(() => Png.Read(new MemoryStream(corrupt)), "PNG read: a damaged chunk fails its CRC");

// Pillow's polygon fill on a mode "1" image: ImageDraw.polygon(t, fill=1) for each triangle, 12 x 9.
var mask = new byte[12 * 9];
foreach (var t in new[]
         {
             new[] { 0.5, 0.2, 7.9, 1.0, 3.2, 8.7 }, new[] { 11.0, 0.0, 11.0, 8.0, 6.0, 4.0 }, new[] { 2.0, 3.0, 9.0, 3.0, 5.5, 3.0 },
         })
    PillowPolygon.Fill(mask, 12, 9, t);
string[] polygon =
{
    "1..........1", "11111111..11", ".111111..111", ".11111111111", "..1111111111", "..1111.11111", "..111....111", "...11.....11",
    "...1.......1",
};
var rows = Enumerable.Range(0, 9).Select(y => new string(Enumerable.Range(0, 12).Select(x => mask[y * 12 + x] != 0 ? '1' : '.').ToArray()));
Check(rows.SequenceEqual(polygon), "polygon fill: truncated vertices, corners and a flat triangle as Pillow fills them");

// Mesh decoding: two streams (the second 16-byte aligned), float positions, half normals, float UVs, two submeshes.
var channelsList = new VertexChannel[14];
channelsList[0] = new VertexChannel(0, 0, 0, 3);      // position: float × 3
channelsList[1] = new VertexChannel(0, 12, 1, 4);     // normal: half × 4
channelsList[4] = new VertexChannel(1, 0, 0, 2);      // UV0, stream 1: float × 2
var vertexData = new MemoryStream();
var w = new BinaryWriter(vertexData);
double[][] positions = { new[] { 1.5, -2.0, 0.25 }, new[] { 0.0, 3.0, -1.0 }, new[] { -0.5, 0.125, 8.0 } };
double[][] normals = { new[] { 0.0, 1.0, 0.0, 0.0 }, new[] { -1.0, 0.0, 0.0, 0.0 }, new[] { 0.5, -0.5, 0.25, 1.0 } };
double[][] uvs = { new[] { 0.0, 1.0 }, new[] { 0.75, 0.5 }, new[] { 1.0, 0.0 } };
for (int i = 0; i < 3; i++)
{
    foreach (var p in positions[i]) w.Write((float)p);
    foreach (var n in normals[i]) w.Write((Half)n);
}
while (vertexData.Length % 16 != 0) w.Write((byte)0xEE);  // stream 0 is 60 bytes; stream 1 starts at 64
foreach (var uv in uvs) { w.Write((float)uv[0]); w.Write((float)uv[1]); }
ushort[] indices16 = { 0, 1, 2, 2, 1, 0 };
var indexBytes = indices16.SelectMany(BitConverter.GetBytes).ToArray();
var subMeshes = new[] { new SubMesh(0, 3, 0, 0), new SubMesh(6, 3, 0, 0) };
var mesh = MeshData.Decode("synthetic", 3, channelsList, vertexData.ToArray(), indexBytes, true, subMeshes);
bool Same(double[][] a, double[][] b) => a.Length == b.Length && a.Zip(b).All(p => p.First.SequenceEqual(p.Second));
Check(Same(mesh.Vertices, positions) && Same(mesh.Normals, normals) && Same(mesh.UV0, uvs) && mesh.BoneWeights == null,
      "mesh: positions, half normals and UVs from two aligned streams");
Check(mesh.Triangles.SequenceEqual(new[] { (0, 1, 2), (2, 1, 0) }), "mesh: two submeshes of 16-bit indices");
var indices32 = new uint[] { 2, 0, 1 }.SelectMany(BitConverter.GetBytes).ToArray();
var mesh32 = MeshData.Decode("synthetic32", 3, channelsList, vertexData.ToArray(), indices32, false, new[] { new SubMesh(0, 3, 0, 0) });
Check(mesh32.Triangles.SequenceEqual(new[] { (2, 0, 1) }), "mesh: 32-bit indices");
Throws<NotSupportedException>(() => MeshData.Decode("based", 3, channelsList, vertexData.ToArray(), indexBytes, true, new[] { new SubMesh(0, 3, 0, 1) }),
                              "mesh: a submesh with baseVertex is refused (UnityPy ignores it)");
Throws<NotSupportedException>(() => MeshData.Decode("quads", 3, channelsList, vertexData.ToArray(), indexBytes, true, new[] { new SubMesh(0, 3, 2, 0) }),
                              "mesh: a non-triangle topology is refused");
Throws<InvalidDataException>(() => MeshData.Decode("short", 2, channelsList, vertexData.ToArray(), indexBytes, true, subMeshes),
                             "mesh: an index past the vertices is refused");
Throws<InvalidDataException>(() => MeshData.Decode("cut", 3, channelsList, vertexData.ToArray().AsSpan(0, 70).ToArray(), indexBytes, true, subMeshes),
                             "mesh: vertex data that ends early is refused");

// The composite: green-only mask texels become glass grey, the rest keep the livery.
var skin = new Image(3, 1, 4, new byte[] { 10, 20, 30, 255, 40, 50, 60, 0, 70, 80, 90, 128 });
var masks = new Image(3, 1, 4, new byte[] { 0, 200, 0, 255, 200, 200, 0, 255, 0, 0, 255, 255 });
var baked = Composite.Bake(skin, masks, out int glass);
Check(glass == 1 && baked.Channels == 3 && baked.Pixels.SequenceEqual(new byte[] { 38, 40, 44, 40, 50, 60, 70, 80, 90 }),
      "composite: glass (green alone) baked grey, lenses and paint keep the livery, alpha dropped");

// The composite's mask resize: Pillow's NEAREST, for sizes up and down and mixed.
foreach (var (sw, sh, dw, dh, index) in Oracles.Nearest)
{
    var numbered = new Image(sw, sh, 2, Enumerable.Range(0, sw * sh).SelectMany(i => new[] { (byte)i, (byte)(i >> 8) }).ToArray());
    var resized = Composite.ResizeNearest(numbered, dw, dh);
    var got = Enumerable.Range(0, dw * dh).Select(i => resized.Pixels[i * 2] | resized.Pixels[i * 2 + 1] << 8);
    Check(resized.Width == dw && resized.Height == dh && got.SequenceEqual(index), $"composite resize {sw}x{sh} -> {dw}x{dh} as Pillow's NEAREST");
}
var bigSkin = new Image(4, 2, 3);
var smallMask = new Image(2, 1, 3, new byte[] { 0, 255, 0, 255, 255, 255 });     // glass on the left half only
Composite.Bake(bigSkin, smallMask, out int resizedGlass);
Check(resizedGlass == 4, "composite: a mask smaller than the livery is resized to it");

// Textures: RGB24 and RGBA32 as stored (the first mip; mips after it ignored), rows flipped to top-down.
var rgb24 = Textures.DecodeBottomUp("rgb", 3, 2, 2, new byte[] { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 99, 99, 99 });
Check(rgb24.Channels == 3 && rgb24.Pixels.SequenceEqual(new byte[] { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 }), "RGB24: 3 channels, first mip only");
var rgba32 = Textures.DecodeBottomUp("rgba", 4, 1, 2, new byte[] { 1, 2, 3, 4, 5, 6, 7, 8 });
Check(rgba32.Channels == 4 && Textures.FlipRows(rgba32).Pixels.SequenceEqual(new byte[] { 5, 6, 7, 8, 1, 2, 3, 4 }),
      "RGBA32: 4 channels, rows flipped top to bottom as UnityPy's image");
Throws<InvalidDataException>(() => Textures.DecodeBottomUp("short", 4, 2, 2, new byte[15]), "texture: image data that ends early is refused");
Throws<InvalidDataException>(() => Textures.DecodeBottomUp("huge", 4, 100000, 2, new byte[16]), "texture: an impossible size is refused");
Throws<NotSupportedException>(() => Textures.DecodeBottomUp("etc", 34, 4, 4, new byte[16]), "texture: an unknown format is refused");

// Sprites, against UnityPy's get_image_from_sprite: Rectangle packing keeps the whole rect, Tight masks it by the mesh,
// packed sprites are turned back by their rotation.
var spriteTexture = new Image(6, 5, 4, Oracles.SpriteTexture);
var spriteChannels = new VertexChannel[1];
spriteChannels[0] = new VertexChannel(0, 0, 0, 3);
var spriteVertexBytes = Oracles.SpriteVertices.SelectMany(v => v.SelectMany(x => BitConverter.GetBytes((float)x))).ToArray();
var spriteMesh = MeshData.Decode("sprite", 3, spriteChannels, spriteVertexBytes, new ushort[] { 0, 1, 2 }.SelectMany(BitConverter.GetBytes).ToArray(),
                                 true, new[] { new SubMesh(0, 3, 0, 0) });
var r = Oracles.SpriteRect;
foreach (var (settings, width, height, rgba) in Oracles.Sprites)
{
    var cut = Textures.Cut("sprite", spriteTexture, r[0], r[1], r[2], r[3], settings, () => spriteMesh, Oracles.SpritePixelsPerUnit);
    Check(cut.Width == width && cut.Height == height && cut.Channels == 4 && cut.Pixels.SequenceEqual(rgba),
          $"sprite settingsRaw {settings}: {((settings & 2) != 0 ? "Rectangle, not masked" : "Tight, masked by its mesh")}, " +
          $"{((settings & 1) != 0 ? $"packed, rotation {(settings >> 2) & 15}" : "not packed")}, as UnityPy draws it");
}
Throws<InvalidDataException>(() => Textures.Cut("sprite", spriteTexture, r[0], r[1], r[2], r[3], 0b10111u, () => spriteMesh, 2),
                             "sprite: an unknown packing rotation is refused (UnityPy raises)");

// Meshes: normalised integer formats on a channel read as numbers are refused (UnityPy reads them as raw integers).
foreach (var (channel, label) in new[] { (0, "position"), (1, "normal"), (4, "UV0"), (12, "bone weights") })
    foreach (var format in new[] { 2, 3, 4, 5 })
    {
        var unorm = new VertexChannel[14];
        unorm[0] = new VertexChannel(0, 0, 0, 3);
        unorm[channel] = new VertexChannel(0, channel == 0 ? 0 : 12, format, 4);
        Throws<NotSupportedException>(() => MeshData.Decode("unorm", 3, unorm, new byte[64], indexBytes, true, subMeshes),
                                      $"mesh: {label} in vertex format {format} is refused");
    }
var colours = new VertexChannel[14];
colours[0] = new VertexChannel(0, 0, 0, 3);
colours[3] = new VertexChannel(0, 12, 2, 4);                               // colour as UNorm8 x 4: not read, accepted
Check(MeshData.Decode("colours", 3, colours, new byte[64], indexBytes, true, subMeshes).Vertices.Length == 3,
      "mesh: a normalised format on a channel nothing reads is accepted");

// Skinning: one or two influences per vertex padded to four with weight 0, as Unity leaves them out.
var skinChannels = new VertexChannel[14];
skinChannels[0] = new VertexChannel(0, 0, 0, 3);
skinChannels[12] = new VertexChannel(0, 12, 0, 2);                          // two float weights
skinChannels[13] = new VertexChannel(0, 20, 8, 2);                          // two UInt16 bone indices
var skinData = new MemoryStream();
var sw2 = new BinaryWriter(skinData);
for (int i = 0; i < 3; i++)
{
    sw2.Write(0f); sw2.Write(0f); sw2.Write(0f);
    sw2.Write(0.25f); sw2.Write(0.75f);
    sw2.Write((ushort)(i + 1)); sw2.Write((ushort)7);
}
var skinned = MeshData.Decode("skinned", 3, skinChannels, skinData.ToArray(), indexBytes, true, subMeshes);
var (padW, padB) = ObjExport.Skin(skinned);
Check(padW[1].SequenceEqual(new[] { 0.25, 0.75, 0, 0 }) && padB[1].SequenceEqual(new double[] { 2, 7, 0, 0 }),
      "skinning: two influences padded to four (weight 0, bone 0)");
var noIndices = new VertexChannel[14];
noIndices[0] = skinChannels[0];
noIndices[12] = skinChannels[12];
Throws<InvalidDataException>(() => ObjExport.Skin(MeshData.Decode("weights only", 3, noIndices, skinData.ToArray(), indexBytes, true, subMeshes)),
                             "skinning: weights without bone indices are refused");

// LZ4: round trips of AssetsTools.NET's own encoder, and every way a damaged block must fail.
var lz4Plain = Enumerable.Range(0, 5000).Select(i => (byte)(i % 7 == 0 ? random.Next(256) : (i / 13) % 251)).ToArray();
var lz4Packed = LZ4ps.LZ4Codec.Encode32HC(lz4Plain, 0, lz4Plain.Length);
var lz4Out = new byte[lz4Plain.Length];
Lz4.Decode(lz4Packed, lz4Out);
Check(lz4Out.SequenceEqual(lz4Plain) && lz4Packed.Length < lz4Plain.Length, "LZ4: a block decodes exactly");
Throws<InvalidDataException>(() => Lz4.Decode(lz4Packed.AsSpan(0, lz4Packed.Length - 9).ToArray(), new byte[lz4Plain.Length]),
                             "LZ4: a block cut short is refused");
Throws<InvalidDataException>(() => Lz4.Decode(lz4Packed, new byte[lz4Plain.Length + 1]), "LZ4: a block shorter than the table says is refused");
Throws<InvalidDataException>(() => Lz4.Decode(lz4Packed, new byte[lz4Plain.Length - 1]), "LZ4: a block longer than the table says is refused");
Throws<InvalidDataException>(() => Lz4.Decode(new byte[] { 0x10, 65, 0, 0 }, new byte[5]), "LZ4: a match offset of 0 is refused");
Throws<InvalidDataException>(() => Lz4.Decode(new byte[] { 0x10, 65, 2, 0 }, new byte[5]), "LZ4: a match before the block's start is refused");

// Bundles: synthetic UnityFS files (no game data) read whole, and refused when cut, padded, damaged or inconsistent.
var temp = Path.Combine(Path.GetTempPath(), $"gamedata-check-{Environment.ProcessId}");
Directory.CreateDirectory(temp);
try
{
    var entry = Enumerable.Range(0, 700).Select(i => (byte)(i % 3 == 0 ? random.Next(256) : i / 5)).ToArray();
    var good = SyntheticBundle.Make(new[] { ("CAB-test.resS", 0u, entry) }, 256, true);
    string Save(string name, byte[] bytes)
    {
        var p = Path.Combine(temp, name);
        File.WriteAllBytes(p, bytes);
        return p;
    }
    byte[] ReadAll(Stream s)
    {
        var m = new MemoryStream();
        s.CopyTo(m);
        return m.ToArray();
    }
    var goodPath = Save("good.bundle", good.Bytes);
    using (var b = new Bundles())
    {
        var loaded = b.Load(goodPath);
        Check(loaded.Files.Count == 0 && ReferenceEquals(loaded, b.Load(goodPath)), "bundle: a whole one loads; loading it again returns the same");
        b.CheckUnchanged();
        File.SetLastWriteTimeUtc(goodPath, DateTime.UtcNow.AddMinutes(1));
        Throws<GameDataException>(() => b.CheckUnchanged(), "bundle: one changed while held is noticed");
    }
    using (var f = File.OpenRead(goodPath))
        Check(ReadAll(new BundleBlockStream(f, good.DataOffset, good.BlockInfos(), "good")).SequenceEqual(entry),
              "bundle: its blocks decode to the entry's bytes");

    void Refused(string what, byte[] bytes)
    {
        var p = Save("bad.bundle", bytes);
        using var b = new Bundles();
        Throws<GameDataException>(() => b.Load(p), what);
    }
    Refused("bundle: one cut short is refused", good.Bytes.AsSpan(0, good.Bytes.Length - 100).ToArray());
    Refused("bundle: one with bytes after its end is refused", good.Bytes.Concat(new byte[10]).ToArray());
    var cutAndRelabelled = good.Bytes.AsSpan(0, good.Bytes.Length - 100).ToArray();
    SyntheticBundle.SetTotalSize(cutAndRelabelled, cutAndRelabelled.Length);
    Refused("bundle: blocks that run past the file's end are refused", cutAndRelabelled);
    // Damage that breaks a block's structure: its first token says no literals, so a match comes first with nothing
    // before it. (Damage inside literals decodes to wrong bytes undetected: LZ4 blocks carry no checksum.)
    var firstBlockDamaged = (byte[])good.Bytes.Clone();
    firstBlockDamaged[good.DataOffset] = 0;
    Refused("bundle: a damaged first block is refused on load", firstBlockDamaged);
    var serialised = SyntheticBundle.Make(new[] { ("CAB-test", 4u, entry) }, 256, true);
    Refused("bundle: an entry marked serialised that isn't is refused", serialised.Bytes);
    Refused("bundle: an entry that runs past the data is refused", SyntheticBundle.Make(new[] { ("CAB-test.resS", 0u, entry) }, 256, true, 1).Bytes);

    var lastBlock = good.Blocks.Count - 1;
    long lastAt = good.DataOffset + good.Blocks.Take(lastBlock).Sum(x => (long)x.Compressed);
    var lateDamage = (byte[])good.Bytes.Clone();
    lateDamage[lastAt] = 0;
    var lateDamagePath = Save("late.bundle", lateDamage);
    using (var b = new Bundles())
        b.Load(lateDamagePath);                                            // only the first block is read on load
    using (var f = File.OpenRead(lateDamagePath))
        Throws<GameDataException>(() => ReadAll(new BundleBlockStream(f, good.DataOffset, good.BlockInfos(), "late")),
                                  "bundle: a damaged later block is refused when read");
    var wrongSize = good.BlockInfos();
    wrongSize[0].DecompressedSize += 1;
    using (var f = File.OpenRead(goodPath))
        Throws<GameDataException>(() => ReadAll(new BundleBlockStream(f, good.DataOffset, wrongSize, "size")),
                                  "bundle: a block that decodes short of the table's size is refused");
    var stored = good.BlockInfos();
    stored[0].Flags = 0;
    using (var f = File.OpenRead(goodPath))
        Throws<GameDataException>(() => new BundleBlockStream(f, good.DataOffset, stored, "stored"),
                                  "bundle: a stored block whose sizes differ is refused");

    // PeekName: the name read from an object's bytes, and refused when it doesn't fit inside the object.
    var objectBytes = new MemoryStream();
    var ow = new BinaryWriter(objectBytes);
    ow.Write(4); ow.Write("Body".ToCharArray()); ow.Write(0);                // a Mesh: m_Name first
    ow.Write(2); ow.Write(new byte[24]); ow.Write(5u); ow.Write(7); ow.Write("Car_Ute".ToCharArray()); ow.Write((byte)0);
    var objects = new AssetsTools.NET.AssetsFileReader(new MemoryStream(objectBytes.ToArray()));
    Check(Bundles.PeekName(objects, 0, 12, AssetsTools.NET.Extra.AssetClassID.Mesh) == "Body"
          && Bundles.PeekName(objects, 12, 44, AssetsTools.NET.Extra.AssetClassID.GameObject) == "Car_Ute",
          "PeekName: a Mesh's name, and a GameObject's after its components and layer");
    Throws<InvalidDataException>(() => Bundles.PeekName(objects, 0, 6, AssetsTools.NET.Extra.AssetClassID.Mesh),
                                 "PeekName: a name longer than its object is refused");
    Throws<InvalidDataException>(() => Bundles.PeekName(objects, 12, 20, AssetsTools.NET.Extra.AssetClassID.GameObject),
                                 "PeekName: more components than the object holds are refused");
    Throws<NotSupportedException>(() => Bundles.PeekName(objects, 0, 12, AssetsTools.NET.Extra.AssetClassID.MonoBehaviour),
                                  "PeekName: a type whose name isn't first is refused");

    // Output: a failed write leaves the old file and no temporary.
    var outFile = Path.Combine(temp, "out", "file.txt");
    Output.WriteText(outFile, "old");
    Throws<InvalidOperationException>(() => Output.Write(outFile, s => { s.WriteByte(1); throw new InvalidOperationException("stop"); }),
                                      "output: a write that fails is passed on");
    Check(File.ReadAllText(outFile) == "old" && Directory.GetFiles(Path.GetDirectoryName(outFile)).Length == 1,
          "output: a failed write leaves the old file and no temporary");

    // Replacing the output folder whole: a write that fails halfway leaves the old folder and nothing beside it; one
    // that succeeds replaces it entirely; a partial folder of a killed run is removed.
    var whole = Path.Combine(temp, "whole");
    Directory.CreateDirectory(Path.Combine(whole, "mammoth"));
    File.WriteAllText(Path.Combine(whole, "mammoth", "old.obj"), "old");
    var abandoned = Path.Combine(temp, "whole.partial-4194305");            // never a process id, on Linux or Windows
    Directory.CreateDirectory(abandoned);
    var wholeLog = new List<string>();
    Throws<InvalidOperationException>(() => Extraction.ReplaceWhole(whole, (dir, l) =>
    {
        Output.WriteText(Path.Combine(dir, "mammoth", "new.obj"), "new");
        throw new InvalidOperationException("stop halfway");
    }, wholeLog.Add), "replace whole: a write that fails is passed on");
    bool Beside() => Directory.GetDirectories(temp).Any(d => Path.GetFileName(d).StartsWith("whole.", StringComparison.Ordinal));
    Check(Directory.GetFiles(whole, "*", SearchOption.AllDirectories).Select(Path.GetFileName).SequenceEqual(new[] { "old.obj" }) && !Beside(),
          "replace whole: a failed write leaves the old folder as it was, no partial folder, and a killed run's removed");
    Extraction.ReplaceWhole(whole, (dir, l) =>
    {
        Output.WriteText(Path.Combine(dir, "mammoth", "new.obj"), "new");
        l($"{Path.Combine(dir, "mammoth", "new.obj")}: written");
    }, wholeLog.Add);
    Check(Directory.GetFiles(whole, "*", SearchOption.AllDirectories).Select(Path.GetFileName).SequenceEqual(new[] { "new.obj" }) && !Beside()
          && wholeLog.Last() == $"{Path.Combine(whole, "mammoth", "new.obj")}: written",
          "replace whole: a write that succeeds replaces the folder entirely, its log naming the final paths");

    // The extraction as a whole, on a fake game folder of synthetic bundles: it fails before writing anything, and an
    // existing output folder is left as it was with no partial folder beside it.
    var game = Path.Combine(temp, "game");
    var aa = Path.Combine(game, "over the hill_Data", "StreamingAssets", "aa", "StandaloneLinux64");
    Directory.CreateDirectory(aa);
    foreach (var n in new[] { "cars_assets_all_0.bundle", "scriptableobjects_assets_all_0.bundle", "r1_canada_scenes_all_0.bundle", "x_monoscripts_0.bundle" })
        File.WriteAllBytes(Path.Combine(aa, n), good.Bytes);
    var extracted = Path.Combine(temp, "extracted");
    Directory.CreateDirectory(Path.Combine(extracted, "mammoth"));
    File.WriteAllText(Path.Combine(extracted, "mammoth", "earlier.obj"), "earlier");
    bool Untouched() => File.ReadAllText(Path.Combine(extracted, "mammoth", "earlier.obj")) == "earlier"
                        && Directory.GetFileSystemEntries(extracted, "*", SearchOption.AllDirectories).Length == 2
                        && !Directory.GetDirectories(temp).Any(d => Path.GetFileName(d).StartsWith("extracted.", StringComparison.Ordinal));
    var log = new List<string>();
    Throws<GameDataException>(() => Extraction.Run(game, null, null, extracted, log.Add), "extraction: a game without the Mammoth fails");
    Check(Untouched(), "extraction: a failed run leaves the earlier extraction as it was, and no partial folder");
    File.WriteAllBytes(Path.Combine(aa, "cars_assets_all_0.bundle"), good.Bytes.AsSpan(0, 300).ToArray());
    Throws<GameDataException>(() => Extraction.Run(game, null, null, extracted, log.Add), "extraction: a cut bundle fails");
    Check(Untouched(), "extraction: after a cut bundle the earlier extraction is as it was");
    Throws<DonorNameException>(() => Extraction.Run(game, null, new[] { "../x" }, Path.Combine(temp, "new"), log.Add),
                               "extraction: a donor name that isn't a plain name is refused");
    Check(!Directory.Exists(Path.Combine(temp, "new")), "extraction: a refused donor name writes nothing");
    Directory.CreateDirectory(Path.Combine(temp, "home"));
    File.WriteAllText(Path.Combine(temp, "home", "notes.txt"), "mine");
    try
    {
        Extraction.Run(game, null, null, Path.Combine(temp, "home"), log.Add);
        Check(false, "extraction: a folder that isn't an extraction is replaced");
    }
    catch (Exception e)
    {
        Check(e.GetType() == typeof(IOException) && e.Message.Contains("something other than an extraction"),
              $"extraction: a folder that isn't an extraction is not replaced ({e.GetType().Name})");
    }
    Check(File.ReadAllText(Path.Combine(temp, "home", "notes.txt")) == "mine", "extraction: that folder is left as it was");
    var vehicles = Path.Combine(temp, "vehicles", "broken");
    Directory.CreateDirectory(vehicles);
    File.WriteAllText(Path.Combine(vehicles, "vehicle.json"), "{\"donor\": \"Mammoth\",}");
    Throws<InvalidDataException>(() => Extraction.ManifestDonors(Path.GetDirectoryName(vehicles)), "manifests: invalid JSON is refused with its path");
}
finally
{
    Directory.Delete(temp, true);
}

Console.WriteLine(failed == 0 ? "all game-data checks pass" : $"{failed} game-data check(s) failed");
return failed == 0 ? 0 : 1;
