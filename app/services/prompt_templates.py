"""电商口播脚本 + 镜头场景 Prompt 模板"""


def build_product_script_prompt(
    content: str = "",
    target_segments: int = 5,
    tts_rate: str = "+0%",
) -> str:
    target_segments = max(target_segments, 3)
    feature_count = max(target_segments - 4, 0)
    type_hint = f"hook(1) → intro(1) → feature({feature_count}) → scene(1) → cta(1)" if feature_count > 0 else "hook(1) → intro(1) → scene(1) → cta(1)" if target_segments >= 4 else "hook(1) → scene(1) → cta(1)"

    # 根据语速计算字数建议（中文口语基准 ~3.5 字/秒）
    rate_num = float(tts_rate.replace("%", "").replace("+", "").replace("default", "0")) if tts_rate else 0
    chars_per_sec = 3.5 * (1 + rate_num / 100)
    min_chars = max(14, int(4.0 * chars_per_sec))
    max_chars = int(8.0 * chars_per_sec)

    return f"""你是一名资深广告导演。根据产品信息撰写{target_segments}段口播脚本。

每段 {min_chars}-{max_chars} 字（约 4-8 秒口播）。
口语化有网感，每段完整独立，不需要分段间过渡词。

产品信息：
{content}

只输出纯 JSON：
{{"segments":[{{"type":"hook","voiceover":"洗澡出来台面全是水"}}]}}

type 顺序：{type_hint}"""


def build_shot_scene_prompt(voiceovers: list[str]) -> str:
    """根据分组后的口播文案生成镜头场景描述。"""
    items = "\n".join(f"镜{i+1}：{v}" for i, v in enumerate(voiceovers))
    return f"""根据每组口播文案生成对应的电商广告镜头场景描述。

{items}

每个镜头描述必须聚焦画面运动（Seedance 以参考图为基底，prompt 只描述动态变化）：
1. 主体：明确画面焦点（如「水杯杯身特写」「产品桌面场景中景」）
2. 动作：画面核心动态（如「水面微微荡漾」「水珠沿杯壁缓慢滑落」「产品旋转展示」）
3. 运镜：镜头如何运动（如「极慢推镜至杯口细节」「稳定环绕」「固定机位产品旋转」）
4. 光影变化：光的动态（如「柔光从左向右扫过杯身」「逆光光晕渐强」）

禁止静态形容词堆砌，每句必须有动词。
一句话描述，30-80 字。

只输出 JSON：{{"scenes":["场景描述1","场景描述2",...]}}"""
