// A line-by-line port of Pillow's polygon filler (Pillow 13.0.0, src/libImaging/Draw.c: ImagingDrawPolygon,
// polygon_generic and their helpers, and src/_imaging.c's _draw_polygon). Draw.c is Copyright (c) 1996-2006 by
// Fredrik Lundh and Copyright (c) 1997-2006 by Secret Labs AB; Pillow is Copyright (c) 2010 by Jeffrey 'Alex' Clark
// and contributors. Used under Pillow's MIT-CMU licence (HPND), whose full text is in LICENSES/Pillow-MIT-CMU.txt.

using System;
using System.Collections.Generic;

namespace Kollektion.Core.GameData
{
    /// <summary>Pillow's filled polygon on a one-byte-per-pixel mask (ImageDraw.polygon(xy, fill=1) on a mode "1"
    /// image; Pillow 13's _imaging.c _draw_polygon and libImaging/Draw.c ImagingDrawPolygon / polygon_generic), so a
    /// tight-packed sprite is masked exactly as UnityPy masks it. Vertices are truncated to integers; the scan line
    /// works in single precision, as the C does.</summary>
    public static class PillowPolygon
    {
        sealed class Edge
        {
            public int X0, Y0, XMin, YMin, XMax, YMax;
            public float Dx;
        }

        static Edge MakeEdge(int x0, int y0, int x1, int y1)
        {
            var e = new Edge { XMin = Math.Min(x0, x1), XMax = Math.Max(x0, x1), YMin = Math.Min(y0, y1), YMax = Math.Max(y0, y1), X0 = x0, Y0 = y0 };
            e.Dx = y0 == y1 ? 0f : (float)(x1 - x0) / (y1 - y0);
            return e;
        }

        // Draw.c's ROUND_UP and ROUND_DOWN on a float: f ± 0.5F in single precision, fabs(f) ± 0.5F in double.
        static int RoundUp(float f) => (int)(f >= 0.0 ? Math.Floor((float)(f + 0.5f)) : -Math.Floor(Math.Abs((double)f) + 0.5));
        static int RoundDown(float f) => (int)(f >= 0.0 ? Math.Ceiling((float)(f - 0.5f)) : -Math.Ceiling(Math.Abs((double)f) - 0.5));
        static float RoundF(float f) => MathF.Round(f, MidpointRounding.AwayFromZero);
        static float At(Edge e, int y) => (float)((float)((y - e.Y0) * e.Dx) + e.X0);

        static void HLine(byte[] mask, int width, int height, int x0, int y, int x1)
        {
            if (y < 0 || y >= height) return;
            if (x0 < 0) x0 = 0;
            else if (x0 >= width) return;
            if (x1 < 0) return;
            if (x1 >= width) x1 = width - 1;
            for (int x = x0; x <= x1; x++) mask[y * width + x] = 255;
        }

        /// <summary>Fills the polygon with 255. points: x, y pairs as Python floats.</summary>
        public static void Fill(byte[] mask, int width, int height, IReadOnlyList<double> points)
        {
            int count = points.Count / 2;
            if (count <= 0) return;
            var xy = new int[count * 2];
            for (int i = 0; i < xy.Length; i++) xy[i] = (int)points[i];   // _draw_polygon truncates

            var edges = new List<Edge>();
            int k;
            for (k = 0; k < count - 1; k++)
            {
                int x0 = xy[k * 2], y0 = xy[k * 2 + 1], x1 = xy[k * 2 + 2], y1 = xy[k * 2 + 3];
                if (y0 == y1 && k != 0 && y0 == xy[k * 2 - 1])
                {
                    // A horizontal line right after another: extend that one.
                    var last = edges[edges.Count - 1];
                    if (x1 > x0 && x0 > xy[k * 2 - 2]) { last.XMax = x1; continue; }
                    if (x1 < x0 && x0 < xy[k * 2 - 2]) { last.XMin = x1; continue; }
                }
                edges.Add(MakeEdge(x0, y0, x1, y1));
            }
            if (xy[k * 2] != xy[0] || xy[k * 2 + 1] != xy[1])
                edges.Add(MakeEdge(xy[k * 2], xy[k * 2 + 1], xy[0], xy[1]));
            Generic(mask, width, height, edges);
        }

        static void Generic(byte[] mask, int width, int height, List<Edge> e)
        {
            var table = new List<Edge>();
            int ymin = height - 1, ymax = 0;
            foreach (var edge in e)
            {
                if (ymin > edge.YMin) ymin = edge.YMin;
                if (ymax < edge.YMax) ymax = edge.YMax;
                if (edge.YMin == edge.YMax)
                {
                    HLine(mask, width, height, edge.XMin, edge.YMin, edge.XMax);
                    continue;
                }
                table.Add(edge);
            }
            if (ymin < 0) ymin = 0;
            if (ymax > height) ymax = height;

            var xx = new float[table.Count * 2];
            for (; ymin <= ymax; ymin++)
            {
                int j = 0;
                for (int i = 0; i < table.Count; i++)
                {
                    var current = table[i];
                    if (ymin < current.YMin || ymin > current.YMax) continue;
                    xx[j++] = At(current, ymin);
                    if (ymin == current.YMax && ymin < ymax)
                    {
                        // Needed to draw consistent polygons
                        xx[j] = xx[j - 1];
                        j++;
                    }
                    else if ((ymin == current.YMin || ymin == current.YMax) && current.Dx != 0)
                    {
                        // Connect discontiguous corners
                        for (int o = 0; o < i; o++)
                        {
                            var other = table[o];
                            if ((ymin != other.YMin && ymin != other.YMax) || other.Dx == 0) continue;
                            if (RoundF(xx[j - 1]) != RoundF(At(other, ymin))) continue;
                            int offset = ymin == current.YMax ? -1 : 1;
                            float adjacent = At(current, ymin + offset);
                            if (ymin + offset >= other.YMin && ymin + offset <= other.YMax)
                            {
                                float adjacentOther = At(other, ymin + offset);
                                if (xx[j - 1] > (float)(adjacent + 1) && xx[j - 1] > (float)(adjacentOther + 1))
                                    xx[j - 1] = RoundF(Math.Max(adjacent, adjacentOther)) + 1;
                                else if (xx[j - 1] < (float)(adjacent - 1) && xx[j - 1] < (float)(adjacentOther - 1))
                                    xx[j - 1] = RoundF(Math.Min(adjacent, adjacentOther)) - 1;
                                break;
                            }
                        }
                    }
                }
                Array.Sort(xx, 0, j);
                for (int i = 1; i < j; i += 2)
                    HLine(mask, width, height, RoundUp(xx[i - 1]), ymin, RoundDown(xx[i]));
            }
        }
    }
}
