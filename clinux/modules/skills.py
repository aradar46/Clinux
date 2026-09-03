"""
Skills module for Clinux.
Wraps SkillManager and AIRuntimeDetector.
"""

from typing import Any, Dict, List
from clinux.modules.base import BaseModule
from targz_manager.ai_manager import SkillManager, AIRuntimeDetector


class SkillsModule(BaseModule):
    id = "skills"
    name = "Skills"
    description = "AI Agent skill toggler across Claude Code, Antigravity, and Codex."

    def __init__(self):
        self.sm = SkillManager()
        self.detector = AIRuntimeDetector()

    def scan(self, **kwargs) -> Dict[str, Any]:
        skills = self.sm.get_all_skills()
        categories = self.sm.get_categories()
        runtimes = self.detector.detect_runtimes()
        return {
            "skills": skills,
            "categories": categories,
            "runtimes": runtimes,
            "total_skills": len(skills),
        }

    def actions(self) -> List[Dict[str, Any]]:
        return [
            {"id": "activate", "description": "Activate skill or category"},
            {"id": "deactivate", "description": "Deactivate skill or category"},
        ]

    def run_action(self, action_name: str, **kwargs) -> Dict[str, Any]:
        target = kwargs.get("target")
        is_category = kwargs.get("is_category", False)
        agent_targets = kwargs.get("agent_targets")

        if action_name == "activate":
            if is_category:
                return self.sm.toggle_category(target, active=True, targets=agent_targets)
            return self.sm.activate_skill(target, targets=agent_targets)
        elif action_name == "deactivate":
            if is_category:
                return self.sm.toggle_category(target, active=False, targets=agent_targets)
            return self.sm.deactivate_skill(target, targets=agent_targets)

        raise NotImplementedError(f"Action '{action_name}' is not supported.")
