## 2026-09-04 - Path vs os.path Overhead in Directory Walks

**Learning:** Instantiating `pathlib.Path` objects inside tight `os.walk` or recursive file traversal loops adds significant object allocation, path parsing, and normalization overhead. In directories with tens of thousands of files (e.g. `/opt`), creating `Path` objects and calling `.stat()`, `.suffix`, and `.lower()` on each file added ~1.7s of unnecessary overhead. Switching to `os.path.join`, fast string slice extension checks (`file[file.rfind('.'):]`), cached directory component sets (`rel_root_parts & {...}`), and single `os.stat` calls sped up `scan_directory_candidates` by over 2x (3.3s -> 1.6s).

**Action:** In directory scanning and file tree traversal hot paths, use `os.path` and `os.stat` directly instead of instantiating `pathlib.Path` objects for every item inside loops.
