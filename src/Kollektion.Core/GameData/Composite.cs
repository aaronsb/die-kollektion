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
            var m = Resize(mask.ToRgb(), skin.Width, skin.Height);
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

        /// <summary>Pillow's resize with NEAREST: each output texel takes the source texel under its centre.</summary>
        static Image Resize(Image img, int width, int height)
        {
            if (img.Width == width && img.Height == height) return img;
            var px = new byte[width * height * img.Channels];
            double sx = (double)img.Width / width, sy = (double)img.Height / height;
            for (int y = 0; y < height; y++)
            {
                int yi = Math.Min(img.Height - 1, (int)((y + 0.5) * sy));
                for (int x = 0; x < width; x++)
                {
                    int xi = Math.Min(img.Width - 1, (int)((x + 0.5) * sx));
                    Buffer.BlockCopy(img.Pixels, (yi * img.Width + xi) * img.Channels, px, (y * width + x) * img.Channels, img.Channels);
                }
            }
            return new Image(width, height, img.Channels, px);
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
