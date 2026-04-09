# 视频分析任务流完整性检查 & 视频复刻方向建议

## 一、系统架构总览

```
┌──────────────┐     ┌──────────────┐     ┌──────────────────────────┐
│   Frontend   │────▶│   API Layer  │────▶│     Service Layer         │
│   (Nuxt 3)   │     │   (FastAPI)  │     │                          │
└──────────────┘     └──────────────┘     │  ProjectService          │
                                          │  ConversationService     │
                                          │  JobService              │
                                          │  VideoAnalysisService    │
                                          │  AnalysisAIService       │
                                          │  AssetService            │
                                          │  SystemSettingsService   │
                                          └──────────────────────────┘
                                                     │
                                          ┌──────────▼──────────┐
                                          │   SQLite (app.db)    │
                                          │ projects             │
                                          │ project_task_steps   │
                                          │ conversations        │
                                          │ conversation_messages│
                                          │ media_assets         │
                                          │ motion_assets        │
                                          │ shot_segments        │
                                          │ storyboards          │
                                          │ storyboard_items     │
                                          │ jobs                 │
                                          └─────────────────────┘
```

---

## 二、当前存在的两套视频分析流

### 流程 A：`ProjectService` 主线（完整 9 步分析工作流）

**入口**: `POST /api/projects/upload` → `ProjectService.create_project()` → BackgroundTasks 调用 `run_project_workflow()`

**9 步工作流**:

| # | step_key | 标题 | 实际实现 | 状态 |
|---|---------|------|---------|------|
| 1 | `extract_video_link` | 提取视频链接 | ✅ 从 URL/上传素材中提取 | 完整 |
| 2 | `validate_video_link` | 验证视频链接 | ✅ 校验协议+平台, TikTok 调 crawler 获取详情 | 完整 |
| 3 | `segment_video_shots` | 切分镜头片段 | ⚠️ 本地上传走 PySceneDetect (需 ffmpeg), URL 走 fallback 生成合成段 | 半完整 |
| 4 | `analyze_video_content` | 分析视频内容 | ⚠️ 实际生成 visual_features 是规则推断（分辨率/镜头密度等），非真正视觉分析 | 有 fallback |
| 5 | `identify_audio_content` | 识别音频内容 | ✅ 支持 faster-whisper (本地) + OpenAI Whisper API 两种引擎 | 完整 |
| 6 | `generate_storyboard` | 生成分镜结构 | ✅ AI 生成 (豆包/OpenAI 等) + fallback 结构化分镜 | 完整 |
| 7 | `generate_response` | 生成分析回复 | ✅ AI 生成电商分析 + fallback 模板 | 完整 |
| 8 | `generate_suggestions` | 生成优化建议 | ✅ AI 生成 5 条优化建议 + fallback | 完整 |
| 9 | `finish` | 全部完成 | ✅ 更新状态为 succeeded | 完整 |

### 流程 B：`ConversationService` → `VideoAnalysisService`（旧版/轻量分析）

**入口**: `POST /api/conversations/{id}/messages` → `message_type=video_analysis_request` → `JobService.create_job_from_message()` → `VideoAnalysisService.run_analysis_job()`

**特点**:
- 直接在请求线程中同步执行（非 BackgroundTasks）
- 使用 **硬编码的 mock 数据**（`_build_mock_result()`），返回固定 3 个候选片段
- 会创建 `motion_assets` 记录
- 会写入会话消息（`job_status` + `video_analysis_result`）

---

## 三、闭环检查结论

### ✅ 已闭环的部分

| 链路 | 起点 | 终点 | 闭环？ |
|------|------|------|--------|
| 项目创建 → 分析完成 | `POST /projects/upload` | project.status=`succeeded` | ✅ |
| 步骤进度追踪 | project_task_steps 初始化 | 逐步更新 status | ✅ |
| 会话消息流 | 创建 conversation + user message | 各步骤写 assistant message | ✅ |
| 资产上传 | `POST /assets/upload` | media_assets 入库 | ✅ |
| 动作资产创建 | VideoAnalysisService.run_analysis_job() | motion_assets 入库 | ✅ |
| 镜头切分持久化 | segment_video_shots 步骤 | shot_segments 表 | ✅ |
| 分镜持久化 | generate_storyboard 步骤 | storyboards + storyboard_items 表 | ✅ |
| 追问对话 | `POST /projects/{id}/messages` | AI 生成回复写入 conversation | ✅ |
| 错误处理 | 任意步骤异常 | 记录 error → 更新 project status=`failed` + 写入 workflow_error 消息 | ✅ |
| TikTok 爬虫 | URL 输入 → 解析 aweme_id → 拉取视频信息/下载链接 | ✅ |

### ⚠️ 未闭环 / 存在断点的部分

#### 1. **`video_remake` 和 `motion_extraction` 任务类型已注册但无实现**
- `JobService.MESSAGE_TYPE_TO_JOB_TYPE` 注册了 `video_remake_request → video_remake` 和 `motion_extract_request → motion_extraction`
- `ConversationService.JOB_MESSAGE_TYPES` 包含这两种消息类型
- **但** `create_message_and_dispatch()` 中只有 `video_analysis` 有执行逻辑（L185-186），其他类型的 job 创建后会永远停在 `queued` 状态
- `ProjectService.SUPPORTED_WORKFLOWS` 只包含 `{"analysis"}`，其他 workflow_type 会直接失败

#### 2. **VideoAnalysisService（流程 B）使用硬编码 mock 数据**
- `_build_mock_result()` 返回固定的 3 个片段，没有真正的视频分析逻辑
- 这套流程没有走 PySceneDetect、没有音频转写、没有 AI 生成
- 它只是一个 placeholder，不算真正的分析

#### 3. **视频下载未完成**
- TikTok crawler 可以获取 `download_url`，但 `_step_validate_video_link()` 中的视频下载代码会将文件下载到本地、创建 media_asset
- **对于非 TikTok 平台**（抖音等），crawler 目录 `crawlers/douyin/` 是空的
- 平台检测支持 tiktok/douyin/youtube/instagram/generic，但 **只有 tiktok 有 crawler 实现**

#### 4. **PySceneDetect 镜头切分仅限本地文件**
- 如果视频是 URL 来源且下载失败/跳过，`segment_video_shots` 会走 fallback 生成合成镜头段，质量不够
- 镜头切分的真正价值依赖真实视频文件

#### 5. **motion_assets 未与 ProjectService 工作流打通**
- ProjectService 的 9 步分析流不会创建 motion_assets
- 只有旧的 VideoAnalysisService（mock 数据）会创建 motion_assets
- 这意味着 **通过 projects/upload 走完整分析后，动作资产库是空的**

#### 6. **前端消息类型的显示逻辑不确定**
- 后端写入了 `workflow_status`, `analysis_reply`, `suggestion_reply`, `workflow_error`, `storyboard_result` 等多种 message_type
- 前端是否都有对应的渲染组件，需要检查前端代码

---

## 四、数据流完整性图谱

```
用户操作                     后端流转                           数据落地
─────────────────────────────────────────────────────────────────────────

POST /projects/upload ──────▶ create_project()
  │                          │ 创建 conversation              → conversations 表
  │                          │ 创建 project                   → projects 表
  │                          │ 初始化 task_steps               → project_task_steps 表
  │                          │ 写入 user/assistant 消息        → conversation_messages 表
  │                          └─▶ BackgroundTasks:
  │                              run_project_workflow()
  │
  │   Step 1: extract_video_link ──▶ 提取 URL/确认上传          → 更新 projects (source_url 等)
  │   Step 2: validate_video_link ─▶ TikTok crawler 获取信息    → 下载视频 → media_assets 表
  │   Step 3: segment_video_shots ─▶ PySceneDetect 切分        → shot_segments 表
  │   Step 4: analyze_video_content▶ 提取视觉特征              → 更新 projects (source_analysis)
  │   Step 5: identify_audio ──────▶ Whisper 转写              → 更新 projects (timeline_segments)
  │                                                             → shot_segments (transcript_text)
  │   Step 6: generate_storyboard ─▶ AI 生成分镜               → storyboards + storyboard_items 表
  │   Step 7: generate_response ───▶ AI 电商分析               → 更新 projects (ecommerce_analysis)
  │                                                             → conversation_messages 表
  │   Step 8: generate_suggestions ▶ AI 优化建议               → conversation_messages 表
  │   Step 9: finish ──────────────▶ 标记 succeeded             → projects.status = 'succeeded'
  │
  │
GET /projects/{id} ─────────▶ get_project_detail()
  │                          │ 查 projects                     
  │                          │ 查 shot_segments                
  │                          │ 查 storyboards + items          
  │                          │ 查 project_task_steps            
  │                          │ 查 conversation_messages         
  │                          └─▶ 完整详情返回前端
  │
POST /projects/{id}/messages▶ add_followup_message()
                              │ 写 user message                → conversation_messages 表
                              │ 调 AnalysisAIService 生成回复
                              └ 写 assistant message           → conversation_messages 表


⚠️ 断裂点: motion_assets 表未被 ProjectService 写入
⚠️ 断裂点: video_remake / motion_extraction 任务创建后无执行器
```

---

## 五、视频复刻方向建议

### 当前状态盘点

根据代码和 `short_drama_motion_asset_plan.md` 规划文档，当前系统处于：

- **Phase 1 已部分完成**: 分析工作流基本跑通，shot_segments + storyboard 已持久化
- **Phase 2 已部分完成**: motion_assets 表已建，CRUD API 已有，但未与主工作流打通
- **Phase 3 未开始**: 视频复刻 (video_remake) 只有空壳定义
- **Phase 4 未开始**: 内容生产系统

### 推荐的下一步实施路线

#### 第一步（建议立即做）：补齐分析到动作资产的闭环

**为什么先做这个**: 目前 ProjectService 分析完成后，分析结果（shot_segments, storyboard）与 motion_assets 是断开的。这是整个复刻链路的基础缺口。

具体任务:
1. 在 `_step_finish()` 或新增一个 `extract_motion_assets` 步骤中，基于 shot_segments + storyboard_items 自动创建 motion_assets
2. 让分析结果中的高置信度片段自动成为 `motion_asset` 候选
3. 在前端展示动作资产候选卡片（已有 `GET /assets/motions` API）

#### 第二步：接入真正的视频内容理解

当前分析步骤中 `analyze_video_content` 只做了规则推断（分辨率、镜头密度）。要支持复刻，需要：

1. **关键帧提取**: 在 `segment_video_shots` 步骤中，从每个 shot_segment 中提取关键帧图片，保存为 media_assets
2. **多模态视觉理解**: 用 GPT-4o / Gemini / 豆包的视觉能力，对关键帧做描述生成（人物外观、场景、构图、光线等）
3. **动作语义标注**: 基于连续多帧或视频片段，让模型输出结构化标签（action_label, emotion_label, temperament_label 等）

#### 第三步：实现视频复刻工作流

**workflow_type = "remake" 的完整链路**:

```
┌──────────────────────────────────────────────────────┐
│                 Video Remake Workflow                  │
├──────────────────────────────────────────────────────┤
│                                                       │
│  1. select_source_asset                              │
│     → 用户选择要复刻的动作资产 (motion_asset)          │
│                                                       │
│  2. define_remake_intent                              │
│     → 确认保留什么(动作/节奏/镜头) & 改写什么          │
│       (人物/场景/风格/色调)                            │
│                                                       │
│  3. build_remake_prompt                               │
│     → 从 motion_asset 的标签 + 用户指令               │
│     → 构造视频生成 prompt                             │
│     → 包含: 动作描述 + 镜头语言 + 目标风格            │
│                                                       │
│  4. generate_video                                    │
│     → 调用视频生成 API (如: 可灵/Runway/Pika/Sora)    │
│     → 传入参考帧 + prompt + motion reference          │
│                                                       │
│  5. evaluate_copyright_distance                       │
│     → 对生成结果做版权距离评估                        │
│     → 输出 copyright_risk_level (low/medium/high)     │
│                                                       │
│  6. save_result                                       │
│     → 保存生成视频为 media_asset                      │
│     → 创建 asset_lineage 派生记录                     │
│     → 写入会话消息展示结果                            │
│                                                       │
└──────────────────────────────────────────────────────┘
```

**关键技术选型建议**:

| 环节 | 推荐方案 | 备注 |
|-----|---------|-----|
| 视频生成 | 可灵 (Kling) / Runway Gen-3 / Pika | 国内首推可灵，海外推 Runway |
| 动作参考 | 先支持 image-to-video + motion reference | 方案 A: 受控变换 |
| 版权评估 | CLIP 向量余弦相似度 + 规则打分 | MVP 阶段够用 |
| 动作保留 | 关键帧序列 + 骨骼姿态提取 (MediaPipe/OpenPose) | 中期方案 B |

#### 第四步：补齐其他平台的爬虫

| 平台 | 当前状态 | 优先级 |
|------|---------|-------|
| TikTok | ✅ 已实现 | - |
| 抖音 | ❌ 目录空 | 高（国内用户核心需求） |
| YouTube | ❌ 无实现 | 中 |
| Instagram | ❌ 无实现 | 低 |

### 架构建议

1. **统一工作流引擎**: 当前 `ProjectService.run_project_workflow()` 是硬编码的步骤序列。建议抽象出一个 `WorkflowEngine`，支持 analysis/remake/create 三种 workflow_type 各自注册步骤链
2. **异步任务队列**: 当前用 `BackgroundTasks`，对于视频生成这种长时间任务（可能 1-5 分钟），建议引入 Celery / ARQ / 或至少一个持久化的 job executor
3. **去掉旧版 VideoAnalysisService**: 流程 B 是 mock 数据的遗留代码，建议废弃，统一走 ProjectService
4. **video_generation 字段**: projects 表已经预留了 `video_generation_json` 字段，结构中已包含 provider/model/prompt/result_video_url 等，说明复刻的数据模型骨架已经有了

---

## 六、总结

### 分析工作流（Analysis）: 85% 完整

**已完成**: 链接提取 → 视频获取 → 镜头切分 → 音频转写 → 分镜生成 → AI 分析 → 优化建议 → 会话消息 → 步骤进度
**缺口**: 
- 视觉内容理解是规则推断非真正 CV
- motion_assets 未与主流程打通
- 抖音等平台 crawler 缺失

### 视频复刻（Remake）: 10% 完整

**已有**: 任务类型定义 + DB 字段预留 + 规划文档
**缺失**: 整个执行链路（选择资产 → 构造 prompt → 调用生成 API → 评估版权 → 保存结果）

### 建议优先级

1. **P0 — 立即做**: motion_assets 与 ProjectService 分析流打通，让"分析→动作资产沉淀"真正闭环
2. **P1 — 短期做**: 关键帧提取 + 多模态视觉理解，提升分析质量
3. **P2 — 中期做**: 视频复刻工作流 MVP（image-to-video + 可灵/Runway）
4. **P3 — 长期做**: 版权距离评估 + 动作骨骼保留的高级复刻
