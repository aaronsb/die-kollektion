using System;
using System.Globalization;
using System.Numerics;
using System.Text;

namespace Kollektion.Core.GameData
{
    /// <summary>Numbers as Python prints them, so files written here match the Python pipeline's byte for byte:
    /// <c>f"{x:.6f}"</c> (<see cref="Fixed"/>), <c>repr(x)</c> (<see cref="Repr"/>) and <c>round(x, n)</c>
    /// (<see cref="Round"/>). Python rounds the exact binary value of a double half to even; .NET's "F6" and
    /// Math.Round(x, 6) don't on every input (a tie such as 0.0078125 at six places), so the decimal value is worked
    /// out here exactly.</summary>
    public static class PyFormat
    {
        static readonly ulong[] Pow10 = BuildPow10();

        static ulong[] BuildPow10()
        {
            var p = new ulong[20];
            p[0] = 1;
            for (int i = 1; i < p.Length; i++) p[i] = p[i - 1] * 10;
            return p;
        }

        /// <summary>Python's <c>f"{v:.{digits}f}"</c>: the exact value rounded half to even, the sign kept on zero
        /// (<c>-0.000000</c>).</summary>
        public static string Fixed(double v, int digits)
        {
            if (double.IsNaN(v)) return "nan";
            if (double.IsInfinity(v)) return v > 0 ? "inf" : "-inf";
            var n = Scaled(v, digits, out bool negative);
            var s = n.ToString(CultureInfo.InvariantCulture);
            if (digits > 0)
            {
                if (s.Length <= digits) s = new string('0', digits + 1 - s.Length) + s;
                s = s.Substring(0, s.Length - digits) + "." + s.Substring(s.Length - digits);
            }
            return negative ? "-" + s : s;
        }

        /// <summary>Python's <c>round(v, digits)</c> for a float: correctly rounded, half to even, sign kept.</summary>
        public static double Round(double v, int digits)
        {
            if (double.IsNaN(v) || double.IsInfinity(v)) return v;
            var n = Scaled(v, digits, out bool negative);
            var r = double.Parse(n.ToString(CultureInfo.InvariantCulture) + "E-" + digits, CultureInfo.InvariantCulture);
            return negative ? -r : r;
        }

        /// <summary>|v| × 10^digits rounded half to even to an integer, from v's exact binary value.</summary>
        static BigInteger Scaled(double v, int digits, out bool negative)
        {
            if (digits < 0 || digits >= Pow10.Length) throw new ArgumentOutOfRangeException(nameof(digits));
            long bits = BitConverter.DoubleToInt64Bits(v);
            negative = bits < 0;
            int exp = (int)((bits >> 52) & 0x7FF);
            ulong mant = (ulong)bits & 0xFFFFFFFFFFFFFUL;
            if (exp == 0) exp = 1;
            else mant |= 1UL << 52;
            int e = exp - 1075;                 // |v| = mant × 2^e
            if (mant == 0) return BigInteger.Zero;
            if (e < 0 && TryScaledFast(mant, -e, Pow10[digits], out ulong q)) return q;
            var p = new BigInteger(mant) * Pow10[digits];
            if (e >= 0) return p << e;
            int k = -e;
            var quotient = p >> k;
            var twiceRest = (p - (quotient << k)) << 1;
            int cmp = twiceRest.CompareTo(BigInteger.One << k);
            return cmp > 0 || (cmp == 0 && !quotient.IsEven) ? quotient + 1 : quotient;
        }

        /// <summary>The common case without allocating: (mant × pow) / 2^k in 128 bits, the quotient fitting 64.</summary>
        static bool TryScaledFast(ulong mant, int k, ulong pow, out ulong q)
        {
            ulong hi = Math.BigMul(mant, pow, out ulong lo);
            ulong rHi, rLo, hHi, hLo;
            if (k >= 128)
            {
                q = 0;                          // mant × pow < 2^117, under half of 2^k
                return true;
            }
            if (k < 64)
            {
                if ((hi >> k) != 0) { q = 0; return false; }
                q = (lo >> k) | (hi << (64 - k));
                rHi = 0; rLo = lo & ((1UL << k) - 1);
                hHi = 0; hLo = 1UL << (k - 1);
            }
            else if (k == 64)
            {
                q = hi;
                rHi = 0; rLo = lo;
                hHi = 0; hLo = 1UL << 63;
            }
            else
            {
                q = hi >> (k - 64);
                rHi = hi & ((1UL << (k - 64)) - 1); rLo = lo;
                hHi = 1UL << (k - 65); hLo = 0;
            }
            int cmp = rHi != hHi ? rHi.CompareTo(hHi) : rLo.CompareTo(hLo);
            if (cmp > 0 || (cmp == 0 && (q & 1) == 1))
            {
                if (q == ulong.MaxValue) return false;
                q++;
            }
            return true;
        }

        /// <summary>Python's <c>repr(v)</c> for a float: the shortest digits that read back as v, positional for
        /// 1e-4 ≤ |v| &lt; 1e16 (with ".0" on whole numbers), else as d.ddde±XX.</summary>
        public static string Repr(double v)
        {
            if (double.IsNaN(v)) return "nan";
            if (double.IsInfinity(v)) return v > 0 ? "inf" : "-inf";
            bool negative = BitConverter.DoubleToInt64Bits(v) < 0;
            if (v == 0) return negative ? "-0.0" : "0.0";
            // .NET's "R" gives the same shortest digits; only the layout differs.
            var r = Math.Abs(v).ToString("R", CultureInfo.InvariantCulture);
            int ePos = r.IndexOf('E');
            int exp10 = ePos < 0 ? 0 : int.Parse(r.Substring(ePos + 1), NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture);
            var mantissa = ePos < 0 ? r : r.Substring(0, ePos);
            int dot = mantissa.IndexOf('.');
            int intDigits = dot < 0 ? mantissa.Length : dot;
            var digits = mantissa.Replace(".", "");
            int decpt = intDigits + exp10;     // v = 0.digits × 10^decpt
            int lead = 0;
            while (lead < digits.Length - 1 && digits[lead] == '0') lead++;
            digits = digits.Substring(lead);
            decpt -= lead;
            digits = digits.TrimEnd('0');
            if (digits.Length == 0) digits = "0";

            var sb = new StringBuilder();
            if (negative) sb.Append('-');
            if (decpt <= -4 || decpt > 16)
            {
                sb.Append(digits[0]);
                if (digits.Length > 1) sb.Append('.').Append(digits, 1, digits.Length - 1);
                int x = decpt - 1;
                sb.Append('e').Append(x < 0 ? '-' : '+').Append(Math.Abs(x).ToString("00", CultureInfo.InvariantCulture));
            }
            else if (decpt <= 0)
                sb.Append("0.").Append('0', -decpt).Append(digits);
            else if (decpt >= digits.Length)
                sb.Append(digits).Append('0', decpt - digits.Length).Append(".0");
            else
                sb.Append(digits, 0, decpt).Append('.').Append(digits, decpt, digits.Length - decpt);
            return sb.ToString();
        }
    }
}
