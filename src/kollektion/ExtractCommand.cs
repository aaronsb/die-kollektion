using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using Kollektion.Core;
using Kollektion.Core.GameData;

namespace Kollektion
{
    /// <summary><c>kollektion extract</c>: the game data the build reads, from the player's own install, into a folder
    /// that is never shared or committed (today's `make extract`, tools/export_game_data.sh). Reads the game folder
    /// only; the game may be running.</summary>
    static class ExtractCommand
    {
        public const string Usage =
            "Usage: kollektion extract --out <dir> [--game <game folder>] [--vehicles <vehicles dir>] [--donor <Car>]...\n\n" +
            "  --out       where to write (the Werkstatt's extracted/ folder)\n" +
            "  --game      the game folder (default: GAME_DIR, else the Steam library holding the game)\n" +
            "  --vehicles  the vehicle folders whose manifests name the donors (default: ./vehicles when present)\n" +
            "  --donor     also a stock car no manifest names: body, colliders, node facts and atlas maps\n";

        public static int Run(string[] args)
        {
            string game = null, vehicles = null, outDir = null;
            var extra = new List<string>();
            for (int i = 1; i < args.Length; i++)
            {
                var a = args[i];
                if (a == "--help" || a == "-h")
                {
                    Console.Write(Usage);
                    return 0;
                }
                if (i + 1 >= args.Length || !(a == "--game" || a == "--vehicles" || a == "--out" || a == "--donor"))
                {
                    Console.Error.Write($"extract: unexpected argument {a}\n\n" + Usage);
                    return 2;
                }
                var value = args[++i];
                switch (a)
                {
                    case "--game": game = value; break;
                    case "--vehicles": vehicles = value; break;
                    case "--out": outDir = value; break;
                    default: extra.Add(value); break;
                }
            }
            if (outDir == null)
            {
                Console.Error.Write("extract: name the folder to write with --out\n\n" + Usage);
                return 2;
            }
            game ??= Platform.GameDir();
            if (game == null)
            {
                Console.Error.WriteLine("extract: the game folder wasn't found; pass it with --game");
                return 1;
            }
            if (vehicles == null && Directory.Exists("vehicles")) vehicles = "vehicles";
            if (vehicles != null && !Directory.Exists(vehicles))
            {
                Console.Error.WriteLine($"extract: no folder {vehicles}");
                return 1;
            }
            Console.WriteLine($"Game folder: {game}");
            Console.WriteLine(vehicles == null ? "No vehicles folder: the Mammoth only" : $"Donors from {vehicles}");
            var clock = Stopwatch.StartNew();
            try
            {
                Extraction.Run(game, vehicles, extra, outDir, Console.WriteLine);
            }
            catch (Exception e) when (e is IOException || e is InvalidDataException || e is NotSupportedException
                                      || e is UnauthorizedAccessException)
            {
                Console.Error.WriteLine($"extract: {e.Message}");
                return 1;
            }
            Console.WriteLine($"Extracted into {outDir} in {clock.Elapsed.TotalSeconds:0.0} s (never share or commit it).");
            return 0;
        }
    }
}
