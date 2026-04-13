"""
Motion Extraction workflow metadata.

当前动作提取使用 TaskQueue + jobs 承载运行状态，
步骤定义仍集中在这里，便于前后端和测试复用。
"""

from app.workflows.engine import TaskStepDefinition


MOTION_EXTRACTION_STEPS = (
    TaskStepDefinition(
        "validate_analysis_data",
        "检查分析数据",
        "确认目标视频已完成分析，shot_segments 和 storyboard 数据可用。",
    ),
    TaskStepDefinition(
        "coarse_filter_shots",
        "粗筛候选片段",
        "基于关键词和时长规则，从所有镜头中筛选可能包含高价值动作的片段。",
    ),
    TaskStepDefinition(
        "tag_candidates",
        "精标动作标签",
        "对候选片段调用模型或规则，生成结构化标签和动作摘要。",
    ),
    TaskStepDefinition(
        "generate_thumbnails",
        "生成预览缩略图",
        "为通过精标的动作片段尽力提取关键帧作为缩略图。",
    ),
    TaskStepDefinition(
        "save_motion_assets",
        "写入动作资产",
        "将标签化的片段写入 motion_assets 表，状态设为 auto_tagged。",
    ),
    TaskStepDefinition(
        "finish",
        "提取完成",
        "动作资产提取流程全部完成，可在资产库中查看。",
    ),
)


__all__ = ["MOTION_EXTRACTION_STEPS"]
