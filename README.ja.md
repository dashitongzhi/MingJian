<div align="center">

<br />

# 明鉴 MingJian

### *明察秋毫、鑑往知来*

**証拠に基づく意思決定、マルチエージェント討論、シナリオシミュレーション、監査可能な推薦のためのオープンソース戦略インテリジェンス・コックピット。**

---

[![Edition](https://img.shields.io/badge/Edition-Community%20OSS-1f6f5b.svg)](#エディション境界)
[![License](https://img.shields.io/badge/License-Apache%202.0-2f6f9f.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.12%2B-2b6cb0.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-0f766e.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-3b82f6.svg)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-frontend-7c3aed.svg)](https://vite.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.8%2B-2563eb.svg)](https://www.typescriptlang.org/)

**Language / 言語**

[English](README.md) · [中文](README.zh-CN.md) · [हिन्दी](README.hi.md) · [日本語](README.ja.md)

<br />

| Signal | MingJian が提供するもの |
| --- | --- |
| Evidence first | すべての推薦が収集ソース、抽出された主張、再生可能なトレースに接続されます。 |
| Debate, not monologue | 専門ロールのエージェントが、回答前に前提を検証します。 |
| Local sovereignty | Community はローカルで実行でき、オープンソースコード、ローカルデータ管理、24時間監視ウィンドウを備えます。 |
| Decision memory | セッション、推薦バージョン、更新、ソース健全性、ユーザー結果を一続きに保持します。 |

</div>

---

## Product Read

MingJian は、不確実性の中で重要な判断を下す人のために作られています。創業者、アナリスト、運用担当者、研究者、戦略チーム、そして「信じるだけの答え」ではなく検証可能な証拠を必要とするチーム向けです。

体験はチャットボックスというより、戦略インテリジェンス・コックピットです。ユーザーが意思決定支援リクエストを出すと、MingJian は証拠収集、分析、シミュレーション、討論評議会、最初の推薦を実行し、その後のソース変化や推薦バージョンも記録します。

---

## エディション境界

| Edition | Distribution | Core Workflow | Commercial Layer |
| --- | --- | --- | --- |
| **Community** | Apache 2.0 self-hosted upstream | 24時間ローカル監視を含む完全な公共意思決定ワークフロー | None |
| **Cloud** | Hosted SaaS subscription | Community 公共コアのスーパーセット | Subscription, metering, tenant operations |
| **Enterprise** | Private / on-prem deployment | Community 公共コアのスーパーセット | License, audit, governance, private connectors |

このリポジトリは **Community** edition です。Cloud subscription surfaces、Enterprise-only governance code、proprietary mobile entry point は、明示的に公開する決定がない限り追加しません。

---

## Decision Workflow

```text
Question
  -> source discovery
  -> evidence extraction
  -> analysis and simulation
  -> role-based debate
  -> recommendation
  -> version timeline
  -> scheduled / source-change refresh
  -> decision record and outcome feedback
```

| Stage | Purpose | User-visible proof |
| --- | --- | --- |
| Gather | ニュース、コード、ソーシャル、公開データから多元的な証拠を集める。 | Source list, cursor health, last checked time. |
| Reason | 証拠を論点、リスク、シミュレーション、構造化された主張へ変換する。 | Analysis artifacts, report sections, debate rounds. |
| Debate | ロール別エージェントが批評、修正、仲裁する。 | Advocate, challenger, arbiter traces. |
| Remember | セッション、推薦バージョン、更新トリガー、結果を永続化する。 | Timeline, recommendation history, feedback records. |

---

## What Makes It Different

| Old AI Analysis | MingJian |
| --- | --- |
| One answer, little context. | Evidence chain, debate trail, recommendation versions. |
| Single-model blind spots. | Support, challenge, arbitration roles による multi-agent critique. |
| Static responses. | Scheduled refresh と source-change updates. |
| Hard to audit. | Deterministic traces, source attribution, decision records. |
| Generic workflow. | Strategy, risk, market, policy, technical, social, security perspectives. |

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

### 7. 9エージェント意思決定カウンシル

**問題点：** 単一のAIモデルには盲点とバイアスがあります。

**明鉴の解決策：** 明鑑は**9つの専門AIエージェント**を配備します — 各エージェントが独自の役割、視点、モデルを持ち、意思決定カウンシルを形成します：

| 役割 | エージェント | 機能 |
|------|------------|------|
| 🟢 **戦略的支持者** | コア | 賛成の論証、支持証拠の発見 |
| 🔴 **リスクチャレンジャー** | コア | 反対の論証、反証の発見 |
| ⚖️ **主任仲裁者** | コア | 証拠に基づく最終裁定 |
| 🔍 **インテリジェンスアナリスト** | パースペクティブ | 証拠品質の評価 |
| 🌍 **地政学エキスパート** | パースペクティブ | 地政学的分析 |
| 💰 **経済アナリスト** | パースペクティブ | 経済/市場分析 |
| ⚔️ **軍事戦略家** | パースペクティブ | 軍事/安全保障分析 |
| 🔮 **テクノロジー予測者** | パースペクティブ | 技術トレンド分析 |
| 👥 **社会影響評価者** | パースペクティブ | 社会/世論分析 |

---

## 🆚 明鉴 vs 競合製品

| 機能 | 明鉴 | Manus | 従来のAI | シングルエージェント | LangChain |
|------|------|-------|----------|-------------------|-----------|
| **データソース** | ✅ 10以上のリアルタイム | ⚠️ 汎用検索 | ❌ 手動入力 | ⚠️ 限定的 | ⚠️ 限定的 |
| **証拠チェーン** | ✅ 完全な追跡可能性 | ❌ 追跡なし | ❌ 追跡なし | ❌ 追跡なし | ❌ 追跡なし |
| **マルチエージェントディベート** | ✅ 9エージェント対立型 | ⚠️ オーケストレータ+サブエージェント | ❌ 単一モデル | ❌ 単一モデル | ⚠️ 基本的 |
| **意思決定トレース** | ✅ 決定論的 | ❌ ブラックボックス | ❌ ブラックボックス | ❌ ブラックボックス | ❌ ブラックボックス |
| **自己修復** | ✅ Jarvisエンジン | ⚠️ 動的再計画 | ❌ なし | ❌ なし | ❌ なし |
| **ストリーミング分析** | ✅ リアルタイム | ✅ リアルタイム | ❌ バッチのみ | ❌ バッチのみ | ⚠️ 限定的 |
| **継続監視** | ✅ WatchRule+自動更新 | ❌ ワンショットタスク | ❌ なし | ❌ なし | ❌ なし |
| **企業ドメイン** | ✅ 完全サポート | ❌ 汎用的 | ⚠️ 汎用的 | ❌ 汎用的 | ❌ 汎用的 |
| **軍事ドメイン** | ✅ 完全サポート | ❌ 汎用的 | ⚠️ 汎用的 | ❌ 汎用的 | ❌ 汎用的 |
| **シナリオ分岐** | ✅ ビームサーチ | ❌ なし | ❌ 手動 | ❌ なし | ❌ なし |
| **ナレッジグラフ** | ✅ 埋め込み対応 | ❌ なし | ❌ なし | ❌ なし | ❌ なし |
| **コード実行** | ⚠️ 計画中 | ✅ フルサンドボックスVM | ❌ なし | ⚠️ 限定的 | ❌ なし |
| **データ主権** | ✅ セルフホスト | ❌ クラウドのみ | ⚠️ 多様 | ⚠️ 多様 | ✅ セルフホスト |
| **オープンソース** | ✅ Apache 2.0 | ❌ クローズドソース | ⚠️ 多様 | ⚠️ 多様 | ✅ 多様 |

---

## 🧭 明鉴 のポジショニング：AI 意思決定参謀

> **汎用ツールではなく、専属の参謀チーム。**

AI Agent の時代が到来した。オーケストレーションレイヤーが複数のサブAgentとツールを調整し、サンドボックス環境で複雑なタスクを自律的に完了する — これは実証済みのパラダイムである。

明鑑はこの基盤の上にさらに進み、**意思決定インテリジェンス**に特化する：

### 設計理念

 設計原則 | 明鉴 の実践 |
---------|------------|
 オーケストレーション > ベースモデル | 9エージェント登録センター、役割別モデル配分 |
 リアルタイムストリーミングが信頼を構築 | ディベートをラウンドごとにレンダリング、ユーザーが全ステップを確認 |
 マルチツール協調 | 12データソース + ディベートエンジン + シミュレーションエンジン |
 失敗時の動的再計画 | ディベート失敗時に自動戦略調整 |

### 中核的な差別化

 次元 | 明鉴 |
------|------|
 **目標** | より良い意思決定を行う |
 **推論方式** | 9エージェントが独立論証、相互質問、仲裁裁定 |
 **エビデンス基盤** | 12データソース構造化収集 → エビデンス抽出 → ナレッジグラフ |
 **継続性** | WatchRule 持続監視 + 定期更新 + 突発イベント検知 |
 **ドメイン深度** | 企業/軍事デュアルドメインシミュレーション、KPI追跡、シナリオ分岐 |
 **透明性** | 推論過程の表示 + ユーザーの投票・質問 |
 **データ主権** | セルフホスト、データは完全にローカル |
 **コスト** | 独自モデル、限界コストはほぼゼロ |

### MoE アーキテクチャ思想

明鉴 の9エージェントシステムは **Mixture of Experts (MoE)** の中核思想から着想を得ている：

```
ユーザーの質問 → ルーター（ディベートフロー）→ エキスパート組み合わせ選択 → 独立推論 → 重み付き裁定
```

DeepSeek-V3が256エキスパートの中から少数のみを活性化させるように、明鑑は9エージェントの中から質問タイプに応じて最適な組み合わせを選択する。コア3役割（支持者/挑戦者/仲裁者）は常に活性化、パースペクティブ6役割は必要に応じて参加 — これがソフトウェアレイヤーでのスパース活性化である。

---

## 🎯 ユースケース

 ユースケース | 説明 | メリット |
----------|-------------|---------|
 **📊 投資リサーチ** | 市場トレンドの分析、投資仮説のディベート | 高速リサーチ、より良い意思決定 |
 **🏭 企業戦略** | 競合インテリジェンス、シナリオプランニング | データ駆動の意思決定、リスク低減 |
 **⚔️ 軍事計画** | 作戦分析、兵站最適化 | 戦略的優位性、より良い成果 |
 **🛡️ リスク管理** | 多角的なリスク評価 | 不確実性の軽減 |
 **📈 市場分析** | リアルタイム市場インテリジェンス | 高速インサイト、より良いポジショニング |
 **🎯 政策分析** | 多様なステークホルダーへの影響評価 | 十分な情報を得た政策、より良い成果 |

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

 サービス | URL |
---------|-----|
 フロントエンド | http://localhost:3001 |
 API | http://localhost:8000 |
 MinIOコンソール | http://localhost:9001 |

MinIOログイン：`.env` の `PLANAGENT_MINIO_ACCESS_KEY` / `PLANAGENT_MINIO_SECRET_KEY` を使用してください。

Dockerスタックを停止するには：

```bash
docker compose -f docker-compose.yml down
```

### 手動開発セットアップ

バックエンドとフロントエンドをマシン上で直接実行して開発したい場合は、このパスを使用してください。

#### 前提条件

開始前に、以下がインストールされていることを確認してください：

 要件 | バージョン | インストール方法 |
-------------|---------|--------------|
 **Python** | 3.12+ | [python.org](https://www.python.org/downloads/) |
 **Node.js** | 18+ | [nodejs.org](https://nodejs.org/) |
 **npm** | 9+ | Node.jsに同梱 |
 **Git** | 2.30+ | [git-scm.com](https://git-scm.com/) |
 **PostgreSQL** | 14+（任意） | [postgresql.org](https://www.postgresql.org/download/) |
 **Redis** | 7+（任意） | [redis.io](https://redis.io/download) |

#### システム要件

 コンポーネント | 最小構成 | 推奨構成 |
-----------|---------|-------------|
 **CPU** | 2コア | 4コア以上 |
 **RAM** | 4 GB | 8 GB以上 |
 **ストレージ** | 10 GB | 50 GB以上 |
 **OS** | macOS、Linux、Windows | macOSまたはLinux |

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
# 先にAPIキーを設定し、接続テストで利用可能なモデルを取得してから、
# 必要な場合だけ返されたモデルIDを貼り付けます。
# PLANAGENT_OPENAI_PRIMARY_MODEL=
# PLANAGENT_OPENAI_PRIMARY_API_KEY=sk-...
# PLANAGENT_OPENAI_EXTRACTION_MODEL=
# PLANAGENT_OPENAI_DEBATE_ADVOCATE_MODEL=
# PLANAGENT_OPENAI_DEBATE_CHALLENGER_MODEL=
# PLANAGENT_OPENAI_DEBATE_ARBITRATOR_MODEL=

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

 プロバイダー | ベースURL |
---|---|
 OpenAI | `https://api.openai.com/v1` |
 **Anthropic (Claude)** | **`https://api.anthropic.com/v1/openai`** |
 DeepSeek | `https://api.deepseek.com/v1` |
 Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` |
 xAI Grok | `https://api.x.ai/v1` |
 Xiaomi MiMo | `https://token-plan-cn.xiaomimimo.com/v1` |
 Zhipu GLM | `https://open.bigmodel.cn/api/paas/v4` |
 MiniMax | `https://api.minimax.chat/v1` |
 任意の互換プロキシ | あなたのプロキシURL |

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
cd frontend-v2
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
cd frontend-v2
npm run dev
# http://localhost:3000 を開く
```

---

## 📦 依存関係

### バックエンド依存関係（Python）

 パッケージ | バージョン | 用途 |
---------|---------|---------|
 **FastAPI** | 0.110+ | 高性能非同期APIフレームワーク |
 **SQLAlchemy** | 2.0+ | データベースORM |
 **Alembic** | 1.16+ | データベースマイグレーション |
 **Pydantic** | 2.11+ | データバリデーション |
 **OpenAI** | 2.28+ | OpenAI APIクライアント |
 **Anthropic** | 0.52+ | Anthropic APIクライアント |
 **Redis** | 6.2+ | イベントバスとキャッシング |
 **pgvector** | 0.3+ | ベクトル類似性検索 |
 **MinIO** | 7.2+ | オブジェクトストレージ |
 **HTTPX** | 0.28+ | 非同期HTTPクライアント |
 **Uvicorn** | 0.35+ | ASGIサーバー |

### フロントエンド依存関係（Node.js）

 パッケージ | バージョン | 用途 |
---------|---------|---------|
 **Vite** | 8+ | フロントエンドビルドツール |
 **React** | 19+ | UIライブラリ |
 **TypeScript** | 6.0+ | 型安全性 |
 **Tailwind CSS** | 4.2+ | ユーティリティファーストCSS |
 **React Router** | 7+ | クライアントサイドルーティング |
 **Recharts** | 3.8+ | チャートライブラリ |

### 開発用依存関係

パッケージ | バージョン | 用途
---------|---------|------
**pytest** | 8.4+ | テストフレームワーク
**pytest-asyncio** | 1.1+ | 非同期テストサポート
**Vitest** | 3.2+ | フロントエンドテストフレームワーク
**Ruff** | 0.12+ | Pythonリンター
**ESLint** | 9+ | JavaScriptリンター
**Prettier** | 3+ | コードフォーマッター

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

**バックエンド — モジュラーパッケージ構造**

```
src/planagent/
├── config/              # config.py (527行) → 4ファイルに分割
│   ├── __init__.py
│   ├── base.py
│   ├── openai.py
│   └── main.py
├── debate/              # debate.py (3273行) → 7モジュールに分割
│   ├── prompts.py
│   ├── rounds.py
│   ├── llm.py
│   ├── adjudication.py
│   ├── revisions.py
│   └── triggers.py
├── simulation/          # simulation.py (2281行) → 6モジュールに分割
│   ├── engine.py
│   ├── scenarios.py
│   ├── impact.py
│   ├── report.py
│   └── domain_packs.py
├── db.py                # Alembic専用に整理済み
├── api/                 # FastAPIルート
├── models/              # SQLAlchemyモデル
├── services/            # ビジネスロジック
├── rules/               # YAMLルール
└── worker/              # バックグラウンドタスク
```

**フロントエンド — サブコンポーネント構造**

```
frontend-v2/src/
├── components/
│   ├── layout/          # アプリシェル、サイドバー、ナビゲーション
│   └── ui/              # 共通コックピットサーフェスと状態コンポーネント
├── pages/               # ダッシュボード、アシスタント、監視、レポート、設定
├── api/                 # APIエンドポイントヘルパー
├── hooks/               # テーマとアプリレベルのReact hooks
└── main.tsx             # Viteエントリーポイント
```

---

## 🧪 テストの実行

```bash
# バックエンドテスト (92ユニットテスト, 0.26秒)
pytest

# カバレッジ付きで実行
pytest --cov=planagent

# 特定のテストを実行
pytest tests/test_debate.py

# 詳細出力で実行
pytest -v
```

```bash
# フロントエンドビルド
cd frontend-v2
npm run build
```

### ストレステスト結果

- ✅ **112件パス、0件失敗**
- 👥 20人の同時ユーザー
- ⚡ 844 RPS（秒間リクエスト数）
- ⏱️ P50 = 1ms

---

## 📊 品質とパフォーマンス

 指標 | 値
------|----
 バックエンドテスト | 92
 フロントエンドテスト | 16
 ストレステスト合格率 | 112/114 (98.2%)
 同時接続 (20ユーザー) | 844 RPS、500エラーなし
 P50 | 1ms
 P95 | 11ms
 最大バックエンドファイル | ~900行 (旧3273行)
 最大フロントエンドページ | ~550行 (旧1665行)

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

このプロジェクトはApache License 2.0の下でライセンスされています - 詳細は[LICENSE](LICENSE)をご覧ください。

---

## 🙏 謝辞

- [FastAPI](https://fastapi.tiangolo.com/) - 高性能非同期API
- [Vite](https://vite.dev/) - フロントエンドビルドツール
- [PostgreSQL](https://www.postgresql.org/) + [pgvector](https://github.com/pgvector/pgvector) - データベース
- [Redis Streams](https://redis.io/docs/data-types/streams/) - イベントストリーミング
- [MinIO](https://min.io/) - オブジェクトストレージ
- [Linux.do](https://linux.do) - オープンソースコミュニティの支援と交流

---

## 📞 お問い合わせ

このプロジェクトに興味をお持ちいただけましたら、コラボレーション、フィードバック、または気軽なお話でも大歓迎です。お気軽にご連絡ください！

- 📧 メール：[cajd6876@gmail.com](mailto:cajd6876@gmail.com) | [2965866908@qq.com](mailto:2965866908@qq.com)
- 🐛 Issues：[GitHub Issues](https://github.com/dashitongzhi/MingJian/issues)
- 💬 ディスカッション：[GitHub Discussions](https://github.com/dashitongzhi/MingJian/discussions)

---

<div align="center">

## 🌟 Star History

[![Star History Chart](https://api.star-history.com/svg?repos=dashitongzhi/MingJian&type=Date)](https://star-history.com/#dashitongzhi/MingJian&Date)

---

**明鉴** — *明察秋毫、鑑往知来*

**明鉴** — *See Clearly, Judge Wisely*

---

**Made with ❤️ by the 明鉴 Team**

</div>
