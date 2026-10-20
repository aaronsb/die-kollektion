using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;

namespace VehicleMods;

/// <summary>Chooses where to reserve the block of memory the hooks' jump slots and relocated code live in.</summary>
/// <remarks>
/// Pure logic over a /proc/self/maps listing, so it can be tested offline against captured layouts
/// (tools/near-plan, tests/maps). Dobby reaches a hook's slot with <c>jmp [rip+disp32]</c> and copies the hooked
/// function's first instructions, RIP-relative operands included, into a code page, so both must lie close to
/// GameAssembly's code; Dobby itself only searches 1 GB around a hook for code, so the block must be within
/// 1 GB of both ends of that code. Choices, in order:
/// <list type="number">
/// <item>An unmapped gap in that window. Coreclr commits only inside its own reservation and the kernel never
/// places a mapping over a live one, so memory claimed in a gap (MAP_FIXED_NOREPLACE) is ours for the session.
/// The biggest gap wins; the block sits at its top.</item>
/// <item>The top of coreclr's executable reservation: the highest no-access run of at least
/// <see cref="MinReservationTail"/> in the reservation that starts at System.Private.CoreLib.dll, allowing a few
/// small mappings above it (2026-10-19: three 12 KB mappings sat between the run and renderD128). Coreclr hands
/// that reservation out strictly upward, so its top is the last part it commits.</item>
/// <item>Nothing: the caller installs no hooks and the game runs without the mod.</item>
/// </list>
/// </remarks>
public static class NearBlockPlanner
{
    public const long Page = 0x1000;
    public const long Granule = 0x10000;                // coreclr reserves and commits in 64 KB granules
    public const long CodeRange = 0x40000000;           // Dobby searches 1 GB around a hook for code pages
    public const long MaxReservation = 0x80000000;      // coreclr reserves at most 2 GB of executable memory
    public const long MinReservationTail = 0x2000000;   // 32 MB: the unused tail of coreclr's reservation
    public const long TopClutter = 0x100000;            // other mappings tolerated above that tail: 1 MB in all

    public readonly struct Region
    {
        public readonly long Start, End;
        public readonly string Perms, Path;
        public Region(long start, long end, string perms, string path) { Start = start; End = end; Perms = perms; Path = path; }
        public bool NoAccess => Perms.StartsWith("---") && Path.Length == 0;
    }

    public enum Kind { Gap, ReservationTop, None }

    /// <summary>What claiming a block came to. Only <see cref="NoPlace"/> says the layout itself has no safe block;
    /// <see cref="Failed"/> (mmap refused, say a mapping raced into the planned range, or the maps couldn't be read)
    /// is worth another try before the hooks.</summary>
    public enum Reservation { Claimed, NoPlace, Failed }

    public static Reservation Outcome(Plan plan, bool mapped) =>
        plan.Kind == Kind.None ? Reservation.NoPlace : mapped ? Reservation.Claimed : Reservation.Failed;

    public readonly struct Plan
    {
        public readonly Kind Kind;
        public readonly long Start, Length, WindowLow, WindowHigh;
        public readonly string Reason;
        public Plan(Kind kind, long start, long length, long low, long high, string reason)
        {
            Kind = kind; Start = start; Length = length; WindowLow = low; WindowHigh = high; Reason = reason;
        }
        public override string ToString() => Kind == Kind.None
            ? $"no placement: {Reason}"
            : $"{Kind} 0x{Start:X}-0x{Start + Length:X} ({Length >> 10} KB): {Reason}";
    }

    public static List<Region> Parse(IEnumerable<string> lines)
    {
        var regions = new List<Region>();
        foreach (var line in lines)
        {
            if (line.StartsWith("#")) continue;
            var fields = line.Split(' ', 6, StringSplitOptions.RemoveEmptyEntries);
            if (fields.Length < 5) continue;
            var range = fields[0].Split('-');
            regions.Add(new Region(long.Parse(range[0], NumberStyles.HexNumber), long.Parse(range[1], NumberStyles.HexNumber),
                fields[1], fields.Length > 5 ? fields[5].Trim() : ""));
        }
        regions.Sort((a, b) => a.Start.CompareTo(b.Start));
        return regions;
    }

    public static List<Region> ReadSelf() => Parse(File.ReadAllLines("/proc/self/maps"));

    /// <summary>GameAssembly.so's executable range, or (0, 0) when it isn't mapped.</summary>
    public static (long Start, long End) GameAssemblyCode(List<Region> regions)
    {
        long start = long.MaxValue, end = 0;
        foreach (var r in regions)
        {
            if (!r.Path.EndsWith("/GameAssembly.so") || r.Perms[2] != 'x') continue;
            start = Math.Min(start, r.Start);
            end = Math.Max(end, r.End);
        }
        return end == 0 ? (0, 0) : (start, end);
    }

    /// <summary>Plans a block of up to <paramref name="want"/> bytes, at least <paramref name="need"/>.</summary>
    public static Plan Choose(List<Region> regions, long want, long need)
    {
        var (textStart, textEnd) = GameAssemblyCode(regions);
        if (textEnd == 0) return new Plan(Kind.None, 0, 0, 0, 0, "GameAssembly.so is not mapped");
        var low = textEnd - CodeRange;
        var high = textStart + CodeRange;

        long bestStart = 0, bestEnd = 0;
        for (var i = 1; i < regions.Count; i++)
        {
            var start = Math.Max(regions[i - 1].End, low);
            var end = Math.Min(regions[i].Start, high);
            if (end - start > bestEnd - bestStart) { bestStart = start; bestEnd = end; }
        }
        if (bestEnd - bestStart >= need)
        {
            var length = Math.Min(want, bestEnd - bestStart) & ~(Page - 1);
            return new Plan(Kind.Gap, bestEnd - length, length, low, high,
                $"top of the largest unmapped gap within 1 GB of GameAssembly's code (0x{bestStart:X}-0x{bestEnd:X})");
        }

        var (runStart, runEnd, why) = ReservationTail(regions);
        if (runEnd == 0) return new Plan(Kind.None, 0, 0, low, high, $"no unmapped gap of {need >> 10} KB within 1 GB of GameAssembly's code, and {why}");
        // /proc/self/maps merges a neighbour's no-access guard page into the run, so stay 64 KB below its
        // 64 KB-aligned end (2026-10-19: a 12 KB mapping's guard page ended the run at 0x7FE902601000).
        var top = Math.Min((runEnd & ~(Granule - 1)) - Granule, high);
        var size = Math.Min(want, top - Math.Max(runStart, low)) & ~(Page - 1);
        if (size < need)
            return new Plan(Kind.None, 0, 0, low, high, $"no unmapped gap within reach, and the top of coreclr's reservation (0x{runStart:X}-0x{runEnd:X}) is out of Dobby's 1 GB code range of GameAssembly");
        return new Plan(Kind.ReservationTop, top - size, size, low, high, $"no unmapped gap within reach; {why}");
    }

    /// <summary>The no-access tail of coreclr's executable reservation: the run it commits last.</summary>
    static (long Start, long End, string Why) ReservationTail(List<Region> regions)
    {
        var coreLib = regions.FindIndex(r => r.Path.EndsWith("/System.Private.CoreLib.dll"));
        if (coreLib < 0) return (0, 0, "System.Private.CoreLib.dll is not mapped");
        var bottom = regions[coreLib].Start;
        var last = coreLib;
        string boundary = "the end of the address space";
        for (var i = coreLib + 1; i < regions.Count; i++)
        {
            var r = regions[i];
            if (r.Start != regions[i - 1].End) { boundary = $"a gap at 0x{regions[i - 1].End:X}"; break; }
            if (r.Path.Length != 0 && !r.Path.EndsWith(".dll") && !r.Path.StartsWith("/dev/zero")) { boundary = Path.GetFileName(r.Path); break; }
            if (r.End - bottom > MaxReservation) { boundary = "2 GB above System.Private.CoreLib.dll"; break; }
            last = i;
        }
        // The highest long no-access run, with only a little other memory between it and the reservation's top.
        long clutter = 0;
        for (var i = last; i > coreLib; i--)
        {
            var r = regions[i];
            if (!r.NoAccess) { clutter += r.End - r.Start; if (clutter > TopClutter) break; continue; }
            var runEnd = r.End;
            var j = i;
            while (j - 1 > coreLib && regions[j - 1].NoAccess && regions[j - 1].End == regions[j].Start) j--;
            var runStart = regions[j].Start;
            if (runEnd - runStart >= MinReservationTail)
                return (runStart, runEnd, $"top of coreclr's executable reservation (no-access tail 0x{runStart:X}-0x{runEnd:X}, {(runEnd - runStart) >> 20} MB, below {boundary})");
            clutter += runEnd - runStart;
            if (clutter > TopClutter) break;
            i = j;
        }
        return (0, 0, $"the reservation above System.Private.CoreLib.dll (to {boundary}) has no no-access tail of {MinReservationTail >> 20} MB under at most {TopClutter >> 10} KB of other memory");
    }

    /// <summary>True when [start, start+length) is still entirely no-access anonymous memory: our reserved block, untouched.</summary>
    public static bool StillReserved(List<Region> regions, long start, long length)
    {
        var at = start;
        foreach (var r in regions)
        {
            if (r.End <= at) continue;
            if (r.Start > at || !r.NoAccess) return false;
            at = r.End;
            if (at >= start + length) return true;
        }
        return false;
    }
}
