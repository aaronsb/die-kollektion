using System;
using System.IO;
using System.Text;

namespace Kollektion.Core
{
    /// <summary>Reads that treat a file the user can't read like a missing one: status and checks report it,
    /// never crash on it (Python's OSError covers both; .NET's UnauthorizedAccessException isn't an IOException).</summary>
    public static class Files
    {
        public static string ReadText(string path)
        {
            try { return File.ReadAllText(path, Encoding.UTF8); }
            catch (Exception e) when (e is IOException || e is UnauthorizedAccessException) { return null; }
        }

        public static byte[] ReadBytes(string path)
        {
            try { return File.ReadAllBytes(path); }
            catch (Exception e) when (e is IOException || e is UnauthorizedAccessException) { return null; }
        }
    }
}
