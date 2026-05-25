from __future__ import annotations

from dataclasses import dataclass
import importlib
import importlib.util
import os
from pathlib import Path
from typing import Any, Callable

import yaml


@dataclass(frozen=True)
class RuleEffect:
    target: str
    op: str
    value: float


@dataclass(frozen=True)
class RuleCondition:
    field: str
    op: str
    value: Any


@dataclass(frozen=True)
class RuleSpec:
    rule_id: str
    domain: str
    action_id: str
    priority: int
    trigger_keywords: tuple[str, ...]
    trigger_conditions: tuple[RuleCondition, ...]
    effects: tuple[RuleEffect, ...]
    explanation_template: str
    handler_id: str | None = None

    def matches(self, statement: str) -> bool:
        lowered = statement.lower()
        return any(keyword.lower() in lowered for keyword in self.trigger_keywords)


RuleHandler = Callable[[dict[str, Any], dict[str, Any]], list[RuleEffect] | list[dict[str, Any]]]
_RULE_HANDLERS: dict[str, RuleHandler] = {}


def rule_handler(rule_id: str) -> Callable[[RuleHandler], RuleHandler]:
    def decorator(func: RuleHandler) -> RuleHandler:
        _RULE_HANDLERS[rule_id] = func
        return func

    return decorator


class RuleRegistry:
    def __init__(self, rules_root: Path) -> None:
        self.rules_root = rules_root
        self._cache: dict[str, list[RuleSpec]] = {}
        self._calibration_weights: dict[str, float] = {}
        self._loaded_python_modules: set[str] = set()

    @property
    def calibration_weights(self) -> dict[str, float]:
        return dict(self._calibration_weights)

    def effective_priority(self, rule: RuleSpec) -> float:
        weight = self._calibration_weights.get(rule.rule_id, 1.0)
        return round(float(rule.priority) * weight, 2)

    def apply_calibration(self, rule_accuracies: dict[str, float]) -> None:
        """Adjust rule weights based on calibration accuracy.

        - Accuracy >= 0.75: boost weight up to 1.3
        - Accuracy <= 0.35: reduce weight down to 0.6
        - Otherwise: drift toward 1.0
        """
        for rule_id, accuracy in rule_accuracies.items():
            accuracy = max(0.0, min(1.0, float(accuracy)))
            current = self._calibration_weights.get(rule_id, 1.0)
            if accuracy >= 0.75:
                target = min(1.3, 1.0 + (accuracy - 0.75) * 2.0)
            elif accuracy <= 0.35:
                target = max(0.6, 1.0 - (0.35 - accuracy) * 2.0)
            else:
                target = 1.0
            self._calibration_weights[rule_id] = round(current * 0.4 + target * 0.6, 4)

    def get_rules(self, domain_id: str) -> list[RuleSpec]:
        if domain_id not in self._cache:
            self._cache[domain_id] = self._load_domain(domain_id)
        return self._cache[domain_id]

    def get_handler(self, rule_id: str) -> RuleHandler | None:
        return _RULE_HANDLERS.get(rule_id)

    def reload(self) -> tuple[list[str], int]:
        self._cache.clear()
        self._calibration_weights.clear()
        self._loaded_python_modules.clear()
        domains: list[str] = []
        total = 0
        if self.rules_root.exists():
            for candidate in sorted(
                path.name for path in self.rules_root.iterdir() if path.is_dir()
            ):
                rules = self.get_rules(candidate)
                if rules:
                    domains.append(candidate)
                    total += len(rules)
        return domains, total

    def _load_domain(self, domain_id: str) -> list[RuleSpec]:
        domain_root = self.rules_root / domain_id
        if not domain_root.exists():
            return []

        self._load_python_handlers(domain_root, domain_id)
        rules: list[RuleSpec] = []
        for yaml_path in sorted(domain_root.rglob("*.yaml")):
            with yaml_path.open("r", encoding="utf-8") as handle:
                payload = yaml.safe_load(handle) or {}
            for raw_rule in payload.get("rules", []):
                rules.append(self._parse_rule(raw_rule))
        rules.sort(key=lambda item: item.priority, reverse=True)
        return rules

    def _parse_rule(self, raw_rule: dict[str, Any]) -> RuleSpec:
        trigger = raw_rule.get("trigger", {})
        conditions = tuple(
            RuleCondition(
                field=str(condition.get("field", "")),
                op=str(condition.get("op", "eq")),
                value=condition.get("value"),
            )
            for condition in trigger.get("conditions", [])
            if isinstance(condition, dict)
        )
        condition_keywords = tuple(
            str(condition.value) for condition in conditions if condition.value is not None
        )
        effects = tuple(
            RuleEffect(
                target=effect["target"],
                op=effect.get("op", "add"),
                value=float(effect["value"]),
            )
            for effect in raw_rule.get("effects", [])
        )
        rule_id = raw_rule["id"]
        action_id = raw_rule.get("action_id") or raw_rule.get("action") or "monitor"
        return RuleSpec(
            rule_id=rule_id,
            domain=raw_rule["domain"],
            action_id=action_id,
            priority=int(raw_rule.get("priority", 50)),
            trigger_keywords=tuple(trigger.get("keywords", ())) + condition_keywords,
            trigger_conditions=conditions,
            effects=effects,
            explanation_template=raw_rule.get(
                "explanation_template",
                "Rule {rule_id} matched the current evidence and selected {action_id}.",
            ),
            handler_id=raw_rule.get("handler") or (rule_id if rule_id in _RULE_HANDLERS else None),
        )

    def _load_python_handlers(self, domain_root: Path, domain_id: str) -> None:
        for python_path in sorted(domain_root.rglob("*.py")):
            module_key = str(python_path.resolve())
            if module_key in self._loaded_python_modules:
                continue
            module_name = f"planagent_dynamic_rules.{domain_id}.{python_path.stem}"
            spec = importlib.util.spec_from_file_location(module_name, python_path)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self._loaded_python_modules.add(module_key)

        for module_name in _configured_rule_modules():
            if module_name in self._loaded_python_modules:
                continue
            importlib.import_module(module_name)
            self._loaded_python_modules.add(module_name)


def _configured_rule_modules() -> list[str]:
    raw = os.getenv("PLANAGENT_RULE_MODULES", "")
    return [item.strip() for item in raw.split(",") if item.strip()]


_rule_registry: RuleRegistry | None = None


def get_rule_registry(rules_root: Path) -> RuleRegistry:
    global _rule_registry
    if _rule_registry is None or _rule_registry.rules_root != rules_root:
        _rule_registry = RuleRegistry(rules_root)
    return _rule_registry
