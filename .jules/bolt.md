# Bolt's Journal - Critical Performance Learnings

## 2026-09-03 - `Path.rglob` vs `os.scandir` for Recursive Directory Size Calculation
**Learning:** In Python standard library codebases, `Path.rglob('*')` to sum file sizes is significantly slower (~3x–10x) than iterative `os.scandir` stack traversal. `Path.rglob` instantiates a `Path` object for every file and folder in the hierarchy and invokes `stat()` calls separately. `os.scandir` yields `DirEntry` objects whose `stat()` metadata is cached directly from Linux/POSIX directory entries without creating excess object overhead.
**Action:** Always prefer `os.scandir` stack-based traversal over `Path.rglob` when calculating directory sizes or walking large application installation trees on Linux.
