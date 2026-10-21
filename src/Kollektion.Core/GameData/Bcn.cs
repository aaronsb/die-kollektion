using System;

namespace Kollektion.Core.GameData
{
    /// <summary>BC1 (DXT1) and BC3 (DXT5) decoding with Pillow's integer rounding (libImaging/BcnDecode.c), which
    /// UnityPy uses, so the PNGs match the Python pipeline's pixel for pixel. Other decoders round the interpolated
    /// colours differently and are off by 1-2 per channel. Output: RGBA, rows in the data's order.</summary>
    public static class Bcn
    {
        public static byte[] DecodeBc1(byte[] src, int width, int height) => Decode(src, width, height, false);

        public static byte[] DecodeBc3(byte[] src, int width, int height) => Decode(src, width, height, true);

        static void Rgb565(int c, int[] into, int at)
        {
            int r = (c & 0xf800) >> 8; r |= r >> 5;
            int g = (c & 0x7e0) >> 3; g |= g >> 6;
            int b = (c & 0x1f) << 3; b |= b >> 5;
            into[at] = r; into[at + 1] = g; into[at + 2] = b; into[at + 3] = 255;
        }

        static byte[] Decode(byte[] src, int width, int height, bool bc3)
        {
            int blockSize = bc3 ? 16 : 8;
            int blocks = ((width + 3) / 4) * ((height + 3) / 4);
            if (src.Length < blocks * blockSize)
                throw new ArgumentException($"{blocks * blockSize} bytes needed for {width}x{height}, {src.Length} given");
            var dst = new byte[width * height * 4];
            var pal = new int[16];             // four RGBA colours
            var alpha = new int[8];
            var block = new byte[64];          // 16 RGBA texels
            int p = 0;
            for (int by = 0; by < height; by += 4)
                for (int bx = 0; bx < width; bx += 4, p += blockSize)
                {
                    int c = bc3 ? p + 8 : p;
                    int c0 = src[c] | src[c + 1] << 8, c1 = src[c + 2] | src[c + 3] << 8;
                    uint lut = BitConverter.ToUInt32(src, c + 4);
                    Rgb565(c0, pal, 0);
                    Rgb565(c1, pal, 4);
                    if (c0 > c1 || bc3)
                    {
                        for (int k = 0; k < 3; k++)
                        {
                            pal[8 + k] = (2 * pal[k] + pal[4 + k]) / 3;
                            pal[12 + k] = (pal[k] + 2 * pal[4 + k]) / 3;
                        }
                        pal[11] = 255; pal[15] = 255;
                    }
                    else
                    {
                        for (int k = 0; k < 3; k++) pal[8 + k] = (pal[k] + pal[4 + k]) / 2;
                        pal[11] = 255;
                        pal[12] = pal[13] = pal[14] = pal[15] = 0;   // transparent black
                    }
                    for (int n = 0; n < 16; n++)
                    {
                        int i = (int)(3 & (lut >> (2 * n))) * 4;
                        for (int k = 0; k < 4; k++) block[n * 4 + k] = (byte)pal[i + k];
                    }
                    if (bc3)
                    {
                        int a0 = src[p], a1 = src[p + 1];
                        alpha[0] = a0; alpha[1] = a1;
                        if (a0 > a1)
                            for (int i = 2; i < 8; i++) alpha[i] = ((8 - i) * a0 + (i - 1) * a1) / 7;
                        else
                        {
                            for (int i = 2; i < 6; i++) alpha[i] = ((6 - i) * a0 + (i - 1) * a1) / 5;
                            alpha[6] = 0; alpha[7] = 255;
                        }
                        int lut1 = src[p + 2] | src[p + 3] << 8 | src[p + 4] << 16;
                        int lut2 = src[p + 5] | src[p + 6] << 8 | src[p + 7] << 16;
                        for (int n = 0; n < 8; n++)
                        {
                            block[n * 4 + 3] = (byte)alpha[7 & (lut1 >> (3 * n))];
                            block[(8 + n) * 4 + 3] = (byte)alpha[7 & (lut2 >> (3 * n))];
                        }
                    }
                    for (int n = 0; n < 16; n++)
                    {
                        int x = bx + (n & 3), y = by + (n >> 2);
                        if (x < width && y < height) Buffer.BlockCopy(block, n * 4, dst, (y * width + x) * 4, 4);
                    }
                }
            return dst;
        }
    }
}
