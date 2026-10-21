using System;
using System.IO;
using System.Text;

namespace Kollektion.Core.GameData
{
    /// <summary>Writing an output file failed (the disk, permissions, the path); the game's files aren't the
    /// cause.</summary>
    public sealed class OutputException : IOException
    {
        public OutputException(string message, Exception inner) : base(message, inner)
        {
        }
    }

    /// <summary>The one way the exporters write a file: its folder made first, the bytes written under a temporary
    /// name of their own beside it and renamed into place, so a failed write leaves the old file or none and no
    /// temporary behind. Text is UTF-8 without a BOM with "\n" line ends on every OS, as the Python writes it.</summary>
    public static class Output
    {
        static readonly UTF8Encoding Utf8 = new UTF8Encoding(false);

        public static void WriteText(string path, string text) => Write(path, s =>
        {
            var bytes = Utf8.GetBytes(text);
            s.Write(bytes, 0, bytes.Length);
        });

        public static void Write(string path, Action<Stream> write)
        {
            var full = Path.GetFullPath(path);
            var tmp = Path.Combine(Path.GetDirectoryName(full), $".{Path.GetFileName(full)}.{Guid.NewGuid():N}.tmp");
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(full));
                using (var f = new FileStream(tmp, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                    write(f);
                File.Move(tmp, full, true);
            }
            catch (Exception e) when (e is IOException || e is UnauthorizedAccessException)
            {
                throw new OutputException($"can't write {full}: {e.Message}", e);
            }
            finally
            {
                try
                {
                    if (File.Exists(tmp)) File.Delete(tmp);
                }
                catch (Exception e) when (e is IOException || e is UnauthorizedAccessException)
                {
                    // The write's own error matters more; a temporary that can't be removed stays.
                }
            }
        }
    }
}
