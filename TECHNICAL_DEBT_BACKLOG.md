# Technical Debt Backlog

## ~~1. 向量搜索的性能瓶颈 (API 层)~~ ✅ 已解决
- **解决方案**: 使用 pgvector 原生向量类型替代 JSON 存储
- **提交**: `2af52b7`, `edd289a`
- **实现**: 新增 `embedding_vector` 列 (vector(64)) + HNSW 索引，使用 `<=>` 余弦距离运算符
- **迁移**: `0021_pgvector_embedding.py`

## ~~2. 路由模块过于庞大 (API 层)~~ ✅ 已解决
- **解决方案**: 已拆分为独立路由模块
- **位置**: `src/planagent/api/routes/` 目录下
- **文件**: admin.py, analysis.py, evidence.py, monitoring.py, prediction.py, providers.py, simulation.py, sources.py

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
