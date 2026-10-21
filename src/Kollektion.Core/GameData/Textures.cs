// Reimplements, for the textures and sprites this game ships, what UnityPy's Texture2DConverter and SpriteHelper
// (UnityPy/export/Texture2DConverter.py, SpriteHelper.py) make of them. UnityPy is Copyright (c) 2019-2026 K0lb3 and
// released under the MIT licence: LICENSES/UnityPy-MIT.txt.

using System;
using System.IO;
using System.Linq;
using AssetsTools.NET.Extra;

namespace Kollektion.Core.GameData
{
    /// <summary>Texture2D and Sprite images as UnityPy gives them (<c>.image</c>): the first mip decoded, rows top to
    /// bottom; a sprite cut from its atlas texture.</summary>
    public static class Textures
    {
        // UnityPy's TextureFormat values.
        const int Rgb24 = 3, Rgba32 = 4, Dxt1 = 10, Dxt5 = 12;
        const int MaxSide = 16384;

        // SpriteSettings.settingsRaw: bit 0 packed, bit 1 packing mode (UnityPy's SpritePackingMode: kSPMTight = 0,
        // kSPMRectangle = 1), bits 2-5 packing rotation (SpritePackingRotation 0-4).
        const int Tight = 0;
        const int FlipHorizontal = 1, FlipVertical = 2, Rotate180 = 3, Rotate90 = 4;

        /// <summary>A texture's first mip from its raw bytes, rows in Unity's order (bottom to top).</summary>
        public static Image DecodeBottomUp(string name, int format, int width, int height, byte[] raw)
        {
            if (width <= 0 || height <= 0 || width > MaxSide || height > MaxSide)
                throw new InvalidDataException($"{name}: a {width}x{height} texture");
            if (raw == null || raw.Length == 0) throw new InvalidDataException($"{name}: no image data");
            switch (format)
            {
                case Dxt1: return new Image(width, height, 4, Bcn.DecodeBc1(raw, width, height, name));
                case Dxt5: return new Image(width, height, 4, Bcn.DecodeBc3(raw, width, height, name));
                case Rgba32: return new Image(width, height, 4, Slice(name, raw, width * height * 4));
                case Rgb24: return new Image(width, height, 3, Slice(name, raw, width * height * 3));
                default: throw new NotSupportedException($"{name}: texture format {format} not supported (DXT1, DXT5, RGBA32, RGB24)");
            }
        }

        static Image DecodeBottomUp(Bundles bundles, Asset tex)
        {
            var f = tex.F;
            byte[] raw = f["image data"].AsByteArray;
            var sd = f["m_StreamData"];
            if ((raw == null || raw.Length == 0) && !sd.IsDummy && sd["path"].AsString.Length > 0)
            {
                ulong size = sd["size"].AsUInt;
                if (size > int.MaxValue) throw new InvalidDataException($"{tex.Name}: {size} bytes of image data");
                raw = bundles.ReadResource(tex, sd["path"].AsString, (long)sd["offset"].AsULong, (int)size);
            }
            return DecodeBottomUp(tex.Name, f["m_TextureFormat"].AsInt, f["m_Width"].AsInt, f["m_Height"].AsInt, raw);
        }

        static byte[] Slice(string name, byte[] raw, int n) =>
            raw.Length >= n ? raw.AsSpan(0, n).ToArray() : throw new InvalidDataException($"{name}: image data ends early");

        /// <summary>Pillow's transpose(FLIP_TOP_BOTTOM): Unity's bottom-up rows as an image's top-down ones.</summary>
        public static Image FlipRows(Image img)
        {
            int stride = img.Width * img.Channels;
            var flipped = new byte[img.Pixels.Length];
            for (int y = 0; y < img.Height; y++)
                Buffer.BlockCopy(img.Pixels, (img.Height - 1 - y) * stride, flipped, y * stride, stride);
            return new Image(img.Width, img.Height, img.Channels, flipped);
        }

        public static Image Decode(Bundles bundles, Asset tex) => FlipRows(DecodeBottomUp(bundles, tex));

        /// <summary>A sprite as UnityPy's get_image_from_sprite draws it: from its SpriteAtlas's render data, or its own
        /// (m_RD) when it is in no atlas, cut by <see cref="Cut"/>. A sprite whose atlas is found by tag only, and one
        /// with a separate alpha texture, are refused.</summary>
        public static Image Sprite(Bundles bundles, Asset sprite)
        {
            var atlas = bundles.Deref(sprite, sprite.F["m_SpriteAtlas"]);
            AssetsTools.NET.AssetTypeValueField data = null;
            if (atlas != null)
            {
                var key = sprite.F["m_RenderDataKey"];
                foreach (var pair in atlas.F["m_RenderDataMap"]["Array"].Children)
                {
                    var k = pair["first"];
                    if (k["first"].Children.Select(c => c.AsUInt).SequenceEqual(key["first"].Children.Select(c => c.AsUInt))
                        && k["second"].AsLong == key["second"].AsLong)
                    {
                        data = pair["second"];
                        break;
                    }
                }
                if (data == null) throw new InvalidDataException($"{sprite.Name}: not found in atlas {atlas.Name}");
            }
            else
            {
                var tags = sprite.F["m_AtlasTags"];
                if (!tags.IsDummy && tags["Array"].Children.Count > 0)
                    throw new NotSupportedException($"{sprite.Name}: its atlas is named by tag only (not supported)");
                data = sprite.F["m_RD"];
            }
            if (!data["alphaTexture"].IsDummy && data["alphaTexture"]["m_PathID"].AsLong != 0)
                throw new NotSupportedException($"{sprite.Name}: separate alpha texture not supported");
            var tex = bundles.Deref(atlas ?? sprite, data["texture"]) ?? throw new InvalidDataException($"{sprite.Name}: no texture");
            var r = data["textureRect"];
            return Cut(sprite.Name, DecodeBottomUp(bundles, tex), r["x"].AsFloat, r["y"].AsFloat, r["width"].AsFloat, r["height"].AsFloat,
                       data["settingsRaw"].AsUInt, () => MeshData.Read(bundles, sprite, sprite.F["m_RD"], sprite.Name),
                       sprite.F["m_PixelsToUnits"].AsFloat);
        }

        /// <summary>SpriteHelper's steps on a texture decoded bottom-up: the rect cropped (rounded as Pillow's crop
        /// rounds, half to even); a packed sprite flipped or turned back by its packing rotation; a tight-packed one
        /// (packing mode 0, packed or not) masked by its mesh's triangles, drawn as Pillow draws polygons; then the rows
        /// flipped. A tight mesh with UVs (which UnityPy copies triangle by triangle) is refused, and so is an unknown
        /// rotation (UnityPy raises on it).</summary>
        public static Image Cut(string name, Image texture, double rx, double ry, double rw, double rh, uint settingsRaw,
                                Func<MeshData> mesh, double pixelsToUnits)
        {
            bool packed = (settingsRaw & 1) != 0;
            int mode = (int)(settingsRaw >> 1) & 1, rotation = (int)(settingsRaw >> 2) & 0xF;
            if (rotation > Rotate90) throw new InvalidDataException($"{name}: packing rotation {rotation} unknown");
            int x0 = (int)Math.Round(rx, MidpointRounding.ToEven), x1 = (int)Math.Round(rx + rw, MidpointRounding.ToEven);
            int y0 = (int)Math.Round(ry, MidpointRounding.ToEven), y1 = (int)Math.Round(ry + rh, MidpointRounding.ToEven);
            if (x0 < 0 || y0 < 0 || x1 > texture.Width || y1 > texture.Height || x1 < x0 || y1 < y0)
                throw new InvalidDataException($"{name}: rect outside its texture");
            int cw = x1 - x0, ch = y1 - y0, n = texture.Channels;
            var img = new Image(cw, ch, n);
            for (int y = 0; y < ch; y++)       // rows still bottom-up, as Pillow crops the unflipped texture
                Buffer.BlockCopy(texture.Pixels, ((y0 + y) * texture.Width + x0) * n, img.Pixels, y * cw * n, cw * n);
            if (packed && rotation != 0) img = Transpose(img, rotation);
            if (mode == Tight) img = MaskByMesh(name, img, mesh(), pixelsToUnits);
            return FlipRows(img);
        }

        /// <summary>Pillow's transpose as SpriteHelper picks it for each packing rotation: FLIP_LEFT_RIGHT,
        /// FLIP_TOP_BOTTOM, ROTATE_180, ROTATE_270 (a quarter turn clockwise).</summary>
        static Image Transpose(Image img, int rotation)
        {
            int w = img.Width, h = img.Height, n = img.Channels;
            bool turn = rotation == Rotate90;
            var outImg = new Image(turn ? h : w, turn ? w : h, n);
            for (int y = 0; y < outImg.Height; y++)
                for (int x = 0; x < outImg.Width; x++)
                {
                    var (sx, sy) = rotation switch
                    {
                        FlipHorizontal => (w - 1 - x, y),
                        FlipVertical => (x, h - 1 - y),
                        Rotate180 => (w - 1 - x, h - 1 - y),
                        _ => (y, h - 1 - x),
                    };
                    Buffer.BlockCopy(img.Pixels, (sy * w + sx) * n, outImg.Pixels, (y * outImg.Width + x) * n, n);
                }
            return outImg;
        }

        /// <summary>UnityPy's mask_sprite: the mesh's triangles, shifted to the origin and scaled by pixels per unit,
        /// filled on a mask; RGBA texels outside it become transparent black, an RGB image gets the mask as alpha.</summary>
        static Image MaskByMesh(string name, Image crop, MeshData mesh, double factor)
        {
            var v = mesh.Vertices;
            if (v == null || v.Length == 0) throw new InvalidDataException($"{name}: tight-packed sprite without a mesh");
            if (mesh.UV0 != null && mesh.UV0.Any(uv => uv[0] != 0 || uv[1] != 0))
                throw new NotSupportedException($"{name}: tight-packed sprite drawn through its UVs (not supported)");
            double minX = v.Min(p => p[0]), minY = v.Min(p => p[1]);
            var mask = new byte[crop.Width * crop.Height];
            foreach (var (a, b, c) in mesh.Triangles)
                PillowPolygon.Fill(mask, crop.Width, crop.Height, new[]
                {
                    (v[a][0] - minX) * factor, (v[a][1] - minY) * factor, (v[b][0] - minX) * factor,
                    (v[b][1] - minY) * factor, (v[c][0] - minX) * factor, (v[c][1] - minY) * factor,
                });
            if (crop.Channels == 4)
            {
                var px = (byte[])crop.Pixels.Clone();
                for (int i = 0; i < mask.Length; i++)
                    if (mask[i] == 0) Array.Clear(px, i * 4, 4);
                return new Image(crop.Width, crop.Height, 4, px);
            }
            var rgb = crop.ToRgb();
            var rgba = new byte[mask.Length * 4];
            for (int i = 0; i < mask.Length; i++)
            {
                Buffer.BlockCopy(rgb.Pixels, i * 3, rgba, i * 4, 3);
                rgba[i * 4 + 3] = mask[i];
            }
            return new Image(crop.Width, crop.Height, 4, rgba);
        }

        /// <summary>The texture and sprite name a texture or sprite is saved under: a sprite <c>&lt;Car&gt;_Icon</c>
        /// as <c>&lt;Car&gt;</c> (tools/export_images.py).</summary>
        public static string FileName(Asset asset) =>
            asset.Type == AssetClassID.Sprite && asset.Name.EndsWith("_Icon", StringComparison.Ordinal)
                ? asset.Name.Substring(0, asset.Name.Length - 5) : asset.Name;
    }
}
