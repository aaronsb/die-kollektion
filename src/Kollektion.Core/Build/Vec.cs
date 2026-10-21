using System;

namespace Kollektion.Core.Build
{
    /// <summary>The 3-vector helpers meshlib uses, with its operation order and Python's compensated sums.</summary>
    public static class Vec
    {
        public static double[] Sub(double[] a, double[] b) => new[] { a[0] - b[0], a[1] - b[1], a[2] - b[2] };

        public static double[] Cross(double[] a, double[] b) =>
            new[] { a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0] };

        /// <summary><c>sum(a[k] * b[k] for k in range(3))</c>.</summary>
        public static double Dot(double[] a, double[] b) => Py.Sum3(a[0] * b[0], a[1] * b[1], a[2] * b[2]);

        public static double Length(double[] v) => Math.Sqrt(Dot(v, v));

        /// <summary>meshlib's _normalised: each component over the length.</summary>
        public static double[] Normalised(double[] v)
        {
            var n = Length(v);
            return new[] { v[0] / n, v[1] / n, v[2] / n };
        }
    }
}
