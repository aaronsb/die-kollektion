// ResizeNearest follows Pillow's nearest-neighbour scaling (Pillow 13.0.0, src/libImaging/Geometry.c,
// ImagingScaleAffine), used under Pillow's MIT-CMU licence (HPND): LICENSES/Pillow-MIT-CMU.txt.

using System;
using System.IO;

namespace Kollektion.Core.GameData
{
    /// <summary>A car's atlas baked the way the game's car shader appears to shade it (tools/composite_atlas.py,
    /// without --tint): the livery <c>&lt;Donor&gt;_skin00</c> with every glass texel of <c>&lt;Donor&gt;_masks</c>
    /// (green alone) set to a dark glass grey. Written as <c>&lt;Donor&gt;_composite.png</c>, RGB.</summary>
    public static class Composite
    {
        static readonly byte[] Glass = { 38, 40, 44 };

        public static Image Bake(Image skin, Image mask, out int glassTexels)
        {
            var outImg = skin.ToRgb();
            var m = ResizeNearest(mask.ToRgb(), skin.Width, skin.Height);
            var px = (byte[])outImg.Pixels.Clone();
            glassTexels = 0;
            for (int i = 0, n = skin.Width * skin.Height; i < n; i++)
            {
                if (m.Pixels[i * 3 + 1] > 127 && m.Pixels[i * 3] <= 127)
                {
                    Buffer.BlockCopy(Glass, 0, px, i * 3, 3);
                    glassTexels++;
                }
            }
            return new Image(outImg.Width, outImg.Height, 3, px);
        }

        /// <summary>Pillow's resize with NEAREST (libImaging/Geometry.c, ImagingScaleAffine): the source position
        /// starts at half a step and adds the step (source size / output size) texel by texel, in doubles, so its
        /// rounding drift is Pillow's; each output texel takes the source texel the position falls in, and stays zero
        /// when it falls outside.</summary>
        public static Image ResizeNearest(Image img, int width, int height)
        {
            if (img.Width == width && img.Height == height) return img;
            int n = img.Channels;
            var px = new byte[width * height * n];
            double ax = (double)img.Width / width, ay = (double)img.Height / height;
            var xin = new int[width];
            double xo = ax * 0.5;
            for (int x = 0; x < width; x++, xo += ax)
                xin[x] = xo < 0 ? -1 : (int)xo;
            double yo = ay * 0.5;
            for (int y = 0; y < height; y++, yo += ay)
            {
                int yi = yo < 0 ? -1 : (int)yo;
                if (yi < 0 || yi >= img.Height) continue;
                for (int x = 0; x < width; x++)
                    if (xin[x] >= 0 && xin[x] < img.Width)
                        Buffer.BlockCopy(img.Pixels, (yi * img.Width + xin[x]) * n, px, (y * width + x) * n, n);
            }
            return new Image(width, height, n, px);
        }

        /// <summary>Bakes <c>&lt;textures&gt;/&lt;donor&gt;_composite.png</c> from the skin and masks there.</summary>
        public static void Write(string textures, string donor, Action<string> log)
        {
            var skin = Png.Read(Path.Combine(textures, $"{donor}_skin00.png"));
            var mask = Png.Read(Path.Combine(textures, $"{donor}_masks.png"));
            var path = Path.Combine(textures, $"{donor}_composite.png");
            Png.Write(path, Bake(skin, mask, out int n));
            log($"{path}: {n} glass texels baked dark");
        }
    }
}
