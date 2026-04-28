# Technical Debt Backlog

## 1. 向量搜索的性能瓶颈 (API 层)
- **位置**: `src/planagent/api/routes.py` 中的 `search_knowledge_graph` 路由。
- **现状**: 目前实现相似度搜索的方式是从数据库中取出最多 1000 个节点，然后在 Python 内存中循环计算 `cosine_similarity` 并排序。
- **建议**: 项目依赖中已经引入了 `pgvector`。建议将这部分逻辑下推到数据库层，利用 PostgreSQL 的 `pgvector` 扩展直接进行向量相似度查询（例如 `ORDER BY embedding <=> :query_vector`）。这能极大提升查询性能，并在知识图谱节点数量增多时保证系统的可扩展性。

## 2. 路由模块过于庞大 (API 层)
- **位置**: `src/planagent/api/routes.py`。
- **现状**: 该文件目前充当了一个“上帝对象”（God file），包含了所有域（分析、模拟、知识图谱、Watch Rules、系统监控等）的路由和大量辅助逻辑。同时，使用 `request.app.state` 来挂载并获取 Service（如 `ensure_app_services`）的方式略显原始。
- **建议**: 
  1. 将 `routes.py` 拆分为多个具体的领域路由模块（例如 `routes/analysis.py`, `routes/simulation.py`, `routes/ingest.py`），然后在 `main.py` 中集中 `include_router`。
  2. 更多地利用 FastAPI 原生的依赖注入（`Depends`）系统来注入各个 Service，而不是依赖在 `request.app.state` 上手动挂载，提升类型安全并降低路由与应用状态的耦合。

## 3. 数据库初始化逻辑包含硬编码迁移 (数据库层)
- **位置**: `src/planagent/db.py` 中的 `init_models` 方法。
- **现状**: 代码中存在针对 SQLite 的硬编码 `PRAGMA table_info` 检查以及 `ALTER TABLE` 语句（比如手动添加 `embedding` 等列）。
- **建议**: 项目中已经配置了 `alembic`。应尽量避免在业务代码中执行 `ALTER TABLE`。对于表结构的变更，应完全交给 Alembic 统一管理，以保证开发、测试和生产环境的数据库结构演进具有一致性。

## 4. 查重逻辑的并发与性能问题 (服务层)
- **位置**: `src/planagent/services/pipeline.py` 中的 `_find_duplicate` 方法。
- **现状**: 在数据入库前，每次都会通过 `dedupe_key` 查询一次数据库以判断是否重复。在大批量数据并发抓取时，这会产生大量 `SELECT` 操作，甚至有并发条件下的竞态风险（Race condition）。
- **建议**: 可以在 `RawSourceItem.dedupe_key` 字段上建立数据库级别的 `UNIQUE CONSTRAINT`。入库时直接执行 `INSERT` 并利用 SQLAlchemy 的处理冲突机制（如 PostgreSQL 的 `on_conflict_do_nothing` 或使用 `try/except IntegrityError`）来处理重复冲突，以减少数据库往返开销并保证绝对的原子性。

## 5. 配置文件过于臃肿
- **位置**: `src/planagent/config.py` 中的 `Settings` 类。
- **现状**: 将所有配置（如各类 API Key、Minio 凭证、OpenAI 模型策略、超时策略等）全部平铺在一个模型中，同时包含了大量属性解析逻辑（`@property`）。
- **建议**: 考虑利用 Pydantic V2 的嵌套模型特性（Nested Models），将配置拆分为诸如 `OpenAISettings`、`MinioSettings`、`DatabaseSettings` 等子模型，使配置结构更加清晰和模块化。
