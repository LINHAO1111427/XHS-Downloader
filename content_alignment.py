"""Bind consumer copy to observed media, independently of technical rendering success."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from xhs_operations import OperationError

VERSION = 1
CHECKS = ('title', 'body', 'sequence', 'appeal')

PLANNING_PROMPT = '''
创作顺序：先从实际素材和已确认反馈找出一个读者想看的点，再共同设计标题、首句和画面。
angle只是候选提示，不能为了完成每日数量生搬硬套。先看可见证据，不要先编卖点再找图配。
一篇只推进一个欲望/问题/满足感；各张图或片段是这个主题的展开，不是商品目录。
例如“差一颗”需要能看见明确空位以及补齐过程；“粉色心动”不能后半篇换成白色笔；
“一排排满”的正文要由落豆到排齐的动作兑现。AI场景能承接配色和生活想象，不能证明实拍性能。
JSON必须另加creative_brief：
{"audience":"具体读者","desire":"他此刻想看或解决什么", "promise":"本篇唯一的观看承诺",
 "first_frame":"缩略封面/首3秒里兑现标题的具体可见细节",
 "progression":"后续内容如何逐步兑现同一个点，而不是换主题",
 "reference_ids":["本次检索到的知识/案例ID"],"feedback_ids":["实际采用的本账号反馈run_id；无则空"],
 "hypothesis":"本次待验证的吸引点","changed_variable":"这次主要测试一个什么变化"}。
每个images或clips元素另加copy_anchor（title或body中逐字摘录的短语）和
viewer_payoff（这一张/段为该短语补充什么可见信息）。第0项必须引用标题中的短语。
这些字段用于创作和复盘，不进入发布文案。不得杜撰来源ID，不把生成稿或主观评分当成真实爆款。
'''

AUDIT_PROMPT = '''
CONTENT_ALIGNMENT_REVIEW：另行核对吸引点和文案画面对应。以实际交付的缩略封面、配图和连续抽帧为准，
分镜描述、来源标题、原先passed=true与用户认可文案都不是画面正确的证据。
先逐项客观观察，再判断：标题的具体承诺是否在第0项兑现；正文每个动作/结果是否确实出现；
整组是否推进同一个点，是否夹杂无关的商品结构展示来凑六张；目标读者有没有具体的点击和继续看理由。
不要把色彩相近当同款同色，不把下豆当装豆，不把满板当缺一颗，不把AI摆拍当真实功能验证。
同类参考只能证明同类动作，不能据此声称在售款性能。镜头微动不是商品动作。
不要因为不喜欢某种审美、词语或短文案就判失败；必须写出具体可见的错配或信息缺失。
不能通过把标题改成空泛的“好看/看看这个工具”来掩盖不连贯素材。
反馈按原适用场景使用：粉色/同一商品身份主题才要求全篇同色同款；明确标注同类参考、
不宣称同一支商品连续操作的动作合集，可以有不同颜色工具，不能仅据此判不连贯。
仍须逐段推进同一个可见动作/满足感；对照、合集与单一商品故事分别判断，不能一律要求说明书式介绍。
根JSON的passed/issues只填技术/结构问题；另外返回alignment对象，完整结构如下：
{"observations":[{"index":0,"observed":"实际看见什么，不能抄分镜",
 "copy_anchor":"对应标题/正文的原文片段；不对应则空字符串",
 "contributes":true,"reason":"这一张/段怎样推进主题；不对应时缺什么"}],
 "checks":[{"target":"title","supported":true,"evidence":"具体引用第几张/段的观察",
 "repair":"none","suggestion":""},
 {"target":"body","supported":true,"evidence":"动作/结果逐一核对依据","repair":"none","suggestion":""},
 {"target":"sequence","supported":true,"evidence":"整组的情绪或信息推进","repair":"none","suggestion":""},
 {"target":"appeal","supported":true,"evidence":"目标读者为什么愿意点开和继续看","repair":"none","suggestion":""}]}。
observations恰好覆盖所有media_count个index，从0开始，不得遗漏/重复。
checks恰好覆盖title/body/sequence/appeal。supported与contributes必须为布尔值。
不通过时repair取copy或media并给出具体suggestion；通过时repair为none。
只有现有画面已经连贯、主体正确、吸引点具体，只是文字描述写错时才用copy；
缺少标题所需动作/结果、主体换色、无关片段、开场不对应时用media，明确所缺画面。
用户锁定文案时保留原文，针对媒体给出修正建议。这里的检查仅判断创作一致性，不预测流量或成交。
'''

REWRITE_PROMPT = '''
CONTENT_ALIGNMENT_REPAIR：基于已经逐张观察过的交付媒体修正文案。
先读取本次本地知识、商品事实、同品类完整案例、最新用户反馈，再读取alignment中的实际观察。
保持原有具体情绪与核心主题，只修正画面不支持的文字；禁止换成泛泛的结构介绍来混过检查。
不要虚构使用经历、价格、性能、效果、销量。只使用媒体实际体现的动作/结果。
返回纯JSON：{"title":"自然口语标题","body":"完整短正文","topics":["#话题"],
 "creative_brief":{...},"anchors":[{"index":0,"copy_anchor":"新标题或正文原文短语",
 "viewer_payoff":"该画面对应的信息"}]}。
creative_brief沿用创作方案字段，修正与现有画面矛盾的描述。来源ID只能用本次实际提供的ID。
anchors恰好覆盖原分镜全部index。第0项引用新标题，后续每项引用新标题或正文。
不改媒体、不改原音频或字幕；如果成片内文字也有错配，需要改媒体，不用正文掩盖。
'''


def reference_ids(run):
    return {s['id'] for key in ('retrieval_sources', 'corpus_sources', 'benchmark_sources')
            for s in run.get(key, []) if s.get('id')}


def validate_direction(plan, content_type, references=None, feedback=None):
    brief = plan.get('creative_brief')
    if not isinstance(brief, dict):
        raise OperationError('创作方案缺少读者吸引点与画面承诺')
    for key in ('audience', 'desire', 'promise', 'first_frame', 'progression', 'hypothesis', 'changed_variable'):
        if not isinstance(brief.get(key), str) or not brief[key].strip() or len(brief[key]) > 1000:
            raise OperationError('创作方案缺少明确的 ' + key)
    for key, allowed in [('reference_ids', references), ('feedback_ids', feedback)]:
        values = brief.get(key)
        if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
            raise OperationError('创作依据ID格式有误')
        if allowed is not None and (not set(values).issubset(allowed) or (key == 'reference_ids' and allowed and not values)):
            raise OperationError('创作方案未引用实际检索到的知识或反馈')
    cards = plan.get('images' if content_type == 'graphic' else 'clips')
    if not isinstance(cards, list) or not cards:
        raise OperationError('创作方案缺少对应的分镜')
    copy = plan.get('title', '') + '\n' + plan.get('body', '')
    for i, card in enumerate(cards):
        anchor, payoff = card.get('copy_anchor'), card.get('viewer_payoff')
        if (not isinstance(anchor, str) or not anchor.strip() or anchor not in (plan.get('title', '') if i == 0 else copy)
                or not isinstance(payoff, str) or not payoff.strip() or len(payoff) > 1000):
            raise OperationError(f'第{i+1}张/段缺少与发布文案逐字对应的画面用途')


def validate_audit(value, count, plan):
    if not isinstance(value, dict):
        raise OperationError('缺少逐张文案与画面检查结果')
    observations, checks = value.get('observations'), value.get('checks')
    if not isinstance(observations, list) or len(observations) != count or not count:
        raise OperationError('文案画面检查遗漏了交付内容')
    indexes = [o.get('index') for o in observations if isinstance(o, dict)]
    if any(type(i) is not int for i in indexes) or sorted(indexes) != list(range(count)):
        raise OperationError('文案画面检查的图片/片段索引有误')
    issues = []
    copy = plan['title'] + '\n' + plan['body']
    for item in observations:
        if (type(item.get('contributes')) is not bool or any(not isinstance(item.get(k), str) or not item[k].strip()
                for k in ('observed', 'reason')) or not isinstance(item.get('copy_anchor'), str)):
            raise OperationError('文案画面检查缺少实际观察依据')
        if item['contributes'] and (not item['copy_anchor'].strip() or item['copy_anchor'] not in copy):
            raise OperationError('画面检查引用了发布文案中不存在的内容')
        if not item['contributes']:
            issues.append({'index': item['index'], 'reason': item['reason'], 'repair_target': 'media', 'replacement_caption': ''})
    if (not isinstance(checks, list) or len(checks) != len(CHECKS)
            or {c.get('target') for c in checks if isinstance(c, dict)} != set(CHECKS)):
        raise OperationError('文案画面检查未覆盖标题、正文、递进和吸引点')
    for check in checks:
        if (type(check.get('supported')) is not bool or not isinstance(check.get('evidence'), str)
                or not check['evidence'].strip() or not isinstance(check.get('suggestion'), str)
                or check.get('repair') not in ('none', 'copy', 'media')):
            raise OperationError('文案画面检查结论格式有误')
        if check['supported'] != (check['repair'] == 'none'):
            raise OperationError('文案画面检查结论与修正目标矛盾')
        if not check['supported']:
            if not check['suggestion'].strip():
                raise OperationError('文案画面检查缺少具体修正建议')
            issues.append({'index': 0, 'reason': check['suggestion'], 'repair_target': check['repair'],
                           'target': check['target'], 'replacement_caption': ''})
    return {**value, 'version': VERSION, 'passed': not issues}, issues


def fingerprint(plan, outputs, resolve):
    # Include burned-in caption/audio plans and final bytes: stale model approval cannot survive edits.
    content = {key: plan.get(key) for key in ('title', 'body', 'topics', 'creative_brief', 'images', 'clips', 'audio_spine')}
    media = []
    for output in outputs:
        hashes = {}
        for key in ('path', 'motion_path', 'preview_path'):
            if output.get(key):
                with Path(resolve(output[key])).open('rb') as stream:
                    hashes[key] = hashlib.file_digest(stream, 'sha256').hexdigest()
        if 'path' not in hashes:
            raise OperationError('交付内容缺少媒体文件')
        media.append({'files': hashes, 'ai_generated': output.get('ai_generated'),
                      'source_identity': output.get('source_identity'), 'source_run_id': output.get('source_run_id')})
    return hashlib.sha256(json.dumps([content, media], ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def validate_delivery(run, resolve):
    plan = run['plan']
    if not plan.get('content_alignment_version'):
        return  # Historical packages retain their original review status until explicitly rechecked.
    review = plan.get('alignment_review') or {}
    count = len(run['outputs']) if run['content_type'] == 'graphic' else review.get('media_count', 0)
    checked, _ = validate_audit(review, count, plan)
    if (plan.get('quality_review', {}).get('passed') is not True or not checked['passed']
            or review.get('fingerprint') != fingerprint(plan, run['outputs'], resolve)):
        raise OperationError('文案与画面尚未对应，或内容已变更；请重新检查后打包')


def copy_repairable(run, review):
    return (not run['plan'].get('copy_locked') and not run.get('publication') and not run.get('published_url')
            and run['state'] != 'published' and review.get('issues')
            and all(i.get('repair_target') == 'copy' for i in review['issues'])
            and run['plan'].get('copy_repair_attempts', 0) < 1)
