using System;
using System.IO;
using System.Linq;
using AssetsTools.NET.Extra;

namespace Kollektion.Core.GameData
{
    /// <summary>Texture2D and Sprite images as UnityPy gives them (<c>.image</c>): the first mip decoded, rows top to
    /// bottom; a sprite cropped from its atlas texture.</summary>
    public static class Textures
    {
        // UnityPy's TextureFormat values.
        const int Rgb24 = 3, Rgba32 = 4, Dxt1 = 10, Dxt5 = 12;

        /// <summary>The texture's first mip with rows in Unity's order (bottom to top).</summary>
        static Image DecodeBottomUp(Bundles bundles, Asset tex)
        {
            var f = tex.F;
            int w = f["m_Width"].AsInt, h = f["m_Height"].AsInt, format = f["m_TextureFormat"].AsInt;
            byte[] raw = f["image data"].AsByteArray;
            var sd = f["m_StreamData"];
            if ((raw == null || raw.Length == 0) && !sd.IsDummy && sd["path"].AsString.Length > 0)
                raw = bundles.ReadResource(tex, sd["path"].AsString, (long)sd["offset"].AsULong, (int)sd["size"].AsUInt);
            if (raw == null || raw.Length == 0) throw new InvalidDataException($"{tex.Name}: no image data");
            switch (format)
            {
                case Dxt1: return new Image(w, h, 4, Bcn.DecodeBc1(raw, w, h));
                case Dxt5: return new Image(w, h, 4, Bcn.DecodeBc3(raw, w, h));
                case Rgba32: return new Image(w, h, 4, Slice(tex, raw, w * h * 4));
                case Rgb24: return new Image(w, h, 3, Slice(tex, raw, w * h * 3));
                default: throw new NotSupportedException($"{tex.Name}: texture format {format} not supported (DXT1, DXT5, RGBA32, RGB24)");
            }
        }

        static byte[] Slice(Asset tex, byte[] raw, int n) =>
            raw.Length >= n ? raw.AsSpan(0, n).ToArray() : throw new InvalidDataException($"{tex.Name}: image data ends early");

        static Image FlipRows(Image img)
        {
            int stride = img.Width * img.Channels;
            var flipped = new byte[img.Pixels.Length];
            for (int y = 0; y < img.Height; y++)
                Buffer.BlockCopy(img.Pixels, (img.Height - 1 - y) * stride, flipped, y * stride, stride);
            return new Image(img.Width, img.Height, img.Channels, flipped);
        }

        public static Image Decode(Bundles bundles, Asset tex) => FlipRows(DecodeBottomUp(bundles, tex));

        /// <summary>A sprite packed in a SpriteAtlas, as UnityPy's SpriteHelper draws it: its textureRect cut from the
        /// atlas texture (rounded as Pillow's crop rounds, half to even); a tight-packed one masked by its mesh's
        /// triangles, drawn as Pillow draws polygons. Rotated packing, and tight meshes with UVs (which UnityPy copies
        /// triangle by triangle), are refused.</summary>
        public static Image Sprite(Bundles bundles, Asset sprite)
        {
            var key = sprite.F["m_RenderDataKey"];
            var atlas = bundles.Deref(sprite, sprite.F["m_SpriteAtlas"])
                        ?? throw new NotSupportedException($"{sprite.Name}: not in a SpriteAtlas (not supported)");
            AssetsTools.NET.AssetTypeValueField data = null;
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
            if (!data["alphaTexture"].IsDummy && data["alphaTexture"]["m_PathID"].AsLong != 0)
                throw new NotSupportedException($"{sprite.Name}: separate alpha texture not supported");
            int settings = (int)data["settingsRaw"].AsUInt;
            bool packed = (settings & 1) != 0, tight = ((settings >> 1) & 1) != 0;
            int rotation = (settings >> 2) & 0xF;
            if (packed && rotation != 0) throw new NotSupportedException($"{sprite.Name}: rotated packing ({rotation}) not supported");

            var tex = bundles.Deref(atlas, data["texture"]) ?? throw new InvalidDataException($"{sprite.Name}: atlas has no texture");
            var img = DecodeBottomUp(bundles, tex);
            var r = data["textureRect"];
            double rx = r["x"].AsFloat, ry = r["y"].AsFloat, rw = r["width"].AsFloat, rh = r["height"].AsFloat;
            int x0 = (int)Math.Round(rx, MidpointRounding.ToEven), x1 = (int)Math.Round(rx + rw, MidpointRounding.ToEven);
            int y0 = (int)Math.Round(ry, MidpointRounding.ToEven), y1 = (int)Math.Round(ry + rh, MidpointRounding.ToEven);
            if (x0 < 0 || y0 < 0 || x1 > img.Width || y1 > img.Height || x1 < x0 || y1 < y0)
                throw new InvalidDataException($"{sprite.Name}: rect outside its atlas texture");
            int cw = x1 - x0, ch = y1 - y0, n = img.Channels;
            var crop = new Image(cw, ch, n);
            for (int y = 0; y < ch; y++)       // rows still bottom-up, as Pillow crops the unflipped atlas
                Buffer.BlockCopy(img.Pixels, ((y0 + y) * img.Width + x0) * n, crop.Pixels, y * cw * n, cw * n);
            if (tight) crop = MaskByMesh(bundles, sprite, crop);
            return FlipRows(crop);
        }

        /// <summary>UnityPy's mask_sprite: the mesh's triangles, shifted to the origin and scaled by pixels per unit,
        /// filled on a mask; RGBA texels outside it become transparent black, an RGB image gets the mask as alpha.</summary>
        static Image MaskByMesh(Bundles bundles, Asset sprite, Image crop)
        {
            var mesh = MeshData.Read(bundles, sprite, sprite.F["m_RD"], sprite.Name);
            var v = mesh.Vertices;
            if (v == null || v.Length == 0) throw new InvalidDataException($"{sprite.Name}: tight-packed sprite without a mesh");
            if (mesh.UV0 != null && mesh.UV0.Any(uv => uv[0] != 0 || uv[1] != 0))
                throw new NotSupportedException($"{sprite.Name}: tight-packed sprite drawn through its UVs (not supported)");
            double minX = v.Min(p => p[0]), minY = v.Min(p => p[1]);
            double factor = sprite.F["m_PixelsToUnits"].AsFloat;
            var mask = new byte[crop.Width * crop.Height];
            foreach (var (a, b, c) in mesh.Triangles)
                PillowPolygon.Fill(mask, crop.Width, crop.Height, new[]
                {
                    (v[a][0] - minX) * factor, (v[a][1] - minY) * factor, (v[b][0] - minX) * factor,
                    (v[b][1] - minY) * factor, (v[c][0] - minX) * factor, (v[c][1] - minY) * factor,
                });
            int n = crop.Channels;
            if (n == 4)
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
