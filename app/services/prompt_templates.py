
def build_product_script_prompt(content: str = "", target_segments: int = 8,) -> str:
    """电商口播脚本"""

    target_segments = max(target_segments, 5)
    feature_count = max(target_segments - 4, 0)
    type_hint = (
        f"hook(1) → intro(1) → feature({feature_count}) → scene(1) → cta(1)"
        if feature_count > 0
        else "hook(1) → intro(1) → scene(1) → cta(1)"
        if target_segments >= 4
        else "hook(1) → scene(1) → cta(1)"
    )

    return f"""你是一名资深广告导演。根据产品信息撰写{target_segments}段口播脚本。

每段 15-30 字。
口语化有网感，每段完整独立，不需要分段间过渡词。

产品信息：
{content}

只输出纯 JSON：
{{"segments":[{{"type":"hook","voiceover":"洗澡出来台面全是水"}}]}}

type 顺序：{type_hint}"""


def build_shot_scene_prompt(voiceovers: list[str]) -> str:
    """根据分组后的口播文案生成双语场景描述（zh 给前端，en 给 Seedance）。"""
    items = "\n".join(f"镜{i+1}：{v}" for i, v in enumerate(voiceovers))
    return f"""你是资深电商广告导演。根据每组口播文案，为 Seedance AI 视频生成工具撰写场景描述。

各组口播：
{items}

每个镜头同时输出中文版和英文版：
- zh：给运营人员看的，通俗描述画面内容和运镜方式，30-50 字
- en：给 Seedance 视频模型用的，40-80 个英文单词，必须包含 shot size / lens / camera movement / lighting / action

━━━ 英文版要素 ━━━
shot size / lens / camera movement / lighting / action
必须是纯视觉描述，不要抽象形容词

━━━ 电商广告最佳实践 ━━━
- 产品特写：极慢推镜 + 微距细节（材质纹理、logo 雕刻、接口做工）
- 功能演示：固定机位 + 产品动作（开合、旋转、水流、冒蒸汽）
- 场景展示：稳定环绕或滑轨 + 环境氛围（桌面上晨光洒落、厨房暖光）

只输出 JSON：
{{"scenes":[{{"zh":"中文描述","en":"English prompt"}}, ...]}}"""
