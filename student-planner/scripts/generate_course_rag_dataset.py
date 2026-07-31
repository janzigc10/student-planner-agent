from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.rag import HashEmbeddings, LocalRAGRetriever
from app.agent.rag_corpus import load_frozen_chunks, write_corpus_artifacts
from app.agent.rag_evaluation import (
    EvaluationQuery,
    EvidenceRequirement,
    Qrel,
    build_dataset_manifest,
    stratified_split,
)
from app.config import settings


CORPUS_VERSION = "rag-course-v1.1"
DATASET_VERSION = "rag-course-golden-v1.1"
MATERIAL_TYPES = (
    "chapter_notes",
    "review_outline",
    "concept_comparison",
    "worked_examples",
    "common_mistakes",
    "exam_requirements",
)


def _topic(
    key: str,
    title: str,
    definition: str,
    mechanism: str,
    contrast: str,
    example: str,
    pitfall: str,
    keywords: str,
) -> dict[str, str]:
    return {
        "key": key,
        "title": title,
        "definition": definition,
        "mechanism": mechanism,
        "contrast": contrast,
        "example": example,
        "pitfall": pitfall,
        "keywords": keywords,
    }


COURSES: dict[str, dict[str, Any]] = {
    "machine_learning": {
        "name": "机器学习基础",
        "topics": [
            _topic("supervised_learning", "监督学习", "监督学习利用带标签样本学习输入到目标的映射。", "训练阶段最小化预测与标签之间的损失，推断阶段把学到的规律用于未见样本。", "它与无监督学习的关键差异是训练数据是否提供目标标签。", "垃圾邮件分类可把邮件特征映射为正常或垃圾标签。", "不能把训练集表现直接当作泛化能力。", "标签、损失函数、泛化、分类、回归"),
            _topic("dataset_split", "训练集验证集与测试集", "训练集拟合参数，验证集选择超参数，测试集只用于最终无偏评估。", "三类数据分工能隔离模型学习、方案选择和最终报告。", "验证集参与模型选择，而测试集不应反复用于调参。", "先用训练集拟合多个深度的决策树，再在验证集选深度，最后只在测试集报告一次。", "测试集泄漏会让最终指标虚高。", "训练集、验证集、测试集、数据泄漏"),
            _topic("cross_validation", "交叉验证", "交叉验证把数据划为若干折，轮流用一折验证并汇总结果。", "多次轮换降低单次划分偶然性，常用于样本较少时估计模型稳定性。", "留出法只评估一次划分，K 折交叉验证会产生 K 次验证结果。", "五折交叉验证中每个样本恰好一次进入验证折。", "预处理必须在每个训练折内部拟合，否则仍会泄漏。", "K折、轮换、均值、方差、数据泄漏"),
            _topic("overfitting_regularization", "过拟合与正则化", "过拟合指模型记住训练细节而不能推广到新样本。", "正则化通过限制参数规模、模型复杂度或训练过程抑制方差。", "欠拟合是表达能力不足，过拟合则是训练好但验证差。", "线性模型加入 L2 惩罚后会压缩大权重。", "正则越强并不总越好，过强会导致欠拟合。", "过拟合、欠拟合、L1、L2、偏差方差"),
            _topic("classification_metrics", "分类评估指标", "准确率衡量总体正确比例，精确率关注预测为正的样本有多少是真的，召回率关注真实正例找回多少。", "混淆矩阵把预测与真值组合成 TP、FP、TN、FN，其他指标由此计算。", "类别不平衡时准确率可能掩盖少数类失败。", "疾病筛查通常优先关注召回率，垃圾邮件拦截还要控制误杀带来的低精确率。", "不能脱离业务代价机械选择单一指标。", "准确率、精确率、召回率、F1、混淆矩阵"),
            _topic("linear_regression", "线性回归", "线性回归用特征的线性组合预测连续目标。", "最小二乘通过最小化残差平方和估计参数。", "线性回归预测连续值，逻辑回归通常用于分类概率。", "用面积、楼层和房龄预测房价是典型线性回归任务。", "相关性和线性拟合不能自动证明因果关系。", "最小二乘、残差、连续目标、共线性"),
            _topic("logistic_regression", "逻辑回归", "逻辑回归把线性得分经 sigmoid 转换为类别概率。", "训练时通常最小化交叉熵，预测时再按阈值转成类别。", "它名称含回归但常用于二分类；与线性回归的输出空间不同。", "根据学习时长预测是否通过考试可得到 0 到 1 的通过概率。", "默认 0.5 阈值不一定符合类别不平衡任务。", "sigmoid、交叉熵、概率、决策阈值"),
            _topic("decision_tree", "决策树", "决策树通过一系列特征条件把样本递归划分到叶节点。", "分类树常用信息增益或基尼指数选择切分。", "树模型易解释但单棵深树容易过拟合。", "信用评估可依次按收入、负债和历史记录进行切分。", "不能只看训练纯度而忽略剪枝和验证。", "信息增益、基尼指数、剪枝、叶节点"),
            _topic("svm", "支持向量机", "支持向量机寻找能最大化类别间隔的分隔超平面。", "只有靠近边界的支持向量直接决定最优间隔。", "核技巧用于处理非线性边界，而线性核保留原始线性空间。", "文本分类中的高维稀疏特征常适合线性支持向量机。", "核参数和惩罚系数需要在验证集选择。", "最大间隔、支持向量、核函数、惩罚系数"),
            _topic("clustering", "聚类", "聚类在没有标签时按相似性组织样本。", "K-means 交替执行样本分配与质心更新以降低簇内平方距离。", "聚类发现数据结构，分类则学习已知标签边界。", "可按学习行为把学生划分为不同复习模式群体。", "簇编号没有天然语义，K 值也不能只凭直觉决定。", "K-means、质心、簇内距离、无监督"),
            _topic("feature_engineering", "特征工程", "特征工程把原始数据转换为更适合模型学习的表示。", "流程包括缺失处理、编码、缩放、组合与筛选，并且只能从训练数据拟合转换参数。", "特征选择保留已有变量，特征构造会生成新变量。", "把时间戳拆成星期与时段可帮助预测学习活跃度。", "先对全数据标准化再切分会造成数据泄漏。", "缺失值、编码、标准化、特征选择"),
            _topic("gradient_descent", "梯度下降", "梯度下降沿损失函数负梯度方向迭代更新参数。", "学习率控制每次步长，批量方式决定每次估计梯度使用多少样本。", "批量梯度稳定但计算重，随机梯度噪声大但更新快。", "学习率过大可能在最优点附近震荡甚至发散。", "损失下降不代表测试误差一定同步下降。", "学习率、梯度、收敛、批量、随机"),
        ],
    },
    "modern_chinese_history": {
        "name": "中国近现代史",
        "topics": [
            _topic("opium_war", "鸦片战争", "鸦片战争使中国社会性质和对外关系发生深刻变化。", "列强以武力和不平等条约扩大权益，传统秩序受到冲击。", "战争失败不只源于武器差距，也与制度、财政和组织能力相关。", "《南京条约》开放通商口岸并改变关税与领土安排。", "不能把近代化起点简单等同于被动失败本身。", "鸦片战争、南京条约、半殖民地半封建"),
            _topic("taiping", "太平天国运动", "太平天国是近代规模巨大的农民战争。", "社会矛盾、灾害和政权组织共同推动其兴起与扩张。", "它反抗清朝统治和外来侵略，但农民阶级局限影响制度建设。", "《天朝田亩制度》体现平均主义理想，《资政新篇》提出近代化设想。", "两份纲领的内容和实际实施程度不能混为一谈。", "太平天国、天朝田亩制度、资政新篇"),
            _topic("westernization", "洋务运动", "洋务运动主张学习西方技术以维护清朝统治。", "先办军事工业，再扩展民用企业、海军和新式教育。", "它开启若干近代化实践，但没有触动封建政治根本结构。", "江南制造总局和轮船招商局分别体现军用与民用方向。", "不能把“自强求富”解释为完整资本主义改革。", "洋务运动、自强、求富、军事工业"),
            _topic("reform1898", "戊戌维新", "戊戌维新试图通过自上而下改革推动制度更新。", "维新派借助皇权发布新政，但缺乏稳定社会基础和武装保障。", "它比洋务运动更关注制度改革，却仍未形成广泛群众动员。", "废除八股、发展实业和改革教育体现变法方向。", "百日维新短暂不等于思想启蒙影响短暂。", "戊戌维新、百日维新、维新派、制度改革"),
            _topic("xinhai", "辛亥革命", "辛亥革命推翻清朝统治并结束君主专制制度。", "革命组织、武装起义和清末危机共同促成政权更替。", "它建立共和制度形式，但没有彻底改变社会经济基础。", "武昌起义后各省响应，中华民国随后成立。", "不能把推翻帝制等同于完成反帝反封建任务。", "辛亥革命、武昌起义、中华民国、共和"),
            _topic("new_culture", "新文化运动", "新文化运动倡导民主与科学并批判旧礼教。", "新式知识传播、报刊和大学空间推动思想解放。", "它与五四运动紧密相连，但前者首先是思想文化启蒙。", "《新青年》成为传播新思想的重要阵地。", "不能把对传统文化的复杂反思简化为全盘否定。", "新文化运动、民主、科学、新青年"),
            _topic("may_fourth", "五四运动", "五四运动是彻底反帝反封建的爱国运动，并推动新民主主义革命发展。", "巴黎和会外交失败引发学生行动，工人和商人加入后运动扩大。", "它不同于单纯校园抗议，社会阶层参与和政治方向均更广。", "工人阶级登上政治舞台成为重要历史变化。", "不能只记日期而忽略群众基础和思想传播。", "五四运动、巴黎和会、工人阶级、新民主主义革命"),
            _topic("cpc_founding", "中国共产党成立", "中国共产党成立使中国革命有了新的领导力量。", "马克思主义传播、工人运动发展和早期组织建立形成条件。", "党的成立与此前资产阶级革命相比体现新的阶级基础和理论指导。", "中共一大确定党的基本组织与奋斗方向。", "不能把成立条件归结为单一外部事件。", "中国共产党、中共一大、马克思主义、工人运动"),
            _topic("anti_japanese", "全民族抗日战争", "全民族抗战是在抗日民族统一战线旗帜下进行的民族解放战争。", "正面战场与敌后战场相互配合，持久抗战消耗侵略力量。", "局部抗战与全面抗战的时间、范围和动员程度不同。", "七七事变后全国性抗战局面形成。", "不能以单一战场替代整个抗战贡献结构。", "抗日民族统一战线、正面战场、敌后战场、持久战"),
            _topic("liberation", "解放战争", "解放战争决定了中国两种前途和政权走向。", "土地政策、群众动员、战略决战和政治争取共同影响胜负。", "防御、反攻和决战阶段的军事任务不同。", "辽沈、淮海、平津三大战役改变全国军事格局。", "不能只用兵力数量解释战争结局。", "解放战争、土地改革、三大战役、群众动员"),
            _topic("founding_prc", "中华人民共和国成立", "中华人民共和国成立标志新民主主义革命取得基本胜利。", "人民政权建设、政协会议和共同纲领为新国家奠定制度基础。", "国家成立与社会主义制度确立是不同历史阶段。", "中国人民政治协商会议第一届全体会议承担建国筹备功能。", "不能把 1949 年直接写成社会主义改造完成。", "中华人民共和国、共同纲领、人民政协、新民主主义"),
            _topic("socialist_transformation", "社会主义改造", "社会主义改造推动生产资料私有制向社会主义公有制转变。", "农业、手工业和资本主义工商业采用不同组织与政策路径。", "改造所有制与发展生产力相互关联但不是同一概念。", "对资本主义工商业实行和平赎买体现特定政策安排。", "不能忽略改造后经济管理仍需继续探索。", "社会主义改造、公有制、和平赎买、三大改造"),
            _topic("reform_opening", "改革开放", "改革开放从 1978 年十一届三中全会后进入新时期。", "农村改革、城市改革、对外开放和体制创新逐步展开。", "改革是社会主义制度自我完善，不等于否定社会主义方向。", "家庭联产承包责任制激发农村生产积极性。", "不能只把开放理解为扩大商品进口。", "改革开放、十一届三中全会、家庭联产承包责任制"),
        ],
    },
    "world_modern_history": {
        "name": "世界现代史",
        "topics": [
            _topic("world_war_one", "第一次世界大战", "第一次世界大战源于帝国主义矛盾、军备竞赛和同盟对抗。", "萨拉热窝事件触发危机链条，同盟承诺使局部冲突升级。", "导火索不是战争深层原因，两者答题时必须区分。", "西线堑壕战体现工业化战争的消耗特征。", "不能把所有参战国目的概括为完全相同。", "第一次世界大战、同盟体系、萨拉热窝、堑壕战"),
            _topic("versailles", "凡尔赛—华盛顿体系", "战后列强通过和约与会议重建国际秩序。", "战胜国围绕领土、赔款和势力范围进行安排。", "体系暂时协调矛盾，却没有消除大国竞争和民族问题。", "《凡尔赛条约》对德国的处置埋下复仇情绪。", "不能把国际组织建立等同于持久和平已经实现。", "凡尔赛体系、华盛顿会议、国际联盟、德国赔款"),
            _topic("russian_revolution", "俄国十月革命", "十月革命建立了世界上第一个社会主义国家政权。", "战争危机、双重政权和布尔什维克策略推动革命发展。", "二月革命推翻沙皇，十月革命解决政权性质问题。", "“全部政权归苏维埃”反映革命阶段变化。", "不能混淆二月革命和十月革命的对象与结果。", "十月革命、二月革命、苏维埃、布尔什维克"),
            _topic("great_depression", "1929—1933年经济危机", "经济危机表现为生产过剩、金融崩溃、失业上升和国际贸易收缩。", "消费能力不足、信用扩张和金融脆弱性相互放大。", "危机是结构性失衡，不只是股市单日下跌。", "美国银行倒闭与企业减产形成负向循环。", "不能把罗斯福新政措施写成危机原因。", "经济危机、生产过剩、失业、金融崩溃"),
            _topic("world_war_two", "第二次世界大战", "第二次世界大战由法西斯扩张、绥靖政策和国际秩序失效等因素推动。", "侵略逐步升级，反法西斯同盟形成后战争力量对比改变。", "欧洲战场与亚洲战场相互关联但时间线不同。", "斯大林格勒战役和中途岛战役分别影响不同战场转折。", "不能忽略中国抗战对世界反法西斯战争的贡献。", "第二次世界大战、法西斯、反法西斯同盟、转折"),
            _topic("united_nations", "联合国成立", "联合国旨在维护国际和平安全并推动国际合作。", "安理会、联合国大会和专门机构承担不同职能。", "联合国比国际联盟更具普遍性，但仍受大国政治影响。", "安理会常任理事国否决权体现大国协调机制。", "不能把大会决议与安理会强制措施等同。", "联合国、安理会、联合国大会、否决权"),
            _topic("cold_war", "冷战", "冷战是美苏主导的全面对抗，主要避免直接大规模战争。", "意识形态、国家利益、安全困境和力量结构共同推动对峙。", "冷战不等于完全没有热战，代理人战争仍然存在。", "柏林危机和古巴导弹危机体现高强度对抗风险。", "不能用单一宣言解释几十年的全部进程。", "冷战、美苏、两极格局、代理人战争"),
            _topic("truman_doctrine", "杜鲁门主义", "杜鲁门主义以援助希腊和土耳其为起点宣示遏制政策。", "美国把地区危机解释为全球意识形态竞争并扩大介入。", "它偏重政治安全承诺，马歇尔计划则突出经济援助。", "1947 年杜鲁门国会演说通常被视为冷战政策公开化。", "不能把杜鲁门主义与北约组织成立混成同一事件。", "杜鲁门主义、遏制、希腊、土耳其"),
            _topic("marshall_plan", "马歇尔计划", "马歇尔计划通过经济援助推动西欧复兴并服务美国遏制战略。", "资金、物资和合作机制缓解战后困难，同时强化西欧与美国联系。", "它与杜鲁门主义目标相通，但主要手段不同。", "欧洲经济合作促进了西欧协调与一体化条件形成。", "不能只写人道援助而忽略冷战政治背景。", "马歇尔计划、经济援助、西欧复兴、遏制"),
            _topic("nato_warsaw", "北约与华约", "北约和华约是冷战两大军事政治集团。", "集体防御承诺把成员安全与集团整体战略绑定。", "北约成立于 1949 年，华约成立于 1955 年，背景与成员不同。", "德国问题和欧洲安全结构推动两大集团对峙。", "不能把两者写成同年成立或完全对称的组织。", "北约、华约、集体防御、军事集团"),
            _topic("decolonization", "亚非拉民族解放运动", "二战后殖民体系在民族运动和国际环境变化中迅速瓦解。", "本土组织、宗主国衰弱和国际支持共同影响独立进程。", "不同地区既有和平移交也有长期武装斗争。", "印度独立和阿尔及利亚战争代表不同路径。", "不能把政治独立等同于经济依附立即消失。", "非殖民化、民族独立、第三世界、殖民体系"),
            _topic("soviet_collapse", "苏联解体", "苏联解体结束了联盟国家形态并改变两极格局。", "经济停滞、政治改革失控、民族问题和制度矛盾共同作用。", "东欧剧变与苏联解体相互关联但不是同一事件。", "1991 年独联体建立标志联盟结构终结。", "不能用单一领导人性格替代结构性分析。", "苏联解体、戈尔巴乔夫、民族问题、两极格局"),
        ],
    },
    "political_theory": {
        "name": "思想政治理论",
        "topics": [
            _topic("marxism", "马克思主义基本立场", "马克思主义坚持人民立场并从实践出发认识和改造世界。", "实践、认识和再实践构成不断深化的认识过程。", "唯物辩证法强调联系发展，形而上学倾向孤立静止。", "社会调查把理论问题放回具体历史条件中分析。", "不能把理论原理写成脱离条件的固定口号。", "人民立场、实践、唯物辩证法、历史条件"),
            _topic("core_values", "社会主义核心价值观", "核心价值观从国家、社会和个人三个层面概括价值要求。", "价值认同通过教育、制度与日常实践转化为行为规范。", "三个层面的词语不能随意互换其适用主体。", "诚信既是个人品格要求，也需要制度环境支持。", "不能只背诵词语而不解释层次关系。", "富强民主文明和谐、自由平等公正法治、爱国敬业诚信友善"),
            _topic("whole_process_democracy", "全过程人民民主", "全过程人民民主贯通选举、协商、决策、管理和监督。", "制度渠道让人民在国家与社会治理各环节持续参与。", "它不把民主缩减为一次性投票，而强调过程与结果统一。", "基层议事协商和人大代表联系群众体现持续参与。", "不能把协商民主理解为没有法定程序的随意讨论。", "全过程人民民主、民主协商、民主决策、民主监督"),
            _topic("rule_of_law", "全面依法治国", "全面依法治国要求科学立法、严格执法、公正司法和全民守法协同推进。", "法治体系通过规范权力、保障权利和稳定预期服务治理。", "依法治国不是机械执法，也不排斥德治的社会作用。", "行政机关公开执法依据能提高权力运行透明度。", "不能把党的领导、人民当家作主和依法治国割裂。", "科学立法、严格执法、公正司法、全民守法"),
            _topic("constitution", "宪法与根本制度", "宪法是国家根本法，规定根本制度、国家机构和公民基本权利义务。", "宪法通过最高法律效力统领普通法律并约束公权力。", "宪法与普通法律调整范围和效力层级不同。", "全国人大及其常委会承担宪法实施监督相关职责。", "不能把宪法原则和某一部门法条文混为一层。", "宪法、根本法、国家机构、公民权利"),
            _topic("peoples_congress", "人民代表大会制度", "人民代表大会制度是我国根本政治制度。", "人民通过选举产生代表，由国家权力机关统一行使国家权力。", "人民代表大会是国家权力机关，人民政协是统一战线组织。", "政府、监察、审判和检察机关由人大产生并受其监督。", "不能把人大代表个人意见等同于国家权力机关决定。", "人民代表大会、国家权力机关、监督、民主集中制"),
            _topic("cppcc", "中国人民政治协商会议", "人民政协是中国共产党领导的多党合作和政治协商重要机构。", "政治协商、民主监督和参政议政构成主要职能。", "政协不是国家权力机关，与人大制度定位不同。", "专题协商可围绕公共政策提出意见建议。", "不能把政协建议直接写成具有强制力的法律决定。", "人民政协、政治协商、民主监督、参政议政"),
            _topic("common_prosperity", "共同富裕", "共同富裕强调全体人民共享发展成果并逐步缩小不合理差距。", "高质量发展、基本公共服务和合理分配制度共同支撑目标。", "共同富裕不是平均主义，也不是少数人先富后固化差距。", "税收、社会保障和公益慈善形成多层次分配调节。", "不能脱离发展阶段承诺同步同等富裕。", "共同富裕、高质量发展、分配制度、公共服务"),
            _topic("new_development", "新发展理念", "创新、协调、绿色、开放、共享构成新发展理念。", "五个方面相互联系，共同回答发展动力、平衡、人与自然、内外联动和成果共享。", "绿色发展不只是末端治理，创新也不只是技术发明。", "产业升级需要同时考虑创新投入、区域协调和资源约束。", "不能把五个理念割裂成互不相关的口号。", "创新、协调、绿色、开放、共享"),
            _topic("ecological_civilization", "生态文明建设", "生态文明建设把资源环境承载力纳入发展决策。", "源头预防、过程控制、损害修复和责任追究形成治理链条。", "生态保护与经济发展不是简单二选一，而要推动绿色转型。", "河长制和生态补偿体现跨区域治理机制。", "不能只依靠个人节约替代产业与制度改革。", "生态文明、绿色发展、生态补偿、资源环境"),
            _topic("cultural_confidence", "文化自信", "文化自信建立在中华优秀传统文化、革命文化和社会主义先进文化基础上。", "创造性转化与创新性发展让文化资源回应当代生活。", "文化自信不等于文化封闭或拒绝交流互鉴。", "传统节日的现代公共表达可以连接历史记忆和当代价值。", "不能把继承传统理解为原样复制全部旧习。", "文化自信、创造性转化、创新性发展、交流互鉴"),
            _topic("community_future", "人类命运共同体", "人类命运共同体强调各国利益相互联系并通过合作应对共同挑战。", "对话协商、共建共享和多边合作构成实践方向。", "共同体理念尊重国家差异，不等于取消国家主权。", "气候变化和公共卫生治理需要跨国协调。", "不能把合作倡议解释为单方面输出制度模式。", "人类命运共同体、多边主义、全球治理、合作"),
        ],
    },
}


def _material_body(course_name: str, topic: dict[str, str], material_type: str) -> str:
    title = topic["title"]
    sections = [
        ("核心界定", f"{topic['definition']} 本节把“{title}”放在{course_name}的课程体系中理解，回答它研究什么、解决什么问题以及答题时应先写出的中心判断。关键词包括{topic['keywords']}。"),
        ("形成机制", f"{topic['mechanism']} 复习时要把条件、过程和结果按因果链展开，避免只有结论没有推理。若题目使用“为什么”“如何发生”等问法，应明确每一环如何推动下一环。"),
        ("概念辨析", f"{topic['contrast']} 对比题不能只列两个定义，还要在比较维度上说明相同点、不同点和适用条件。最常见维度包括目标、输入、过程、结果与局限。"),
        ("案例说明", f"{topic['example']} 案例的作用是把抽象概念落到可观察事实，但案例本身不能替代概念解释。作答时先指出案例对应哪个机制，再说明它支持什么结论。"),
        ("高频易错", f"{topic['pitfall']} 易错题通常利用相近术语、时间顺序、主体范围或因果倒置设置干扰。检查答案时应逐一核对对象、条件、时间和结论强度。"),
        ("证据组织", f"围绕{title}组织证据时，可使用“定义—机制—例证—限制”的四步结构。{topic['definition']} {topic['mechanism']} 最后补充{topic['pitfall']}，可以防止答案只剩口号。"),
        ("简答题模板", f"若题目要求解释{title}，第一句给出中心定义；第二段写关键机制：{topic['mechanism']}；第三段用案例支撑：{topic['example']}；结尾指出边界：{topic['pitfall']}。"),
        ("比较题模板", f"比较题先确定共同讨论对象，再选择稳定维度。可以把{title}与相邻概念放在目标、条件、方法、结果四栏中比较。核心区别提示是：{topic['contrast']}"),
        ("应用练习", f"练习一：用不超过一百字解释{title}。练习二：根据“{topic['example']}”判断涉及的关键概念。练习三：针对“{topic['pitfall']}”改写一段错误答案并说明理由。"),
        ("复习检查表", f"完成本资料后，应能准确写出{title}的定义，复述机制，完成一次比较，解释一个案例并识别一个陷阱。自测关键词为：{topic['keywords']}。若遗漏任一项，应回到对应章节补证据。"),
        ("综合联系", f"{title}不是孤立知识点。它可以与课程中的前因、并行概念和后续影响建立联系。联系时仍应以材料证据为准，不把外部常识或未经说明的现实案例直接写成课程结论。"),
        ("章节小结", f"本章围绕{title}形成完整复习链：{topic['definition']} 其运作或发展逻辑是：{topic['mechanism']}；与相邻概念的辨析重点是：{topic['contrast']}；典型案例是：{topic['example']}"),
    ]
    if material_type == "worked_examples":
        sections[8] = (
            "例题与解析",
            f"例题：请结合材料说明{title}的核心机制与边界。解析：先写“{topic['definition']}”，"
            f"再展开“{topic['mechanism']}”，随后引用“{topic['example']}”，最后用“{topic['pitfall']}”"
            "排除过度概括。评分点分别对应概念、过程、证据和限制。",
        )
    elif material_type == "common_mistakes":
        sections[4] = (
            "错题诊断",
            f"错误答案常写成“{title}只有一个原因并自动产生唯一结果”。这忽略了条件和边界。"
            f"正确修订应保留“{topic['mechanism']}”，并明确“{topic['pitfall']}”。"
            "订正时同时标出错误类型：主体错、时间错、因果倒置、范围过大或概念混淆。",
        )
    extensions = [
        f"边界补充：{topic['contrast']} 因此定义题不仅要写“是什么”，还要指出它不是什么，以及判断对象是否满足成立条件。",
        f"机制补充：可以把“{topic['mechanism']}”拆成起点、传导环节和结果三个节点，再检查案例“{topic['example']}”能否逐项对应。",
        f"辨析补充：先统一比较对象，再用目标、条件、主体、过程、结果五个维度建表。需要特别防止的错误是：{topic['pitfall']}",
        f"证据补充：案例只能证明与其范围相称的结论。“{topic['example']}”适合支持本节机制，但不能据此推导材料没有提供的外部事实。",
        f"错因补充：看到相近术语时先圈定主体和时间，再检查因果方向。若答案出现“必然、完全、唯一”等绝对词，应回到“{topic['pitfall']}”重新判断。",
        f"组织补充：完整证据链至少包含一个直接定义片段和一个机制或案例片段。关键词“{topic['keywords']}”用于定位材料，不应替代句子之间的逻辑。",
        f"表达补充：简答题每段只承担一个功能。定义段回答对象，机制段说明过程，案例段落地，限制段控制结论强度；中心内容仍是“{topic['definition']}”",
        f"评分补充：比较题若只写两列定义，通常缺少关系判断。高质量答案应明确共同点、差异点、适用条件，并用“{topic['contrast']}”作结。",
        f"练习补充：完成练习后，把答案中的每个判断回指到具体材料句。若某句只能依赖常识而找不到本资料证据，应删除、降格或明确标为资料不足。",
        f"自测补充：先遮住正文口述{title}，再用关键词检查遗漏。第二轮只看易错点修改答案，第三轮用案例验证是否真正理解，而非机械背诵。",
        f"联系补充：跨章节联系必须说明连接理由。可以从共同主体、连续时间、相似机制或相反结果建立关系，但不得只因两个术语同时出现就认定有因果。",
        f"总结补充：最终应形成可核查的四句话：概念是“{topic['definition']}”；机制是“{topic['mechanism']}”；例证是“{topic['example']}”；边界是“{topic['pitfall']}”",
    ]
    return f"# {title}\n\n" + "\n\n".join(
        (
            f"## {heading}\n\n{text}\n\n"
            f"复核任务：请围绕“{title}”重述本节的{heading}，"
            "并分别标出材料中的事实、解释、例子和限制。\n\n"
            f"{extensions[index]}\n\n"
            f"定向练习 {index + 1}：从本节找出一个能直接支持“{title}”的句子，"
            f"再写一个与“{heading}”有关但材料尚未支持的判断。前者保留为答案证据，"
            "后者应标记为待查或资料不足，不能依靠常识补全。"
        )
        for index, (heading, text) in enumerate(sections)
    )


def _write_materials(output_dir: Path, course_limit: int | None, topic_limit: int | None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    course_items = list(COURSES.items())[:course_limit]
    for course_id, course in course_items:
        for topic_index, topic in enumerate(course["topics"][:topic_limit]):
            material_type = MATERIAL_TYPES[topic_index % len(MATERIAL_TYPES)]
            relative = Path(course_id) / topic["key"] / f"{material_type}.md"
            path = output_dir / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            front_matter = "\n".join(
                [
                    "---",
                    f"course_id: {course_id}",
                    f"course_name: {course['name']}",
                    f"chapter_id: {topic['key']}",
                    f"material_type: {material_type}",
                    "synthetic: true",
                    f"corpus_version: {CORPUS_VERSION}",
                    f"title: {topic['title']}",
                    "---",
                    "",
                ]
            )
            path.write_text(
                front_matter
                + _material_body(course["name"], topic, material_type)
                + "\n",
                encoding="utf-8",
            )
            records.append(
                {
                    "course_id": course_id,
                    "course_name": course["name"],
                    "topic": topic,
                    "source_id": relative.as_posix(),
                }
            )
    return records


def _chunks_by_source(chunks: list[Any]) -> dict[str, list[Any]]:
    result: dict[str, list[Any]] = {}
    for chunk in chunks:
        result.setdefault(chunk.source_id, []).append(chunk)
    return result


def _primary_chunks(source_chunks: list[Any], topic: dict[str, str], count: int = 2) -> list[Any]:
    keyword = topic["title"]
    matching = [chunk for chunk in source_chunks if keyword in chunk.text]
    return (matching or source_chunks)[:count]


def _base_full_query(
    *,
    query_id: str,
    record: dict[str, Any],
    source_chunks: list[Any],
    query_type: str,
) -> EvaluationQuery:
    topic = record["topic"]
    primary = _primary_chunks(source_chunks, topic, 2)
    qrels = tuple(
        Qrel(chunk_id=chunk.chunk_id, relevance=2 if index == 0 else 1)
        for index, chunk in enumerate(primary)
    )
    prompts = {
        "exact_entity": f"{topic['title']}的核心定义和关键词是什么？",
        "paraphrase": f"不用照抄教材，解释一下{topic['title']}是怎样运作或发展的。",
        "summary": f"请按定义、机制、案例和易错点总结{topic['title']}。",
        "long_student_query": (
            f"我复习{record['course_name']}时总把相近概念混在一起。请结合资料说明"
            f"{topic['title']}的中心判断、形成机制、一个案例以及最容易写错的边界。"
        ),
    }
    return EvaluationQuery(
        query_id=query_id,
        query=prompts[query_type],
        course_id=record["course_id"],
        query_type=query_type,
        answerability="full",
        reference_answer=(
            f"{topic['definition']} {topic['mechanism']} 例子：{topic['example']} "
            f"边界：{topic['pitfall']}"
        ),
        relevant_source_ids=(record["source_id"],),
        qrels=qrels,
        evidence_requirements=(),
        expected_terms=tuple(
            term.strip() for term in topic["keywords"].split("、") if term.strip()
        )[:4],
    )


def _pair_query(
    *,
    query_id: str,
    left: dict[str, Any],
    right: dict[str, Any],
    chunks_by_source: dict[str, list[Any]],
    query_type: str,
) -> EvaluationQuery:
    left_chunk = _primary_chunks(chunks_by_source[left["source_id"]], left["topic"], 1)[0]
    right_chunk = _primary_chunks(chunks_by_source[right["source_id"]], right["topic"], 1)[0]
    if query_type == "comparison":
        query = (
            f"比较{left['topic']['title']}与{right['topic']['title']}，"
            "说明两者的核心含义、机制和不能混淆的地方。"
        )
    else:
        query = (
            f"把{left['topic']['title']}和{right['topic']['title']}串成一条复习逻辑，"
            "分别给出关键机制，并说明它们如何共同帮助理解本课程。"
        )
    return EvaluationQuery(
        query_id=query_id,
        query=query,
        course_id=left["course_id"],
        query_type=query_type,
        answerability="full",
        reference_answer=(
            f"{left['topic']['title']}：{left['topic']['definition']} "
            f"{right['topic']['title']}：{right['topic']['definition']} "
            f"辨析：{left['topic']['contrast']} {right['topic']['contrast']}"
        ),
        relevant_source_ids=(left["source_id"], right["source_id"]),
        qrels=(
            Qrel(chunk_id=left_chunk.chunk_id, relevance=2),
            Qrel(chunk_id=right_chunk.chunk_id, relevance=2),
        ),
        evidence_requirements=(
            EvidenceRequirement(
                requirement_id="left_concept",
                any_of_chunk_ids=(left_chunk.chunk_id,),
            ),
            EvidenceRequirement(
                requirement_id="right_concept",
                any_of_chunk_ids=(right_chunk.chunk_id,),
            ),
        ),
        expected_terms=(left["topic"]["title"], right["topic"]["title"]),
    )


def _seed_queries(
    records: list[dict[str, Any]],
    chunks_by_source: dict[str, list[Any]],
    *,
    per_course_limit: int,
) -> list[EvaluationQuery]:
    by_course: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_course.setdefault(record["course_id"], []).append(record)
    queries: list[EvaluationQuery] = []
    for course_id, course_records in by_course.items():
        course_queries: list[EvaluationQuery] = []
        query_types = ("exact_entity", "paraphrase", "summary", "long_student_query")
        for index, record in enumerate(course_records[:12]):
            course_queries.append(
                _base_full_query(
                    query_id=f"{course_id}-topic-{index + 1:02d}",
                    record=record,
                    source_chunks=chunks_by_source[record["source_id"]],
                    query_type=query_types[index % len(query_types)],
                )
            )
        pair_offsets = (
            (
                (0, 1, "comparison"),
                (2, 3, "multi_concept"),
            )
            if per_course_limit < 20
            else (
                (0, 1, "comparison"),
                (2, 3, "comparison"),
                (4, 5, "multi_concept"),
                (6, 7, "multi_concept"),
            )
        )
        for pair_index, (left_index, right_index, query_type) in enumerate(pair_offsets, 1):
            if right_index >= len(course_records):
                continue
            course_queries.append(
                _pair_query(
                    query_id=f"{course_id}-pair-{pair_index:02d}",
                    left=course_records[left_index],
                    right=course_records[right_index],
                    chunks_by_source=chunks_by_source,
                    query_type=query_type,
                )
            )
        partial_records = (
            course_records[-1:]
            if per_course_limit < 20
            else course_records[8:10]
        )
        for partial_index, record in enumerate(partial_records, 1):
            primary = _primary_chunks(
                chunks_by_source[record["source_id"]],
                record["topic"],
                1,
            )[0]
            course_queries.append(
                EvaluationQuery(
                    query_id=f"{course_id}-partial-{partial_index:02d}",
                    query=(
                        f"资料是否能完整说明{record['topic']['title']}，"
                        "并给出本校今年任课教师未公开的期末原题和标准答案？"
                    ),
                    course_id=course_id,
                    query_type="long_student_query",
                    answerability="partial",
                    reference_answer=(
                        f"资料只能支持课程概念：{record['topic']['definition']} "
                        "不包含本校未公开的期末原题。"
                    ),
                    relevant_source_ids=(record["source_id"],),
                    qrels=(Qrel(chunk_id=primary.chunk_id, relevance=1),),
                    evidence_requirements=(),
                    expected_terms=(record["topic"]["title"],),
                )
            )
        distractor_chunks = [
            chunks_by_source[record["source_id"]][0]
            for record in course_records[:3]
        ]
        none_prompts = (
            (
                "请根据复习资料给出明天本市精确到分钟的降雨开始时间。",
            )
            if per_course_limit < 20
            else (
                "请根据复习资料给出明天本市精确到分钟的降雨开始时间。",
                "请根据课程资料预测下一期彩票开奖的全部号码。",
            )
        )
        for none_index, prompt in enumerate(none_prompts, 1):
            course_queries.append(
                EvaluationQuery(
                    query_id=f"{course_id}-none-{none_index:02d}",
                    query=prompt,
                    course_id=course_id,
                    query_type="out_of_scope",
                    answerability="none",
                    reference_answer="",
                    relevant_source_ids=(),
                    qrels=tuple(
                        Qrel(chunk_id=chunk.chunk_id, relevance=0)
                        for chunk in distractor_chunks
                    ),
                    evidence_requirements=(),
                    expected_terms=(),
                )
            )
        queries.extend(course_queries[:per_course_limit])
    return queries


def _pool_qrels(
    queries: list[EvaluationQuery],
    *,
    corpus_dir: Path,
    chunks_by_source: dict[str, list[Any]],
) -> list[EvaluationQuery]:
    old_vector_provider = settings.rag_vector_store_provider
    old_reranker_key = settings.rag_reranker_api_key
    old_reranker_url = settings.rag_reranker_base_url
    settings.rag_vector_store_provider = "memory"
    settings.rag_reranker_api_key = ""
    settings.rag_reranker_base_url = ""
    try:
        retriever = LocalRAGRetriever(corpus_dir, embeddings=HashEmbeddings())
        pooled: list[EvaluationQuery] = []
        for query in queries:
            qrel_map = {qrel.chunk_id: qrel.relevance for qrel in query.qrels}
            candidate_hits: dict[str, dict[str, Any]] = {}
            for mode in (
                "embedding_only",
                "bm25_only",
                "hybrid_rrf",
                "hybrid_rerank",
            ):
                for hit in retriever.retrieve(
                    query.query,
                    top_k=20,
                    mode=mode,
                    allow_reranker_fallback=True,
                ):
                    metadata = dict(hit.get("metadata") or {})
                    chunk_id = str(hit.get("chunk_id") or metadata.get("chunk_id") or "")
                    if chunk_id:
                        candidate_hits[chunk_id] = hit
            relevant_sources = set(query.relevant_source_ids)
            for chunk_id, hit in candidate_hits.items():
                if chunk_id in qrel_map:
                    continue
                metadata = dict(hit.get("metadata") or {})
                source = str(metadata.get("source_id") or metadata.get("source") or "")
                qrel_map[chunk_id] = 1 if source in relevant_sources else 0
            pooled.append(
                replace(
                    query,
                    qrels=tuple(
                        Qrel(chunk_id=chunk_id, relevance=relevance)
                        for chunk_id, relevance in sorted(
                            qrel_map.items(),
                            key=lambda item: (-item[1], item[0]),
                        )
                    ),
                )
            )
        return pooled
    finally:
        settings.rag_vector_store_provider = old_vector_provider
        settings.rag_reranker_api_key = old_reranker_key
        settings.rag_reranker_base_url = old_reranker_url


def generate_dataset(output_dir: Path, *, profile: str) -> dict[str, Any]:
    if profile == "pilot":
        course_limit = 2
        topic_limit = 5
        per_course_limit = 10
        dataset_version = f"{DATASET_VERSION}-pilot"
    else:
        course_limit = None
        topic_limit = None
        per_course_limit = 20
        dataset_version = DATASET_VERSION
    output_dir.mkdir(parents=True, exist_ok=True)
    records = _write_materials(output_dir, course_limit, topic_limit)
    _, _, corpus_manifest = write_corpus_artifacts(output_dir)
    _, chunks = load_frozen_chunks(output_dir)
    chunks_by_source = _chunks_by_source(chunks)
    queries = _seed_queries(
        records,
        chunks_by_source,
        per_course_limit=per_course_limit,
    )
    queries = _pool_qrels(
        queries,
        corpus_dir=output_dir,
        chunks_by_source=chunks_by_source,
    )
    assignments = stratified_split(queries)
    queries = [
        replace(query, split=assignments[query.query_id])
        for query in queries
    ]
    dataset_path = output_dir / "golden_queries.jsonl"
    dataset_path.write_text(
        "".join(
            json.dumps(query.to_json(), ensure_ascii=False, sort_keys=True) + "\n"
            for query in queries
        ),
        encoding="utf-8",
    )
    dataset_manifest = build_dataset_manifest(
        queries,
        dataset_version=dataset_version,
        corpus_manifest_sha256=corpus_manifest["manifest_sha256"],
    )
    dataset_manifest.update(
        {
            "profile": profile,
            "synthetic": True,
            "annotation_method": (
                "synthetic topic truth plus four-mode Top-20 pooling; "
                "relevant source chunks receive graded labels"
            ),
            "human_review_status": "synthetic_unreviewed",
        }
    )
    manifest_path = output_dir / "dataset_manifest.json"
    manifest_path.write_text(
        json.dumps(dataset_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return {
        "profile": profile,
        "output_dir": str(output_dir.resolve()),
        "source_count": corpus_manifest["source_count"],
        "chunk_count": corpus_manifest["chunk_count"],
        "query_count": len(queries),
        "development_count": dataset_manifest["development_count"],
        "test_count": dataset_manifest["test_count"],
        "corpus_manifest_sha256": corpus_manifest["manifest_sha256"],
        "dataset_sha256": dataset_manifest["dataset_sha256"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate deterministic synthetic course RAG corpus and golden set."
    )
    parser.add_argument(
        "--profile",
        choices=("pilot", "full", "both"),
        default="both",
    )
    parser.add_argument(
        "--pilot-dir",
        type=Path,
        default=Path("data/rag/course_pilot"),
    )
    parser.add_argument(
        "--full-dir",
        type=Path,
        default=Path("data/rag/course_v1"),
    )
    args = parser.parse_args()
    results = []
    if args.profile in {"pilot", "both"}:
        results.append(generate_dataset(args.pilot_dir, profile="pilot"))
    if args.profile in {"full", "both"}:
        results.append(generate_dataset(args.full_dir, profile="full"))
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
