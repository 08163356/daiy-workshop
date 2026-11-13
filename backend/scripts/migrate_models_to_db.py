"""迁移思维模型数据到数据库

将原来存在 models.json 中的思维模型数据导入到 thinking_models 表。
这是一次性迁移脚本，运行后即可删除。

运行方式：
    cd reading-system/backend
    python scripts/migrate_models_to_db.py
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import select
from app.core.database import async_session_maker, init_db
from app.models.thinking_model import ThinkingModel


# 原 models.json 的数据
MODELS_DATA = [
    {"title": "🎲 黑天鹅思维模型", "description": "<strong>核心理念：</strong>小概率事件具有巨大影响力，不可预测但可以准备<br><br><strong>两个世界观：</strong>• 平均斯坦：正态分布，可预测，样本代表整体<br>• 极端斯坦：幂律分布，不可预测，个体改变整体<br><br><strong>应对策略：</strong>在极端斯坦领域保持开放性，在平均斯坦领域追求稳定性"},
    {"title": "🔍 稀缺心智模型", "description": "<strong>核心发现：</strong>稀缺俘获注意力，产生\"隧道效应\"<br><br><strong>双刃剑效应：</strong>• 专注红利：deadline前效率飙升<br>• 带宽税：认知资源被占用<br>• 隧道视野：只看眼前紧迫<br><br><strong>对抗策略：</strong>建立\"余闲\"（Slack）"},
    {"title": "🎯 Ikigai四圈模型", "description": "<strong>核心理念：</strong>找到四圈交集，发现生命意义<br><br><strong>四个维度：</strong>• 热爱的 • 擅长的 • 世界需要的 • 能获得报酬的<br><br><strong>实践方法：</strong>画四圈列清单，找交集，补齐缺失的圈"},
    {"title": "💰 机会成本决策模型", "description": "<strong>核心公式：</strong>真实成本 = 直接成本 + 放弃的最佳替代选项价值<br><br><strong>时间外包决策：</strong>• 计算隐性时薪 • 如果外包成本 < 隐性时薪×时间，就外包<br><br><strong>应用场景：</strong>家务外包、通勤选择、学习投资"},
    {"title": "🔄 反脆弱性模型", "description": "<strong>核心公式：</strong>适当压力 + 恢复时间 = 变得更强<br><br><strong>应用场景：</strong>• 身体训练 • 技能学习 • 社交能力 • 职业发展<br><br><strong>关键洞察：</strong>错误是进步的机会，小错误预防大错误"},
    {"title": "⚙️ 福格行为模型", "description": "<strong>核心公式：</strong>B = MAT (行为 = 动机 × 能力 × 触发器)<br><br><strong>实践策略：</strong>• 降低门槛 • 设计触发器 • 即时庆祝 • 环境优化"},
    {"title": "🎯 系统思维模型", "description": "<strong>核心理念：</strong>个体行为 ≠ 系统行为<br><br><strong>思维层次：</strong>• 个体层面 • 关系层面 • 组织层面 • 社会层面"},
    {"title": "🎯 最小可行实验模型", "description": "<strong>核心理念：</strong>用最小成本验证假设<br><br><strong>步骤：</strong>• 明确假设 • 设计最小实验 • 执行并收集数据 • 分析决策"},
    {"title": "🔍 杠铃策略模型", "description": "<strong>核心理念：</strong>将资源分配在两端：极保守+极冒险，避免中间地带<br><br><strong>应用：</strong>投资、职业规划、技能学习"},
    {"title": "🧠 认知卸载模型", "description": "<strong>核心理念：</strong>将认知负担外包给工具和系统<br><br><strong>方法：</strong>• GTD系统 • 笔记系统 • 自动化工具"},
    {"title": "📊 决策矩阵模型", "description": "<strong>核心理念：</strong>用矩阵量化多维度决策<br><br><strong>方法：</strong>列出选项和评估维度，加权打分"},
    {"title": "🔄 PDCA循环模型", "description": "<strong>核心理念：</strong>Plan-Do-Check-Act 持续改进<br><br><strong>应用：</strong>个人成长、项目管理、习惯养成"},
    {"title": "🎯 二八法则模型", "description": "<strong>核心理念：</strong>20%的投入产生80%的结果<br><br><strong>应用：</strong>聚焦关键少数，放弃次要多数"},
    {"title": "🧠 费曼学习法模型", "description": "<strong>核心理念：</strong>用教别人的方式学习<br><br><strong>步骤：</strong>• 选择概念 • 用简单语言解释 • 找到盲点 • 精简提炼"},
    {"title": "💡 第一性原理思维模型", "description": "<strong>核心理念：</strong>回到事物最基本的假设，从头推导<br><br><strong>方法：</strong>• 剥离表象 • 找到本质 • 重新构建"},
    {"title": "🔄 复利思维模型", "description": "<strong>核心公式：</strong>终值 = 本金 × (1+利率)^时间<br><br><strong>应用：</strong>投资、学习、人脉、健康都适用复利法则"},
    {"title": "🎯 OKR目标管理模型", "description": "<strong>核心理念：</strong>Objectives（目标）+ Key Results（关键结果）<br><br><strong>方法：</strong>设定有挑战的目标，用可衡量的关键结果追踪"},
    {"title": "🧠 心流状态模型", "description": "<strong>核心理念：</strong>技能水平与挑战难度匹配时进入心流<br><br><strong>条件：</strong>• 明确目标 • 即时反馈 • 技能匹配挑战"},
    {"title": "💡 逆向思维模型", "description": "<strong>核心理念：</strong>反过来想，总是反过来想<br><br><strong>方法：</strong>• 想要成功→先想如何失败 • 想要幸福→先避免什么让人不幸"},
    {"title": "🔍 确认偏误模型", "description": "<strong>核心理念：</strong>人倾向于寻找支持已有观点的证据<br><br><strong>对抗：</strong>• 主动寻找反面证据 • 红队思维 • 预设反对者角色"},
    {"title": "🎯 能力圈模型", "description": "<strong>核心理念：</strong>在能力圈内决策，知道边界在哪<br><br><strong>实践：</strong>• 明确知道什么 • 明确不知道什么 • 逐步扩大能力圈"},
    {"title": "📊 期望值决策模型", "description": "<strong>核心公式：</strong>期望值 = Σ(概率 × 收益)<br><br><strong>应用：</strong>投资决策、职业选择、风险评估"},
    {"title": "🔄 习惯环路模型", "description": "<strong>核心理念：</strong>暗示→惯常行为→奖赏 的循环<br><br><strong>改变方法：</strong>• 保持暗示和奖赏 • 替换惯常行为"},
    {"title": "🧠 元认知模型", "description": "<strong>核心理念：</strong>思考关于思考的思考<br><br><strong>实践：</strong>• 监控自己的思维过程 • 识别认知偏误 • 调整思维策略"},
    {"title": "💡 框架效应模型", "description": "<strong>核心理念：</strong>信息呈现方式影响决策<br><br><strong>应用：</strong>• 识别框架 • 重新框定问题 • 多角度看待同一信息"},
    {"title": "🎯 MVP思维模型", "description": "<strong>核心理念：</strong>最小可行产品，快速验证<br><br><strong>步骤：</strong>• 核心假设 • 最小功能集 • 快速上线 • 收集反馈"},
    {"title": "🔍 沉没成本谬误模型", "description": "<strong>核心理念：</strong>已投入的成本不应影响未来决策<br><br><strong>对抗：</strong>• 只看未来收益 • 忽略已投入 • 重新评估"},
    {"title": "📊 非对称风险模型", "description": "<strong>核心理念：</strong>承担风险的人和做决策的人应该是同一批人<br><br><strong>应用：</strong>• 投资决策 • 职业选择 • 判断建议的可靠性"},
    {"title": "🧠 知行合一模型", "description": "<strong>核心理念：</strong>知道和做到之间有巨大鸿沟<br><br><strong>实践：</strong>• 用行动验证认知 • 从小事开始 • 持续反思"},
    {"title": "💡 少即是多模型", "description": "<strong>核心理念：</strong>通过减法获得更多<br><br><strong>应用：</strong>• 信息减负 • 决策简化 • 聚焦核心"},
    {"title": "🔄 安全边际模型", "description": "<strong>核心理念：</strong>在估计值基础上留出缓冲空间<br><br><strong>应用：</strong>• 投资估值 • 项目规划 • 时间管理"},
    {"title": "🎯 二阶思维模型", "description": "<strong>核心理念：</strong>不只想第一步，还要想后续连锁反应<br><br><strong>方法：</strong>• 然后呢？ • 然后呢？ • 长期影响是什么？"},
]


async def migrate():
    """执行迁移"""
    print("=" * 50)
    print("思维模型迁移：JSON → 数据库")
    print("=" * 50)

    await init_db()

    async with async_session_maker() as db:
        imported = 0
        skipped = 0

        for m in MODELS_DATA:
            title = m["title"]

            # 检查是否已存在
            existing = await db.scalar(
                select(ThinkingModel).where(ThinkingModel.title == title)
            )
            if existing:
                skipped += 1
                print(f"  ⏭️  已存在: {title}")
                continue

            model = ThinkingModel(
                title=title,
                description=m.get("description", ""),
                mention_count=1,
            )
            db.add(model)
            imported += 1
            print(f"  ✅ 导入: {title}")

        await db.commit()

        print()
        print(f"导入完成: {imported} 个新模型, {skipped} 个已存在")
        print(f"共 {len(MODELS_DATA)} 个思维模型")


if __name__ == "__main__":
    asyncio.run(migrate())
