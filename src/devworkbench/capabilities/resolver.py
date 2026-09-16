"""Capability Resolver enforcing the Mandatory Tool Selection Hierarchy."""

from typing import Dict, List, Optional

from devworkbench.capabilities.model import (
    CapabilityResult,
    CapabilityType,
    ToolPriority,
    ToolProvider,
)
from devworkbench.capabilities.registry import CapabilityRegistry


class CapabilityResolver:
    """Resolves requested capabilities to the highest-priority available tool provider."""

    def __init__(self, registry: Optional[CapabilityRegistry] = None) -> None:
        self.registry = registry or CapabilityRegistry()

    @staticmethod
    def _compute_reason(provider: Optional[ToolProvider], priority: ToolPriority) -> str:
        """Generate human-readable explanation for provider selection."""
        if not provider:
            return "No safe automated provider available locally. Manual review required."
        if priority == ToolPriority.NATIVE:
            cmd = f" ('{provider.real_command}')" if provider.real_command else ""
            return f"Official native {provider.name} tool{cmd} provides the requested capability."
        if priority == ToolPriority.OPENSOURCE:
            cmd = f" ('{provider.real_command}')" if provider.real_command else ""
            return f"Established open-source solution '{provider.name}'{cmd} ({provider.source}) provides the capability."
        if priority == ToolPriority.DEVWORKBENCH:
            return f"DevWorkBench deterministic rules and logic ({provider.name}) active as verified fallback."
        return "Manual review required."

    def resolve(
        self,
        capability: CapabilityType,
        preference: str = "auto",
    ) -> CapabilityResult:
        """Resolve a capability using the strict priority hierarchy or user preference.

        Priority Order:
          1. Native / Official ecosystem tool
          2. Established Open-Source tool / Python library
          3. DevWorkBench deterministic logic
          4. Manual Review
        """
        all_providers = self.registry.get_providers_for_capability(capability)
        pref_lower = (preference or "auto").strip().lower()

        fallback_chain = [f"{p.priority.name}:{p.name}" for p in all_providers]

        if pref_lower == "manual":
            return CapabilityResult(
                capability=capability,
                selected_provider=None,
                priority=ToolPriority.MANUAL,
                status="manual_review",
                all_providers=all_providers,
                fallback_chain=fallback_chain,
                reason="Manual review explicitly configured by user.",
                message="Manual review explicitly configured.",
            )

        # Handle explicit priority preference
        target_priority: Optional[ToolPriority] = None
        if pref_lower == "native":
            target_priority = ToolPriority.NATIVE
        elif pref_lower in ["opensource", "open-source", "oss"]:
            target_priority = ToolPriority.OPENSOURCE
        elif pref_lower in ["devworkbench", "dwb", "internal"]:
            target_priority = ToolPriority.DEVWORKBENCH

        if target_priority is not None:
            matching = [p for p in all_providers if p.priority == target_priority]
            if not matching:
                return CapabilityResult(
                    capability=capability,
                    selected_provider=None,
                    priority=target_priority,
                    status="no_provider",
                    all_providers=all_providers,
                    fallback_chain=fallback_chain,
                    reason=f"No {target_priority.name} provider registered for capability '{capability.value}'.",
                    message=f"No {target_priority.name} provider registered for capability '{capability.value}'.",
                )

            available_match = next((p for p in matching if p.is_available), None)
            if available_match:
                return CapabilityResult(
                    capability=capability,
                    selected_provider=available_match,
                    priority=target_priority,
                    status="available",
                    all_providers=all_providers,
                    fallback_chain=fallback_chain,
                    reason=f"Configured preference for {target_priority.name} provider '{available_match.name}'.",
                )

            # Explicitly requested priority exists but is not locally available
            unavailable_provider = matching[0]
            # Find fallback if available
            fallback = next((p for p in all_providers if p.is_available), None)
            fb_name = f"{fallback.priority.name}:{fallback.name}" if fallback else "MANUAL_REVIEW"
            return CapabilityResult(
                capability=capability,
                selected_provider=None,
                priority=target_priority,
                status="configured_unavailable",
                all_providers=all_providers,
                fallback_chain=fallback_chain,
                fallback_provider=fb_name,
                reason=f"Configured {target_priority.name} provider '{unavailable_provider.name}' is unavailable locally.",
                message=(
                    f"Configured {target_priority.name} provider '{unavailable_provider.name}' is unavailable. "
                    f"{unavailable_provider.install_hint or 'Please install the required tool.'}"
                ),
            )

        # Automatic resolution: Strictly traverse priority 1 -> 2 -> 3 -> 4
        # Never choose lower priority when higher priority is available!
        selected: Optional[ToolProvider] = None
        for provider in all_providers:
            if provider.is_available:
                selected = provider
                break

        if selected is not None:
            # Check if any next fallback exists
            idx = all_providers.index(selected)
            next_fb = next((p for p in all_providers[idx + 1:] if p.is_available), None)
            fb_str = f"{next_fb.priority.name}:{next_fb.name}" if next_fb else None

            return CapabilityResult(
                capability=capability,
                selected_provider=selected,
                priority=selected.priority,
                status="available",
                all_providers=all_providers,
                fallback_chain=fallback_chain,
                fallback_provider=fb_str,
                reason=self._compute_reason(selected, selected.priority),
            )

        # No automated provider available -> Fallback to Priority 4: Manual Review
        return CapabilityResult(
            capability=capability,
            selected_provider=None,
            priority=ToolPriority.MANUAL,
            status="manual_review",
            all_providers=all_providers,
            fallback_chain=fallback_chain,
            reason="No automated provider is available locally. Manual review required.",
            message=f"No automated provider available for '{capability.value}'. Manual review required.",
        )

    def resolve_all(
        self,
        preferences: Optional[Dict[str, str]] = None,
    ) -> Dict[CapabilityType, CapabilityResult]:
        """Resolve all registered capabilities against configuration preferences."""
        prefs = preferences or {}
        results: Dict[CapabilityType, CapabilityResult] = {}

        # Collect unique capabilities
        all_caps = {p.capability for p in self.registry.providers}
        for cap in sorted(all_caps, key=lambda c: c.value):
            pref = prefs.get(cap.value, prefs.get(cap.name.lower(), "auto"))
            results[cap] = self.resolve(cap, preference=pref)

        return results
