using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Kollektion.Core.GameData;

// Usage: dotnet run --project tools/gamedata-check
// Checks the pieces of `kollektion extract` that decide whether its files match the Python pipeline's, with no game
// files: every expected value below was printed by CPython 3.14 and Pillow 13.0.0 (the pipeline's own libraries).
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
Throws<ArgumentException>(() => Bcn.DecodeBc1(colour4, 8, 4), "BC1: too few bytes for the size");

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

Console.WriteLine(failed == 0 ? "all game-data checks pass" : $"{failed} game-data check(s) failed");
return failed == 0 ? 0 : 1;
