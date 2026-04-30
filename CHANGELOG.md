# Changelog

All notable changes to 明鉴 (MingJian) will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Investment analysis example scenario
- Military logistics example scenario
- "Why Choose 明鉴" section in README
- Roadmap and Technical Highlights sections
- Mermaid architecture diagram
- MIT License
- Contributing guide

## [0.5.0] - 2026-04-30

### Added
- Jarvis integration with self-review, cross-review, repair, and arbitrator cycles
- Debate protocol with advocate, challenger, and arbitrator roles
- Strategic console with daily brief, saved sessions, and streaming discussion
- Scenario search with beam-search branch generation
- Startup KPI scorecard for enterprise-agent scenarios
- Preset API for isolated founder lab environments
- Source health monitoring and snapshot management

### Changed
- Improved pagination with `{items, total, limit, offset}` response format
- Nested OpenAI configuration for better multi-target routing
- Extracted simulation branching logic into dedicated module

### Fixed
- InMemoryEventBus test compatibility
- Dead code removal and circular import resolution

## [0.4.0] - 2026-03-25

### Added
- Military baseline simulation with scenario branching
- Geo-asset snapshots and external-shock records
- Unified workbench aggregation endpoint
- Report generation for company and military scenarios
- Conflict-aware review worker for automated claim resolution

### Changed
- Improved event bus with dead-letter queue support
- Enhanced source adapters with X/Twitter integration

## [0.3.0] - 2026-03-01

### Added
- Corporate simulation with decision trace generation
- Scenario branching with baseline fork metadata
- KPI comparison output for scenario analysis
- Replay package export for simulation results

### Changed
- Improved SQLAlchemy models for better query performance
- Enhanced YAML-based rule loading with reload support

## [0.2.0] - 2026-02-01

### Added
- Evidence ingestion pipeline with multiple source adapters
- Claim extraction with AI-powered and heuristic fallbacks
- Review queue for human-in-the-loop validation
- Knowledge graph with embedding-backed search
- Streaming analysis endpoint with progress events

### Changed
- Improved OpenAI integration with Responses API support
- Enhanced configuration with per-target model routing

## [0.1.0] - 2026-01-15

### Added
- Initial FastAPI control plane with core endpoints
- SQLAlchemy models for evidence chain and simulation artifacts
- Event bus abstraction with in-memory and Redis Streams backends
- Alembic migration for Phase 1 schema
- Basic health check and status endpoints

[Unreleased]: https://github.com/dashitongzhi/MingJian/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/dashitongzhi/MingJian/compare/v0.4.0...v0.5.0
[0.4.0]: https://github.com/dashitongzhi/MingJian/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/dashitongzhi/MingJian/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/dashitongzhi/MingJian/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/dashitongzhi/MingJian/releases/tag/v0.1.0