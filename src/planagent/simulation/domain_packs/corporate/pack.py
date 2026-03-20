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
        ]

    @property
    def action_library(self) -> list[ActionSpec]:
        return [
            ActionSpec("hire", "Increase team capacity."),
            ActionSpec("optimize_cost", "Reduce infrastructure and operating cost."),
            ActionSpec("ship_feature", "Invest in product delivery."),
            ActionSpec("raise_price", "Protect margins by adjusting pricing."),
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
                },
            ),
        ]


registry.register(CorporateDomainPack())
