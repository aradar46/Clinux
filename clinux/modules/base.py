"""
Base module contract and registry for Clinux modules.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from clinux.capabilities import capabilities


class BaseModule(ABC):
    id: str = "base"
    name: str = "Base Module"
    description: str = "Base module template"

    def available(self) -> bool:
        """Check if module is available on the current system."""
        return True

    @abstractmethod
    def scan(self, **kwargs) -> Dict[str, Any]:
        """Perform read-only system scan and return structured data."""
        pass

    def actions(self) -> List[Dict[str, Any]]:
        """Return list of supported actions with metadata."""
        return []

    def run_action(self, action_name: str, **kwargs) -> Dict[str, Any]:
        """Execute a specific module action."""
        raise NotImplementedError(f"Action '{action_name}' is not implemented for module '{self.id}'.")


class ModuleRegistry:
    def __init__(self):
        self._modules: Dict[str, BaseModule] = {}

    def register(self, module: BaseModule) -> None:
        self._modules[module.id] = module

    def get(self, module_id: str) -> Optional[BaseModule]:
        return self._modules.get(module_id)

    def list_all(self) -> List[BaseModule]:
        return list(self._modules.values())

    def list_available(self) -> List[BaseModule]:
        return [m for m in self._modules.values() if m.available()]


registry = ModuleRegistry()
