using System;
using System.Buffers.Binary;
using System.IO;
using System.IO.Compression;
using System.Text;

namespace Kollektion.Core.GameData
{
    /// <summary>An 8-bit image: 1 (grey), 2 (grey, alpha), 3 (RGB) or 4 (RGBA) channels, rows top to bottom.</summary>
    public sealed class Image
    {
        public int Width { get; }
        public int Height { get; }
        public int Channels { get; }
        public byte[] Pixels { get; }

        public Image(int width, int height, int channels, byte[] pixels = null)
        {
            if (width < 0 || height < 0 || channels < 1 || channels > 4) throw new ArgumentException("bad image shape");
            Width = width;
            Height = height;
            Channels = channels;
            Pixels = pixels ?? new byte[width * height * channels];
            if (Pixels.Length != width * height * channels) throw new ArgumentException("pixel count doesn't match");
        }

        /// <summary>As Pillow's convert("RGB"): grey copied to each channel, alpha dropped.</summary>
        public Image ToRgb()
        {
            if (Channels == 3) return this;
            var rgb = new byte[Width * Height * 3];
            for (int i = 0, n = Width * Height; i < n; i++)
            {
                int s = i * Channels;
                if (Channels <= 2)
                    rgb[i * 3] = rgb[i * 3 + 1] = rgb[i * 3 + 2] = Pixels[s];
                else
                {
                    rgb[i * 3] = Pixels[s]; rgb[i * 3 + 1] = Pixels[s + 1]; rgb[i * 3 + 2] = Pixels[s + 2];
                }
            }
            return new Image(Width, Height, 3, rgb);
        }
    }

    /// <summary>PNG reading and writing for 8-bit, non-interlaced images, on the framework's zlib (no dependency).
    /// The writer picks a filter per row as libpng does (smallest sum of absolute differences); its bytes differ
    /// from Pillow's, its pixels don't.</summary>
    public static class Png
    {
        static readonly byte[] Signature = { 137, 80, 78, 71, 13, 10, 26, 10 };
        static readonly uint[] CrcTable = BuildCrcTable();

        static uint[] BuildCrcTable()
        {
            var t = new uint[256];
            for (uint n = 0; n < 256; n++)
            {
                uint c = n;
                for (int k = 0; k < 8; k++) c = (c & 1) != 0 ? 0xEDB88320u ^ (c >> 1) : c >> 1;
                t[n] = c;
            }
            return t;
        }

        static uint Crc(uint crc, byte[] data, int offset, int count)
        {
            for (int i = offset; i < offset + count; i++) crc = CrcTable[(crc ^ data[i]) & 0xff] ^ (crc >> 8);
            return crc;
        }

        static int ColourType(int channels) => channels switch { 1 => 0, 2 => 4, 3 => 2, 4 => 6, _ => -1 };

        /// <summary>Writes under a temporary name and renames it into place, so an interrupted run leaves the old file
        /// or none (Blender loads a partial PNG as an empty image).</summary>
        public static void Write(string path, Image image)
        {
            var tmp = path + ".part";
            try
            {
                using (var f = new FileStream(tmp, FileMode.Create, FileAccess.Write))
                    Write(f, image);
                File.Move(tmp, path, true);
            }
            finally
            {
                if (File.Exists(tmp)) File.Delete(tmp);
            }
        }

        public static void Write(Stream output, Image image)
        {
            output.Write(Signature, 0, Signature.Length);
            var ihdr = new byte[13];
            BinaryPrimitives.WriteInt32BigEndian(ihdr.AsSpan(0), image.Width);
            BinaryPrimitives.WriteInt32BigEndian(ihdr.AsSpan(4), image.Height);
            ihdr[8] = 8;
            ihdr[9] = (byte)ColourType(image.Channels);
            WriteChunk(output, "IHDR", ihdr, ihdr.Length);
            using (var idat = new MemoryStream())
            {
                using (var z = new ZLibStream(idat, CompressionLevel.Optimal, true))
                    WriteFiltered(z, image);
                WriteChunk(output, "IDAT", idat.GetBuffer(), (int)idat.Length);
            }
            WriteChunk(output, "IEND", Array.Empty<byte>(), 0);
        }

        static void WriteChunk(Stream output, string type, byte[] data, int length)
        {
            var head = new byte[8];
            BinaryPrimitives.WriteInt32BigEndian(head, length);
            Encoding.ASCII.GetBytes(type, 0, 4, head, 4);
            output.Write(head, 0, 8);
            output.Write(data, 0, length);
            uint crc = Crc(Crc(0xFFFFFFFFu, head, 4, 4), data, 0, length) ^ 0xFFFFFFFFu;
            var tail = new byte[4];
            BinaryPrimitives.WriteUInt32BigEndian(tail, crc);
            output.Write(tail, 0, 4);
        }

        static void WriteFiltered(Stream z, Image image)
        {
            int bpp = image.Channels, stride = image.Width * bpp;
            var prior = new byte[stride];
            var row = new byte[stride];
            var best = new byte[stride + 1];
            var trial = new byte[stride + 1];
            for (int y = 0; y < image.Height; y++)
            {
                Buffer.BlockCopy(image.Pixels, y * stride, row, 0, stride);
                long bestSum = long.MaxValue;
                for (byte filter = 0; filter <= 4; filter++)
                {
                    trial[0] = filter;
                    long sum = 0;
                    for (int i = 0; i < stride; i++)
                    {
                        int a = i >= bpp ? row[i - bpp] : 0, b = prior[i], c = i >= bpp ? prior[i - bpp] : 0;
                        byte v = (byte)(row[i] - Predict(filter, a, b, c));
                        trial[i + 1] = v;
                        sum += v < 128 ? v : 256 - v;
                    }
                    if (sum < bestSum)
                    {
                        bestSum = sum;
                        Buffer.BlockCopy(trial, 0, best, 0, stride + 1);
                    }
                }
                z.Write(best, 0, stride + 1);
                (prior, row) = (row, prior);
            }
        }

        static int Predict(int filter, int a, int b, int c)
        {
            switch (filter)
            {
                case 0: return 0;
                case 1: return a;
                case 2: return b;
                case 3: return (a + b) >> 1;
                default:
                    int p = a + b - c, pa = Math.Abs(p - a), pb = Math.Abs(p - b), pc = Math.Abs(p - c);
                    return pa <= pb && pa <= pc ? a : pb <= pc ? b : c;
            }
        }

        public static Image Read(string path)
        {
            using var f = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
            return Read(f, path);
        }

        public static Image Read(Stream input, string name = "PNG")
        {
            var sig = new byte[8];
            if (ReadFull(input, sig) != 8 || !sig.AsSpan().SequenceEqual(Signature))
                throw new InvalidDataException($"{name}: not a PNG");
            int width = 0, height = 0, channels = 0;
            var idat = new MemoryStream();
            var head = new byte[8];
            while (true)
            {
                if (ReadFull(input, head) != 8) throw new InvalidDataException($"{name}: truncated");
                int length = BinaryPrimitives.ReadInt32BigEndian(head);
                var type = Encoding.ASCII.GetString(head, 4, 4);
                if (length < 0) throw new InvalidDataException($"{name}: bad chunk length");
                var data = new byte[length + 4];
                if (ReadFull(input, data) != data.Length) throw new InvalidDataException($"{name}: truncated");
                uint crc = Crc(Crc(0xFFFFFFFFu, head, 4, 4), data, 0, length) ^ 0xFFFFFFFFu;
                if (crc != BinaryPrimitives.ReadUInt32BigEndian(data.AsSpan(length)))
                    throw new InvalidDataException($"{name}: {type} chunk fails its CRC");
                if (type == "IHDR")
                {
                    width = BinaryPrimitives.ReadInt32BigEndian(data);
                    height = BinaryPrimitives.ReadInt32BigEndian(data.AsSpan(4));
                    int depth = data[8], colour = data[9], interlace = data[12];
                    channels = colour switch { 0 => 1, 4 => 2, 2 => 3, 6 => 4, _ => 0 };
                    if (depth != 8 || channels == 0 || interlace != 0)
                        throw new NotSupportedException($"{name}: only 8-bit grey, RGB and RGBA PNGs without interlacing are read " +
                                                        $"(bit depth {depth}, colour type {colour}, interlace {interlace})");
                }
                else if (type == "IDAT")
                    idat.Write(data, 0, length);
                else if (type == "IEND")
                    break;
            }
            if (channels == 0) throw new InvalidDataException($"{name}: no IHDR");
            int stride = width * channels;
            var pixels = new byte[stride * height];
            idat.Position = 0;
            using (var z = new ZLibStream(idat, CompressionMode.Decompress))
            {
                var prior = new byte[stride];
                var row = new byte[stride + 1];
                for (int y = 0; y < height; y++)
                {
                    if (ReadFull(z, row) != row.Length) throw new InvalidDataException($"{name}: image data ends early");
                    int filter = row[0];
                    if (filter > 4) throw new InvalidDataException($"{name}: unknown filter {filter}");
                    int at = y * stride;
                    for (int i = 0; i < stride; i++)
                    {
                        int a = i >= channels ? pixels[at + i - channels] : 0, b = prior[i];
                        int c = i >= channels ? prior[i - channels] : 0;
                        pixels[at + i] = (byte)(row[i + 1] + Predict(filter, a, b, c));
                    }
                    Buffer.BlockCopy(pixels, at, prior, 0, stride);
                }
            }
            return new Image(width, height, channels, pixels);
        }

        static int ReadFull(Stream s, byte[] buffer)
        {
            int n = 0;
            while (n < buffer.Length)
            {
                int r = s.Read(buffer, n, buffer.Length - n);
                if (r == 0) break;
                n += r;
            }
            return n;
        }
    }
}
