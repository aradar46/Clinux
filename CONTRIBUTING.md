# Contributing to Clinux

Thank you for contributing to Clinux! To maintain clean architecture, safety, and maintainability across all modules, all code must adhere to the following 10 mandatory rules:

1. **UI never executes shell commands directly.** All UI layers (web, CLI, terminal) must request data or invoke actions through application services and modules.
2. **Modules never import UI code.** Modules must remain decoupled from presentation logic and produce structured data models or dictionary results.
3. **Scanners never modify the system.** Scanning and detection operations must be strictly read-only.
4. **Destructive operations require explicit actions.** Any operation that modifies the system or deletes files must be isolated in explicit action methods.
5. **All subprocesses go through `Runner`.** Never call `subprocess.run` or `os.system` directly. Always use `clinux.runner.runner` for consistent execution, logging, timeout handling, and dry-run support.
6. **All user configuration goes through `Config`.** Use `clinux.config.Config` for declarative user options and preferences.
7. **System detection goes through `Capabilities`.** Use `clinux.capabilities.capabilities` to query system binaries and capabilities rather than scattering `shutil.which` calls across the codebase.
8. **No feature-specific global state.** Keep modules stateless or explicitly scoped to instance parameters.
9. **No duplicated path definitions.** Define and import central path constants from `clinux.paths`.
10. **Python stdlib only.** Zero external dependencies allowed. Ensure compatibility with Python 3.8+.
