using System;
using System.IO;
using Kollektion.Core;
using Kollektion.Core.Build;

namespace Kollektion
{
    /// <summary>
    /// <c>kollektion build &lt;vehicles/NAME/vehicle.json&gt; [--extracted DIR] [--generated DIR] [--out DIR]</c>: the
    /// vehicle's meshes, as tools/build_vehicle.py builds them. The extracted folder defaults to the checkout's
    /// extracted/ (two levels above the vehicle folder), the output to the vehicle's build/; --generated reads parts
    /// named generated/... from another folder (the generators' output) in place of the vehicle's own.
    /// </summary>
    static class BuildCommand
    {
        const string Usage = "Usage: kollektion build <vehicle.json> [--extracted DIR] [--generated DIR] [--out DIR]\n";

        public static int Run(string[] args)
        {
            string manifest = null, extracted = null, generated = null, output = null;
            for (var i = 1; i < args.Length; i++)
            {
                var value = i + 1 < args.Length ? args[i + 1] : null;
                switch (args[i])
                {
                    case "--extracted" when value != null: extracted = value; i++; break;
                    case "--generated" when value != null: generated = value; i++; break;
                    case "--out" when value != null: output = value; i++; break;
                    default:
                        if (manifest != null || args[i].StartsWith("--", StringComparison.Ordinal))
                        {
                            Console.Error.Write(Usage);
                            return 2;
                        }
                        manifest = args[i];
                        break;
                }
            }
            if (manifest == null)
            {
                Console.Error.Write(Usage);
                return 2;
            }

            var text = Files.ReadText(manifest);
            if (text == null)
            {
                Console.Error.WriteLine($"Can't read {manifest}.");
                return 1;
            }
            var vehicleDir = Path.GetDirectoryName(Path.GetFullPath(manifest));
            extracted ??= Path.Combine(vehicleDir, "..", "..", "extracted");
            output ??= Path.Combine(vehicleDir, "build");
            try
            {
                using var document = VehicleBuild.Parse(text);
                var build = new VehicleBuild(manifest, extracted, generated, Console.Out);
                var missing = build.Run(document.RootElement, output);
                if (missing.Count == 0) return 0;
                Console.Error.WriteLine("missing game meshes; export them from your own install first (README, \"Building from source\"):\n  " +
                                        string.Join("\n  ", missing) + "\n" +
                                        $"(extracted/ is {Path.GetFullPath(extracted)}" +
                                        (generated == null ? ")" : $", generated/ is {Path.GetFullPath(generated)})"));
                return 1;
            }
            catch (BuildException e)
            {
                Console.Error.WriteLine($"{manifest}: {e.Message}");
                return 1;
            }
        }
    }
}
