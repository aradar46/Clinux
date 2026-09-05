import os
import re
import socket
import shutil
import urllib.request
import urllib.error
import json
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

from .db import Database


class SkillManager:
    """
    Manages discovery and activation/deactivation of AI agent skills across
    Claude Code, Antigravity/Agy, Gemini, and Codex.
    """

    # A skills root contains category directories and an ``active_skills``
    # directory.  Example: root/writing/my-skill/SKILL.md.
    DEFAULT_SKILLS_ROOT = Path.home() / ".config" / "skills"

    DEFAULT_TARGET_DIRS = {
        "claude": Path.home() / ".claude" / "skills",
        "agy": Path.home() / ".gemini" / "antigravity-cli" / "skills",
        "gemini": Path.home() / ".gemini" / "skills",
        "codex": Path.home() / ".codex" / "skills",
    }

    # Gemini and Antigravity keep user skills in more than one supported
    # location on installations in the wild. Keep each user-facing location
    # in sync; deliberately exclude builtin and backup directories.
    DEFAULT_EXTRA_TARGET_DIRS = {
        "gemini": [Path.home() / ".gemini" / "config" / "skills"],
        "agy": [Path.home() / ".gemini" / "antigravity" / "skills"],
    }
    LEGACY_AGY_DIR = Path.home() / ".claude" / "skills" / "Agy"

    def __init__(
        self,
        skills_root: Optional[Path] = None,
        repo_dirs: Optional[List[Path]] = None,
        target_dirs: Optional[Dict[str, Path]] = None,
    ):
        # repo_dirs is retained for callers using the previous public API.
        # New callers should pass one categorized skills_root.
        if skills_root is not None:
            self.skills_root = Path(skills_root).expanduser().resolve()
        elif repo_dirs:
            self.skills_root = Path(repo_dirs[0]).expanduser().resolve()
        else:
            self.skills_root = self.DEFAULT_SKILLS_ROOT
        self.repo_dirs = [self.skills_root]
        self.active_dir = self.skills_root / "active_skills"
        self.target_dirs = {
            k: Path(v) for k, v in (target_dirs or self.DEFAULT_TARGET_DIRS).items()
        }
        self.extra_target_dirs = (
            {} if target_dirs else self.DEFAULT_EXTRA_TARGET_DIRS
        )

    def _target_paths(self, target_name: str) -> List[Path]:
        """Return every directory that must mirror an agent's active skills."""
        paths = [self.target_dirs[target_name]]
        paths.extend(self.extra_target_dirs.get(target_name, []))
        return paths

    @staticmethod
    def parse_skill_metadata(skill_dir: Path) -> Tuple[str, str]:
        """
        Extract skill name and description from SKILL.md YAML frontmatter.
        """
        md_file = skill_dir / "SKILL.md"
        name = skill_dir.name
        description = ""

        if not md_file.exists():
            return name, description

        try:
            with open(md_file, "r", encoding="utf-8", errors="replace") as f:
                lines = [f.readline() for _ in range(40)]
                content = "".join(lines)

            # Match name
            m_name = re.search(r"^name:\s*(?:[\"']?)([^\"'\r\n]+)(?:[\"']?)", content, re.MULTILINE)
            if m_name:
                name = m_name.group(1).strip()

            # Match description
            m_desc = re.search(
                r"^description:\s*(?:>-\s*\n(?:\s+([^\r\n]+)\n?)+|[\"']([^\"']+)[\"']|([^\r\n]+))",
                content,
                re.MULTILINE,
            )
            if m_desc:
                if m_desc.group(2):
                    description = m_desc.group(2).strip()
                elif m_desc.group(3):
                    description = m_desc.group(3).strip()
                else:
                    # Multi-line block scalar
                    desc_lines = []
                    in_desc = False
                    for line in lines:
                        if re.match(r"^description:\s*>-", line):
                            in_desc = True
                            continue
                        if in_desc:
                            if line.startswith("  ") or line.startswith("\t"):
                                desc_lines.append(line.strip())
                            else:
                                break
                    description = " ".join(desc_lines)
        except Exception:
            pass

        return name, description

    def get_categories(self) -> List[str]:
        """
        Find all categories in configured skill repositories.
        """
        categories = set()
        for r_dir in self.repo_dirs:
            if not r_dir.exists():
                continue
            for item in r_dir.iterdir():
                if item.name == "active_skills":
                    continue
                if item.is_dir() and not item.name.startswith("."):
                    for sub in item.iterdir():
                        if sub.is_dir() and (sub / "SKILL.md").exists():
                            categories.add(item.name)
                            break
        return sorted(categories)

    def get_all_skills(self) -> List[Dict[str, Any]]:
        """
        Scan repositories and return all skills with active status per agent.
        """
        skills = []
        seen_keys = set()

        for r_dir in self.repo_dirs:
            if not r_dir.exists():
                continue

            for cat_item in sorted(r_dir.iterdir()):
                if not cat_item.is_dir() or cat_item.name.startswith("."):
                    continue

                if cat_item.name == "active_skills":
                    continue
                category = cat_item.name
                for skill_dir in sorted(cat_item.iterdir()):
                    if not skill_dir.is_dir() or not (skill_dir / "SKILL.md").exists():
                        continue

                    skill_key = f"{category}/{skill_dir.name}"
                    if skill_key in seen_keys:
                        continue
                    seen_keys.add(skill_key)

                    name, description = self.parse_skill_metadata(skill_dir)
                    status = self.get_skill_status_by_name(skill_dir.name, skill_dir)

                    skills.append({
                        "key": skill_key,
                        "category": category,
                        "name": skill_dir.name,
                        "display_name": name,
                        "path": str(skill_dir),
                        "description": description,
                        "active": status["active"],
                        "active_targets": status["active_targets"],
                    })

        return skills

    def get_skill_status_by_name(self, skill_name: str, skill_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Check whether a skill is linked into the shared active_skills directory.
        """
        active_targets = {}
        is_any_active = False

        active_link = self.active_dir / skill_name
        if active_link.is_symlink():
            try:
                is_any_active = not skill_path or active_link.resolve() == skill_path.resolve()
            except OSError:
                is_any_active = False

        # Targets are mirrors, so report whether each has the matching managed
        # symlink, while active remains the state of the shared directory.
        for target_name in self.target_dirs:
            matches = []
            for target_dir in self._target_paths(target_name):
                dest = target_dir / skill_name
                try:
                    matches.append(dest.is_symlink() and dest.resolve() == active_link.resolve())
                except OSError:
                    matches.append(False)
            active_targets[target_name] = is_any_active and all(matches)

        return {
            "active": is_any_active,
            "active_targets": active_targets
        }

    def get_skill_status(self, skill_key: str) -> Dict[str, Any]:
        parts = skill_key.split("/", 1)
        skill_name = parts[1] if len(parts) > 1 else parts[0]
        return self.get_skill_status_by_name(skill_name)

    def _find_skill_path(self, skill_key: str) -> Optional[Path]:
        parts = skill_key.split("/", 1)
        if len(parts) == 2:
            cat, name = parts
            for r_dir in self.repo_dirs:
                p = r_dir / cat / name
                if p.exists() and (p / "SKILL.md").exists():
                    return p
        else:
            name = parts[0]
            for r_dir in self.repo_dirs:
                if not r_dir.exists():
                    continue
                for cat_dir in r_dir.iterdir():
                    if cat_dir.is_dir():
                        p = cat_dir / name
                        if p.exists() and (p / "SKILL.md").exists():
                            return p
        return None

    def activate_skill(
        self, skill_key: str, targets: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Activate a skill in active_skills, then mirror it to every agent.
        """
        skill_path = self._find_skill_path(skill_key)
        if not skill_path:
            return {"success": False, "error": f"Skill '{skill_key}' not found"}

        skill_name = skill_path.name
        # targets is intentionally ignored: every agent mirrors active_skills.
        activated = []
        errors = []
        self.active_dir.mkdir(parents=True, exist_ok=True)
        active_link = self.active_dir / skill_name
        if active_link.is_symlink():
            try:
                if active_link.resolve() != skill_path.resolve():
                    return {
                        "success": False,
                        "error": f"An active skill named '{skill_name}' already points to another category",
                    }
            except OSError:
                pass
            active_link.unlink()
        elif active_link.exists():
            return {"success": False, "error": f"Refused to replace real directory at {active_link}"}
        try:
            active_link.symlink_to(skill_path)
        except OSError as e:
            return {"success": False, "error": f"Failed to activate skill: {e}"}

        activated, errors = self._sync_skill_to_targets(skill_name)

        return {
            "success": len(errors) == 0 or len(activated) > 0,
            "skill": skill_name,
            "activated_targets": activated,
            "errors": errors,
        }

    def deactivate_skill(
        self, skill_key: str, targets: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Deactivate a skill from active_skills and remove its managed mirrors.
        """
        parts = skill_key.split("/", 1)
        skill_name = parts[1] if len(parts) > 1 else parts[0]
        deactivated = []
        errors = []
        active_link = self.active_dir / skill_name
        if active_link.is_symlink():
            try:
                requested_path = self._find_skill_path(skill_key)
                if requested_path and active_link.resolve() != requested_path.resolve():
                    return {
                        "success": False,
                        "error": f"Active skill '{skill_name}' belongs to another category",
                    }
                active_link.unlink()
            except OSError as e:
                errors.append(f"Failed to remove active skill symlink: {e}")
        elif active_link.exists():
            errors.append(f"Refused to remove real directory at {active_link}")

        for tgt in self.target_dirs:
            for target_dir in self._target_paths(tgt):
                dest = target_dir / skill_name
                if dest.is_symlink():
                    try:
                        dest.unlink()
                        deactivated.append(tgt)
                    except OSError as e:
                        errors.append(f"Failed to remove mirror for {tgt}: {e}")
        self._remove_legacy_agy_mirror(skill_name)

        return {
            "success": len(errors) == 0 or len(deactivated) > 0,
            "skill": skill_name,
            "deactivated_targets": deactivated,
            "errors": errors,
        }

    def _sync_skill_to_targets(self, skill_name: str) -> Tuple[List[str], List[str]]:
        """Create or refresh each agent's safe, managed mirror symlink."""
        synced, errors = [], []
        source = self.active_dir / skill_name
        for target_name in self.target_dirs:
            for target_dir in self._target_paths(target_name):
                try:
                    target_dir.mkdir(parents=True, exist_ok=True)
                    dest = target_dir / skill_name
                    if dest.is_symlink():
                        dest.unlink()
                    elif dest.exists():
                        errors.append(f"Real directory exists at {dest} for {target_name}; skipping.")
                        continue
                    dest.symlink_to(source)
                    synced.append(target_name)
                except OSError as e:
                    errors.append(f"Failed to mirror skill for {target_name}: {e}")
        self._remove_legacy_agy_mirror(skill_name)
        return synced, errors

    def _remove_legacy_agy_mirror(self, skill_name: str) -> None:
        """Remove only the old managed Agy links accidentally placed in Claude."""
        legacy_link = self.LEGACY_AGY_DIR / skill_name
        if legacy_link.is_symlink():
            try:
                legacy_link.unlink()
            except OSError:
                return
        try:
            self.LEGACY_AGY_DIR.rmdir()
        except OSError:
            pass  # It is either absent or contains user-owned content.

    def sync_active_skills(self) -> Dict[str, Any]:
        """Bring all agent folders in line with the shared active_skills set."""
        synced, errors = [], []
        if not self.active_dir.exists():
            return {"success": True, "synced": synced, "errors": errors}
        for entry in self.active_dir.iterdir():
            if entry.is_symlink():
                names, sync_errors = self._sync_skill_to_targets(entry.name)
                synced.extend(names)
                errors.extend(sync_errors)
        return {"success": not errors, "synced": synced, "errors": errors}

    def toggle_category(
        self, category: str, active: bool, targets: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Activate or deactivate all skills inside a category.
        """
        all_skills = self.get_all_skills()
        cat_skills = [s for s in all_skills if s["category"] == category]

        results = []
        for s in cat_skills:
            if active:
                res = self.activate_skill(s["key"], targets=targets)
            else:
                res = self.deactivate_skill(s["key"], targets=targets)
            results.append(res)

        return {
            "success": True,
            "category": category,
            "active": active,
            "count": len(cat_skills),
            "results": results,
        }


class AIStorageManager:
    """
    Manages local model weights and agent workspace storage.
    Supports Hugging Face hub, PyTorch checkpoints, Ollama models,
    and agent session caches.
    """

    DEFAULT_HF_HUB = Path.home() / ".cache" / "huggingface" / "hub"
    DEFAULT_TORCH_HUB = Path.home() / ".cache" / "torch" / "hub" / "checkpoints"
    DEFAULT_OLLAMA_DIR = Path.home() / ".ollama" / "models"
    DEFAULT_CLAUDE_PROJECTS = Path.home() / ".claude" / "projects"
    DEFAULT_CURSOR_STORAGE = Path.home() / ".config" / "Cursor" / "User" / "workspaceStorage"
    DEFAULT_GEMINI_BRAIN = Path.home() / ".gemini" / "antigravity" / "brain"

    def __init__(
        self,
        hf_hub_path: Optional[Path] = None,
        torch_path: Optional[Path] = None,
        ollama_path: Optional[Path] = None,
        claude_projects_path: Optional[Path] = None,
        cursor_storage_path: Optional[Path] = None,
        gemini_brain_path: Optional[Path] = None,
    ):
        self.hf_hub = Path(hf_hub_path or self.DEFAULT_HF_HUB)
        self.torch_hub = Path(torch_path or self.DEFAULT_TORCH_HUB)
        self.ollama_dir = Path(ollama_path or self.DEFAULT_OLLAMA_DIR)
        self.claude_projects = Path(claude_projects_path or self.DEFAULT_CLAUDE_PROJECTS)
        self.cursor_storage = Path(cursor_storage_path or self.DEFAULT_CURSOR_STORAGE)
        self.gemini_brain = Path(gemini_brain_path or self.DEFAULT_GEMINI_BRAIN)

    @staticmethod
    def _compute_dir_stats(path: Path) -> Tuple[int, int]:
        total_size = 0
        file_count = 0
        if not path.exists():
            return 0, 0

        if path.is_file():
            try:
                return path.stat().st_size, 1
            except Exception:
                return 0, 0

        stack = [path]
        while stack:
            curr = stack.pop()
            try:
                with os.scandir(curr) as it:
                    for entry in it:
                        try:
                            if entry.is_symlink():
                                file_count += 1
                                continue
                            if entry.is_dir():
                                stack.append(Path(entry.path))
                            else:
                                total_size += entry.stat().st_size
                                file_count += 1
                        except (PermissionError, FileNotFoundError):
                            continue
            except (PermissionError, FileNotFoundError):
                continue
        return total_size, file_count

    def scan_models(self) -> List[Dict[str, Any]]:
        models = []

        # 1. Hugging Face Hub
        if self.hf_hub.exists():
            for item in sorted(self.hf_hub.iterdir()):
                if item.is_dir() and item.name.startswith("models--"):
                    raw_name = item.name[len("models--"):]
                    display_name = raw_name.replace("--", "/")
                    size_bytes, file_count = self._compute_dir_stats(item)
                    try:
                        mtime = item.stat().st_mtime
                    except Exception:
                        mtime = 0

                    models.append({
                        "id": f"hf:{item.name}",
                        "source": "huggingface",
                        "name": display_name,
                        "raw_id": item.name,
                        "path": str(item),
                        "size_bytes": size_bytes,
                        "size_formatted": Database.format_size(size_bytes),
                        "file_count": file_count,
                        "mtime": mtime,
                    })

        # 2. PyTorch Checkpoints
        if self.torch_hub.exists():
            for item in sorted(self.torch_hub.iterdir()):
                if item.is_file() and item.suffix in (".pth", ".pt", ".bin"):
                    size_bytes = item.stat().st_size
                    mtime = item.stat().st_mtime
                    models.append({
                        "id": f"torch:{item.name}",
                        "source": "torch",
                        "name": item.name,
                        "raw_id": item.name,
                        "path": str(item),
                        "size_bytes": size_bytes,
                        "size_formatted": Database.format_size(size_bytes),
                        "file_count": 1,
                        "mtime": mtime,
                    })

        # 3. Ollama Models (API first, fallback to directory)
        ollama_models = self._scan_ollama()
        models.extend(ollama_models)

        return models

    def _scan_ollama(self) -> List[Dict[str, Any]]:
        models = []
        # Try local Ollama daemon API
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags", headers={"User-Agent": "Clinux"})
            with urllib.request.urlopen(req, timeout=0.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for m in data.get("models", []):
                    name = m.get("name", "unknown")
                    size = m.get("size", 0)
                    models.append({
                        "id": f"ollama:{name}",
                        "source": "ollama",
                        "name": name,
                        "raw_id": name,
                        "path": "Ollama Service",
                        "size_bytes": size,
                        "size_formatted": Database.format_size(size),
                        "file_count": 1,
                        "mtime": 0,
                    })
                return models
        except Exception:
            pass

        # Fallback to scanning ~/.ollama/models manifests if exists
        manifest_dir = self.ollama_dir / "manifests"
        if manifest_dir.exists():
            for registry in manifest_dir.iterdir():
                if registry.is_dir():
                    for user_dir in registry.iterdir():
                        if user_dir.is_dir():
                            for model_dir in user_dir.iterdir():
                                if model_dir.is_dir():
                                    for tag_file in model_dir.iterdir():
                                        if tag_file.is_file():
                                            tag = tag_file.name
                                            m_name = f"{user_dir.name}/{model_dir.name}:{tag}"
                                            models.append({
                                                "id": f"ollama:{m_name}",
                                                "source": "ollama",
                                                "name": m_name,
                                                "raw_id": m_name,
                                                "path": str(tag_file),
                                                "size_bytes": 0,
                                                "size_formatted": "Local",
                                                "file_count": 1,
                                                "mtime": tag_file.stat().st_mtime,
                                            })
        return models

    def scan_workspaces(self) -> List[Dict[str, Any]]:
        workspaces = []

        # 1. Claude Code
        if self.claude_projects.exists():
            size_bytes, count = self._compute_dir_stats(self.claude_projects)
            if size_bytes > 0 or count > 0:
                workspaces.append({
                    "id": "claude_projects",
                    "name": "Claude Code Projects & Sessions",
                    "path": str(self.claude_projects),
                    "description": "Conversation histories, terminal logs, and session contexts. Safe to prune.",
                    "size_bytes": size_bytes,
                    "size_formatted": Database.format_size(size_bytes),
                    "file_count": count,
                })

        # 2. Cursor Workspace Storage
        if self.cursor_storage.exists():
            size_bytes, count = self._compute_dir_stats(self.cursor_storage)
            if size_bytes > 0 or count > 0:
                workspaces.append({
                    "id": "cursor_storage",
                    "name": "Cursor Workspace Storage",
                    "path": str(self.cursor_storage),
                    "description": "Local workspace index databases and state snapshots.",
                    "size_bytes": size_bytes,
                    "size_formatted": Database.format_size(size_bytes),
                    "file_count": count,
                })

        # 3. Antigravity Brain
        if self.gemini_brain.exists():
            size_bytes, count = self._compute_dir_stats(self.gemini_brain)
            if size_bytes > 0 or count > 0:
                workspaces.append({
                    "id": "gemini_brain",
                    "name": "Antigravity Session Brain",
                    "path": str(self.gemini_brain),
                    "description": "Historical conversation transcripts, scratchpad files, and generated artifacts.",
                    "size_bytes": size_bytes,
                    "size_formatted": Database.format_size(size_bytes),
                    "file_count": count,
                })

        return workspaces

    def scan_all(self) -> Dict[str, Any]:
        models = self.scan_models()
        workspaces = self.scan_workspaces()

        total_bytes = sum(m["size_bytes"] for m in models) + sum(w["size_bytes"] for w in workspaces)

        return {
            "models": models,
            "workspaces": workspaces,
            "total_size_bytes": total_bytes,
            "total_size_formatted": Database.format_size(total_bytes),
        }

    def delete_model(self, model_id: str) -> Dict[str, Any]:
        """
        Delete a single model checkpoint or folder.
        """
        parts = model_id.split(":", 1)
        if len(parts) != 2:
            return {"success": False, "error": f"Invalid model ID format: {model_id}"}

        source, identifier = parts

        if source in ("hf", "huggingface"):
            target_dir = self.hf_hub / identifier
            if not target_dir.exists() or not target_dir.is_dir():
                return {"success": False, "error": f"Hugging Face model folder not found: {identifier}"}
            if not target_dir.name.startswith("models--"):
                return {"success": False, "error": "Safety check failed: not a valid HF model directory"}

            size_bytes, _ = self._compute_dir_stats(target_dir)
            shutil.rmtree(target_dir)
            return {"success": True, "freed_bytes": size_bytes, "freed_formatted": Database.format_size(size_bytes)}

        elif source == "torch":
            target_file = self.torch_hub / identifier
            if not target_file.exists() or not target_file.is_file():
                return {"success": False, "error": f"PyTorch checkpoint not found: {identifier}"}
            size_bytes = target_file.stat().st_size
            target_file.unlink()
            return {"success": True, "freed_bytes": size_bytes, "freed_formatted": Database.format_size(size_bytes)}

        elif source == "ollama":
            # Call Ollama delete endpoint
            try:
                req = urllib.request.Request(
                    "http://localhost:11434/api/delete",
                    data=json.dumps({"name": identifier}).encode("utf-8"),
                    headers={"Content-Type": "application/json", "User-Agent": "Clinux"},
                    method="DELETE"
                )
                with urllib.request.urlopen(req, timeout=5.0) as resp:
                    if resp.status in (200, 204):
                        return {"success": True, "freed_bytes": 0, "freed_formatted": "Removed from Ollama"}
            except Exception as e:
                return {"success": False, "error": f"Failed to delete via Ollama API: {e}"}

        return {"success": False, "error": f"Unsupported model source: {source}"}

    def clean_workspace(self, workspace_id: str) -> Dict[str, Any]:
        """
        Safely clean an agent workspace directory. Never deletes user configs or credentials.
        """
        target_map = {
            "claude_projects": self.claude_projects,
            "cursor_storage": self.cursor_storage,
            "gemini_brain": self.gemini_brain,
        }

        path = target_map.get(workspace_id)
        if not path or not path.exists():
            return {"success": False, "error": f"Workspace target not found: {workspace_id}"}

        initial_size, initial_count = self._compute_dir_stats(path)

        # Clean contents of path without removing the root directory
        for item in path.iterdir():
            try:
                # Do not delete critical files
                if item.name in (".credentials.json", "settings.json", "auth.json"):
                    continue
                if item.is_dir() and not item.is_symlink():
                    shutil.rmtree(item)
                else:
                    item.unlink()
            except Exception:
                continue

        new_size, new_count = self._compute_dir_stats(path)
        freed_bytes = max(0, initial_size - new_size)
        freed_files = max(0, initial_count - new_count)

        return {
            "success": True,
            "freed_bytes": freed_bytes,
            "freed_formatted": Database.format_size(freed_bytes),
            "freed_files": freed_files,
        }


class AIRuntimeDetector:
    """
    Detects local AI runtimes and daemons.
    """

    KNOWN_PORTS = {
        "ollama": (11434, "Ollama Local Daemon"),
        "llamacpp": (8080, "llama.cpp Server"),
        "vllm": (8000, "vLLM Server"),
        "openwebui": (3000, "Open-WebUI"),
    }

    @classmethod
    def check_port(cls, port: int, host: str = "127.0.0.1") -> bool:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False

    @classmethod
    def get_runtime_status(cls) -> Dict[str, Any]:
        statuses = []
        for service_id, (port, name) in cls.KNOWN_PORTS.items():
            online = cls.check_port(port)
            statuses.append({
                "id": service_id,
                "name": name,
                "port": port,
                "online": online,
            })
        return {"services": statuses}
