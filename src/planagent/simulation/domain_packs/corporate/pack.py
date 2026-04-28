from __future__ import annotations

from planagent.simulation.domain_packs import DomainPack, registry
from planagent.simulation.specs import ActionSpec, ActorTemplate, EntityTypeSpec, EventTypeSpec, StateFieldSpec


class CorporateDomainPack(DomainPack):
    @property
    def domain_id(self) -> str:
        return "corporate"

    @property
    def entity_types(self) -> list[EntityTypeSpec]:
        return [
            EntityTypeSpec("company", "Company or startup in the monitored ecosystem."),
            EntityTypeSpec("supplier", "Critical infrastructure or supply-chain provider."),
        ]

    @property
    def state_fields(self) -> list[StateFieldSpec]:
        return [
            StateFieldSpec("cash", "Available operating cash.", 100.0),
            StateFieldSpec("runway_weeks", "Estimated runway in weeks.", 52),
            StateFieldSpec("infra_cost_index", "Infrastructure cost pressure index.", 1.0),
            StateFieldSpec("delivery_velocity", "Normalized delivery velocity.", 1.0),
            StateFieldSpec("brand_index", "Brand and market trust index.", 1.0),
            StateFieldSpec("market_share", "Estimated market share.", 0.05),
            StateFieldSpec("team_morale", "Team morale index.", 1.0),
            StateFieldSpec("pipeline", "Qualified revenue pipeline coverage index.", 1.0),
            StateFieldSpec("active_deployments", "Current count-adjusted implementation load.", 3.0),
            StateFieldSpec("implementation_capacity", "Deployment and onboarding capacity.", 3.0),
            StateFieldSpec("support_load", "Customer support and incident load.", 0.35),
            StateFieldSpec("reliability_debt", "Accumulated reliability and quality debt.", 0.28),
            StateFieldSpec("gross_margin", "Normalized gross margin ratio.", 0.62),
            StateFieldSpec("nrr", "Net revenue retention index.", 1.02),
            StateFieldSpec("churn_risk", "Renewal and logo churn risk.", 0.12),
        ]

    @property
    def action_library(self) -> list[ActionSpec]:
        return [
            ActionSpec("hire", "Increase team capacity."),
            ActionSpec("optimize_cost", "Reduce infrastructure and operating cost."),
            ActionSpec("ship_feature", "Invest in product delivery."),
            ActionSpec("raise_price", "Protect margins by adjusting pricing."),
            ActionSpec("focus_vertical", "Narrow into a defensible vertical wedge."),
            ActionSpec("tighten_scope", "Reduce deployment scope to land faster."),
            ActionSpec("improve_reliability", "Trade speed for trust and product stability."),
            ActionSpec("monitor", "Hold position while collecting more evidence."),
        ]

    @property
    def event_types(self) -> list[EventTypeSpec]:
        return [
            EventTypeSpec("market_price_change", "Market or supplier price moved materially."),
            EventTypeSpec("competitor_launch", "A competitor launched a notable product."),
        ]

    @property
    def actor_templates(self) -> list[ActorTemplate]:
        return [
            ActorTemplate(
                "ai_model_provider",
                {
                    "cash": 120.0,
                    "runway_weeks": 52,
                    "infra_cost_index": 1.0,
                    "delivery_velocity": 1.0,
                    "brand_index": 1.0,
                    "market_share": 0.08,
                    "team_morale": 1.0,
                    "pipeline": 1.05,
                    "active_deployments": 5.0,
                    "implementation_capacity": 4.5,
                    "support_load": 0.42,
                    "reliability_debt": 0.3,
                    "gross_margin": 0.58,
                    "nrr": 1.03,
                    "churn_risk": 0.11,
                },
            ),
            ActorTemplate(
                "developer_tools_saas",
                {
                    "cash": 60.0,
                    "runway_weeks": 78,
                    "infra_cost_index": 0.9,
                    "delivery_velocity": 1.1,
                    "brand_index": 0.95,
                    "market_share": 0.04,
                    "team_morale": 1.05,
                    "pipeline": 0.92,
                    "active_deployments": 3.0,
                    "implementation_capacity": 3.2,
                    "support_load": 0.33,
                    "reliability_debt": 0.24,
                    "gross_margin": 0.74,
                    "nrr": 1.01,
                    "churn_risk": 0.1,
                },
            ),
        ]


registry.register(CorporateDomainPack())
