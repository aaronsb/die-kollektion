using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Runtime.InteropServices;
using BepInEx;

namespace VehicleMods;

/// <summary>Keeps the native hooks' jump slots and trampolines out of coreclr's executable reservation.</summary>
/// <remarks>
/// BepInEx hooks IL2CPP methods with libdobby. Dobby writes <c>jmp [rip+disp32]</c> at the hooked function and
/// keeps the 8-byte target slot, and the relocated prologue, in "near" pages within 2 GB (1 GB for code) of it.
/// It finds room by reading /proc/self/maps and maps those pages MAP_FIXED into no-access memory, which near
/// GameAssembly is coreclr's executable reservation below libcoreclr. Coreclr later commits that range for JIT
/// code and overwrites the slots, and the next call to a hooked method jumps through garbage
/// (2026-10-18: SIGSEGV entering LocalVehicleCustomizationController.RefreshMountedUpgrades at the mechanic).
/// Before the plugin's own hooks exist this maps pages of its own in free address space, retires Dobby's
/// existing near pages for new allocations, hands Dobby the new pages, and moves the hooks already in place
/// onto a slot page of its own.
/// </remarks>
static unsafe class DobbyNearPages
{
    const int ProtRead = 1, ProtWrite = 2, ProtExec = 4;
    const int MapPrivate = 0x02, MapFixed = 0x10, MapAnonymous = 0x20, MapFixedNoReplace = 0x100000;
    const int DobbyReadWrite = 2, DobbyReadExecute = 4;    // MemoryPermission of Dobby's data and code chunks
    const long CodeRange = 0x40000000;                     // relocated prologues stay within 1 GB of the hook
    const long MaxReservation = 0x80000000;                // coreclr reserves at most 2 GB of executable memory
    const long MinReservationRun = 0x8000000;              // 128 MB: larger than any glibc arena reservation
    const int Page = 0x1000;

    // Dobby structures: LiteMutableArray { vtable, vtable, items @0x10, count @0x18 } and the page records
    // NearMemoryArena::PushPage creates { page @0, size @8, cursor @0x10, permission @0x18 }.
    const int ArrayItems = 0x10, ArrayCount = 0x18;
    const int ChunkPage = 0, ChunkSize = 8, ChunkCursor = 0x10, ChunkPermission = 0x18;

    static IntPtr pageChunks, dataPage, codePage;

    [DllImport("libc", SetLastError = true)]
    static extern IntPtr mmap(IntPtr addr, UIntPtr length, int prot, int flags, int fd, IntPtr offset);

    [DllImport("libc", SetLastError = true)]
    static extern int munmap(IntPtr addr, UIntPtr length);

    [DllImport("libc", SetLastError = true)]
    static extern int mprotect(IntPtr addr, UIntPtr length, int prot);

    readonly struct Region
    {
        public readonly long Start, End;
        public readonly string Perms, Path;
        public Region(long start, long end, string perms, string path) { Start = start; End = end; Perms = perms; Path = path; }
    }

    /// <summary>Runs once on the entry thread before any of the plugin's hooks; logs and leaves Dobby as it was on any failure.</summary>
    public static void Install()
    {
        var regions = ReadMaps();
        long textStart = long.MaxValue, textEnd = 0;
        foreach (var r in regions)
        {
            if (!r.Path.EndsWith("/GameAssembly.so") || r.Perms[2] != 'x') continue;
            textStart = Math.Min(textStart, r.Start);
            textEnd = Math.Max(textEnd, r.End);
        }
        if (textEnd == 0)
        {
            Plugin.Logger.LogWarning("Dobby pages: GameAssembly.so not in /proc/self/maps; leaving Dobby as it is");
            return;
        }

        var dobby = NativeLibrary.Load(Path.Combine(Paths.BepInExAssemblyDirectory, "libdobby.so"));
        pageChunks = *(IntPtr*)NativeLibrary.GetExport(dobby, "_ZN15NearMemoryArena11page_chunksE");
        var pushPage = (delegate* unmanaged[Cdecl]<ulong, int, int>)NativeLibrary.GetExport(dobby, "_ZN15NearMemoryArena8PushPageEm16MemoryPermission");
        if (pageChunks == IntPtr.Zero)
        {
            Plugin.Logger.LogWarning("Dobby pages: Dobby has no near pages yet; leaving it as it is");
            return;
        }

        // Four pages: one for jump slots, two for relocated prologues, one for the slots moved off Dobby's pages.
        // Every hooked function lies in GameAssembly's code, so the pages must be within Dobby's 1 GB code range
        // of both its ends.
        var low = textEnd - CodeRange;
        var high = textStart + CodeRange;
        var pages = MapInHole(regions, low, high, 4);
        var where = "a free hole";
        if (pages == IntPtr.Zero)
        {
            pages = MapAtReservationTop(regions, low, high, 4, out where);
            if (pages == IntPtr.Zero) Plugin.Logger.LogWarning($"Dobby pages: no free hole within 1 GB of GameAssembly's code, and {where}");
        }
        if (pages == IntPtr.Zero)
        {
            Plugin.Logger.LogError($"Dobby pages: no free hole and no usable coreclr reservation within 1 GB of GameAssembly's code (0x{textStart:X}-0x{textEnd:X}); "
                + "the hooks' jump slots stay on Dobby's pages inside coreclr's executable reservation, where JIT code can overwrite them: "
                + "expect a crash the next time a hooked method runs after that (e.g. entering the mechanic)");
            return;
        }
        Plugin.Logger.LogInfo($"Dobby pages: mapped 0x{(long)pages:X}-0x{(long)pages + 4 * Page:X} in {where}");
        dataPage = pages;
        codePage = pages + Page;
        var slotPage = pages + 3 * Page;
        mprotect(codePage, (UIntPtr)(2 * Page), ProtRead | ProtExec);

        var oldDataPages = new List<(long Start, long End)>();
        long oldSlots = 0;
        var items = *(IntPtr*)(pageChunks + ArrayItems);
        var count = *(uint*)(pageChunks + ArrayCount);
        for (var i = 0; i < count; i++)
        {
            var chunk = ((IntPtr*)items)[i];
            var start = *(long*)(chunk + ChunkPage);
            var size = *(long*)(chunk + ChunkSize);
            var used = *(long*)(chunk + ChunkCursor) - start;
            var permission = *(int*)(chunk + ChunkPermission);
            Plugin.Logger.LogInfo($"Dobby pages: retiring near page 0x{start:X} ({(permission == DobbyReadWrite ? "slots" : "code")}, {used} of {size} bytes used, {Describe(regions, start)})");
            if (permission == DobbyReadWrite)
            {
                oldDataPages.Add((start, start + size));
                oldSlots += used / 8;
            }
            *(long*)(chunk + ChunkCursor) = start + size;    // full: AllocateChunk skips it from now on
        }
        pushPage((ulong)dataPage, DobbyReadWrite);
        pushPage((ulong)codePage, DobbyReadExecute);
        pushPage((ulong)(codePage + Page), DobbyReadExecute);
        Plugin.Logger.LogInfo($"Dobby pages: new hooks use 0x{(long)dataPage:X} (slots) and 0x{(long)codePage:X} (code), {((long)dataPage - textStart) / (1 << 20)} MB from the start of GameAssembly's code");

        MoveSlots(regions, oldDataPages, oldSlots, slotPage);
    }

    /// <summary>Logs how much of the plugin's pages Dobby has used, after the hooks are in.</summary>
    public static void LogUsage()
    {
        if (dataPage == IntPtr.Zero) return;
        var items = *(IntPtr*)(pageChunks + ArrayItems);
        var count = *(uint*)(pageChunks + ArrayCount);
        for (var i = 0; i < count; i++)
        {
            var chunk = ((IntPtr*)items)[i];
            var start = *(long*)(chunk + ChunkPage);
            if (start < (long)dataPage || start > (long)codePage + Page) continue;
            Plugin.Logger.LogInfo($"Dobby pages: 0x{start:X} holds {*(long*)(chunk + ChunkCursor) - start} bytes of {(*(int*)(chunk + ChunkPermission) == DobbyReadWrite ? "slots" : "code")}");
        }
    }

    /// <summary>Points every live hook that jumps through a slot on Dobby's old pages at a copy on <paramref name="slotPage"/>.</summary>
    /// <remarks>
    /// A <c>jmp [rip+disp32]</c> reaches 2 GB, so every module that could jump through an old slot is scanned, not
    /// only GameAssembly. Slots no live jump uses belong to hooks already undone: BepInEx hooks
    /// il2cpp_runtime_invoke to start the chainloader and removes that hook (DobbyDestroy restores the original
    /// bytes) once the chainloader is up, leaving its slot and relocated prologue behind as dead bytes.
    /// </remarks>
    static void MoveSlots(List<Region> regions, List<(long Start, long End)> oldDataPages, long oldSlots, IntPtr slotPage)
    {
        if (oldDataPages.Count == 0) return;
        long reachLow = long.MaxValue, reachHigh = 0;
        foreach (var (start, end) in oldDataPages)
        {
            reachLow = Math.Min(reachLow, start - int.MaxValue);
            reachHigh = Math.Max(reachHigh, end + int.MaxValue);
        }
        var moved = 0;
        var slots = (long*)slotPage;
        foreach (var r in regions)
        {
            if (r.Perms[2] != 'x' || !r.Path.StartsWith("/") || r.End <= reachLow || r.Start >= reachHigh) continue;
            var module = Path.GetFileName(r.Path);
            var moduleBase = ModuleBase(regions, r.Path);
            for (var entry = r.Start; entry + 6 <= r.End; entry += 16)    // compiled functions start 16-byte aligned
            {
                var code = (byte*)entry;
                if (code[0] != 0xFF || code[1] != 0x25) continue;
                var slot = entry + 6 + *(int*)(code + 2);
                if (!InAny(oldDataPages, slot)) continue;
                var target = *(long*)slot;
                if (!IsExecutable(regions, target))
                {
                    Plugin.Logger.LogWarning($"Dobby pages: hook at {module}+0x{entry - moduleBase:X} has a damaged slot (0x{target:X}); left as it is");
                    continue;
                }
                if (moved == Page / 8) break;
                var newSlot = (long)(slots + moved);
                var disp = newSlot - (entry + 6);
                if (disp != (int)disp) continue;
                slots[moved++] = target;
                // A 4-byte store inside one cache line is atomic, and the old and new slots hold the same target.
                var pageStart = (IntPtr)(entry & ~(long)(Page - 1));
                mprotect(pageStart, (UIntPtr)Page, ProtRead | ProtWrite | ProtExec);
                *(int*)(code + 2) = (int)disp;
                mprotect(pageStart, (UIntPtr)Page, ProtRead | ProtExec);
                Plugin.Logger.LogInfo($"Dobby pages: moved the slot of the hook at {module}+0x{entry - moduleBase:X}");
            }
        }
        mprotect(slotPage, (UIntPtr)Page, ProtRead);
        Plugin.Logger.LogInfo($"Dobby pages: moved {moved} live hook slot(s) to 0x{(long)slotPage:X}; {oldSlots - moved} slot(s) on Dobby's old pages have no live jump (hooks already undone)");
    }

    static long ModuleBase(List<Region> regions, string path)
    {
        foreach (var r in regions)
            if (r.Path == path) return r.Start;
        return 0;
    }

    /// <summary>Maps <paramref name="count"/> pages in an unmapped hole inside [<paramref name="low"/>, <paramref name="high"/>).</summary>
    static IntPtr MapInHole(List<Region> regions, long low, long high, int count)
    {
        var length = count * Page;
        for (var i = 1; i < regions.Count; i++)
        {
            var start = Math.Max(regions[i - 1].End, low);
            var end = Math.Min(regions[i].Start, high);
            if (end - start < length) continue;
            // MAP_FIXED_NOREPLACE fails rather than replace anything mapped since the maps were read.
            var got = mmap((IntPtr)start, (UIntPtr)length, ProtRead | ProtWrite, MapPrivate | MapAnonymous | MapFixedNoReplace, -1, IntPtr.Zero);
            if (got == (IntPtr)(-1)) continue;
            if ((long)got == start) return got;
            munmap(got, (UIntPtr)length);    // a kernel without MAP_FIXED_NOREPLACE treats the address as a hint
        }
        return IntPtr.Zero;
    }

    /// <summary>Maps <paramref name="count"/> pages over the top of coreclr's executable reservation.</summary>
    /// <remarks>
    /// Coreclr's PAL hands out that reservation strictly upward from its bottom (ExecutableMemoryAllocator keeps a
    /// next-free address), so its top is the last part it would commit, after nearly 2 GB of code and loader heaps.
    /// The reservation is found from System.Private.CoreLib.dll, which coreclr maps into it first: walking upward,
    /// every mapping up to the reservation's top is coreclr's (unnamed memory or a mapped *.dll image) or one of
    /// Dobby's MAP_FIXED pages, because the kernel places nothing else inside a reservation. The walk ends at an
    /// unmapped gap or at a file mapping that is not a *.dll. The reservation's top need not touch libcoreclr:
    /// 2026-10-18 22:10 it ended 128 MB below it, under a GPU mapping. Only the top pages of the no-access run that
    /// ends there are replaced, and only if that run is at least <see cref="MinReservationRun"/> long (glibc's
    /// 64 MB arena reservations never are); nothing coreclr has committed is touched.
    /// </remarks>
    static IntPtr MapAtReservationTop(List<Region> regions, long low, long high, int count, out string why)
    {
        var length = count * Page;
        var coreLib = regions.FindIndex(r => r.Path.EndsWith("/System.Private.CoreLib.dll"));
        if (coreLib < 0)
        {
            why = "System.Private.CoreLib.dll is not mapped";
            return IntPtr.Zero;
        }
        long runStart = 0, runEnd = 0, top = 0;
        string boundary = null;
        for (var i = coreLib; ; i++)
        {
            if (i == regions.Count) { top = regions[i - 1].End; boundary = "the end of the address space"; break; }
            var r = regions[i];
            if (i > coreLib && r.Start != regions[i - 1].End) { top = regions[i - 1].End; boundary = $"a gap at 0x{top:X}"; break; }
            if (r.Path.Length != 0 && !r.Path.EndsWith(".dll")) { top = r.Start; boundary = Path.GetFileName(r.Path); break; }
            if (r.Start - regions[coreLib].Start > MaxReservation)
            {
                why = $"no reservation boundary within 2 GB above System.Private.CoreLib.dll (0x{regions[coreLib].Start:X})";
                return IntPtr.Zero;
            }
            if (r.Perms == "---p" && r.Path.Length == 0)
            {
                if (runEnd != r.Start) runStart = r.Start;
                runEnd = r.End;
            }
        }
        if (runEnd != top || top - runStart < MinReservationRun)
        {
            why = $"the reservation above System.Private.CoreLib.dll ends at 0x{top:X} (below {boundary}) without a no-access run of {MinReservationRun >> 20} MB under it";
            return IntPtr.Zero;
        }
        var start = top - length;
        if (start < low || top > high)
        {
            why = $"the reservation's top 0x{top:X} (below {boundary}) is out of Dobby's 1 GB code range of GameAssembly";
            return IntPtr.Zero;
        }
        var got = mmap((IntPtr)start, (UIntPtr)length, ProtRead | ProtWrite, MapPrivate | MapAnonymous | MapFixed, -1, IntPtr.Zero);
        if (got != (IntPtr)start)
        {
            why = $"mmap at 0x{start:X} failed (errno {Marshal.GetLastWin32Error()})";
            return IntPtr.Zero;
        }
        why = $"the top of coreclr's executable reservation (0x{runStart:X}-0x{top:X}, below {boundary})";
        return got;
    }

    static List<Region> ReadMaps()
    {
        var regions = new List<Region>();
        foreach (var line in File.ReadAllLines("/proc/self/maps"))
        {
            var fields = line.Split(' ', 6, StringSplitOptions.RemoveEmptyEntries);
            var range = fields[0].Split('-');
            regions.Add(new Region(long.Parse(range[0], NumberStyles.HexNumber), long.Parse(range[1], NumberStyles.HexNumber),
                fields[1], fields.Length > 5 ? fields[5].Trim() : ""));
        }
        return regions;
    }

    static bool InAny(List<(long Start, long End)> ranges, long address)
    {
        foreach (var (start, end) in ranges)
            if (address >= start && address < end) return true;
        return false;
    }

    static bool IsExecutable(List<Region> regions, long address)
    {
        foreach (var r in regions)
            if (address >= r.Start && address < r.End) return r.Perms[2] == 'x';
        return false;
    }

    // Which mapping a Dobby page sits in, and how far it is from the no-access reservation it was carved from.
    static string Describe(List<Region> regions, long address)
    {
        for (var i = 0; i < regions.Count; i++)
        {
            var r = regions[i];
            if (address < r.Start || address >= r.End) continue;
            var below = i > 0 && regions[i - 1].Perms.StartsWith("---") && regions[i - 1].End == r.Start;
            var above = i + 1 < regions.Count && regions[i + 1].Perms.StartsWith("---") && regions[i + 1].Start == r.End;
            return below || above ? $"{r.Perms}, inside a no-access reservation" : r.Perms;
        }
        return "unmapped";
    }
}
