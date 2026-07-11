# 精铺 AI 工作台 (Precision Commerce AI)

> 面向电商选品运营的全链路 AI 工具，解决"选品分析 → 差异化策略 → 营销素材生成"的手工低效问题。

## 功能链路

```
1688 采集 ──▶ 深度分析 ──▶ 差异化策略 ──▶ AI 生图
                (多模态 LLM)     (三套策略)      (Seedream 4.5)

商品文案 ──▶ 口播脚本 ──▶ TTS 配音 ──▶ 视频合成
              (透传模式)    (edge-tts)     (MoviePy / Seedance)
```

### 各模块详解

| 模块 | 路由 | 技术实现 |
|------|------|---------|
| **1688 采集** | `POST /scraper/scrape` | DrissionPage 浏览器自动化，DOM 自适应抓取 + 系统代理绕过 |
| **深度分析** | `POST /analysis/submit` | DeepSeek 多模态（商品文本 + 图片 data URL），结构化输出 |
| **差异化策略** | `POST /analysis/strategies` | 三策略异步并发（痛点解决/效率功能/情绪品质），独立入库 |
| **AI 生图** | `POST /images/generate` | 策略驱动 prompt 注入，Seedream 4.5 API，支持参考图 |
| **口播脚本** | `POST /video/generate-script` | LLM JSON mode，声明式 prompt 约束段数，无硬编码兜底 |
| **TTS 配音** | `POST /video/generate-tts` | edge-tts 微软神经语音，逐字时间戳 → 标点切句 SRT |
| **视频合成** | `POST /video/compose` / `POST /video/compose-premium` | 快速模式：MoviePy Ken Burns + 过渡；精品模式：Seedance AI 生成 + 拼接 |
| **任务追踪** | `GET /tasks/{task_id}` | 前后端统一轮询 `poll8000`，Celery 异步结果回调 |

## 架构设计

### 分层架构

```
Route 层 ── Pydantic 参数校验，任务创建 + 下发，立即返回 task_id
  │
Service 层 ── 纯业务逻辑，不碰 HTTP / 数据库
  │
Repository 层 ── 数据访问封装，只暴露必要查询
  │
Model 层 ── SQLAlchemy 2.0 Mapped，Base.metadata.create_all 自动建表
```

### 异步任务管线

所有耗时操作通过 Celery 异步执行，Redis 作为 broker，前端轮询 `GET /tasks/{task_id}` 获取状态。

**五队列优先级隔离：**

| 队列 | 优先级 | 任务 | 设计意图 |
|------|--------|------|---------|
| `video` | 9 | 脚本生成、TTS | 流水线关键路径，优先保障 |
| `ai` | 7 | 分析、策略、生图 | IO 密集（API 调用），高并发安全 |
| `scraper` | 5 | 1688 爬取 | 浏览器自动化，内存大户 |
| `compose` | 3 | 视频合成 | CPU 密集（MoviePy），压低防饥饿 |
| `default` | 1 | 僵尸任务清理 | 后台维护，最低优先级 |

**可靠性保障：**

- `task_acks_late=True` — Worker 崩溃任务自动重分派
- `worker_prefetch_multiplier=1` — 公平调度，避免长任务堵队
- 指数退避重试（`retry_backoff=True`，最多 3 次）
- Celery Beat 每 30 分钟扫描 RUNNING 超过 2 小时的任务，自动标记 FAILURE

### 数据库设计

| 表 | 记录数 | 设计原因 |
|---|--------|---------|
| `tasks` | 所有异步任务 | 统一生命周期追踪，`result_json` 做任务快照 |
| `products` | 爬取商品 | `product_id` 索引，串联分析 & 视频的关联关系 |
| `analyses` | 每次分析 1 行 | 输入字段可查询（品类/价格），输出全文存 TEXT |
| `strategies` | 每次分析 3 行 | A/B/C 独立行，`analysis_task_id` FK 维持血缘 |
| `videos` | 每次合成 1 行 | 交付物追踪（素材/输出路径/时长/分辨率） |

## 技术栈

```
Python 3.9+ · FastAPI · Celery · Redis · MySQL 8
SQLAlchemy 2.0 (Mapped) · Pydantic v2
DeepSeek API · Seedream 4.5 · Seedance 1.5 Pro
edge-tts · MoviePy 2.x · DrissionPage
Docker Compose · Celery Flower · Celery Beat
```

## 快速启动

### 环境变量

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | 文本分析 / 脚本生成 |
| `ARK_API_KEY` | 火山方舟（Seedream + Seedance） |
| `DATABASE_URL` | MySQL 连接串 |
| `REDIS_URL` | Celery broker |

```bash
cp .env.example .env          # 填入 API Key
docker-compose up -d          # 一键启动六个服务
```

服务端口：
- `:8000` — 前端界面 + API
- `:8000/docs` — Swagger 接口文档
- `:5555` — Flower 任务监控面板

## 项目结构

```
app/
├── api/routes/        thin route, only validate + dispatch
├── services/          business logic (analysis, images, script, tts, video)
├── tasks/             Celery task definitions (5-queue routing)
├── models/            ORM (Task, Product, Analysis, Strategy, Video)
├── schemas/           Pydantic request/response models
├── core/              infrastructure (config, db, celery, paths, logging)
├── repositories/      data access layer
└── workers/           celery app entry point
static/                vanilla JS frontend (index.html)
output/                generated assets (images, audio, videos)
```
