"""Product-independent full-background replacement requirements.

These are production/review requirements, not claims of a trained renderer or
proof that a material was recognized. Material selection uses actual assets.
"""
from copy import deepcopy
import json

RULE_ID = 'user-universal-product-live-background-20261007'
VERSION = 1
BACKGROUND_CHECKS = ('background_completeness', 'edge_quality', 'lighting_contact',
                     'material_response', 'camera_perspective', 'temporal_background')
MATERIAL_ROUTES = [
    {'material': 'opaque', 'label': '不透明硬质商品',
     'method': '连续分割与精细抠像；保留商品结构、标签和动作，匹配新场景光向、色温与接触阴影。'},
    {'material': 'transparent', 'label': '透明及半透明商品',
     'method': '分别处理外轮廓、透射、折射和内部旧环境；单一蒙版贴背景不足以完成换景。'},
    {'material': 'reflective', 'label': '金属及高反光商品',
     'method': '检查高光与环境反射，匹配新场景；修改反光不得重绘标识、改变形状或材料质感。'},
    {'material': 'thin_openwork', 'label': '细杆、网孔及镂空商品',
     'method': '保护细小部件和端点，替换孔隙内旧背景；逐帧检查漏抠、断裂、黑白边及闪烁。'},
    {'material': 'soft_fiber', 'label': '织物、毛绒及柔性商品',
     'method': '精细透明度保留纤维、软边及形变；检查去色污染与运动模糊，避免硬切边。'},
    {'material': 'articulated_contact', 'label': '机械活动及手持操作商品',
     'method': '逐帧保留关节、接触、遮挡次序和真实动作；恢复显露背景，检查支撑与空间关系。'},
]


def workflow_contract():
    return {
        'version': VERSION, 'rule_id': RULE_ID, 'scope': 'all_product_categories',
        'goal': '完整替换背景，商品完整、动作真实，合成具有实拍观感。',
        'material_status': 'must_assess_actual_assets',
        'material_routes': deepcopy(MATERIAL_ROUTES),
        'steps': ['核对同款原素材与最新反馈', '依据实际画面确认材质组合和遮挡',
                  '锁定商品结构与真实动作，制作完整新环境',
                  '处理轮廓、孔隙、透明区域、反射及接触光影',
                  '匹配镜头与场景运动，检查全部连续帧及关键细节原尺寸裁图',
                  '逐项验收后同步导出Live、预览与账号记录',
                  '记录失败帧、修正参数、对照版本和用户确认，供后续同材质商品复用'],
        'acceptance_checks': list(BACKGROUND_CHECKS),
        'fallback_policy': '效果不足保留待修正并记录具体缺口；保留旧背景、虚化铺底或裁掉商品不能记为完整换景完成。',
        'learning_record': ['product_id', 'source_hashes', 'material_evidence', 'model_version',
                            'parameters', 'failed_frames', 'defects', 'before_after',
                            'review_result', 'user_confirmed'],
        'benchmark': '固定同源输入按六类材质及混合材质比较；记录通过率、缺件/残边/闪烁及成本。未实测项标待测试。',
        'completion_claim': '自动检查和模型判断不等于用户确认，也不代表模型权重已训练。',
    }


BACKGROUND_REVIEW_PROMPT = '''
所有商品的场景真实感也必须逐项检查，不能只看主体完整或Live格式。
background_completeness：完整替换目标下检查主体外、孔隙内和透明区是否残留旧背景；虚化铺底不等于完整换景。
edge_quality：检查黑白边、缺件、漏抠、锯齿、旧背景色污染；细节看不清判uncertain。
lighting_contact：光向、色温、景深和接触阴影是否协调，有无漂浮或贴纸感。
material_response：按实际材质检查透射、折射、环境反射、金属高光、织物软边；未知材质或不可辨认判uncertain。
camera_perspective：商品与新场景透视、尺度、支撑位置及相机运动是否一致。
temporal_background：检查每帧的轮廓抖动、背景滑动、穿帮、显露区域和帧间光影变化。
subject_observations每项保留checks，另加background_checks，包含以下全部项目及具体可见依据：
''' + json.dumps({key: {'status': 'pass|fail|uncertain', 'evidence': '具体画面/帧依据'}
                  for key in BACKGROUND_CHECKS}, ensure_ascii=False) + '''。
原环境素材不虚构发生过换景，按实际画面检查自然空间关系；静态图注明不涉及动态。
用户指定纯文字封面可逐项注明不涉及商品场景。任何fail或uncertain都保留待修正。
不能因输出规格正确、蒙版覆盖完整或核心像素未变就判实拍观感通过。
'''
