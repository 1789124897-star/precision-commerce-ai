"""分析 & 策略 Prompt 构建"""

STRATEGY_TYPES = {
    "A": {"name": "痛点解决型", "description": "聚焦核心痛点，用功能差异打动用户"},
    "B": {"name": "效率功能型", "description": "强调使用效率和功能创新"},
    "C": {"name": "情绪品质型", "description": "情感共鸣和品质升级路线"},
}


def build_analysis_prompt(name: str, function: str, price: str, extra: str, custom_prompt: str = "") -> str:
    if custom_prompt.strip():
        return custom_prompt.replace("{name}", name).replace("{function}", function).replace("{price}", price).replace("{extra}", extra or "无")

    return f"""
请结合商品图片和商品文本信息完成一份结构化分析报告。

商品信息：
- 商品标题：{name}
- 核心功能：{function}
- SKU规格：{price}
- 产品信息：{extra or "无"}

请严格按下面结构输出：
1. 核心用户画像（3类）
2. 典型购买场景（3个）
3. 核心痛点（5个）
4. 核心卖点（5个，强调用户价值，并标注来源是视觉、功能还是规格）
5. 推荐营销方向（3个）

要求：
- 输出必须使用简体中文
- 结合图片中的材质、颜色、造型、质感、使用场景进行判断
- 语言要适合电商运营、商品策划和营销团队直接使用
"""


def build_strategy_prompt(analysis: str, strategy_code: str, strategy_name: str, system_prompt: str = "") -> str:
    role = system_prompt.strip() or "你是一名资深电商策略师，专门为精铺卖家设计差异化营销方案。"
    return f"""
{role}
方案类型：{strategy_name}（{STRATEGY_TYPES[strategy_code]["description"]}）

以下是商品分析报告：

{analysis}

请基于以上分析，输出一套完整的差异化运营方案（{strategy_code} 方案），严格按下方 JSON 格式输出，不能有多余字段，所有中文内容使用简体中文。

━━━━━━━━━━━━━━━━━━━━
输出 JSON 结构：
━━━━━━━━━━━━━━━━━━━━

{{
  "type": "{strategy_name}",
  "route_name": "给方案起一个响亮好记的名字，例如：租房神器路线、办公效率路线、品质生活路线",

  "positioning": {{
    "target_users": ["3类目标用户，越具体越好，如：一线城市合租白领"],
    "core_pain_points": ["3-5个核心痛点"],
    "anchor_point": "一句话差异化锚点，用户为什么选你的产品"
  }},

  "competitor_guess": {{
    "price_range": "根据产品定位推测竞品价格区间，如：9.9-29.9元",
    "style_summary": "竞品主流风格，如：传统塑料款主打低价，缺乏设计感",
    "gap_opportunity": "市场空白机会，竞品没做到的差异化方向"
  }},

  "keywords": {{
    "core_keywords": ["2-3个核心大词，如：磁吸漱口杯"],
    "scene_keywords": ["2-3个场景长尾词，如：租房免打孔漱口杯"],
    "feature_keywords": ["2-3个功能长尾词，如：倒挂沥水漱口杯"],
    "title_suggestion": "组合后的建议标题，30字以内"
  }},

  "main_images": [
    {{
      "position": 1,
      "type": "痛点对比",
      "purpose": "让用户3秒理解产品价值",
      "title_text": "主图上叠加的文案，如：告别积水杂乱的洗漱台",
      "prompt": "主体、场景、构图、光影、风格五要素均需明确。构图建议对比式（左右分屏或新旧对比），突出产品带来的改变，画面有视觉冲击力。"
    }},
    {{
      "position": 2,
      "type": "安装/使用便捷",
      "purpose": "降低购买顾虑",
      "title_text": "主图文案",
      "prompt": "主体、场景、构图、光影、风格五要素均需明确。构图建议使用中景，展示使用过程或安装效果，画面干净利落、实用主义风格。"
    }},
    {{
      "position": 3,
      "type": "场景展示",
      "purpose": "场景价值或空间效果",
      "title_text": "主图文案",
      "prompt": "主体、场景、构图、光影、风格五要素均需明确。构图建议产品融入真实使用环境（居家/办公/出行），自然光或柔和室内光，生活感强。"
    }},
    {{
      "position": 4,
      "type": "功能特写",
      "purpose": "突出核心卖点或使用效果",
      "title_text": "主图文案",
      "prompt": "主体、场景、构图、光影、风格五要素均需明确。构图建议微距特写或浅景深，产品核心功能区域占画面70%以上，突出细节和材质。"
    }},
    {{
      "position": 5,
      "type": "材质/品质",
      "purpose": "建立信任感",
      "title_text": "主图文案",
      "prompt": "主体、场景、构图、光影、风格五要素均需明确。构图建议产品平铺或45°展示，高质感布光（侧光/逆光勾边），突出工艺细节和材质纹理。"
    }}
  ],

  "detail_pages": [
    {{
      "position": 1,
      "type": "痛点共鸣",
      "section_title": "抓人的标题，如：你的漱口杯还在积水发霉吗？",
      "purpose": "让用户产生共鸣",
      "prompt": "主体、场景、构图、光影、风格五要素均需明确。构图建议生活场景代入，写实摄影风格，自然光，让用户产生'这就是我'的代入感。"
    }},
    {{
      "position": 2,
      "type": "解决方案",
      "section_title": "方案标题",
      "purpose": "展示产品如何解决问题",
      "prompt": "主体、场景、构图、光影、风格五要素均需明确。构图建议产品居中突出，干净背景（白底或纯色），展示产品解决问题的关键画面。"
    }},
    {{
      "position": 3,
      "type": "安装/使用演示",
      "section_title": "演示标题",
      "purpose": "消除使用障碍",
      "prompt": "主体、场景、构图、光影、风格五要素均需明确。构图建议步骤分解或动作定格，信息图风格，清晰展示安装步骤或操作方法。"
    }},
    {{
      "position": 4,
      "type": "多场景展示",
      "section_title": "场景标题",
      "purpose": "覆盖更多使用场景",
      "prompt": "主体、场景、构图、光影、风格五要素均需明确。构图建议多场景拼贴或代表性场景切换，展现产品在不同环境下的适配性。"
    }},
    {{
      "position": 5,
      "type": "规格参数",
      "section_title": "产品尺寸与规格",
      "purpose": "关闭最后疑虑",
      "prompt": "主体、场景、构图、光影、风格五要素均需明确。构图建议白底正视，均匀布光无阴影，预留标注文字区，展示尺寸、颜色选项、SKU信息。"
    }}
  ],

  "pricing": {{
    "suggested_price_range": "建议售价区间，如：19.9-39.9元",
    "sku_strategy": [
      {{"name": "引流款", "desc": "规格和价格，如单杯装19.9元", "purpose": "低价引流抢占搜索"}},
      {{"name": "利润款", "desc": "规格和价格", "purpose": "主力利润款"}},
      {{"name": "高价款", "desc": "规格和价格", "purpose": "拉高客单价"}}
    ],
    "anchor_note": "价格锚点说明，对标什么、靠什么溢价"
  }},

  "review_strategy": {{
    "guided_keywords": ["5个评价引导关键词，让买家自然提到"],
    "photo_suggestions": ["3个买家秀拍摄角度建议"],
    "qa_seeds": ["3个预设问答，布局问大家关键词"]
  }}
}}

━━━━━━━━━━━━━━━━━━━━
重要要求：
━━━━━━━━━━━━━━━━━━━━
1. 所有字段必须填写，不能有空数组或空字符串
2. prompt 字段必须具体、可直接用于 AI 生图，包含构图、光照、风格关键词
3. 每个方案的 route_name、anchor_point 必须互不相同，体现 {strategy_code} 方案的差异化路线
4. 仅输出 JSON，不要有任何解释文字或 markdown 标记
5. 为精铺卖家设计，强调差异化溢价，不是低价走量
"""
