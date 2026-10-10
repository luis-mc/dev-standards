using System.Text.RegularExpressions;
using Xunit;

namespace Guards;

/// <summary>
/// STACKSPEC 13.5 guard test (starter): no source file may contain a
/// merge-conflict marker line.
///
/// Markers left in a committed file break the build in some languages and
/// silently change behaviour in config and data files. The branch gate and the
/// pre-push hook run every test in category Guard on every push, whatever
/// changed.
///
/// Markdown and plain text are excluded: seven '=' alone on a line is a setext
/// heading underline there, not a conflict.
/// </summary>
[Trait("Category", "Guard")]
public class NoConflictMarkersGuard
{
    private static readonly HashSet<string> Scanned = new(StringComparer.OrdinalIgnoreCase)
    {
        ".cs", ".csproj", ".props", ".targets", ".sln", ".slnx", ".json", ".yml", ".yaml",
        ".toml", ".xml", ".config", ".sql", ".sh", ".ts", ".tsx", ".js", ".css", ".html",
    };

    private static readonly HashSet<string> SkipDirs = new(StringComparer.OrdinalIgnoreCase)
    {
        ".git", "bin", "obj", "node_modules", ".delivery",
    };

    // Built from pieces so this file does not contain a marker line itself.
    private static readonly Regex Start = new("^" + new string('<', 7) + "( |$)");
    private static readonly Regex Separator = new("^" + new string('=', 7) + "$");
    private static readonly Regex End = new("^" + new string('>', 7) + "( |$)");

    /// <summary>Nearest ancestor holding .git (a directory, or a file in a worktree).</summary>
    private static string RepositoryRoot()
    {
        for (var dir = new DirectoryInfo(AppContext.BaseDirectory); dir is not null; dir = dir.Parent)
        {
            if (Directory.Exists(Path.Combine(dir.FullName, ".git")) ||
                File.Exists(Path.Combine(dir.FullName, ".git")))
            {
                return dir.FullName;
            }
        }
        throw new InvalidOperationException("no .git above " + AppContext.BaseDirectory);
    }

    private static IEnumerable<string> SourceFiles(string dir)
    {
        foreach (var file in Directory.EnumerateFiles(dir))
        {
            if (Scanned.Contains(Path.GetExtension(file))) yield return file;
        }
        foreach (var sub in Directory.EnumerateDirectories(dir))
        {
            if (SkipDirs.Contains(Path.GetFileName(sub))) continue;
            foreach (var file in SourceFiles(sub)) yield return file;
        }
    }

    [Fact]
    public void NoSourceFileContainsAConflictMarker()
    {
        var root = RepositoryRoot();
        var files = SourceFiles(root).ToList();
        Assert.True(files.Count > 0, "scanned no files; an empty scan would pass for the wrong reason");

        var hits = new List<string>();
        foreach (var file in files)
        {
            var number = 0;
            foreach (var line in File.ReadLines(file))
            {
                number++;
                if (Start.IsMatch(line) || Separator.IsMatch(line) || End.IsMatch(line))
                {
                    hits.Add($"{Path.GetRelativePath(root, file).Replace('\\', '/')}:{number}: {line}");
                }
            }
        }

        Assert.True(hits.Count == 0, "merge-conflict markers found:\n" + string.Join("\n", hits));
    }
}
