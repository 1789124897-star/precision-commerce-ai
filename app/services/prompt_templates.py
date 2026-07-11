"""电商口播脚本 Prompt 模板"""


def build_product_script_prompt(
    content: str = "",
    target_segments: int = 8,
) -> str:
    return f"""根据产品信息撰写短视频口播脚本，{target_segments} 段，每段 12-18 字，口语化有网感。

产品信息：
{content}

输出 JSON：
{{"segments": [{{"type": "hook|intro|feature|scene|cta", "voiceover": "...", "image_keywords": []}}]}}

type 顺序：hook(1) → intro(1) → feature({target_segments - 4}) → scene(1) → cta(1)"""
