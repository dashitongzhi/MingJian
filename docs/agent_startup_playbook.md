# AI Agent Startup Playbook

This playbook turns the 明鉴 startup scenario into an operating plan for the first 12 months of an enterprise-focused agent company.

## Positioning

The default recommendation is not to build a general "agent platform." Build a workflow product that owns one painful, high-frequency, high-accountability job inside an existing system of record.

Good wedge characteristics:

- the buyer already has budget
- the workflow has repeatable structure
- success can be measured in hours saved, cycle time reduced, or error rate reduced
- the team can prove reliability with narrow guardrails

## 12-month roadmap

### Months 1-2: Choose the wedge

- Pick one workflow and one buyer, not a category.
- Interview 15-20 operators and map the current workflow end to end.
- Define the "must complete" outcome, the system integrations, and the human escalation path.
- Refuse broad platform work until one wedge has a measurable before/after story.

Exit gate:

- one workflow
- one buyer persona
- one measurable KPI set

### Months 3-4: Land design partners

- Close 3-5 design partners in the same vertical or adjacent operational environment.
- Ship the minimum workflow loop with audit logs, fallback behavior, and explicit escalation.
- Track accuracy, task completion rate, manual override rate, and time-to-value from day one.

Exit gate:

- 3 live design partners
- first credible ROI story
- <20 percent of tasks require manual salvage

### Months 5-6: Convert pilots to paid deployments

- Narrow scope instead of broadening features.
- Convert the best design partner into a paid production account.
- Prioritize security review, deployment reliability, and integration depth over new surface area.
- Package the offer around outcomes, not "autonomous agents."

Exit gate:

- 1-2 paid accounts
- repeatable deployment checklist
- first renewal or expansion signal

### Months 7-9: Build the moat in operations

- Turn incidents, failure cases, and overrides into product feedback loops.
- Add workflow-specific evaluation datasets, routing logic, and reviewer tooling.
- Prove that the system gets safer and cheaper to operate over time.
- Start a narrow outbound motion into accounts that resemble the existing wins.

Exit gate:

- stable weekly reliability metrics
- second and third repeatable paid use case inside the same wedge
- references that speak to deployment quality, not just novelty

### Months 10-12: Expand carefully

- Expand within the account before expanding across categories.
- Hire only when the work is repeatable and the deployment playbook is stable.
- Separate "innovation work" from "production-hardening work."
- Publish case studies that show time saved, cycle-time improvement, or revenue protected.

Exit gate:

- meaningful renewal rate
- net revenue expansion inside the first cohort
- less founder dependence in onboarding and support

## GTM model

Recommended motion:

- wedge-specific outbound to operators and their functional leaders
- founder-led sales until the first repeatable deployment pattern exists
- proof-heavy case studies and ROI calculators instead of generic thought leadership

Recommended packaging:

- pilot fee with explicit production-success criteria
- production pricing tied to completed work, active seats in the workflow, or protected volume
- paid implementation for messy integrations when needed

Do not lead with:

- generic agent orchestration
- "we work for every team"
- benchmark numbers without workflow context

## Metrics that matter

Track these every month:

- time to first successful deployment
- task completion rate without manual salvage
- manual override rate
- median resolution or cycle-time reduction
- renewal and expansion rate
- deployment gross margin
- runway after delivery headcount is fully loaded

## How to use this with 明鉴

1. Load `examples/agent_startup/evidence_ingest.json`.
2. Run the baseline, upside, and downside simulation payloads.
3. Compare the resulting recommendations and matched rules.
4. Use the gaps between scenarios to decide whether the next quarter should focus on wedge, reliability, or sales motion.
