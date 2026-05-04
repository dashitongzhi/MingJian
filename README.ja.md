<div align="center">

<img src="frontend/public/mingjian-icon.jpg" width="160" alt="明鉴 Icon">

# 明鉴 (MingJian)

### *明察秋毫、鑑往知来*

**AI駆動マルチエージェントプラットフォーム | 証拠駆動シナリオシミュレーションと戦略的意思決定**

---

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-green.svg)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-15-black.svg)](https://nextjs.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.8-blue.svg)](https://www.typescriptlang.org/)
[![GitHub stars](https://img.shields.io/github/stars/dashitongzhi/MingJian?style=social)](https://github.com/dashitongzhi/MingJian/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/dashitongzhi/MingJian?style=social)](https://github.com/dashitongzhi/MingJian/network/members)

**🌐 言語選択 / Language Selection**

[**🇬🇧 English**](README.md) | [**🇨🇳 中文**](README.zh-CN.md) | [**🇮🇳 हिन्दी**](README.hi.md) | [**🇯🇵 日本語**](README.ja.md)

---

![明鉴 Platform Overview](frontend/public/mingjian-hero.jpg)

</div>

---

## 🌟 なぜ明鉴を選ぶのか？

> **「証拠駆動分析、マルチエージェントディベート、リアルタイムシミュレーションを一つの統合ワークスペースに結合した最初のオープンソースプラットフォーム」**

明鉴は単なるAIツールではありません — 組織が戦略的意思決定を行う方法における**パラダイムシフト**です。10以上のリアルタイムデータソース、対立型マルチエージェントディベート、そして決定論的な意思決定トレースを組み合わせることで、明鉴は従来のAIシステムを悩ませる「ブラックボックス」問題を排除します。

---

## 🎯 現在のインテリジェント分析の問題点

現在のAI分析システム — ChatGPTからエンタープライズコパイロットまで — すべてが同じ根本的な欠陥を持っています：

- ❌ **ハルシネーションを事実として扱う** — LLMは統計情報、出典、結論を実データに基づかずに自信を持ってでっち上げます。真実と虚構の区別がつきません。
- ❌ **単一モデルのブラインドスポット** — 一つのモデル、一つの世界観。相互検証もなく、対立的な挑戦もなく、第二の意見もありません。バイアスは検出されません。
- ❌ **ブラックボックスの推論** — 答えは得られますが、*どのように*？証拠の連鎖も、出典の帰属もなく、ロジックの監査や再現もできません。
- ❌ **古い知識、証拠なし** — モデルは時間的に凍結されたトレーニングデータに依存しています。ニュース、市場、センサーからリアルタイムインテリジェンスを取得できません — *知る*のではなく*推測*しているのです。
- ❌ **自己修正なし** — AIの出力は「発射して忘れる」方式です。エラーは黙って伝播します。レビューループも、品質ゲートも、反復的な精査もありません。
- ❌ **断片化したワークフロー** — データ収集、分析、ディベート、レポート作成が別々のツールで行われます。各引き継ぎのたびにコンテキストが失われます。
- ❌ **再現性ゼロ** — 同じクエリを2回実行すると、異なる答えが返されます。決定論的なトレースも、意思決定ログも、説明責任もありません。

## 💡 明鉴の解決策

明鉴は推測を**証拠**に、意見を**ディベート**に、ブラックボックスを**トレース**に置き換えます：

- ✅ **証拠に基づく** — すべての分析が10以上のソース（Google News、Reddit、GitHub、GDELT、X/Twitterなど）からのリアルタイムデータに基づいて構築されます。ハルシネーションも捏造もありません。
- ✅ **マルチエージェント対立型ディベート** — GPT、Gemini、Claude、Grokは単に同意するだけでなく、お互いに**挑戦**します。ブラインドスポットが露呈し、バイアスに異議が唱えられます。
- ✅ **完全な監査証跡** — すべてのステップが記録されます：参照したソース、行われた議論、意思決定。完全に透明で、完全に再現可能です。
- ✅ **リアルタイムインテリジェンス** — ライブデータの取り込み、ストリーミング分析、即時インサイトの提供。凍結されたトレーニングデータはありません。
- ✅ **自己修復パイプライン** — Jarvisエンジンが自らの出力をレビュー、批評、反復し、品質しきい値に達するまで実行します。エラーはあなたの手に届く前に検出されます。

---

## 🔬 コア機能

### 1. 推測ではなく証拠に基づく

**問題点：** 従来のAIツールは作業過程を示さずに答えを提示します。

**明鉴の解決策：** 明鉴は10以上のデータソースからの**現実世界の証拠**に基づいてすべての決定を裏付けます。すべての主張は追跡可能で、すべての決定は監査可能です。

### 2. マルチエージェントディベートプロトコル

**問題点：** 単一のAIモデルにはブラインドスポットとバイアスがあります。

**明鉴の解決策：** 複数のAIモデル（GPT、Gemini、Claude、Grok）があなたの決定について**ディベート**し、仮定に挑戦し、証拠に基づいた結論に到達します。

### 3. デュアルドメイン専門性

**問題点：** ほとんどのAIツールは汎用的で、特定のドメインを理解していません。

**明鉴の解決策：** 明鉴は**企業向け**（市場分析、競合インテリジェンス）と**軍事向け**（作戦計画、兵站）の両方をドメイン固有のルールとモデルでサポートします。

### 4. 意思決定トレースによる完全な監査可能性

**問題点：** AIがどのように結論に至ったか説明できません。

**明鉴の解決策：** すべてのシミュレーションは**決定論的意思決定トレース**を生成します — AIがどのように結論に至ったかのステップバイステップの記録です。ブラックボックスはありません。

### 5. Jarvis自己修復エンジン

**問題点：** AIの出力は間違っている可能性がありますが、気づいた時には手遅れです。

**明鉴の解決策：** 明鉴は自らの出力をレビューし、弱点を特定し、品質しきい値に達するまで反復します — すべて人間の介入なしで実行されます。

### 6. リアルタイムストリーミング分析

**問題点：** AIの完了を待ってから、ブラックボックスの結果を受け取ります。

**明鉴の解決策：** 分析リクエストを送信すると、AIがリアルタイムで作業する様子を確認できます — ストリーミング進捗イベント、ソースの帰属、中間結果とともにお届けします。

---

## 🆚 明鉴 vs 競合製品

| 機能 | 明鉴 | 従来のAI | シングルエージェント | LangChain |
|---------|------|----------------|--------------|-----------|
| **データソース** | ✅ 10以上のリアルタイム | ❌ 手動入力 | ⚠️ 限定的 | ⚠️ 限定的 |
| **証拠チェーン** | ✅ 完全な追跡可能性 | ❌ 追跡なし | ❌ 追跡なし | ❌ 追跡なし |
| **マルチエージェントディベート** | ✅ 対立型推論 | ❌ 単一モデル | ❌ 単一モデル | ⚠️ 基本的 |
| **意思決定トレース** | ✅ 決定論的 | ❌ ブラックボックス | ❌ ブラックボックス | ❌ ブラックボックス |
| **自己修復** | ✅ Jarvisエンジン | ❌ なし | ❌ なし | ❌ なし |
| **ストリーミング分析** | ✅ リアルタイム | ❌ バッチのみ | ❌ バッチのみ | ⚠️ 限定的 |
| **企業ドメイン** | ✅ 完全サポート | ⚠️ 汎用的 | ❌ 汎用的 | ❌ 汎用的 |
| **軍事ドメイン** | ✅ 完全サポート | ⚠️ 汎用的 | ❌ 汎用的 | ❌ 汎用的 |
| **シナリオ分岐** | ✅ ビームサーチ | ❌ 手動 | ❌ なし | ❌ なし |
| **ナレッジグラフ** | ✅ 埋め込み対応 | ❌ なし | ❌ なし | ❌ なし |
| **オープンソース** | ✅ MITライセンス | ⚠️ 多様 | ⚠️ 多様 | ✅ 多様 |

---

## 🎯 ユースケース

| ユースケース | 説明 | メリット |
|----------|-------------|---------|
| **📊 投資リサーチ** | 市場トレンドの分析、投資仮説のディベート | 高速リサーチ、より良い意思決定 |
| **🏭 企業戦略** | 競合インテリジェンス、シナリオプランニング | データ駆動の意思決定、リスク低減 |
| **⚔️ 軍事計画** | 作戦分析、兵站最適化 | 戦略的優位性、より良い成果 |
| **🛡️ リスク管理** | 多角的なリスク評価 | 不確実性の軽減 |
| **📈 市場分析** | リアルタイム市場インテリジェンス | 高速インサイト、より良いポジショニング |
| **🎯 政策分析** | 多様なステークホルダーへの影響評価 | 十分な情報を得た政策、より良い成果 |

---

## 🚀 クイックスタート

### ワンクリックDockerセットアップ

明鉴をローカルで実行する最も速い方法はDockerセットアップスクリプトです。Dockerの確認、`.env.example`から`.env`の作成、OpenAI APIキーの入力、フルスタックの起動を行います。

#### 前提条件

まず[Docker Desktop](https://www.docker.com/products/docker-desktop/)をインストールしてから、以下を実行してください：

```bash
chmod +x setup.sh
./setup.sh
```

スクリプトが完了したら、以下のURLを開いてください：

| サービス | URL |
|---------|-----|
| フロントエンド | http://localhost:3001 |
| API | http://localhost:8000 |
| MinIOコンソール | http://localhost:9001 |

MinIOログイン：`planagent` / `planagent123`

Dockerスタックを停止するには：

```bash
docker compose -f docker-compose.yml down
```

### 手動開発セットアップ

バックエンドとフロントエンドをマシン上で直接実行して開発したい場合は、このパスを使用してください。

#### 前提条件

開始前に、以下がインストールされていることを確認してください：

| 要件 | バージョン | インストール方法 |
|-------------|---------|--------------|
| **Python** | 3.12+ | [python.org](https://www.python.org/downloads/) |
| **Node.js** | 18+ | [nodejs.org](https://nodejs.org/) |
| **npm** | 9+ | Node.jsに同梱 |
| **Git** | 2.30+ | [git-scm.com](https://git-scm.com/) |
| **PostgreSQL** | 14+（任意） | [postgresql.org](https://www.postgresql.org/download/) |
| **Redis** | 7+（任意） | [redis.io](https://redis.io/download) |

#### システム要件

| コンポーネント | 最小構成 | 推奨構成 |
|-----------|---------|-------------|
| **CPU** | 2コア | 4コア以上 |
| **RAM** | 4 GB | 8 GB以上 |
| **ストレージ** | 10 GB | 50 GB以上 |
| **OS** | macOS、Linux、Windows | macOSまたはLinux |

#### 環境変数

プロジェクトルートに以下の変数を含む`.env`ファイルを作成してください：

```bash
# ═══════════════════════════════════════════════════════════════
# AIモデル設定
# ═══════════════════════════════════════════════════════════════
# 開始するには1つのAPIキーがあれば十分です。
# システムは同じキーをすべての7つのモデルスロット
#（primary、extraction、x_search、report、debate_advocate、
#  debate_challenger、debate_arbitrator）に自動的に使用します。
# 個別にオーバーライドしない限り。

PLANAGENT_OPENAI_API_KEY=your_api_key_here

# 個別のターゲットをオーバーライド（未設定の場合は共通値にフォールバック）
# PLANAGENT_OPENAI_PRIMARY_MODEL=gpt-4.1
# PLANAGENT_OPENAI_PRIMARY_API_KEY=sk-...
# PLANAGENT_OPENAI_EXTRACTION_MODEL=gpt-4.1-mini
# PLANAGENT_OPENAI_DEBATE_ADVOCATE_MODEL=claude-sonnet-4-20250514
# PLANAGENT_OPENAI_DEBATE_CHALLENGER_MODEL=gemini-2.5-flash
# PLANAGENT_OPENAI_DEBATE_ARBITRATOR_MODEL=grok-3

# ═══════════════════════════════════════════════════════════════
# データベース（任意 — ローカル開発ではSQLiteがデフォルト）
# ═══════════════════════════════════════════════════════════════
# PLANAGENT_DATABASE_URL=postgresql+psycopg://planagent:planagent@localhost:5432/planagent

# ═══════════════════════════════════════════════════════════════
# Redis（任意 — 本番環境のイベントバス用）
# ═══════════════════════════════════════════════════════════════
# PLANAGENT_REDIS_URL=redis://localhost:6379/0

# ═══════════════════════════════════════════════════════════════
# MinIOオブジェクトストレージ（任意）
# ═══════════════════════════════════════════════════════════════
# PLANAGENT_MINIO_ENDPOINT=localhost:9000
# PLANAGENT_MINIO_ACCESS_KEY=minioadmin
# PLANAGENT_MINIO_SECRET_KEY=minioadmin

# ═══════════════════════════════════════════════════════════════
# X / Twitter（任意 — ソーシャルインテリジェンス用）
# ═══════════════════════════════════════════════════════════════
# X_BEARER_TOKEN=your_x_bearer_token

# ═══════════════════════════════════════════════════════════════
# フロントエンド
# ═══════════════════════════════════════════════════════════════
NEXT_PUBLIC_API_URL=/api
```

> **💡 重要なポイント：** **1つ**のモデルプロバイダー（例：OpenAI、または任意のOpenAI互換API）にしかアクセスできない場合でも、すべての7つのモデルスロットに使用できます。`PLANAGENT_OPENAI_API_KEY`を設定するだけで、システムが残りを自動的に補完します。開始するために4つの異なるAPIキーは必要ありません。

#### 互換性のあるプロバイダー

すべてのスロットはOpenAI互換の`/chat/completions`エンドポイントを使用します。プロバイダーを自由に組み合わせることができます：

| プロバイダー | ベースURL |
|---|---|
| OpenAI | `https://api.openai.com/v1` |
| **Anthropic (Claude)** | **`https://api.anthropic.com/v1/openai`** |
| DeepSeek | `https://api.deepseek.com/v1` |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` |
| xAI Grok | `https://api.x.ai/v1` |
| Xiaomi MiMo | `https://token-plan-cn.xiaomimimo.com/v1` |
| Zhipu GLM | `https://open.bigmodel.cn/api/paas/v4` |
| MiniMax | `https://api.minimax.chat/v1` |
| 任意の互換プロキシ | あなたのプロキシURL |

> **例：** OpenAIをプライマリ分析に、DeepSeekを抽出に、Claudeをディベートに使用 — すべて1つの設定で。

#### インストール手順

```bash
# 1. リポジトリをクローン
git clone https://github.com/dashitongzhi/MingJian.git
cd planagent

# 2. Python仮想環境を作成・有効化
python -m venv .venv
source .venv/bin/activate  # Windowsの場合: .venv\Scripts\activate

# 3. Pythonの依存関係をインストール
pip install -e ".[dev]"

# 4. フロントエンドの依存関係をインストール
cd frontend
npm install
cd ..

# 5. 環境を設定
cp .env.example .env
# .envファイルをAPIキーと設定で編集

# 6. データベースを初期化（PostgreSQLを使用する場合）
# 'planagent'という名前のデータベースを作成
# マイグレーションを実行
alembic upgrade head

# 7. バックエンドサーバーを起動
uvicorn planagent.main:app --reload --host 0.0.0.0 --port 8000

# 8. フロントエンドを起動（新しいターミナルで）
cd frontend
npm run dev
# http://localhost:3000 を開く
```

---

## 📦 依存関係

### バックエンド依存関係（Python）

| パッケージ | バージョン | 用途 |
|---------|---------|---------|
| **FastAPI** | 0.110+ | 高性能非同期APIフレームワーク |
| **SQLAlchemy** | 2.0+ | データベースORM |
| **Alembic** | 1.16+ | データベースマイグレーション |
| **Pydantic** | 2.11+ | データバリデーション |
| **OpenAI** | 2.28+ | OpenAI APIクライアント |
| **Anthropic** | 0.52+ | Anthropic APIクライアント |
| **Redis** | 6.2+ | イベントバスとキャッシング |
| **pgvector** | 0.3+ | ベクトル類似性検索 |
| **MinIO** | 7.2+ | オブジェクトストレージ |
| **HTTPX** | 0.28+ | 非同期HTTPクライアント |
| **Uvicorn** | 0.35+ | ASGIサーバー |

### フロントエンド依存関係（Node.js）

| パッケージ | バージョン | 用途 |
|---------|---------|---------|
| **Next.js** | 15+ | Reactフレームワーク |
| **React** | 19+ | UIライブラリ |
| **TypeScript** | 5.8+ | 型安全性 |
| **Tailwind CSS** | 4.1+ | ユーティリティファーストCSS |
| **SWR** | 2.3+ | データフェッチング |
| **Recharts** | 2.15+ | チャートライブラリ |
| **Zustand** | 5.0+ | 状態管理 |

### 開発用依存関係

| パッケージ | バージョン | 用途 |
|---------|---------|---------|
| **pytest** | 8.4+ | テストフレームワーク |
| **pytest-asyncio** | 1.1+ | 非同期テストサポート |
| **Ruff** | 0.12+ | Pythonリンター |
| **ESLint** | 9+ | JavaScriptリンター |
| **Prettier** | 3+ | コードフォーマッター |

---

## 🏗️ システムアーキテクチャ

```mermaid
graph TB
    subgraph "User Interface"
        Console[Strategic Console]
        API[FastAPI Control Plane]
    end
    
    subgraph "Core Services"
        Evidence[Evidence Ingestion]
        Simulation[Simulation Engine]
        Debate[Debate Engine]
        Jarvis[Jarvis Integration]
    end
    
    subgraph "Data Sources"
        RSS[RSS Feeds]
        News[Google News]
        Reddit[Reddit]
        GitHub[GitHub]
        X[X/Twitter]
        GDELT[GDELT]
    end
    
    subgraph "Storage"
        PostgreSQL[(PostgreSQL)]
        Redis[(Redis)]
        MinIO[(MinIO)]
    end
    
    Console --> API
    API --> Evidence
    API --> Simulation
    API --> Debate
    API --> Jarvis
    
    Evidence --> RSS
    Evidence --> News
    Evidence --> Reddit
    Evidence --> GitHub
    Evidence --> X
    Evidence --> GDELT
```

---

## 📁 プロジェクト構造

```
planagent/
├── src/planagent/           # Pythonバックエンド
│   ├── api/                 # FastAPIルート
│   ├── core/                # データベース、設定
│   ├── models/              # SQLAlchemyモデル
│   ├── services/            # ビジネスロジック
│   ├── engine/              # シミュレーションエンジン
│   ├── rules/               # YAMLルール
│   └── worker/              # バックグラウンドタスク
├── frontend/                # Next.jsフロントエンド
│   ├── src/app/             # Reactページ
│   ├── src/lib/             # APIクライアント
│   └── public/              # 静的アセット
├── migrations/              # データベースマイグレーション
├── tests/                   # テストファイル
├── docs/                    # ドキュメント
├── examples/                # シナリオ例
├── .env.example/            # 環境テンプレート
├── docker-compose.yml       # Docker設定
├── pyproject.toml           # Pythonプロジェクト設定
└── package.json             # Node.jsプロジェクト設定
```

---

## 🧪 テストの実行

```bash
# すべてのテストを実行
pytest

# カバレッジ付きで実行
pytest --cov=planagent

# 特定のテストを実行
pytest tests/test_debate.py

# 詳細出力で実行
pytest -v

# フロントエンドテストを実行
cd frontend
npm test
```

---

## 📚 ドキュメント

- [📖 完全テクニカルレポート](docs/planagent_full_report.md)
- [🚀 エージェントスタートアッププレイブック](docs/agent_startup_playbook.md)
- [🔧 技術的負債バックログ](TECHNICAL_DEBT_BACKLOG.md)
- [🤝 コントリビューションガイド](CONTRIBUTING.md)
- [📝 変更履歴](CHANGELOG.md)

---

## 🤝 コントリビューション

コントリビューションを歓迎します！[コントリビューションガイド](CONTRIBUTING.md)をご覧ください。

```bash
# 1. リポジトリをフォーク
# 2. 機能ブランチを作成
git checkout -b feature/amazing-feature

# 3. 変更を加える
# 4. テストを実行
pytest

# 5. 変更をコミット
git commit -m "feat: add amazing feature"

# 6. ブランチにプッシュ
git push origin feature/amazing-feature

# 7. プルリクエストを開く
```

---

## 📄 ライセンス

このプロジェクトはMITライセンスの下でライセンスされています - 詳細は[LICENSE](LICENSE)をご覧ください。

---

## 🙏 謝辞

- [FastAPI](https://fastapi.tiangolo.com/) - 高性能非同期API
- [Next.js](https://nextjs.org/) - Reactフレームワーク
- [PostgreSQL](https://www.postgresql.org/) + [pgvector](https://github.com/pgvector/pgvector) - データベース
- [Redis Streams](https://redis.io/docs/data-types/streams/) - イベントストリーミング
- [MinIO](https://min.io/) - オブジェクトストレージ

---

## 📞 お問い合わせ

このプロジェクトに興味をお持ちいただけましたら、コラボレーション、フィードバック、または気軽なお話でも大歓迎です。お気軽にご連絡ください！

- 📧 メール：[cajd6876@gmail.com](mailto:cajd6876@gmail.com) | [2965866908@qq.com](mailto:2965866908@qq.com)
- 🐛 Issues：[GitHub Issues](https://github.com/dashitongzhi/MingJian/issues)
- 💬 ディスカッション：[GitHub Discussions](https://github.com/dashitongzhi/MingJian/discussions)

---

<div align="center">

## 🌟 スター履歴

[![Star History Chart](https://api.star-history.com/svg?repos=dashitongzhi/MingJian&type=Date)](https://star-history.com/#dashitongzhi/MingJian&Date)

---

**明鉴** — *明察秋毫、鑑往知来*

**明鉴** — *See Clearly, Judge Wisely*

---

**Made with ❤️ by the 明鉴 Team**

</div>
