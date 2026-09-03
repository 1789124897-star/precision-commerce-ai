# AI 任务工作台 — 全链路异步任务管线

> 基于 FastAPI + Celery 的全链路异步任务平台，覆盖数据采集、AI 分析、内容生成、多媒体合成等场景。

## 功能链路

```
数据采集 ──▶ 深度分析 ──▶ 策略生成 ──▶ AI 生图
            (多模态 LLM)  (三路并发)    (GPT / Seedream)

文本输入 ──▶ 脚本生成 ──▶ TTS 合成 ──▶ 视频合成
            (LLM 结构化) (edge-tts)  (MoviePy / Seedance)
```

### 各模块详解

| 模块 | 路由 | 功能说明 |
| --- | --- | --- |
| **数据采集** | `POST /api/v1/scraper/scrape` | 输入 URL，自动提取页面上的图片和文本，存入数据库 |
| **深度分析** | `POST /api/v1/analysis/submit` | 对采集到的文本和图片做多模态 AI 分析，输出结构化结论 |
| **策略生成** | `POST /api/v1/analysis/strategies` | 基于分析结果，生成多角度的营销策略，三路并发入库 |
| **AI 生图** | `POST /api/v1/images/generate` | 并发生图：一次提交多个提示词，服务端同时出图，可带参考图 |
| **生图参考图** | `POST /api/v1/images/upload-images` | 将参考图保存到服务器，返回可访问路径（支持多图） |
| **脚本生成** | `POST /api/v1/video/generate-script` | 将文本转为口播脚本，LLM 直接输出 JSON，代码层只做段数对齐 |
| **TTS 合成** | `POST /api/v1/video/generate-tts` | 将脚本文本合成为语音文件，同时输出逐字对齐的字幕文件 |
| **镜头脚本** | `POST /api/v1/video/generate-shot` | 将口播脚本拆分为 Seedance 分镜场景描述 |
| **视频素材上传** | `POST /api/v1/video/upload-images` / `upload-audio` / `upload-srt` | 合成前上传图片 / 音频 / 字幕素材 |
| **视频合成** | `POST /api/v1/video/compose` / `POST /api/v1/video/compose-premium` | 将图片/视频素材 + 音频 + 字幕合成为成品视频 |
| **任务追踪** | `GET /api/v1/tasks` / `GET /api/v1/tasks/{task_id}` | 任务列表（分页/筛选/导出）与单任务进度轮询，完成后返回结果 |

## 架构设计

### 分层架构

```
Route 层 ── Pydantic 参数校验，任务创建 + 下发，立即返回 task_id
  │
Service 层 ── 业务逻辑编排，调用外部 AI 接口，与框架层、数据层解耦
  │
Repository 层 ── 数据访问封装，只暴露必要查询
  │
Model 层 ── SQLAlchemy 2.0 Mapped，Alembic 管理表结构，启动时自动升级
```

### 异步任务管线

所有耗时操作通过 Celery 异步执行，Redis 作为消息代理，任务状态通过 `GET /tasks/{task_id}` 轮询，历史任务通过 `GET /tasks` 分页筛选、`GET /tasks/export` 导出。

**可靠性保障：**

- `task_acks_late=True` — Worker 崩溃任务自动重分派
- `worker_prefetch_multiplier=1` — 公平调度，避免长任务堵队
- 指数退避重试（`retry_backoff=True`，最多 3 次）
- Celery Beat 每 30 分钟扫描 RUNNING 超过 2 小时的任务，自动标记 FAILURE

### 数据库设计

| 表 | 用途 | 设计原因 |
| --- | --- | --- |
| `tasks` | 所有异步任务 | 统一生命周期追踪，`request_json` / `result_json` 双快照 |
| `products` | 采集数据存档 | 每次采集 1 行，`task_id` 唯一关联采集任务，供分析/生图取用素材 |
| `analyses` | 每次分析 1 行 | 输入字段可查询（商品名/价格区间），输出全文存 TEXT |
| `strategies` | 每次分析 3 行 | A/B/C 独立行，`analysis_task_id` 关联回分析任务维持血缘 |
| `videos` | 每次合成 1 行 | 交付物追踪（素材/输出路径/时长/分辨率） |

## 技术栈

```
Python 3.9+ · FastAPI · Celery · Redis · MySQL 8
SQLAlchemy 2.0 (Mapped) · Pydantic v2
DeepSeek / GPT / Kimi / 豆包多模态 · Seedream / GPT 生图 · Seedance 1.5 Pro / 2.0 Mini
edge-tts · MoviePy 2.x · DrissionPage
Docker Compose · Celery Flower · Celery Beat
```

## 快速启动

### 环境变量

| 变量 | 说明 |
|------|------|
| `DEEPSEEK_API_KEY` | 文本分析 / 策略生成 / 脚本生成（DeepSeek） |
| `VOLCANO_API_KEY` | 火山方舟（Seedream 生图 + Seedance 视频 + 豆包多模态） |
| `GPT_API_KEY` | GPT 多模态分析 + 生图（默认生图模型 gpt-image-2） |
| `KIMI_API_KEY` | Kimi 多模态分析 |
| `APIMART_API_KEY` | Seedance 2.0 Mini 视频（中转） |
| `DATABASE_URL` | MySQL 连接串 |
| `REDIS_URL` | Celery broker |
| `IMAGE_MAX_CONCURRENT` | 单任务生图最大并发数（默认 3） |
| `PROXY_PROVIDER` | 爬虫代理源：none / free / brightdata |
| `ALIBABA_1688_EMAIL/PASSWORD` | 1688 账号（Cookie 持久化，应对登录墙） |

```bash
cp .env.example .env          # 填入 API Key
docker-compose up -d          # 一键启动（API + Celery Worker + Beat + Flower + MySQL + Redis）
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
├── tasks/             Celery 任务定义
├── models/            ORM 模型（Task/Product/Analysis/Strategy/Video）
├── schemas/           Pydantic 请求/响应模型
├── core/              基础设施（配置/数据库/Celery/路径/日志）
├── repositories/      数据访问封装
├── config/            爬虫站点配置（YAML）
└── llm/               AI 客户端（DeepSeek / GPT / Kimi / 豆包 / Seedream / Seedance）
static/                前端页面（index.html）
logs/                  三层文件日志 + 控制台（app/error/task）
output/                产物目录（图片/音频/视频）
```
