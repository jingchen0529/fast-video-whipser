# Fast Video Whisper

一个面向短视频/电商内容场景的 AI 视频工作平台，后端基于 FastAPI，前端基于 Nuxt 4。项目目前已经不只是一个基础骨架，而是包含视频分析、爆款复刻、爆款创作、动作资产提取、资产库、系统设置、权限认证等完整业务模块。

## 项目主要功能

### 1. 视频工作台

- 支持上传本地视频，或提交 TikTok/视频链接作为任务输入
- 支持三类核心工作流：
  - `analysis`：视频分析
  - `remake`：爆款复刻
  - `create`：爆款创作
- 项目执行状态通过任务时间线持续更新，前端会轮询展示步骤进度

### 2. 视频分析工作流

围绕“对标视频分析”提供完整流程：

- 提取和校验视频链接
- 使用 PySceneDetect 切分镜头
- 提取音频并通过 `faster-whisper` 做转写
- 生成结构化分镜（storyboard）
- 输出视频内容分析结果
- 生成可执行的优化建议

### 3. 爆款复刻工作流

- 分析参考视频的节奏、镜头、卖点结构
- 解析用户的复刻意图
- 自动构造视频生成 Prompt
- 调用视频生成 provider 执行生成
- 轮询第三方生成结果
- 将生成视频回写到项目和资产库

当前系统设置中已经为视频生成预留了多 provider 配置能力，例如豆包、可灵、Veo、万相和自定义兼容服务。

### 4. 爆款创作工作流

- 根据用户 brief 解析创作目标
- 自动生成脚本、镜头结构和推荐口播
- 结合风格参考组织生成素材
- 调用视频生成模型生成初版视频
- 回写生成状态和产出结果

### 5. 动作资产提取

这是项目里比较完整的一条独立能力链：

- 基于已经分析完成的视频结果读取 `shot_segments` 和 `storyboard`
- 先做规则粗筛，再做 AI 精标
- 自动提取动作片段缩略图与片段文件
- 写入 `motion_assets`
- 支持前端动作资产检索、详情查看、审核和批量审核

### 6. 资产库

- 上传视频、图片、音频等媒体资产
- 查看存储使用量
- 预览和下载媒体文件
- 删除单个或批量删除资产
- 查看动作资产列表及来源视频

### 7. 系统设置

系统设置页支持通过界面维护各类模型与运行参数，包括：

- `analysis`：分析模型 provider
- `transcription`：转写模型 provider
- `remake`：视频生成 provider
- `motion_extraction`：动作提取的阈值和模型 provider

大部分 AI 相关配置通过数据库持久化，不要求全部写在 `.env` 中。

### 8. 认证与权限

- 基于用户/角色/菜单的 RBAC 权限体系
- HttpOnly 的 access/refresh cookie
- CSRF 防护
- 登录验证码
- 登录失败限流
- 自动初始化管理员账号、角色和菜单

### 9. API 与静态前端托管

- FastAPI 自动提供 Swagger 文档
- 前端开发态由 Nuxt 提供页面
- 也支持把前端构建到 `static/` 后由 FastAPI 单端口托管

## 技术栈

### 后端

- FastAPI
- SQLAlchemy
- PyMySQL
- Pydantic Settings
- Alembic
- httpx

### 前端

- Nuxt 4
- Vue 3
- Pinia
- shadcn-nuxt / Radix Vue

### 媒体与 AI

- `faster-whisper`
- `PySceneDetect`
- `ffmpeg`
- `ffprobe`

## 项目结构

```text
.
├── app/
│   ├── api/                # 路由层
│   ├── auth/               # 认证、鉴权、RBAC
│   ├── core/               # 应用装配、配置、日志、异常
│   ├── db/                 # 数据库初始化、连接与 session
│   ├── models/             # ORM 模型
│   ├── repositories/       # 数据访问
│   ├── schemas/            # 请求/响应 schema
│   ├── services/           # 业务逻辑
│   └── workflows/          # analysis / remake / create / motion_extraction
├── frontend/               # Nuxt 4 前端
├── static/                 # 前端静态构建产物
├── tests/                  # pytest 测试
├── .env.example            # 环境变量示例
├── main.py                 # 后端启动入口
└── scripts/run.py          # 前后端统一启动脚本
```

## 环境准备

建议先准备好以下依赖：

- Python 3.10 或更高版本
- Node.js 18 或更高版本
- `pnpm`
- MySQL 8.x
- FFmpeg（至少确保 `ffmpeg` 和 `ffprobe` 在 `PATH` 中可用）

说明：

- 项目默认使用 MySQL，启动时会根据 `DATABASE_URL` 自动创建数据库和表结构
- 如果系统里没有 `ffprobe`，通用媒体时长探测会受影响，仅保留 WAV 的有限兜底能力
- 如果系统里没有 `ffmpeg`，动作提取流程中的缩略图和片段生成会被跳过

## 安装依赖

### 1. 创建虚拟环境

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows Git Bash:

```bash
python -m venv .venv
source .venv/Scripts/activate
```

### 2. 安装后端依赖

```bash
pip install -r requirements.txt
```

### 3. 安装前端依赖

```bash
cd frontend
pnpm install
cd ..
```

## 环境变量配置

先复制一份配置文件：

```bash
cp .env.example .env
```

至少建议检查以下配置：

```env
DATABASE_URL=mysql+pymysql://root@127.0.0.1/fast-video-whipser
AUTH_JWT_SECRET=change-me-to-a-random-32-plus-char-secret
AUTH_INITIAL_ADMIN_PASSWORD=ChangeMe123!
HOST=0.0.0.0
PORT=8000
```

其中最重要的是：

- `DATABASE_URL`：后端连接的 MySQL 地址
- `AUTH_JWT_SECRET`：JWT 密钥，生产环境务必改掉默认值
- `AUTH_INITIAL_ADMIN_PASSWORD`：首次启动时初始化管理员密码
- `HOST` / `PORT`：后端监听地址

`.env` 主要负责基础运行和认证配置；分析模型、转写模型、视频生成模型等 provider 配置，建议在系统设置页里维护。

## 启动方式

### 1. 只启动后端

```bash
python3 main.py
```

或者使用带热更新的统一脚本：

```bash
python3 scripts/run.py backend
```

启动后可访问：

- API 文档：`http://127.0.0.1:8000/docs`
- 健康检查：`http://127.0.0.1:8000/api/health`

### 2. 只启动前端

前提是后端已经在 `8000` 端口运行。

```bash
python3 scripts/run.py frontend
```

启动后访问：

- 前端页面：`http://127.0.0.1:3000`

开发态下，前端会把 `/api/*` 请求代理到后端。

### 3. 前后端一起启动（推荐开发方式）

```bash
python3 scripts/run.py dev
```

该模式会同时启动：

- FastAPI：`http://127.0.0.1:8000`
- Nuxt：`http://127.0.0.1:3000`

### 4. 构建前端静态资源

```bash
python3 scripts/run.py build-frontend
```

该命令会在 `frontend/` 下执行 `nuxt generate`，并把构建结果复制到项目根目录的 `static/`。

### 5. 单端口模式启动

如果你希望由 FastAPI 同时托管 API 和前端静态页面，可以使用：

```bash
python3 scripts/run.py combined --build
```

完成后直接访问：

- `http://127.0.0.1:8000`

这个模式下：

- `/api/*` 仍然是后端接口
- 其他前端页面由 `static/` 中的构建产物提供

## 首次启动后建议操作

### 1. 使用初始化管理员登录

默认管理员账号来自 `.env`：

- 用户名：`AUTH_INITIAL_ADMIN_USERNAME`
- 邮箱：`AUTH_INITIAL_ADMIN_EMAIL`
- 密码：`AUTH_INITIAL_ADMIN_PASSWORD`

如果使用前端开发模式，可先打开：

- `http://127.0.0.1:3000/auth/login`

### 2. 进入系统设置补齐模型配置

建议登录后先到设置页检查：

- 分析模型 provider
- 转写模型 provider
- 视频生成 provider
- 动作提取 provider

如果你暂时只是验证登录、权限、资产上传等基础流程，这些 provider 可以后配；但若要真正跑通分析、复刻、创作和动作提取，通常需要先填好对应的 API Key 或本地模型配置。

## 主要页面

- `/auth/login`：登录页
- `/video/workbench`：视频工作台
- `/video/history`：历史任务与详情
- `/motion/extract`：动作提取
- `/assets`：资产库
- `/assets/motions`：动作资产库
- `/settings`：系统设置

## 常用接口

- `GET /api/health`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/projects/upload`
- `GET /api/projects`
- `GET /api/projects/{project_id}`
- `POST /api/assets/upload`
- `GET /api/assets`
- `GET /api/assets/motions`
- `POST /api/assets/motions/extract`
- `GET /api/settings`
- `POST /api/tiktok/info`

## 运行测试

```bash
PYTHONPATH=. pytest
```

## 补充说明

- 后端启动时会自动初始化数据库、默认菜单、默认角色和初始管理员
- `scripts/run.py` 是本项目推荐的统一启动入口，适合开发阶段使用
- `frontend/README.md` 仍然是 Nuxt 默认模板说明，实际项目启动方式请以本 README 为准
