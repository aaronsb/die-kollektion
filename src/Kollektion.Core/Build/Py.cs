using System;
using System.Globalization;
using System.Text;

namespace Kollektion.Core.Build
{
    /// <summary>
    /// Python's float behaviour where the build's output depends on it, so the port writes the bytes
    /// tools/meshlib.py wrote: <c>sum()</c> (Neumaier-compensated since CPython 3.12), <c>math.hypot</c> (CPython's
    /// own vector_norm, not libm's), <c>round(x, 4)</c> as a grouping key, <c>min</c>/<c>max</c> ties, and number
    /// formatting (format specs and <c>repr</c>). Plain + - * / and sqrt are IEEE on both sides; cos, sin, tan and
    /// acos call the C library's on both, so on Linux they agree bit for bit.
    /// </summary>
    public static class Py
    {
        static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

        /// <summary>Python's <c>sum()</c> of floats, started from the int 0: the first item is added to 0.0 plainly,
        /// the rest with Neumaier compensation, the compensation added back at the end.</summary>
        public struct Sum
        {
            double hi, lo;
            bool started;

            public void Add(double x)
            {
                if (!started)
                {
                    hi = 0.0 + x;
                    lo = 0.0;
                    started = true;
                    return;
                }
                var t = hi + x;
                if (Math.Abs(hi) >= Math.Abs(x)) lo += (hi - t) + x;
                else lo += (x - t) + hi;
                hi = t;
            }

            public double Value => lo != 0.0 && double.IsFinite(lo) ? hi + lo : hi;
        }

        public static double Sum3(double a, double b, double c)
        {
            var s = new Sum();
            s.Add(a);
            s.Add(b);
            s.Add(c);
            return s.Value;
        }

        /// <summary><c>math.hypot(x, y)</c>: CPython's vector_norm, faithfully rounded with a differential correction.</summary>
        public static double Hypot(double x, double y)
        {
            x = Math.Abs(x);
            y = Math.Abs(y);
            var max = 0.0;
            if (x > max) max = x;
            if (y > max) max = y;
            if (double.IsInfinity(max)) return max;
            if (double.IsNaN(x) || double.IsNaN(y)) return double.NaN;
            return VectorNorm(new[] { x, y }, max);
        }

        static double VectorNorm(double[] vec, double max)
        {
            if (max == 0.0 || vec.Length <= 1) return max;
            var maxE = Math.ILogB(max) + 1;     // frexp's exponent
            if (maxE < -1023)
            {
                const double DblMin = 2.2250738585072014e-308;
                for (var i = 0; i < vec.Length; i++) vec[i] /= DblMin;
                return DblMin * VectorNorm(vec, max / DblMin);
            }
            var scale = Math.ScaleB(1.0, -maxE);
            double csum = 1.0, frac1 = 0.0, frac2 = 0.0;
            foreach (var v in vec)
            {
                var x = v * scale;
                var prHi = x * x;
                var prLo = Math.FusedMultiplyAdd(x, x, -prHi);
                var smHi = csum + prHi;
                var smLo = (csum - smHi) + prHi;
                csum = smHi;
                frac1 += prLo;
                frac2 += smLo;
            }
            var h = Math.Sqrt(csum - 1.0 + (frac1 + frac2));
            {
                var prHi = -h * h;
                var prLo = Math.FusedMultiplyAdd(-h, h, -prHi);
                var smHi = csum + prHi;
                var smLo = (csum - smHi) + prHi;
                csum = smHi;
                frac1 += prLo;
                frac2 += smLo;
            }
            var d = csum - 1.0 + (frac1 + frac2);
            h += d / (2.0 * h);
            return h / scale;
        }

        /// <summary><c>min(a, b)</c>: b only when strictly smaller, so ties and NaN keep a.</summary>
        public static double Min(double a, double b) => b < a ? b : a;

        /// <summary><c>max(a, b)</c>: b only when strictly larger.</summary>
        public static double Max(double a, double b) => b > a ? b : a;

        public static double Degrees(double radians) => radians * (180.0 / Math.PI);

        public static double Radians(double degrees) => degrees * (Math.PI / 180.0);

        /// <summary>The integer <c>round(x, 4)</c> stands for, x * 10^4 rounded half to even on x's exact binary
        /// value (as CPython's dtoa does): equal keys exactly when Python's rounded floats are equal, -0.0 and 0.0
        /// alike. For |x| below about 9e14.</summary>
        public static long RoundKey4(double x)
        {
            var bits = BitConverter.DoubleToInt64Bits(x);
            var negative = bits < 0;
            var exponent = (int)((bits >> 52) & 0x7FF);
            var mantissa = (ulong)bits & 0xFFFFFFFFFFFFFUL;
            if (exponent == 0x7FF) throw new ArgumentOutOfRangeException(nameof(x), "not a finite number");
            if (exponent == 0) exponent = 1;
            else mantissa |= 1UL << 52;
            var shift = 1075 - exponent;        // x = mantissa / 2^shift
            long n;
            if (shift <= 0)
            {
                if (shift < -10) throw new ArgumentOutOfRangeException(nameof(x), "too large to round");
                n = checked((long)(mantissa << -shift) * 10000);
            }
            else if (shift >= 70) n = 0;        // mantissa * 10^4 < 2^67: below one half
            else
            {
                // The 128-bit product, shifted right with the bits it drops deciding the rounding.
                var hi = Math.BigMul(mantissa, 10000UL, out var lo);
                var q = shift >= 64 ? hi >> (shift - 64) : (lo >> shift) | (hi << (64 - shift));
                var half = Bit(hi, lo, shift - 1);
                var below = AnyBelow(hi, lo, shift - 1);
                if (half && (below || (q & 1) == 1)) q++;
                n = checked((long)q);
            }
            return negative ? -n : n;
        }

        static bool Bit(ulong hi, ulong lo, int k) => k >= 64 ? ((hi >> (k - 64)) & 1) == 1 : ((lo >> k) & 1) == 1;

        static bool AnyBelow(ulong hi, ulong lo, int k)
        {
            if (k == 0) return false;
            if (k <= 64) return (lo & (k == 64 ? ulong.MaxValue : (1UL << k) - 1)) != 0;
            return lo != 0 || (hi & ((1UL << (k - 64)) - 1)) != 0;
        }

        /// <summary><c>f"{x:.Nf}"</c>: .NET's fixed-point formatting is exact and rounds half to even on the binary
        /// value, as Python's does, and keeps the sign of a negative result that rounds to zero.</summary>
        public static string Fixed(double x, int decimals) => x.ToString(FixedFormats[decimals], Inv);

        /// <summary><c>f"{x:+.Nf}"</c>.</summary>
        public static string Signed(double x, int decimals)
        {
            var s = Fixed(x, decimals);
            return s.StartsWith("-", StringComparison.Ordinal) ? s : "+" + s;
        }

        static readonly string[] FixedFormats = { "F0", "F1", "F2", "F3", "F4", "F5", "F6" };

        /// <summary><c>repr(x)</c>: the shortest digits that round-trip, laid out as Python does (fixed between 1e-4
        /// and 1e16 with at least one decimal, else d.ddde±XX).</summary>
        public static string Repr(double x)
        {
            if (double.IsNaN(x)) return "nan";
            if (double.IsInfinity(x)) return x > 0 ? "inf" : "-inf";
            var negative = BitConverter.DoubleToInt64Bits(x) < 0;
            if (x == 0.0) return negative ? "-0.0" : "0.0";
            var r = Math.Abs(x).ToString("R", Inv);
            var e = r.IndexOfAny(new[] { 'E', 'e' });
            var mantissa = e < 0 ? r : r.Substring(0, e);
            var exp10 = e < 0 ? 0 : int.Parse(r.Substring(e + 1), NumberStyles.AllowLeadingSign, Inv);
            var dot = mantissa.IndexOf('.');
            var intPart = dot < 0 ? mantissa : mantissa.Substring(0, dot);
            var fracPart = dot < 0 ? "" : mantissa.Substring(dot + 1);
            var digits = intPart + fracPart;
            var decpt = intPart.Length + exp10;     // value = 0.DIGITS * 10^decpt
            var lead = 0;
            while (lead < digits.Length - 1 && digits[lead] == '0') lead++;
            digits = digits.Substring(lead);
            decpt -= lead;
            digits = digits.TrimEnd('0');
            var sb = new StringBuilder();
            if (negative) sb.Append('-');
            if (decpt <= -4 || decpt > 16)
            {
                sb.Append(digits[0]);
                if (digits.Length > 1) sb.Append('.').Append(digits, 1, digits.Length - 1);
                var exp = decpt - 1;
                sb.Append('e').Append(exp < 0 ? '-' : '+').Append(Math.Abs(exp).ToString("00", Inv));
            }
            else if (decpt <= 0) sb.Append("0.").Append('0', -decpt).Append(digits);
            else if (decpt >= digits.Length) sb.Append(digits).Append('0', decpt - digits.Length).Append(".0");
            else sb.Append(digits, 0, decpt).Append('.').Append(digits, decpt, digits.Length - decpt);
            return sb.ToString();
        }
    }
}
