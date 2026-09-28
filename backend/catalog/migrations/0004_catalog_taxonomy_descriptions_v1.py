from django.db import migrations


# The descriptions below are transcribed from
# "Catalog分类体系定稿_v1.0_2026-09-21.docx".  Examples are only appended
# where the source document defines an example for that individual category.
CATEGORIES = {
    "material_type": {
        "picture_book": ("绘本", "以图文共同叙事为主，图像承担明显信息。\n例子：普通故事绘本、情绪绘本"),
        "graded_reader": ("分级读物", "按语言/阅读等级系统组织的读物。\n例子：ORT、RAZ 等体系中的分级内容"),
        "early_reader": ("初级自主阅读", "面向刚开始自主阅读的儿童，句子较短、版面支持较强。\n例子：Ready-to-Read Pre-Level 1 / Level 1 一类"),
        "chapter_book": ("章节书", "按章节组织、文字量更高、图像依赖降低。\n例子：桥梁后期/初章及更高章节读物"),
        "comic": ("漫画", "主要依靠分格、对白、连续画面叙事。\n例子：儿童漫画、图像小说"),
        "reference": ("百科 / 工具类", "以查阅、知识说明、概念介绍为主要目的。\n例子：儿童百科、图鉴、知识手册"),
        "poetry": ("诗歌 / 童谣材料", "以诗歌、童谣或韵文作品为主要材料形态。\n例子：童谣集、儿童诗集"),
    },
    "genre": {
        "fiction": ("虚构", "核心人物/情节属于虚构叙事。"),
        "nonfiction": ("非虚构", "以真实事实、知识、真实人物或真实事件为主。"),
        "adventure": ("冒险", "核心吸引力来自探索、旅程、风险或未知经历。"),
        "fantasy": ("奇幻", "明显包含魔法、幻想世界或非现实规则。"),
        "humor": ("幽默", "笑料、反差、荒诞或喜剧效果是明显阅读特征。"),
        "mystery": ("悬疑 / 解谜", "围绕谜题、线索、寻找真相展开。"),
        "biography": ("传记", "以真实人物经历为核心。"),
        "poetry_rhyme": ("诗歌 / 韵文", "作品表达明显以诗歌、韵文、节奏为核心。"),
    },
    "theme": {
        "daily_life": ("日常生活", "吃饭、穿衣、洗澡、出门、购物、睡觉等生活事件。"),
        "family": ("家庭", "亲子、兄弟姐妹、祖辈、家庭关系。"),
        "friendship": ("友情", "交朋友、相处、冲突、和好。"),
        "school": ("学校", "入园、上学、老师、同学、课堂与学校生活。"),
        "growth": ("成长", "长大、变化、第一次经历、能力成长。"),
        "courage": ("勇气", "面对害怕、尝试、挑战。"),
        "emotion": ("情绪", "情绪体验、识别、表达与应对。"),
        "social_relationship": ("人际关系", "同伴互动、规则、误会、边界、社交关系。"),
        "problem_solving": ("解决问题", "遇到问题、尝试方案、解决或调整。"),
        "independence": ("独立", "自己完成、独立行动、自理。"),
        "sharing": ("分享", "分享物品、资源、机会。"),
        "cooperation": ("合作", "共同完成任务、团队配合。"),
        "fear": ("害怕", "怕黑、怕陌生人、怕动物、怕失败等。"),
        "anger": ("愤怒", "生气、发脾气、冲突后的愤怒。"),
        "sadness": ("悲伤", "失落、难过、被拒绝后的悲伤。"),
        "jealousy": ("嫉妒", "比较、被忽视、别人得到自己想要的东西。"),
        "frustration": ("挫败", "失败、做不到、等待、受阻。"),
        "separation_anxiety": ("分离焦虑", "与父母/照顾者分开、入园等。"),
        "confidence": ("自信", "自我肯定、敢尝试、建立信心。"),
        "empathy": ("同理心", "理解并回应他人的感受。"),
        "embarrassment": ("尴尬 / 羞怯", "被关注、出错、社交尴尬。"),
        "grief": ("失落 / 哀伤", "重要的人/物离开、死亡、长期失落。"),
    },
    "topic": {
        "animals": ("动物", "泛动物主题。"),
        "dinosaurs": ("恐龙", "恐龙故事或恐龙知识。"),
        "pets": ("宠物", "猫、狗等家庭宠物。"),
        "insects": ("昆虫", "昆虫及相关知识。"),
        "ocean_animals": ("海洋动物", "鲸、鲨鱼、海豚等。"),
        "plants": ("植物", "植物、生长、花草树木。"),
        "nature": ("自然", "自然环境、生态、户外自然。"),
        "weather": ("天气", "雨、雪、风、云、气象。"),
        "vehicles": ("交通工具", "汽车、火车、飞机、工程车辆等。"),
        "robots": ("机器人", "机器人角色、机器人知识。"),
        "machines": ("机械 / 工程", "机械结构、工具、工程设备。"),
        "body": ("身体", "身体部位、人体结构。"),
        "health": ("健康", "卫生、疾病预防、健康习惯。"),
        "space": ("太空", "宇宙、星球、火箭、宇航员。"),
        "earth": ("地球", "地球、地貌、地理环境。"),
        "science": ("科学", "难归入更具体 topic 的综合科学。"),
        "math": ("数学", "数字、形状、数量、数学概念。"),
        "arts_music": ("艺术 / 音乐", "绘画、音乐、乐器、表演。"),
        "food": ("食物", "食物、烹饪、饮食。"),
        "sports": ("运动", "球类、跑跳、运动项目。"),
        "holidays": ("节日", "圣诞、万圣节、春节等节日内容。"),
    },
    "reading_form": {
        "repetitive_pattern": ("重复 / 可预测句型", "大量重复句式或固定结构，孩子容易预测、跟说。\n例子：Brown Bear, Brown Bear 一类"),
        "rhyme_rhythm": ("押韵 / 强韵律", "明显押韵、节奏、韵律感。\n例子：童谣、强节奏绘本"),
        "interactive": ("互动式", "要求读者回答、寻找、模仿、做动作或参与。\n例子：找一找、跟我做、问答式绘本"),
        "wordless": ("无字 / 极少文字", "主要依靠图像讲故事，文字极少或没有。\n例子：无字绘本"),
        "cumulative": ("累积式结构", "前面的句子/事件不断叠加重复，形成累积。\n例子：The House That Jack Built 一类结构"),
    },
}


def update_taxonomy(apps, schema_editor):
    Category = apps.get_model("catalog", "CatalogCategory")
    for category_type, categories in CATEGORIES.items():
        for code, (name_zh, description) in categories.items():
            updated = Category.objects.filter(category_type=category_type, code=code).update(
                name_zh=name_zh,
                description=description,
            )
            if updated != 1:
                raise RuntimeError(f"Expected one catalog category for {category_type}:{code}, updated {updated}")


class Migration(migrations.Migration):
    dependencies = [("catalog", "0003_catalog_taxonomy_v1")]

    operations = [migrations.RunPython(update_taxonomy, migrations.RunPython.noop)]
