# MingJian Community Development Guide

This directory is the public open-source upstream for MingJian.

```text
/Users/kral/project/mingjian/mingjian
```

## Role

Use this repository as the main development line for the shared product core.

Most daily development should happen here.

## Build Here

Add or fix features here when they improve the core open-source product:

- Multi-agent debate quality
- Evidence collection and weighting
- Source provider stability
- Basic WatchRule monitoring
- Basic report/export features
- Local Docker Compose deployment
- Core API contracts
- Core frontend workflows
- Documentation and examples
- Bug fixes and performance improvements
- Public plugin interfaces

## Do Not Put Here

Do not add commercial-only implementation here unless you intentionally want it
to become part of the open-source Community Edition:

- Billing and subscription logic
- SaaS usage limits and metering
- Cloud organization/workspace product flows
- SSO / SAML / OIDC implementations
- Compliance-grade audit log systems
- Enterprise-only connectors
- Private deployment automation
- SLA/support tooling

## Rule of Thumb

If a feature makes MingJian better for every self-hosted user, build it here.

If a feature exists mainly because someone is paying for hosted operations,
enterprise control, compliance, or deployment support, build it in a commercial
edition instead.

## Sync Direction

Commercial editions should follow this repository, not the other way around.

```text
mingjian -> mingjian-cloud
mingjian -> mingjian-enterprise
```

Avoid copying Cloud or Enterprise implementation back into this repository unless
the feature is meant to become public.
