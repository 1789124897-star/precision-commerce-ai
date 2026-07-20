# AI 任务工作台 — 多队列异步任务管线实践

> 基于 FastAPI + Celery 的全链路异步任务平台，覆盖数据采集、AI 分析、内容生成、多媒体合成等场景。

## 功能链路

```
数据采集 ──▶ 深度分析 ──▶ 策略生成 ──▶ AI 生图
            (多模态 LLM)  (三路并发)    (Seedream 4.5)

文本输入 ──▶ 脚本生成 ──▶ TTS 合成 ──▶ 视频合成
            (透传模式)    (edge-tts)   (MoviePy / Seedance)
```

### 各模块详解

| 模块 | 路由 | 功能说明 |
|------|------|---------|
| **数据采集** | `POST /scraper/scrape`                     | 输入 URL，自动提取页面上的图片和文本，存入数据库               |
| **深度分析** | `POST /analysis/submit`                    | 对采集到的文本和图片做多模态 AI 分析，输出结构化结论           |
| **策略生成** | `POST /analysis/strategies`                | 基于分析结果，生成多角度的营销策略，三路并发入库               |
| **AI 生图** | `POST /images/generate`                     | 将策略文案转化为图片生成指令，调用 Seedream 4.5 出图           |
| **脚本生成** | `POST /video/generate-script`              | 将文本转为口播脚本，LLM 结构化输出，不做代码层修补             |
| **TTS 合成** | `POST /video/generate-tts`                 | 将脚本文本合成为语音文件，同时输出逐字对齐的字幕文件           |
| **视频合成** | `POST /video/compose` / `POST /video/compose-premium` | 将图片/视频素材 + 音频 + 字幕合成为成品视频         |
| **任务追踪** | `GET /tasks/{task_id}`                     | 前端轮询查询异步任务进度，任务完成后自动返回结果               |

## 架构设计

### 分层架构

```
Route 层 ── Pydantic 参数校验，任务创建 + 下发，立即返回 task_id
  │
Service 层 ── 业务逻辑编排，调用外部 AI 接口，与框架层、数据层解耦
  │
Repository 层 ── 数据访问封装，只暴露必要查询
  │
Model 层 ── SQLAlchemy 2.0 Mapped，Base.metadata.create_all 自动建表
```

### 异步任务管线

所有耗时操作通过 Celery 异步执行，Redis 作为消息代理，任务状态通过 `GET /tasks/{task_id}` 统一查询。

**五队列优先级隔离：**

| 队列 | 优先级 | 任务 | 设计意图 |
|------|--------|------|---------|
| `video` | 9 | 脚本生成、TTS | 流水线关键路径，优先保障 |
| `ai` | 7 | 分析、策略、生图 | IO 密集（API 调用），高并发安全 |
| `scraper` | 5 | 数据采集 | 浏览器自动化，内存大户 |
| `compose` | 3 | 视频合成 | CPU 密集（MoviePy），压低防饥饿 |
| `default` | 1 | 僵尸任务清理 | 后台维护，最低优先级 |

**可靠性保障：**

- `task_acks_late=True` — Worker 崩溃任务自动重分派
- `worker_prefetch_multiplier=1` — 公平调度，避免长任务堵队
- 指数退避重试（`retry_backoff=True`，最多 3 次）
- Celery Beat 每 30 分钟扫描 RUNNING 超过 2 小时的任务，自动标记 FAILURE

### 数据库设计

| 表 | 用途 | 设计原因 |
|---|--------|---------|
| `tasks` | 所有异步任务 | 统一生命周期追踪，`result_json` 做任务快照 |
| `products` | 采集数据 | `product_id` 索引，串联分析 & 视频的关联关系 |
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
docker-compose up -d          # 一键启动（API + Celery Workers × 4 + MySQL + Redis）
```

服务端口：
- `:8000` — 前端界面 + API
- `:8000/docs` — Swagger 接口文档
- `:5555` — Flower 任务监控面板

## 项目结构

```
app/
├── api/routes/        路由层（参数校验 + 任务下发）
├── services/          业务逻辑（分析/生图/脚本/TTS/视频）
├── tasks/             Celery 任务定义（五队列路由）
├── models/            ORM 模型（Task/Product/Analysis/Strategy/Video）
├── schemas/           Pydantic 请求/响应模型
├── core/              基础设施（配置/数据库/Celery/路径/日志）
├── repositories/      数据访问封装
└── tasks/             Celery 任务定义（五队列路由）
static/                前端页面（index.html）
logs/                  四层分离日志（app/error/task）
output/                产物目录（图片/音频/视频）
```
