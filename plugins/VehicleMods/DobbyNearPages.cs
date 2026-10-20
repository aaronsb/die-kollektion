using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using BepInEx;

namespace VehicleMods;

/// <summary>Keeps the native hooks' jump slots and trampolines out of coreclr's executable reservation.</summary>
/// <remarks>
/// BepInEx hooks IL2CPP methods with libdobby. Dobby writes <c>jmp [rip+disp32]</c> at the hooked function and
/// keeps the 8-byte target slot, and the relocated prologue, in "near" pages within 2 GB (1 GB for code) of it.
/// It finds room by reading /proc/self/maps and maps those pages MAP_FIXED into no-access memory, which near
/// GameAssembly is coreclr's executable reservation; coreclr later commits that range for JIT code and loader
/// heaps, overwrites the slots, and the next call to a hooked method jumps through garbage (2026-10-18 at the
/// mechanic; 2026-10-19 during the logo, after a game update, when Dobby's slot page sat at coreclr's committed
/// frontier). Near memory can't be avoided: five of the seven hooked prologues hold RIP-relative operands in
/// their first bytes, and Dobby's relocated copies need disp32 reach to GameAssembly's data.
/// <see cref="Reserve"/> claims a block of our own at plugin Load, as early as our code runs (P/Invoke only, no
/// IL2CPP types), where <see cref="NearBlockPlanner"/> finds room: an unmapped gap, or the top of coreclr's
/// reservation. <see cref="Install"/>, before the plugin's own hooks, re-validates the block, commits four
/// pages of it, retires Dobby's existing near pages for new allocations, hands Dobby the new pages, and moves
/// the hooks already in place onto a slot page of its own. With no usable block it returns false and the
/// plugin installs no hooks, so the game runs without the mod rather than crash.
/// </remarks>
static unsafe class DobbyNearPages
{
    const int ProtNone = 0, ProtRead = 1, ProtWrite = 2, ProtExec = 4;
    const int MapPrivate = 0x02, MapFixed = 0x10, MapAnonymous = 0x20, MapNoReserve = 0x4000, MapFixedNoReplace = 0x100000;
    const int DobbyReadWrite = 2, DobbyReadExecute = 4;    // MemoryPermission of Dobby's data and code chunks
    const int Page = 0x1000;
    const long Want = 4 << 20, Need = 4 * Page;            // a generous block, PROT_NONE until used; four pages in use

    // Dobby structures: LiteMutableArray { vtable, vtable, items @0x10, count @0x18 } and the page records
    // NearMemoryArena::PushPage creates { page @0, size @8, cursor @0x10, permission @0x18 }.
    const int ArrayItems = 0x10, ArrayCount = 0x18;
    const int ChunkPage = 0, ChunkSize = 8, ChunkCursor = 0x10, ChunkPermission = 0x18;

    static IntPtr pageChunks, dataPage, codePage;
    static long blockStart, blockLength;

    [DllImport("libc", SetLastError = true)]
    static extern IntPtr mmap(IntPtr addr, UIntPtr length, int prot, int flags, int fd, IntPtr offset);

    [DllImport("libc", SetLastError = true)]
    static extern int munmap(IntPtr addr, UIntPtr length);

    [DllImport("libc", SetLastError = true)]
    static extern int mprotect(IntPtr addr, UIntPtr length, int prot);

    /// <summary>Claims the block at plugin Load. Native calls only; failures are logged and retried at <see cref="Install"/>.
    /// False when nothing was claimed.</summary>
    public static bool Reserve()
    {
        try
        {
            return Claim(NearBlockPlanner.ReadSelf(), "at Load");
        }
        catch (Exception e)
        {
            Plugin.Logger.LogWarning($"Dobby pages: reserving at Load failed ({e.Message}); trying again before the hooks");
            return false;
        }
    }

    static bool Claim(List<NearBlockPlanner.Region> regions, string when)
    {
        var plan = NearBlockPlanner.Choose(regions, Want, Need);
        if (plan.Kind == NearBlockPlanner.Kind.None)
        {
            Plugin.Logger.LogWarning($"Dobby pages: nothing to reserve {when}: {plan.Reason}{SaveMaps(when, plan.Reason)}");
            return false;
        }
        // A gap is claimed with MAP_FIXED_NOREPLACE, which fails rather than replace anything mapped since the maps
        // were read; the reservation's top is no-access memory coreclr reserved and will reach last, replaced in place.
        var flags = MapPrivate | MapAnonymous | MapNoReserve | (plan.Kind == NearBlockPlanner.Kind.Gap ? MapFixedNoReplace : MapFixed);
        var got = mmap((IntPtr)plan.Start, (UIntPtr)plan.Length, ProtNone, flags, -1, IntPtr.Zero);
        if (got != (IntPtr)plan.Start)
        {
            if (got != (IntPtr)(-1)) munmap(got, (UIntPtr)plan.Length);    // a kernel without MAP_FIXED_NOREPLACE treats the address as a hint
            Plugin.Logger.LogWarning($"Dobby pages: reserving {when} at 0x{plan.Start:X} failed (errno {Marshal.GetLastWin32Error()}): {plan}");
            return false;
        }
        blockStart = plan.Start;
        blockLength = plan.Length;
        Plugin.Logger.LogInfo($"Dobby pages: reserved {when}: {plan}");
        return true;
    }

    /// <summary>Copies /proc/self/maps to BepInEx/dobby-maps.txt (each session starts it afresh) so a layout with no
    /// safe block can be read, and turned into a tests/maps case once its paths are scrubbed. Returns the log
    /// line's tail.</summary>
    static string SaveMaps(string when, string reason)
    {
        try
        {
            var path = Path.Combine(Paths.BepInExRootPath, "dobby-maps.txt");
            var text = $"# {when}: {reason}\n" + File.ReadAllText("/proc/self/maps");
            if (mapsSaved) File.AppendAllText(path, text); else File.WriteAllText(path, text);
            mapsSaved = true;
            return $" (memory map saved to {path})";
        }
        catch (Exception e)
        {
            return $" (the memory map couldn't be saved: {e.Message})";
        }
    }

    static bool mapsSaved;

    /// <summary>Runs once on the entry thread before any of the plugin's hooks. False: no safe pages, install no hooks.</summary>
    public static bool Install()
    {
        var regions = NearBlockPlanner.ReadSelf();
        var (textStart, textEnd) = NearBlockPlanner.GameAssemblyCode(regions);
        if (textEnd == 0)
        {
            Plugin.Logger.LogError("Dobby pages: GameAssembly.so not in /proc/self/maps; installing no hooks");
            return false;
        }
        var dobby = NativeLibrary.Load(Path.Combine(Paths.BepInExAssemblyDirectory, "libdobby.so"));
        pageChunks = *(IntPtr*)NativeLibrary.GetExport(dobby, "_ZN15NearMemoryArena11page_chunksE");
        var pushPage = (delegate* unmanaged[Cdecl]<ulong, int, int>)NativeLibrary.GetExport(dobby, "_ZN15NearMemoryArena8PushPageEm16MemoryPermission");
        if (pageChunks == IntPtr.Zero)
        {
            Plugin.Logger.LogError("Dobby pages: Dobby has no page list; installing no hooks");
            return false;
        }

        if (blockLength != 0 && !NearBlockPlanner.StillReserved(regions, blockStart, blockLength))
        {
            Plugin.Logger.LogWarning($"Dobby pages: the block reserved at Load (0x{blockStart:X}) was changed since; choosing again");
            blockLength = 0;
        }
        if (blockLength == 0 && !Claim(regions, "before the hooks"))
        {
            Plugin.Logger.LogError($"Dobby pages: no safe place for the hooks' jump slots within reach of GameAssembly's code (0x{textStart:X}-0x{textEnd:X}); "
                + "installing no hooks, so the game runs without Die Kollektion this session. Please report this with BepInEx/LogOutput.log");
            return false;
        }

        // Four pages: one for jump slots, two for relocated prologues, one for the slots moved off Dobby's pages.
        var pages = (IntPtr)blockStart;
        mprotect(pages, (UIntPtr)(4 * Page), ProtRead | ProtWrite);
        dataPage = pages;
        codePage = pages + Page;
        var slotPage = pages + 3 * Page;
        mprotect(codePage, (UIntPtr)(2 * Page), ProtRead | ProtExec);
        Plugin.Logger.LogInfo($"Dobby pages: using 0x{blockStart:X}-0x{blockStart + 4 * Page:X} of the 0x{blockStart:X}-0x{blockStart + blockLength:X} block");

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
        Plugin.Logger.LogInfo($"Dobby pages: new hooks use 0x{(long)dataPage:X} (slots) and 0x{(long)codePage:X} (code), {Math.Max(textStart - (long)dataPage, (long)dataPage - textEnd) / (1 << 20)} MB from GameAssembly's code");

        MoveSlots(regions, oldDataPages, oldSlots, slotPage);
        return true;
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
    static void MoveSlots(List<NearBlockPlanner.Region> regions, List<(long Start, long End)> oldDataPages, long oldSlots, IntPtr slotPage)
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

    static long ModuleBase(List<NearBlockPlanner.Region> regions, string path)
    {
        foreach (var r in regions)
            if (r.Path == path) return r.Start;
        return 0;
    }

    static bool InAny(List<(long Start, long End)> ranges, long address)
    {
        foreach (var (start, end) in ranges)
            if (address >= start && address < end) return true;
        return false;
    }

    static bool IsExecutable(List<NearBlockPlanner.Region> regions, long address)
    {
        foreach (var r in regions)
            if (address >= r.Start && address < r.End) return r.Perms[2] == 'x';
        return false;
    }

    // Which mapping a Dobby page sits in, and how far it is from the no-access reservation it was carved from.
    static string Describe(List<NearBlockPlanner.Region> regions, long address)
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
