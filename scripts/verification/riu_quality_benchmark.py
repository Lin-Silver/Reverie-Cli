"""Fixed real-model RIU benchmark through the production native Desktop.

The loopback recorder forwards unchanged JSON to the configured provider endpoint.
It never authors or repairs HTML. Raw requests, native SSE, sessions and failed
attempts are retained. Credentials are removed from all isolated config backups.
"""
from __future__ import annotations

import argparse
import copy
import codecs
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import os
from pathlib import Path
from contextlib import contextmanager
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ReverieCli-py"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from desktop_process import launch_options, stop_process, wait_for_packaged_page
TASK_FILE = Path(__file__).with_name("fixtures") / "riu-natural-tasks.json"


def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def prepare_isolated_workspace(workspace):
    """Keep parent repository instructions out of a fresh quality sample."""
    workspace = Path(workspace).resolve()
    if any(workspace.iterdir()):
        raise ValueError('Quality workspace must be empty before initialization')
    subprocess.run(['git', '-c', 'init.templateDir=', '-c', 'init.defaultBranch=verification',
                    'init', '--quiet', str(workspace)], check=True, capture_output=True)
    from reverie.context_engine.workspace import detect_workspace_profile
    profile = detect_workspace_profile(workspace)
    if Path(profile.vcs_root).resolve() != workspace or profile.instruction_layers:
        raise RuntimeError('Fresh quality workspace inherited unrelated repository context')
    return {'vcs_root': profile.vcs_root, 'instruction_layers': [], 'fresh_repository': True}


def configure_model_source(cfg, original, source, model, *, recorder_url=None, api_url=None):
    cfg.active_model_source = source
    if source == 'standard':
        from reverie.config import ModelConfig
        cfg.models = [ModelConfig(model, model, recorder_url or api_url, '')]
        cfg.active_model_index = 0
        return
    provider = copy.deepcopy(getattr(original, source))
    provider['selected_model_id'] = model
    if api_url:
        provider['api_url'] = api_url
    if recorder_url:
        provider['api_url'] = recorder_url
        provider['endpoint'] = '/chat/completions'
    setattr(cfg, source, provider)


def tool_scope_violations(names, fixture, task):
    if task['id'] == 'text':
        return list(names)
    if 'forbidden_tools' in fixture:
        return [name for name in names if name in fixture['forbidden_tools']]
    return [name for name in names if name not in ['create_file', 'render_view']]


def quality_outcome(checks, violations, repairs, *, generation_only=False):
    if violations:
        return 'model_violation'
    if generation_only:
        return 'registered_unvalidated'
    if not checks or not all(check['passed'] for check in checks):
        return 'semantic_failure'
    return 'repaired_success' if repairs else 'first_pass'


def record_service_incidents(case):
    """Keep recovered errors without replacing a complete quality verdict."""
    requests = case.get('requests', [])
    case['upstream_stream_errors'] = [r['upstream_stream_error'] for r in requests if r.get('upstream_stream_error')]
    case['transport_incidents'] = [r['transport_error'] for r in requests if r.get('transport_error')
                                   and r.get('transport_error_origin', 'upstream') != 'downstream']
    case['downstream_disconnects'] = [r['transport_error'] for r in requests if r.get('transport_error')
                                      and r.get('transport_error_origin') == 'downstream']
    if case.get('outcome') not in {'timeout', 'first_pass', 'repaired_success', 'model_violation', 'host_routing_violation'}:
        if case['upstream_stream_errors']:
            case['outcome'] = 'service_unavailable'
        if case['transport_incidents']:
            case['outcome'] = 'service_transport_error'


class MissingBusinessControl(ValueError):
    """A rendered answer has no usable accessible control for the task."""


def classify_quality_error(error, phase):
    """Attribute model HTTP failures without interpreting browser log numbers."""
    if isinstance(error, MissingBusinessControl):
        return 'semantic_failure'
    if not phase.startswith('model-'):
        return 'validator_or_product_error'
    if '[empty-provider-stream]' in str(error):
        return 'service_transport_error'
    if isinstance(error, TimeoutError):
        return 'timeout'
    status = getattr(error, 'status_code', None)
    if status is None:
        status = getattr(getattr(error, 'response', None), 'status_code', None)
    if isinstance(status, int) and 400 <= status <= 599:
        return 'service_unavailable'
    if re.search(r'\bHTTP(?:/\d(?:\.\d)?)?(?:\s+(?:error|status(?:\s+code)?))?\s*[:=]?\s*(?:4\d\d|5\d\d)\b', str(error), re.I):
        return 'service_unavailable'
    return 'validator_or_product_error'


def quality_repair_feedback(checks):
    """Describe observable failures without supplying code or tool instructions."""
    labels = {
        'registered-view': '当前对话里没有可以直接操作的回答',
        'required-numeric-control': '数值控件缺少有效实值，默认值和恢复值不能只放在占位提示中',
        'required-accessible-control': '必需的输入控件没有可用的文字标签',
        'initial-business-result': '初始参数对应的结果不正确',
        'local-recalculation': '改变输入后结果没有正确更新',
        'invalid-input-feedback': '负数输入没有被拒绝或明确标为无效',
        'zero-state': '输入为零时结果或空状态不正确',
        'restored-business-result': '重新打开后输入保留了，但显示的结果没有按这些输入重新计算',
        'selected-route-state-reload': '重新打开后选中的路线丢失',
        'selected-route-process-restart-recovery': '退出并重新启动应用后选中的路线丢失',
        'empty-data-feedback': '没有匹配数据时缺少明确提示',
        'live-host-theme': '页面没有跟随应用切换深浅主题',
        'readable-text-before-theme': '当前主题中部分文字或输入值与所在卡片背景对比过低，难以阅读',
        'readable-text-after-theme': '切换深浅主题后部分文字或输入值与所在卡片背景对比过低，难以阅读',
        'saved-state-reload': '重新打开后主要输入没有保留',
        'all-control-state-reload': '重新打开后部分输入或选项丢失',
        'actual-process-restart-recovery': '退出并重新启动应用后主要输入丢失',
        'all-control-process-restart-recovery': '退出并重新启动应用后部分输入或选项丢失',
        'modified-view-registration': '刚才要求的修改没有出现在当前可操作的回答里',
        'stored-version-history': '修改没有保留刚才那一份回答的版本关系',
        'replacement-version-provenance': '修改另开了回答，没有更新刚才那一份',
        'business-controls-operable': '业务控件不能按可见标签完成所需操作',
        'layout-pip-primary-result': '画中画小窗口首屏看不到主要结果数值，请把数值汇总和关键输入集中到顶部，图表与辅助明细放在后面',
        'layout-pip': '画中画小窗口首屏不能完整显示主要输入控件，请把主要结果和关键输入集中到顶部',
        'layout-pip-controls': '画中画小窗口首屏有业务输入被截断或放在屏外，请把主要结果和关键输入集中到顶部',
        'mode-preserves-controls-fullscreen': '切换到工作面板后输入或选项被重置',
        'mode-preserves-controls-pip': '切换到画中画后输入或选项被重置',
        'mode-preserves-controls-inline': '切回对话后输入或选项被重置',
        'invalid-budget-feedback': '负预算没有被拒绝或明确标为无效',
        'valid-submission': '报名成功后的确认没有正确显示姓名、邮箱、人数和当前总价',
        'form-reentry-action': '报名成功后缺少可用的编辑信息或再次报名入口',
        'chart-visible-bars': '正倍率时柱状图没有实际显示，可能仍被空状态或错误提示遮挡',
        'chart-readable-data': '月份明细没有按当前倍率显示正确数据',
        'falsy-control-state-reload': '重新打开后零值或取消勾选的状态丢失',
        'distance-filter': '改变最多步行距离后，路线没有按预算和距离共同筛选',
        'selection-feedback': '选择路线后没有明确显示实际选择的方案',
        'selectable-routes': '符合条件的路线缺少可操作的选择入口',
        'default-price-order': '商品初始顺序没有按价格从低到高排列',
        'keyword-filters-data': '按关键词筛选后的商品不正确',
        'sort-descending': '切换到价格降序后的商品顺序不正确',
        'stock-filter': '只看有库存时显示的商品不正确',
        'combined-table-filters': '关键词和库存条件没有同时生效',
        'natural-language-price-filter': '新增价格上限与关键词、库存的组合筛选不正确',
        'new-price-filter-default': '新增价格上限的默认值不符合要求',
        'clear-filter-action': '没有匹配商品时，清除筛选不能恢复商品列表',
        'default-combined-filter': '初始路线没有按当前预算和步行距离共同筛选',
        'both-route-constraints': '默认预算、步行距离或符合条件的路线不正确',
        'round-trip-default': '新增的往返开关没有默认选中',
        'round-trip-changes-formula': '取消往返后费用没有按每天单程一次更新',
        'round-trip-controls-daily-count': '其他次数输入覆盖了往返规则：选中时应始终每天两次，取消时一次',
        'sort-state-reload': '重新打开后价格排序丢失',
        'sort-state-falsy-reload': '取消勾选后重新打开，价格排序丢失',
        'sort-process-restart-recovery': '退出并重新启动应用后价格排序丢失',
        'required-field-validation': '报名时没有检查空姓名和邮箱',
        'email-validation': '报名时没有拒绝无效邮箱',
        'name-length-validation': '姓名超过二十字时没有限制或提示',
        'people-range-validation': '报名时没有拒绝零人数',
        'people-maximum-validation': '报名时没有拒绝超过五人的人数',
        'keyboard-focus': '无法用键盘聚焦主要输入控件',
        'no-horizontal-overflow': '窄窗口出现了横向溢出',
        'fare-recalculation': '改变单次票价后年度费用没有正确更新',
        'months-recalculation': '改变年通勤月数后年度费用没有正确更新',
        'fare-zero-state': '票价为零时年度费用不为零',
        'months-zero-state': '月数为零时年度费用不为零',
        'fare-invalid-input': '负票价没有被拒绝或明确标为无效',
        'months-invalid-input': '负月数没有被拒绝或明确标为无效',
        'two-decimal-currency': '费用没有保留两位小数',
    }
    problems = []
    for check in checks:
        if check.get('passed'):
            continue
        key = check['name'].removeprefix('modified-')
        label = labels.get(check['name'], labels.get(key, '部分业务交互或显示检查没有通过'))
        if key.startswith('readable-state-'):
            label = '错误、空状态或成功确认中有文字与自身背景对比过低，请检查深浅主题及滚动后显示的按钮和提示'
        elif key.startswith('theme-state-'):
            label = '切换深浅主题时，当前输入、选择或表单状态被改变'
        elif key == 'route-choice-action':
            label = '符合条件的方案缺少实际可操作的选择控件'
        elif key == 'route-choice-keyboard-accessible':
            label = '选择方案的控件不能通过键盘聚焦和操作'
        if label not in problems:
            problems.append(label)
    return ('刚才的回答还有这些问题：' + '；'.join(problems) + '。'
            '请修好当前这份回答，保留原任务的数据、默认值和验证要求，'
            '让我可以直接在当前对话里操作，并检查输入变化、错误提示和重新打开后的状态。')


def run_quality_stage(case, phase, prompt, send, assess, max_repairs, *, checkpoint=None):
    """Keep every attempt; only normal feedback turns consume the shared budget."""
    attempt = 0
    while True:
        stage = phase if not attempt else f"{phase}-repair-{case['repair_count']}"
        checks = []
        evidence = {'stage': stage, 'phase': phase, 'checks': checks}
        case.setdefault('stages', []).append(evidence)
        if checkpoint:
            checkpoint()
        try:
            saved = send(prompt, stage)
            value = assess(saved, stage, checks.append)
        except Exception as error:
            evidence.update(passed=False, error=type(error).__name__ + ': ' + str(error))
            if checkpoint:
                checkpoint()
            raise
        evidence['passed'] = bool(checks) and all(c['passed'] for c in checks) and not case.get('violations')
        if value and value.get('ref'):
            evidence['view_ref'] = value['ref']
        if checkpoint:
            checkpoint()
        if evidence['passed'] or case.get('violations') or case['repair_count'] >= max_repairs:
            # The caller accumulates later phases into its own list. Preserve
            # this stage's generation/modification snapshot in the raw report.
            return saved, value, list(checks)
        case['repair_count'] += 1
        attempt += 1
        prompt = quality_repair_feedback(checks)


def check_modified_view(frame, task, original_ref, revised_ref, record):
    if original_ref == revised_ref:
        record({'name': 'modified-view-registration', 'passed': False,
                'detail': 'No new view revision was registered after the modification.'})
        return
    semantic_checks(frame, task, modified=True,
                    record=lambda check: record({**check, 'name': 'modified-' + check['name']}))


def assistant_text(messages):
    from reverie.session.roles import from_stored_role
    return '\n'.join(str(m.get('content') or '') for m in messages
                     if from_stored_role(m.get('role')) == 'assistant')


def execution_state(events, session_id):
    """Observe the production coordinator, independent of transient button layout."""
    started, active = False, False
    for item in events:
        event = item.get('event', {})
        if event.get('type') == 'executors.changed':
            active = any(entry.get('sessionId') == session_id for entry in event.get('entries', []))
            started = started or active
    return started, active


def start_event_capture(page):
    # A full document reload drops both the globals and the old subscription.
    return page.evaluate("""()=>{
        if (!window.__qualityEvents) {
            window.__qualityEvents=[];
            window.reverie.onEvent(e=>window.__qualityEvents.push({at:performance.now(),event:e}));
        }
        return window.__qualityEvents.length;
    }""")


def settle_view(page, frame, *, paint_timeout_ms=2000):
    # An OOPIF can retain stale pointer hit regions immediately after moving.
    # Offscreen Chromium frames may stop painting altogether. Bring the real
    # iframe into view before waiting, and report stalled paints explicitly.
    paint = """timeout=>new Promise(resolve=>{
        let pending;
        const timer=setTimeout(()=>{cancelAnimationFrame(pending);resolve(false)},timeout);
        pending=requestAnimationFrame(()=>{
            pending=requestAnimationFrame(()=>{clearTimeout(timer);resolve(true)});
        });
    })"""
    def wait_for_paint(target, label):
        if not target.evaluate(paint, paint_timeout_ms):
            raise RuntimeError(f'{label} did not paint twice within {paint_timeout_ms}ms')
    wait_for_paint(page, 'Host')
    frame.frame_element().scroll_into_view_if_needed(timeout=5000)
    wait_for_paint(page, 'Host after iframe scroll')
    wait_for_paint(frame, 'Component')


def wait_for_registered_view_frame(page, view_ref, *, process=None, timeout_ms=30000):
    """Bind the actual registered child frame, retaining identity across mode moves."""
    from playwright.sync_api import Error as BrowserError

    view_id, revision = view_ref
    deadline = time.monotonic() + timeout_ms / 1000
    if process is not None and process.poll() is not None:
        raise RuntimeError('Owned Desktop exited before its registered child frame was ready')
    if page.is_closed():
        raise RuntimeError('Owned Desktop page closed before its registered child frame was ready')
    anchor = page.locator(f'.interactive-view-anchor[data-view-key$=":{view_id}:{revision}"]')
    anchor.wait_for(state='attached', timeout=timeout_ms)
    # A previously fullscreen/PiP surface lives outside its inline anchor.
    # Normalize using its real host action before binding this exact revision.
    matching = page.locator(f'iframe[data-view-id="{view_id}"]')
    pending = anchor.locator(f'iframe[data-view-id="{view_id}"]')
    last_error = None
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError('Owned Desktop exited before its registered child frame was ready')
        if page.is_closed():
            raise RuntimeError('Owned Desktop page closed before its registered child frame was ready')
        try:
            # Opening a saved session can replace its provisional anchor. Keep
            # discovery actions within the same bounded, re-resolving loop.
            remaining = min(500, max(1, int((deadline-time.monotonic())*1000)))
            anchor.scroll_into_view_if_needed(timeout=remaining)
            expand = anchor.get_by_role('button', name='展开', exact=True)
            if expand.count():
                expand.click(timeout=remaining)
            # Session loading can restore a detached mode after the anchor has
            # appeared. Discover that actual surface throughout the bounded wait.
            if not pending.count() and matching.count():
                inline = matching.last.locator('..').locator('[data-view-mode="inline"]')
                if inline.count() and inline.is_visible() and inline.is_enabled():
                    inline.click(timeout=min(1000, max(1, int((deadline-time.monotonic())*1000))))
            handle = pending.element_handle(timeout=min(500, max(1, int((deadline-time.monotonic())*1000))))
            inside = handle.content_frame() if handle is not None else None
            if inside is not None:
                inside.locator('body').wait_for(timeout=min(500, max(1, int((deadline-time.monotonic())*1000))))
                source = handle.get_attribute('src')
                if not source:
                    raise RuntimeError('Registered native iframe has no resource URL')
                # The opaque per-instance URL remains unique after Electron's
                # atomic DOM mode move. A parent-scoped locator would go stale.
                bound = page.locator('iframe[src=' + json.dumps(source) + ']')
                return bound, inside
        except BrowserError as error:
            last_error = error
        page.wait_for_timeout(min(50, max(1, int((deadline-time.monotonic())*1000))))
    raise RuntimeError('No actual registered Desktop child frame became ready') from last_error


def wait_for_body_theme_change(frame, before, *, timeout=2000):
    """Allow asynchronous host-context delivery before judging a theme update."""
    from playwright.sync_api import TimeoutError
    try:
        frame.wait_for_function("""before=>{
            const style=getComputedStyle(document.body);
            return style.backgroundColor!==before.bg||style.color!==before.color;
        }""", arg=before, timeout=timeout)
    except TimeoutError:
        pass
    return frame.locator('body').evaluate('e=>({bg:getComputedStyle(e).backgroundColor,color:getComputedStyle(e).color})')


VISIBLE_TEXT_CONTRAST_PROBE = r"""() => {
  const samples = [], indeterminate = [], seen = new Set();
  const rgba = value => {
    const match = value.match(/^rgba?\(([^)]+)\)$/);
    if (!match) return null;
    const numbers = match[1].split(/[,\s/]+/).filter(Boolean).map(Number);
    return numbers.length >= 3 && numbers.every(Number.isFinite)
      ? [...numbers.slice(0, 3), numbers[3] ?? 1] : null;
  };
  const over = (foreground, background) => foreground.slice(0, 3)
    .map((value, index) => value * foreground[3] + background[index] * (1 - foreground[3]));
  const luminance = rgb => rgb.map(value => value / 255)
    .map(value => value <= .04045 ? value / 12.92 : ((value + .055) / 1.055) ** 2.4)
    .reduce((sum, value, index) => sum + value * [.2126, .7152, .0722][index], 0);
  const inspect = (element, text, kind, textNode = null, textStyle = null) => {
    if (!text.trim() || element.namespaceURI !== 'http://www.w3.org/1999/xhtml' ||
        element.closest('script,style,template,[aria-hidden="true"],button:disabled,input:disabled,select:disabled,textarea:disabled')) return;
    const bounds = element.getBoundingClientRect(), elementStyle = getComputedStyle(element), style = textStyle || elementStyle;
    if (!bounds.width || !bounds.height || style.visibility !== 'visible' || style.display === 'none') return;
    let rectangles = [bounds];
    if (textNode) {
      const range = document.createRange();
      range.selectNodeContents(textNode);
      rectangles = [...range.getClientRects()];
    }
    let paintedBounds = null;
    const painted = rectangles.some(rectangle => {
      let left = Math.max(0, rectangle.left), right = Math.min(innerWidth, rectangle.right);
      let top = Math.max(0, rectangle.top), bottom = Math.min(innerHeight, rectangle.bottom);
      for (let node = element.parentElement; node; node = node.parentElement) {
        const clip = getComputedStyle(node), box = node.getBoundingClientRect();
        if (['hidden', 'clip', 'scroll', 'auto'].includes(clip.overflowX)) {
          left = Math.max(left, box.left); right = Math.min(right, box.right);
        }
        if (['hidden', 'clip', 'scroll', 'auto'].includes(clip.overflowY)) {
          top = Math.max(top, box.top); bottom = Math.min(bottom, box.bottom);
        }
      }
      if (left >= right || top >= bottom) return false;
      const hit = document.elementFromPoint((left + right) / 2, (top + bottom) / 2);
      if (hit && (element.contains(hit) || hit.contains(element))) {
        paintedBounds = {left, right, top, bottom, x:(left+right)/2, y:(top+bottom)/2};
        return true;
      }
      return false;
    });
    if (!painted) return;
    const key = kind + ':' + text + ':' + [bounds.x, bounds.y, bounds.width, bounds.height].join(',');
    if (seen.has(key)) return;
    seen.add(key);
    const layers = [];
    let reason = null, leafOpacity = 1;
    const root = document.documentElement, rootPaint = getComputedStyle(root);
    const rootBackground = rgba(rootPaint.backgroundColor);
    const bodyPaintsCanvas = rootPaint.backgroundImage === 'none' && rootBackground?.[3] === 0;
    // Group opacity and blending above an opaque card still affect its pixels.
    for (let node = element; node; node = node.parentElement) {
      const paint = getComputedStyle(node);
      if (Number(paint.opacity) === 0) return;
      if (Number(paint.opacity) !== 1) {
        const background=rgba(paint.backgroundColor);
        if(node===element&&!element.children.length&&background?.[3]===0&&paint.backgroundImage==='none')
          leafOpacity=Number(paint.opacity);
        else reason = 'group-opacity';
      }
      if (paint.filter !== 'none' || paint.mixBlendMode !== 'normal') reason = 'filter-or-blend';
    }
    if (style.textShadow !== 'none') reason = 'text-shadow';
    for (let node = element; node; node = node.parentElement) {
      const paint = getComputedStyle(node);
      // An absolutely positioned bar label can overflow its colored parent.
      // Only backgrounds that actually cover the glyph area paint behind it.
      const boxes = [...node.getClientRects()];
      const canvas = node === root || node === document.body && bodyPaintsCanvas;
      const covers = canvas || boxes.some(box => box.left <= paintedBounds.x && box.right >= paintedBounds.x &&
        box.top <= paintedBounds.y && box.bottom >= paintedBounds.y);
      if (!covers) continue;
      if (paint.backgroundImage !== 'none') { reason = 'background-image'; break; }
      const color = rgba(paint.backgroundColor);
      if (!color) { reason = 'unresolved-background-color'; break; }
      if (color[3] > 0) {
        const wholeGlyph = canvas || boxes.some(box => box.left <= paintedBounds.left + .1 && box.right >= paintedBounds.right - .1 &&
          box.top <= paintedBounds.top + .1 && box.bottom >= paintedBounds.bottom - .1);
        if (!wholeGlyph) { reason = 'background-boundary'; break; }
        layers.push(color);
      }
      if (color[3] >= 1) break;
    }
    if (!reason && (!layers.length || layers.at(-1)[3] < 1)) reason = 'transparent-to-host';
    const foreground = rgba(style.color);
    if (!foreground) reason = 'unresolved-foreground-color';
    else foreground[3] *= leafOpacity * (textStyle ? Number(textStyle.opacity) : 1);
    const detail = {kind, text: text.trim().slice(0, 160), color: style.color,
      font_size: parseFloat(style.fontSize), font_weight: Number(style.fontWeight)};
    if (reason) { indeterminate.push({...detail, reason}); return; }
    let background = layers.at(-1).slice(0, 3);
    for (let index = layers.length - 2; index >= 0; index--) background = over(layers[index], background);
    const foregroundPaint = over(foreground, background), a = luminance(foregroundPaint), b = luminance(background);
    const ratio = (Math.max(a, b) + .05) / (Math.min(a, b) + .05);
    const minimum = detail.font_size >= 24 || detail.font_size >= 18.666 && detail.font_weight >= 700 ? 3 : 4.5;
    samples.push({...detail, background, ratio, minimum, passed: ratio + .001 >= minimum});
  };
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) inspect(node.parentElement, node.textContent, 'text', node);
  for (const input of document.querySelectorAll('input:not([type="hidden"]):not([type="checkbox"]):not([type="radio"]):not([type="range"]):not([type="file"]),select,textarea')) {
    if (input.value) inspect(input, input.tagName === 'SELECT' ? input.selectedOptions[0]?.textContent || input.value : input.value, 'control-value');
    else if(input.placeholder) inspect(input, input.placeholder, 'placeholder', null, getComputedStyle(input,'::placeholder'));
  }
  return {tested: samples.length, failures: samples.filter(sample => !sample.passed), samples, indeterminate};
}"""


def visible_text_contrast(frame, *, timeout=2000):
    """Observe visible HTML text and values; unknown paint remains indeterminate.

    Solid ancestor backgrounds and alpha colors are measurable here. Gradients,
    group opacity and other unresolved paint require actual visual inspection;
    these observations do not certify the complete rendered document.
    """
    previous, stable = None, 0
    deadline = time.monotonic() + timeout / 1000
    while True:
        evidence = frame.evaluate(VISIBLE_TEXT_CONTRAST_PROBE)
        signature = json.dumps(evidence, sort_keys=True)
        stable = stable + 1 if signature == previous else 0
        if stable >= 2 or time.monotonic() >= deadline:
            return evidence
        previous = signature
        frame.wait_for_timeout(100)


def swept_text_contrast(frame):
    """Inspect scroll-revealed text/controls, restoring public viewport positions."""
    snapshot = frame.evaluate_handle('''()=>[document.scrollingElement,...document.querySelectorAll('*')]
        .filter((e,i,all)=>e&&all.indexOf(e)===i&&(e.scrollHeight>e.clientHeight||e.scrollWidth>e.clientWidth))
        .map(e=>({element:e,x:e.scrollLeft,y:e.scrollTop}))''')
    results = []
    try:
        results.append(visible_text_contrast(frame))
        size = frame.evaluate('({height:innerHeight,max:Math.max(0,document.scrollingElement.scrollHeight-innerHeight)})')
        step = max(1, int(size['height'] * .75))
        for y in list(range(0, int(size['max']), step)) + [size['max']]:
            frame.evaluate('y=>window.scrollTo(0,y)', y)
            results.append(visible_text_contrast(frame))
        controls = frame.locator('input,select,textarea,button,[role=alert],[role=status]')
        for index in range(controls.count()):
            element = controls.nth(index)
            if element.is_visible():
                element.scroll_into_view_if_needed()
                results.append(visible_text_contrast(frame))
    finally:
        snapshot.evaluate('positions=>positions.forEach(({element,x,y})=>element.scrollTo(x,y))')
        snapshot.dispose()
    samples, unknown = {}, {}
    for result in results:
        for sample in result['samples']:
            samples.setdefault(json.dumps(sample, sort_keys=True), sample)
        for sample in result['indeterminate']:
            unknown.setdefault(json.dumps(sample, sort_keys=True), sample)
    values = list(samples.values())
    return {'tested': len(values), 'samples': values, 'failures': [s for s in values if not s['passed']],
            'indeterminate': list(unknown.values()), 'viewports_examined': len(results)}


@contextmanager
def observe_field_validation(locator):
    """Observe associated error updates during real input/submit actions.

    The remote observer holds audit counters only; it never changes the field,
    its validity, the model DOM or private business state.
    """
    observation = locator.evaluate_handle('''field=>{
        const ids=[...(new Set(((field.getAttribute('aria-describedby')||'')+' '+
            (field.getAttribute('aria-errormessage')||'')).split(/\\s+/).filter(Boolean)))];
        const audit={ids,updates:0};
        const inside=node=>{
            if(node.nodeType!==1)node=node.parentElement;
            if(!node)return false;
            return ids.some(id=>node.id===id||document.getElementById(id)?.contains(node));
        };
        const carries=node=>inside(node)||node.nodeType===1&&
            [...node.querySelectorAll('[id]')].some(child=>ids.includes(child.id));
        audit.observer=new MutationObserver(records=>{
            if(records.some(record=>inside(record.target)||
                [...record.addedNodes,...record.removedNodes].some(carries)))audit.updates++;
        });
        audit.observer.observe(document.documentElement,{subtree:true,childList:true,characterData:true,
            attributes:true,attributeFilter:['hidden','class','style','aria-hidden']});
        return audit;
    }''')
    try:
        yield observation
    finally:
        try:
            observation.evaluate('audit=>audit.observer.disconnect()')
            observation.dispose()
        except Exception:
            pass  # A closed native target must not replace its original error.


def field_validation_feedback(frame, locator, message, before_text, *, observation=None):
    """Accept native invalidity or new visible, field-specific inline feedback."""
    if locator.evaluate('e=>!e.validity.valid || e.getAttribute("aria-invalid")==="true"'):
        return True
    previous = set(before_text.splitlines())
    added = '\n'.join(line for line in frame.locator('body').inner_text().splitlines() if line not in previous)
    if re.search(message, added):
        return True
    if observation is not None:
        current = observation.evaluate('''audit=>{
            const visible=e=>{
                if(!e||!e.getClientRects().length)return false;
                for(let n=e;n;n=n.parentElement){const s=getComputedStyle(n);
                    if(s.display==='none'||s.visibility!=='visible'||Number(s.opacity)===0)return false;}
                return true;
            };
            return {updates:audit.updates,text:audit.ids.map(id=>document.getElementById(id))
                .filter(visible).map(e=>e.innerText).join('\\n')};
        }''')
        return current['updates'] > 0 and bool(re.search(message, current['text']))
    return False



class Recorder:
    def __init__(self, output, upstream, secret, *, models_url=None, request_timeout=900):
        self.output, self.upstream, self.secret = output, upstream, secret
        self.request_timeout = request_timeout
        parts = urlsplit(upstream)
        catalog_path = parts.path.removesuffix('/chat/completions').rstrip('/') + '/models'
        self.models_url = models_url or urlunsplit((parts.scheme, parts.netloc, catalog_path, parts.query, ''))
        self.records, self.case = [], "startup"
        self.catalog_records = []
        recorder = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_GET(self):
                # Model selection refreshes a source's live catalog before
                # generation. Recording Chat must preserve that path too.
                import requests
                if urlsplit(self.path).path.rstrip('/') != '/v1/models':
                    self.send_error(404)
                    return
                url = recorder.models_url
                headers = {k: v for k, v in self.headers.items()
                           if k.lower() not in {'host', 'connection', 'accept-encoding'}}
                with requests.get(url, headers=headers, timeout=30) as response:
                    self.send_response(response.status_code)
                    self.send_header('Content-Type', response.headers.get('Content-Type', 'application/json'))
                    self.send_header('Content-Length', str(len(response.content)))
                    if response.headers.get('Retry-After'):
                        self.send_header('Retry-After', response.headers['Retry-After'])
                    self.end_headers()
                    saved = recorder.output / f'catalog-{time.time_ns()}.json'
                    saved.write_bytes(response.content)
                    recorder.catalog_records.append({'path': str(saved), 'status': response.status_code,
                        'sha256': hashlib.sha256(response.content).hexdigest(),
                        'retry_after': response.headers.get('Retry-After')})
                    dump(recorder.output / 'catalog-requests.json', recorder.catalog_records)
                    (recorder.output / 'catalog-response.json').write_bytes(response.content)
                    self.wfile.write(response.content)

            def do_POST(self):
                import requests
                started = time.perf_counter()
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                payload = json.loads(raw)
                index = len(recorder.records)
                target = recorder.output / f"request-{index:04d}"
                public = raw.decode("utf-8").replace(recorder.secret, "[redacted]") if recorder.secret else raw.decode("utf-8")
                target.with_suffix(".json").write_text(public, encoding="utf-8")
                system = [m for m in payload.get("messages", []) if m.get("role") == "system"]
                record = {"case": recorder.case, "request": str(target.with_suffix('.json')), "model": payload.get("model"), "body_bytes": len(raw), "body_characters": len(raw.decode('utf-8')), "system_characters": sum(len(str(m.get('content', ''))) for m in system), "system_messages": len(system), "schema_characters": len(json.dumps(payload.get('tools', []), ensure_ascii=False)), "tools": len(payload.get('tools', [])), "started_monotonic": started}
                record['client_identity'] = {name: self.headers[name] for name in ['User-Agent', 'x-opencode-client']
                                             if self.headers.get(name)}
                record['system_sha256'] = hashlib.sha256(json.dumps(system, ensure_ascii=False).encode()).hexdigest()
                record['request_sha256'] = hashlib.sha256(raw).hexdigest()
                record['schemas_sha256'] = hashlib.sha256(json.dumps(payload.get('tools', []), ensure_ascii=False, sort_keys=True).encode()).hexdigest()
                record['tool_choice'] = payload.get('tool_choice')
                record.update(upstream_read_wait_ms=0.0, downstream_io_ms=0.0, recorder_processing_ms=0.0)
                recorder.records.append(record)
                dump(recorder.output / "requests.json", recorder.records)
                headers = {k: v for k, v in self.headers.items() if k.lower() not in {"host", "content-length", "connection", "accept-encoding"}}
                headers["Accept-Encoding"] = "identity"

                def downstream(operation, *args):
                    io_started = time.perf_counter()
                    try:
                        return operation(*args)
                    except (OSError, ValueError):
                        record['transport_error_origin'] = 'downstream'
                        raise
                    finally:
                        record['downstream_io_ms'] += (time.perf_counter()-io_started)*1000

                try:
                    with requests.post(recorder.upstream, data=raw, headers=headers, stream=True, timeout=(30, recorder.request_timeout)) as response:
                        record.update(status=response.status_code, headers_ms=(time.perf_counter()-started)*1000,
                                      response_content_type=response.headers.get('Content-Type', ''))
                        if response.headers.get('Retry-After'):
                            record['retry_after'] = response.headers['Retry-After']
                        if response.headers.get('Server-Timing'):
                            record['provider_server_timing'] = response.headers['Server-Timing']
                        self.send_response(response.status_code)
                        self.send_header("Content-Type", response.headers.get("Content-Type", "application/json"))
                        if response.headers.get('Retry-After'):
                            self.send_header('Retry-After', response.headers['Retry-After'])
                        self.send_header("Transfer-Encoding", "chunked")
                        self.send_header("Connection", "close")
                        downstream(self.end_headers)
                        buffer = ''
                        decoder = codecs.getincrementaldecoder('utf-8')()
                        tool_arguments = {}

                        def read_upstream():
                            io_started = time.perf_counter()
                            try:
                                return response.raw.read1(64 * 1024, decode_content=True)
                            finally:
                                record['upstream_read_wait_ms'] += (time.perf_counter()-io_started)*1000

                        with target.with_suffix('.sse').open('wb') as stream:
                            for chunk in iter(read_upstream, b''):
                                if not chunk:
                                    continue
                                processing_started = time.perf_counter()
                                record.setdefault("first_wire_chunk_ms", (time.perf_counter()-started)*1000)
                                buffer += decoder.decode(chunk)
                                while '\n' in buffer:
                                    line, buffer = buffer.split('\n', 1)
                                    if not line.startswith('data:'):
                                        continue
                                    if line[5:].strip() == '[DONE]':
                                        record['sse_done'] = True
                                        continue
                                    try:
                                        event = json.loads(line[5:].strip())
                                    except (ValueError, TypeError):
                                        continue
                                    elapsed = (time.perf_counter()-started)*1000
                                    if event.get('error'):
                                        record['upstream_stream_error'] = event['error']
                                    if event.get('usage'):
                                        record['usage'] = event['usage']
                                    if event.get('model'):
                                        record['response_model'] = event['model']
                                    if event.get('nvext'):
                                        record['provider_metrics'] = event['nvext']
                                    for choice in event.get('choices') or []:
                                        if choice.get('finish_reason'):
                                            record.setdefault('finish_reasons', []).append(choice['finish_reason'])
                                        delta = choice.get('delta') or {}
                                        if delta.get('content'):
                                            record.setdefault('first_content_ms', elapsed)
                                        if delta.get('reasoning_content') or delta.get('reasoning'):
                                            record.setdefault('first_reasoning_ms', elapsed)
                                        for call in delta.get('tool_calls', []):
                                            record.setdefault('first_tool_fragment_ms', elapsed)
                                            function = call.get('function') or {}
                                            if function.get('name'):
                                                record.setdefault('response_tool_names', []).append(function['name'])
                                            key = call.get('index', 0)
                                            tool_arguments[key] = tool_arguments.get(key, '') + (function.get('arguments') or '')
                                            try:
                                                if isinstance(json.loads(tool_arguments[key]), dict):
                                                    record.setdefault('first_parseable_tool_arguments_ms', elapsed)
                                            except ValueError:
                                                pass
                                stream.write(chunk)
                                record['recorder_processing_ms'] += (time.perf_counter()-processing_started)*1000
                                downstream(self.wfile.write, f'{len(chunk):x}\r\n'.encode() + chunk + b'\r\n')
                                downstream(self.wfile.flush)
                            downstream(self.wfile.write, b'0\r\n\r\n')
                            downstream(self.wfile.flush)
                except Exception as error:
                    record["transport_error"] = type(error).__name__ + ": " + str(error)
                    record.setdefault('transport_error_origin', 'upstream')
                finally:
                    record["complete_ms"] = (time.perf_counter()-started)*1000
                    if target.with_suffix('.sse').exists():
                        record['response_sha256'] = hashlib.sha256(target.with_suffix('.sse').read_bytes()).hexdigest()
                    dump(recorder.output / "requests.json", recorder.records)
                    self.close_connection = True

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


VALUE_CONTROL_SELECTOR = 'input,select,textarea,[role="checkbox"],[role="switch"],button[aria-pressed],[role="button"][aria-pressed]'
CHECKED_CONTROL_SELECTOR = 'input[type="checkbox"],[role="checkbox"],[role="switch"]'


def latest_published_view_reference(messages, store, session_id):
    """Read publication order from actual tool results, not opaque ID order."""
    from reverie.views import visible_view_references

    messages = list(messages)
    names = {call.get('id'): call.get('function', {}).get('name')
             for message in messages for call in message.get('tool_calls', [])}
    for message in reversed(messages):
        call_id = message.get('tool_call_id')
        if message.get('role') != 'tool' or names.get(call_id) != 'render_view':
            continue
        references = visible_view_references([message])
        if not references:
            continue
        matching, errors = [], []
        for reference in references:
            try:
                manifest = store.current_manifest(session_id, *reference)
            except (OSError, ValueError) as error:
                errors.append(error)
                continue
            if manifest.tool_call_id == call_id:
                matching.append(reference)
        if len(matching) != 1:
            if not matching and errors:
                raise errors[0]
            raise ValueError('View publication does not identify exactly one stored revision for this tool call.')
        return matching[0]
    return None


def inspect_native_model_errors(items, session_id):
    """Retain recovered errors and identify a terminal error in this turn's run."""
    events = []
    for item in items:
        envelope = item.get('event', {})
        event = envelope.get('event', {}) if envelope.get('type') == 'prompt.event' else envelope
        if isinstance(event, dict) and event.get('session_id') == session_id:
            events.append(event)
    run = next((event.get('run_id') for event in events
                if event.get('type') == 'run.started' and event.get('run_id')), None)
    errors, last = [], None
    if run:
        for event in events:
            if event.get('run_id') != run or event.get('type') != 'ui.event':
                continue
            model = event.get('event', {})
            if not isinstance(model, dict):
                continue
            if model.get('event') == 'model_error':
                errors.append(model)
                last = model
            elif model.get('event') == 'model_response' and model.get('status') == 'success':
                last = None
    return {'run_id': run, 'errors': errors, 'terminal_error': last}


def reload_registered_view(page, view_ref, session_label, *, process=None):
    """Rebind both locators to the real new instance after a genuine reload."""
    page.reload()
    page.locator('.session-item').filter(has_text=session_label).click(timeout=120000)
    page.locator('.session-loading').wait_for(state='hidden', timeout=60000)
    return wait_for_registered_view_frame(page, view_ref, process=process)


def control(frame, name):
    if name == '天数':
        monthly = frame.get_by_label(re.compile('每月.*(?:天|工作日)|(?:工作|通勤).*天数|天数.*(?:每月|月)')).and_(frame.locator('input,select,textarea'))
        if monthly.count():
            return monthly.first
    aliases = {"关键词": "关键词|搜索|查找|商品名称", "倍率": "倍率|倍数|系数|缩放", "预算": "预算|最高费用|最高价格", "姓名": "姓名|名字", "邮箱": "邮箱|电子邮件|email", "票价": "票价|单次费用|单程费用", "月数": "月数|月份|通勤月|一年.*月|年.*月", "天数": "天数|工作日|通勤日"}
    return frame.get_by_label(re.compile(aliases.get(name, name), re.I)).and_(frame.locator('input,select,textarea')).first


def stock_filter_control(frame):
    pattern = re.compile('库存|有货|in stock', re.I)
    labelled = frame.get_by_label(pattern).first
    if labelled.count():
        return labelled
    for role in ['checkbox', 'switch']:
        candidate = frame.get_by_role(role, name=pattern)
        if candidate.count():
            return candidate.first
    pressed = frame.get_by_role('button', name=pattern).and_(
        frame.locator('[aria-pressed="true"],[aria-pressed="false"]'))
    if pressed.count():
        return pressed.first
    return labelled


def set_toggle_checked(field, enabled):
    """Use actual native or ARIA checkbox/switch actions and observe the result."""
    if not field.count() or not field.is_visible() or not field.is_enabled():
        return False
    if field.evaluate('e=>e.tagName') == 'INPUT':
        if field.evaluate('e=>e.type') != 'checkbox':
            return False
        field.set_checked(enabled)
        return field.is_checked() == enabled
    role = field.get_attribute('role')
    pressed_button = role not in {'checkbox', 'switch'} and field.evaluate('e=>e.matches("button,[role=button]")')
    if not pressed_button and role not in {'checkbox', 'switch'}:
        return False
    attribute = 'aria-pressed' if pressed_button else 'aria-checked'
    value = field.get_attribute(attribute)
    if value not in {'true', 'false'}:
        return False
    expected = 'true' if enabled else 'false'
    if value != expected:
        from playwright.sync_api import expect

        field.click()
        try:
            expect(field).to_have_attribute(attribute, expected, timeout=3000)
        except AssertionError:
            return False
    return field.get_attribute(attribute) == expected


def set_stock_filter(field, enabled):
    """Operate a labelled select, checkbox or accessible stock switch."""
    if not field.count():
        return False
    if field.evaluate('e=>e.tagName') == 'SELECT':
        options = field.locator('option').evaluate_all('es=>es.map(e=>({label:e.textContent,value:e.value}))')
        pattern = '有库存|有货|在售' if enabled else '全部|所有|不限|不过滤|all'
        option = next((option for option in options if re.search(pattern, option['label'], re.I)), None)
        if option is None:
            return False
        field.select_option(value=option['value'])
    elif field.evaluate('e=>e.tagName') == 'INPUT':
        if enabled:
            field.check()
        else:
            field.uncheck()
    else:
        return set_toggle_checked(field, enabled)
    return True


def _point_unobstructed_in_parents(frame, x, y):
    """Read hit targets through each iframe ancestor before a real pointer action."""
    while frame.parent_frame is not None:
        element = frame.frame_element()
        geometry = element.evaluate('''e=>{
            const r=e.getBoundingClientRect();
            return {left:r.left,top:r.top,width:r.width,height:r.height,
                    offsetWidth:e.offsetWidth,offsetHeight:e.offsetHeight,
                    borderLeft:e.clientLeft,borderTop:e.clientTop};
        }''')
        if not geometry['offsetWidth'] or not geometry['offsetHeight']:
            return False
        x = geometry['left'] + (geometry['borderLeft'] + x) * geometry['width'] / geometry['offsetWidth']
        y = geometry['top'] + (geometry['borderTop'] + y) * geometry['height'] / geometry['offsetHeight']
        frame = frame.parent_frame
        if not frame.evaluate('({element,x,y})=>document.elementFromPoint(x,y)===element',
                              {'element': element, 'x': x, 'y': y}):
            return False
    return True


def blur_inside_component(locator):
    """Commit a sole field using a real click that stays inside its iframe."""
    frame = locator.element_handle().owner_frame()
    body = frame.locator('body')
    points = body.evaluate("""body=>{
        const box=body.getBoundingClientRect(),left=Math.max(0,box.left),right=Math.min(innerWidth,box.right),
            top=Math.max(0,box.top),bottom=Math.min(innerHeight,box.bottom);
        const interactive='input,select,textarea,button,a[href],label,[role=button],[role=radio],[role=checkbox],[contenteditable=true]';
        const points=[];
        for(const y of [top+24,(top+bottom)/2,bottom-24])for(const x of [left+24,(left+right)/2,right-24]){
            if(x<=left||x>=right||y<=top||y>=bottom)continue;
            const hit=document.elementFromPoint(x,y);
            if(!hit||!body.contains(hit)||hit.closest(interactive))continue;
            let safe=true;
            for(let node=hit;node;node=node.parentElement){
                if(node.tabIndex>=0||typeof node.onclick==='function'||getComputedStyle(node).cursor==='pointer'){safe=false;break}
                if(node===body)break;
            }
            if(safe)points.push({x:x-box.left,y:y-box.top,viewportX:x,viewportY:y});
        }
        return points;
    }""")
    for point in points:
        if _point_unobstructed_in_parents(frame, point['viewportX'], point['viewportY']):
            body.click(position={'x': point['x'], 'y': point['y']})
            return
    raise RuntimeError('Verifier could not find an unobstructed inert visible area for a real input blur.')


def change(locator, value, *, tab_key=None):
    kind = locator.evaluate("e=>e.type")
    if kind == "range":
        limits = locator.evaluate("e=>({min:Number(e.min||0),max:Number(e.max||100),step:Number(e.step||1)})")
        target = min(limits['max'], max(limits['min'], float(value)))
        locator.focus()
        locator.press('Home')
        for _ in range(round((target-limits['min'])/limits['step'])):
            locator.press('ArrowRight')
    elif kind == 'select-one':
        locator.select_option(value=value)
    else:
        locator.fill(value)
        navigation = locator.evaluate("""e=>{
            const focusable=[...document.querySelectorAll('input,select,textarea,button,a[href],[tabindex]')]
                .filter(n=>!n.disabled&&n.tabIndex>=0&&n.getClientRects().length&&getComputedStyle(n).visibility!=='hidden');
            return {count:focusable.length,last:focusable.at(-1)===e};
        }""")
        if navigation['count'] <= 1:
            # Either Tab direction can leave a one-control component, focus a
            # distant host control and legitimately destroy the offscreen view.
            blur_inside_component(locator)
        else:
            if tab_key is None:
                tab_key = 'Shift+Tab' if navigation['last'] else 'Tab'
            locator.press(tab_key)
    return locator.input_value()


def number_pattern(value):
    integral = value == int(value)
    if integral:
        value = int(value)
    grouping = '[,， \u00a0\u202f\u2009]?'
    return re.compile(r'(?<![\d.-])' + re.escape(f'{value:,}').replace(',', grouping)
                      + (r'(?:\.0+)?' if integral else '0*') + r'(?![\d.])')


def numeric_control_value(locator, label):
    """Missing real numeric values are semantic failures, never float crashes."""
    try:
        value = float(locator.input_value())
        if math.isfinite(value):
            return value
    except (TypeError, ValueError):
        pass
    raise MissingBusinessControl('No finite current value in numeric control: ' + label)


def empty_result_feedback(text):
    return bool(re.search(
        r'(?:没有|无|暂无|未找到|未匹配(?:到)?|找不到)(?!\s*(?:错误|问题|异常))'
        r'[^\n]{0,160}(?:匹配|商品|结果|路线|方案|条目|记录|数据)'
        r'|(?:未匹配到|未找到)(?=$|[。！!\n])|暂无结果|无匹配'
        r'|\b(?:no(?:\s+matching)?|zero)\s+(?:results?|matches|items?|products?|routes?|records?|data)\b'
        r'|\bnothing (?:found|matches)\b', text, re.I))


def check_negative_input(frame, field, *, commit=None):
    """Observe rejection or new invalid feedback, excluding static help text."""
    before = frame.locator('body').inner_text()
    previous_marker = field.evaluate('e=>e.getAttribute("aria-invalid")')
    actual = change(field, '-1')
    if commit:
        commit()
    after = frame.locator('body').inner_text()
    prior_lines = {' '.join(line.split()) for line in before.splitlines()}
    new_feedback = '\n'.join(line for line in after.splitlines() if ' '.join(line.split()) not in prior_lines)
    try:
        still_negative = float(actual) < 0
    except (TypeError, ValueError):
        still_negative = False
    new_marker = field.evaluate('e=>e.getAttribute("aria-invalid")') == 'true' and previous_marker != 'true'
    message = bool(re.search(r'错误|有误|无效|不合理|不能|不得|不应|不小于|非负|不负|至少|大于|≥|请[^\n]*有效|invalid|error', new_feedback, re.I))
    # A newly displayed explicit bound can reject the value without saying
    # "invalid" (for example, "must be between 1 and 12"). Verify the actual
    # value lies outside that bound; unchanged help and inclusive bounds fail.
    excluding_ranges = []
    if still_negative:
        pattern = r'(?:必须在|应在|需在|must\s+be\s+between)\s*(-?\d+(?:\.\d+)?)\s*(?:-|~|～|–|—|至|到|and|to)\s*(-?\d+(?:\.\d+)?)'
        for match in re.finditer(pattern, new_feedback, re.I):
            lower, upper = map(float, match.groups())
            if lower <= upper and not lower <= float(actual) <= upper:
                excluding_ranges.append({'lower': lower, 'upper': upper})
    return {'passed': not still_negative or new_marker or message or bool(excluding_ranges), 'actual': actual,
            'text': after, 'new_feedback': new_feedback, 'new_invalid_marker': new_marker,
            'new_excluding_ranges': excluding_ranges}


def selection_feedback(text):
    return [' '.join(line.split()) for line in text.splitlines()
            if re.search('已选|选择了|当前选择|所选|选择的是', line)
            and any(name in line for name in ['山谷', '日落', '城郊', '湖畔'])]


CHOICE_CONFIRM_PATTERN = r'^(确认选择|确认所选|确认方案|选定路线|confirm(?: selection| choice)?|select route)$'


def selected_route_names(frame):
    """Read native selected semantics and local confirmation regions across lines."""
    return frame.evaluate('''confirmationPattern=>{
        const names=['山谷','日落','城郊','湖畔'], selected=new Set();
        const matches=text=>names.filter(name=>text.includes(name));
        const visible=e=>e.getClientRects().length>0&&getComputedStyle(e).visibility==='visible';
        const add=text=>{const found=matches(text);if(found.length===1)selected.add(found[0]);};
        const requiresConfirmation=[...document.querySelectorAll('button,[role=button]')]
            .some(e=>visible(e)&&new RegExp(confirmationPattern,'i').test(e.innerText.trim()));
        for(const e of document.querySelectorAll('input[type=radio]:checked,[aria-pressed=true],[aria-checked=true],[aria-selected=true]')){
            if(!visible(e)||requiresConfirmation)continue;
            const text=e.matches('input')?[...(e.labels||[])].map(label=>label.innerText).join(' '):e.innerText;
            add(text||e.getAttribute('aria-label')||'');
        }
        const past=/已选|选择了|选了|当前选择|所选|选择的是|selected|you chose/i;
        const empty=/未选择|尚未|未选|没有选择|no selection|not selected|none selected/i;
        const regions=[...document.querySelectorAll('[role=status],[aria-live],output,section,article,div,p')]
            .filter(e=>visible(e)&&!e.closest('footer,aside,details')&&past.test(e.innerText)
                &&!empty.test(e.innerText)&&matches(e.innerText).length===1);
        for(const e of regions.filter(e=>!regions.some(other=>other!==e&&e.contains(other))))add(e.innerText);
        return [...selected].sort();
    }''', CHOICE_CONFIRM_PATTERN)


def result_items(frame, task_id):
    """Read visible records, excluding prose that repeats the source data.

    Semantic rows and ordinary cards are both supported. A record contains one
    entity and its values; a footer listing the whole fixture is not a record.
    The returned paths are used only for real pointer actions, never DOM writes.
    """
    names = {'table': ['水杯', '台灯', '笔记本', '收纳盒'],
             'comparison': ['山谷', '日落', '城郊', '湖畔']}[task_id]
    return frame.evaluate("""({names,comparison})=>{
        const visible=e=>e.getClientRects().length>0 && getComputedStyle(e).visibility!=='hidden';
        const matches=text=>names.filter(name=>text.includes(name));
        const path=e=>{
            const parts=[];
            for(let node=e;node&&node.nodeType===1;node=node.parentElement){
                const tag=node.localName;
                const siblings=node.parentElement?[...node.parentElement.children].filter(n=>n.localName===tag):[node];
                parts.unshift(tag+':nth-of-type('+(siblings.indexOf(node)+1)+')');
            }
            return parts.join('>');
        };
        const selector='tr,[role="row"],li,[role="listitem"],article,section,div'+(comparison?',label,button,[role="button"],[role="radio"]':'');
        const candidates=[...document.querySelectorAll(selector)].filter(e=>{
            if(!visible(e)||e.closest('footer,aside,small,details'))return false;
            const text=e.innerText, found=matches(text);
            if(found.length!==1||!/[0-9]/.test(text))return false;
            if(comparison){
                if((text.match(/[0-9]+(?:\\.[0-9]+)?/g)||[]).length<2)return false;
            }
            if(e.matches('tr,[role="row"],li,[role="listitem"],article,button,[role="button"],[role="radio"]')||
                comparison&&e.matches('label')&&e.querySelector('input[type=radio]'))return true;
            return [...e.querySelectorAll('h1,h2,h3,h4,h5,h6,span,strong,b,div,p')]
                .some(n=>n.matches('h1,h2,h3,h4,h5,h6')&&n.textContent.includes(found[0])
                    ||new RegExp('^'+found[0]+'(?:路线|方案|商品)?$').test(n.textContent.trim()));
        });
        return candidates.filter(e=>!candidates.some(other=>other!==e&&e.contains(other)))
            .map(e=>({name:matches(e.innerText)[0],text:e.innerText,path:path(e)}));
    }""", {'names': names, 'comparison': task_id == 'comparison'})


def result_item_action(frame, item):
    """Discover a record's actual choice action separately from its data."""
    record = frame.locator(item['path'])
    if record.evaluate('e=>e.matches("button,[role=button],[role=radio]")'):
        return record
    radio = record.get_by_role('radio').first
    if radio.count():
        return radio
    button = record.get_by_role('button', name=re.compile('选|choose|select|pick', re.I)).first
    if button.count():
        return button
    if record.evaluate('e=>typeof e.onclick==="function"||e.tabIndex>=0&&getComputedStyle(e).cursor==="pointer"'):
        return record
    return None


def choose_result_item(frame, item):
    action = result_item_action(frame, item)
    if action is None:
        return False
    if action.evaluate('e=>e.type==="radio"'):
        action.check()
        # Some valid UIs separate choosing a radio from confirming the choice.
        # Exercise that explicit real action instead of assuming a change event
        # alone commits the user's selection.
        confirms = frame.get_by_role('button', name=re.compile(CHOICE_CONFIRM_PATTERN, re.I))
        for confirm in confirms.element_handles():
            if confirm.is_visible() and confirm.is_enabled():
                confirm.click()
                break
    else:
        action.click()
    return True


def apply_filters_if_present(frame):
    actions = frame.get_by_role('button', name=re.compile(
        '^(筛选(?:路线|结果|方案)?|应用.*筛选|确认筛选|apply.*filter|filter(?: routes| results)?)$', re.I))
    for action in actions.element_handles():
        if action.is_visible() and action.is_enabled():
            action.click()
            return True
    return False


def commit_parameter_changes(frame, task_id):
    """Use an explicit apply/calculate action when the task's UI provides one."""
    if task_id == 'comparison':
        return apply_filters_if_present(frame)
    if task_id not in {'calculator', 'chart'}:
        return False
    actions = frame.get_by_role('button', name=re.compile(
        '^(应用(?:倍率|参数|更改)?|重新计算|计算(?:费用|结果)?|更新(?:图表|数据|结果)?|apply(?: changes)?|recalculate|calculate|update(?: chart| results)?)$', re.I))
    for action in actions.element_handles():
        if action.is_visible() and action.is_enabled():
            action.click()
            return True
    return False


def submission_confirmation(frame, people, total):
    """Check the confirmation itself rather than a price elsewhere in the form."""
    regions = frame.evaluate("""()=>{
        const candidates=[...document.querySelectorAll('section,article,div,p,output,[role="status"],[role="alert"]')]
            .filter(e=>e.getClientRects().length&&e.innerText.includes('王小明')&&e.innerText.includes('synthetic@example.invalid'));
        return candidates.filter(e=>!candidates.some(other=>other!==e&&e.contains(other))).map(e=>e.innerText);
    }""")
    correct = [text for text in regions if number_pattern(people).search(text)
               and number_pattern(total).search(text)]
    return {'passed': bool(correct), 'people': people, 'total': total, 'regions': regions}


def reopen_form_through_button(frame):
    actions = frame.get_by_role('button', name=re.compile('新的报名|继续报名|重新|再次|再填|重填|返回|编辑|修改信息|new registration|continue registration|edit', re.I))
    for action in actions.element_handles():
        if action.is_visible() and action.is_enabled():
            action.click()
            field = control(frame, '人数')
            if field.count() and field.is_visible() and field.is_enabled():
                return True
    return False


def submit_form_confirmation(frame, *, modified, record):
    # A prior validation phase may already have submitted successfully. Return
    # through a real edit/new-entry action before looking for another submit.
    field = control(frame, '人数')
    if not field.count() or not field.is_visible() or not field.is_enabled():
        reopened = reopen_form_through_button(frame)
        record({'name': 'form-reentry-action', 'passed': reopened,
                'detail': 'A completed form needs a usable edit/new-entry action.'})
        if not reopened:
            return
        field = control(frame, '人数')
    try:
        people = numeric_control_value(field, '人数')
    except MissingBusinessControl:
        record({'name': 'required-numeric-control', 'passed': False, 'detail': '人数'})
        return
    actions = frame.get_by_role('button', name=re.compile('报名|提交'))
    submit = next((action for action in actions.element_handles()
                   if action.is_visible() and action.is_enabled()), None)
    if submit is None:
        record({'name': 'valid-submission', 'passed': False, 'detail': 'Missing usable submit action.'})
        return
    submit.click()
    confirmation = submission_confirmation(frame, people, people*(100 if modified else 80))
    record({'name': 'valid-submission', 'passed': confirmation['passed'], 'detail': confirmation})


def chart_evidence(frame, multiplier, *, modified):
    """Read chart geometry/hit testing and per-month values after real inputs."""
    charts = frame.locator('svg,canvas,[role="img"]')
    count = 4 if modified else 3
    # CSS columns need no particular tag, class name or ARIA image role. Locate
    # the smallest month-labelled region with multiple painted descendants;
    # aligned, differently sized bars distinguish it from ordinary data cards.
    css_paths = frame.evaluate("""count=>{
        const months=[/[一1]\\s*月/,/[二2]\\s*月/,/[三3]\\s*月/,/[四4]\\s*月/].slice(0,count);
        const painted=e=>{
            if(e.closest('table,[role="table"],button,input,select,textarea'))return false;
            const r=e.getBoundingClientRect(),s=getComputedStyle(e);
            return r.width>3&&r.height>3&&s.visibility!=='hidden'&&
                (s.backgroundImage!=='none'||!['transparent','rgba(0, 0, 0, 0)'].includes(s.backgroundColor));
        };
        const roots=[...document.querySelectorAll('figure,section,div')].filter(e=>
            e.getClientRects().length&&!e.matches('[role="img"]')&&!e.querySelector('svg,canvas')&&
            months.every(pattern=>pattern.test(e.innerText))&&[...e.querySelectorAll('div,span')].filter(painted).length>=count);
        const path=e=>{
            const parts=[];
            for(let n=e;n&&n.nodeType===1;n=n.parentElement){
                const same=n.parentElement?[...n.parentElement.children].filter(s=>s.localName===n.localName):[n];
                parts.unshift(n.localName+':nth-of-type('+(same.indexOf(n)+1)+')');
            }
            return parts.join('>');
        };
        return roots.filter(e=>!roots.some(other=>other!==e&&e.contains(other))).map(path);
    }""", count)
    candidates = [(charts.nth(index), False) for index in range(charts.count())]
    candidates += [(frame.locator(path), True) for path in css_paths]
    plots = []
    for chart, css_inferred in candidates:
        if not chart.is_visible():
            continue
        chart.scroll_into_view_if_needed()
        plots.append(chart.evaluate("""host=>{
            const painted=e=>{
                const r=e.getBoundingClientRect(),s=getComputedStyle(e);
                if(r.width<3||r.height<3||s.visibility==='hidden'||s.opacity==='0')return false;
                const x=Math.max(1,Math.min(innerWidth-1,r.left+r.width/2));
                const y=Math.max(1,Math.min(innerHeight-1,r.top+r.height/2));
                if(x<r.left||x>r.right||y<r.top||y>r.bottom)return false;
                const hit=document.elementFromPoint(x,y);
                return !!hit&&(hit===e||e.contains(hit)||hit.contains(e));
            };
            const shapes=[...host.querySelectorAll('rect,path,polygon,div,span')].filter(e=>{
                if(e.closest('table,[role="table"],button,input,select,textarea'))return false;
                const s=getComputedStyle(e),r=e.getBoundingClientRect();
                const fill=e.namespaceURI==='http://www.w3.org/2000/svg'?s.fill:s.backgroundColor;
                return (s.backgroundImage!=='none'||fill&&fill!=='none'&&fill!=='transparent'&&fill!=='rgba(0, 0, 0, 0)')&&r.width>3&&r.height>3;
            });
            const bars=shapes.filter(e=>!shapes.some(other=>other!==e&&e.contains(other)));
            const bounds=host.getBoundingClientRect();
            return {tag:host.localName,label:host.getAttribute('aria-label'),width:bounds.width,height:bounds.height,
                visible:painted(host),bars:bars.map(e=>{
                    const r=e.getBoundingClientRect();
                    return {visible:painted(e),height:r.height,width:r.width,bottom:r.bottom,left:r.left};
                })};
        }"""))
        plots[-1]['css_inferred'] = css_inferred

    def proportional_css_bars(plot):
        visible = [bar for bar in plot['bars'] if bar['visible']]
        for position, size, thickness in [('bottom', 'height', 'width'), ('left', 'width', 'height')]:
            for reference in visible:
                # Ordinary dashboard cards can share a left edge or baseline.
                # Bars also share a comparable thickness across their value axis.
                aligned = [bar[size] for bar in visible
                           if abs(bar[position]-reference[position]) <= 4
                           and abs(bar[thickness]-reference[thickness]) <= max(4, reference[thickness]*0.15)]
                if len(aligned) >= count and max(aligned)/max(min(aligned), 1) >= 1.4:
                    return True
        return False

    visible = any(plot['visible'] and plot['width'] >= 80 and plot['height'] >= 50 and (plot['tag'] == 'canvas'
                  or sum(bar['visible'] for bar in plot['bars']) >= count
                  and (not plot['css_inferred'] or proportional_css_bars(plot))) for plot in plots)
    rows = frame.evaluate("""()=>[...document.querySelectorAll('tr,[role="row"],li,p,div')]
        .filter(e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden')
        .map(e=>e.innerText).filter(t=>/[一二三四1-4]\\s*月/.test(t)&&/[0-9]/.test(t))""")
    months = [(r'(?:一|1)\s*月', 120), (r'(?:二|2)\s*月', 80), (r'(?:三|3)\s*月', 160)]
    if modified:
        months.append((r'(?:四|4)\s*月', 100))
    details = []
    for month, base in months:
        matching = [row for row in rows if re.search(month, row)
                    and sum(bool(re.search(pattern, row)) for pattern, _ in months) == 1]
        details.append({'month': month, 'expected': base*multiplier,
                        'passed': any(number_pattern(base*multiplier).search(row) for row in matching),
                        'rows': matching})
    return {'visible_bars': visible, 'plots': plots, 'readable_data': all(d['passed'] for d in details),
            'details': details}


def canvas_paints(frame):
    """Read painted content for a zero-state comparison; do not alter the canvas."""
    canvases = frame.locator('canvas').evaluate_all('''elements=>elements.map((element,index)=>{
        const style=getComputedStyle(element);
        const visible=!!element.getClientRects().length&&style.visibility!=='hidden';
        let image=null;
        if(visible){try{image=element.toDataURL()}catch{}}
        return {index,visible,image};
    })''')
    return [{'index': item['index'], 'visible': item['visible'],
             'sha256': hashlib.sha256(item['image'].encode()).hexdigest() if item['image'] else None}
            for item in canvases]


def chart_zero_state(frame, before_text, before_paints, *, modified):
    after = frame.locator('body').inner_text()
    previous = {' '.join(line.split()) for line in before_text.splitlines()}
    new_feedback = '\n'.join(line for line in after.splitlines() if ' '.join(line.split()) not in previous)
    paints = canvas_paints(frame)
    visible = [item for item in paints if item['visible']]
    prior = {item['index']: item for item in before_paints}
    if visible:
        # Canvas geometry cannot identify bar values. Require a changed readable
        # empty-state message AND changed pixels (or a hidden canvas); a stale
        # positive chart with a static/new caption cannot satisfy this probe.
        cleared_plot = all(item['sha256'] is not None and item['index'] in prior
                           and item['sha256'] != prior[item['index']]['sha256'] for item in visible)
    else:
        cleared_plot = not chart_evidence(frame, 0, modified=modified)['visible_bars']
    return {'passed': empty_result_feedback(new_feedback) and cleared_plot,
            'new_feedback': new_feedback, 'cleared_or_changed_plot': cleared_plot,
            'before_canvas_paints': before_paints, 'after_canvas_paints': paints, 'text': after}


def expected_business_result(task, control_value, *, modified):
    factors = {'calculator': 12*12*(2 if modified else 1),
               'chart': 460 if modified else 360, 'form': 100 if modified else 80}
    return float(control_value) * factors[task['id']]


# Share discovery of a labelled result; a plot tick or reference amount is not a total.
LABELLED_PRIMARY_RESULT_SCRIPT = r"""({names, kind}) => {
  const labelPattern = new RegExp('^'+names+'\\s*[:：]?$', 'i');
  const inlinePattern = new RegExp('^('+names+')\\s*[:：]?\\s*(.*)$', 'i');
  const normal = text => String(text || '').replace(/\s+/g, ' ').trim();
  const visible = element => {
    if (!element.getClientRects().length || getComputedStyle(element).visibility !== 'visible') return false;
    for (let ancestor = element; ancestor; ancestor = ancestor.parentElement) {
      const style = getComputedStyle(ancestor);
      if (style.display === 'none' || Number(style.opacity) === 0 || style.contentVisibility === 'hidden') return false;
    }
    return true;
  };
  const read = element => {
    const nodes = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    const texts = [];
    while (nodes.nextNode()) {
      const parent = nodes.currentNode.parentElement;
      if (visible(parent) && !parent.closest('script,style,pre,code,template')) texts.push(nodes.currentNode.textContent);
    }
    return normal(texts.join(''));
  };
  const amount = text => {
    const value = normal(text).replace(/，/g, ',');
    const match = value.match(kind === 'water' ? /^([+-]?(?:\d{1,3}(?:[,\s]\d{3})+|\d+)(?:\.\d+)?)(?:\s*(?:升|公升|L|liters?))?$/i : /^[¥￥$€]?\s*([+-]?(?:\d{1,3}(?:[,\s]\d{3})+|\d+)(?:\.\d+)?)(?:\s*(?:元|人民币|CNY|RMB))?$/i);
    return match ? Number(match[1].replace(/[,\s]/g, '')) : null;
  };
  const found = [], used = new Set();
  const add = (label, element, text, method) => {
    const value = amount(text);
    if (value === null || !Number.isFinite(value) || used.has(element)) return false;
    used.add(element); found.push({label, value, text: normal(text), method, tag: element.tagName.toLowerCase(), id: element.id || null, rect: (() => { const r = element.getBoundingClientRect(); return {top:r.top,bottom:r.bottom,left:r.left,right:r.right,width:r.width,height:r.height,visible:visible(element)}; })()}); return true;
  };
  const elements = [...document.querySelectorAll('body *')].filter(element => visible(element) && !element.closest('thead,script,style,pre,code,template'));
  for (const element of elements) {
    const aria = normal(element.getAttribute('aria-label'));
    if (labelPattern.test(aria) && !element.matches('input,select,textarea')) add(aria, element, read(element), 'accessible-result');
    const own = normal([...element.childNodes].filter(node => node.nodeType === Node.TEXT_NODE).map(node => node.textContent).join(' '));
    const inline = own.match(inlinePattern);
    if (inline && inline[2] && add(inline[1], element, inline[2], 'inline-result')) continue;
    const label = labelPattern.test(own) ? own : labelPattern.test(read(element)) ? read(element) : null;
    if (!label) continue;
    if (element.closest('thead')) continue;
    const forId = element.getAttribute('for'), associated = forId && document.getElementById(forId);
    if (associated && visible(associated) && !associated.matches('input,select,textarea') && add(label, associated, read(associated), 'labelled-result')) continue;
    const row = element.closest('tr');
    if (row) {
      const cells = [...row.cells].filter(cell => cell !== element && !cell.contains(element) && visible(cell));
      if (kind === 'water' && cells.length) {
        // Detail tables can retain a base-data total beside the adjusted total.
        // Use its column heading rather than assuming which numeric cell is current.
        const table = row.closest('table');
        const currentColumns = new Set([...table.rows].filter(other => other !== row).flatMap(other =>
          [...other.cells].flatMap((cell, index) => /调整|倍率|倍后|当前|换算|scaled|adjusted|current|×/i.test(read(cell)) ? [index] : [])));
        const current = [...row.cells].filter((cell, index) => cells.includes(cell) && currentColumns.has(index));
        const result = current.length === 1 ? current[0] : cells.length === 1 ? cells[0] : null;
        if (result) add(label, result, read(result), 'current-table-total');
        continue;
      }
      if (cells.length === 1 && add(label, cells[0], read(cells[0]), 'labelled-table-row')) continue;
    }
    const self = read(element), remainder = self.startsWith(label) ? self.slice(label.length).replace(/^\s*[:：]/, '') : '';
    if (remainder && add(label, element, remainder, 'label-and-value')) continue;
    const sibling = element.nextElementSibling;
    if (sibling && visible(sibling) && !sibling.matches('input,select,textarea') && add(label, sibling, read(sibling), 'adjacent-result')) continue;
    for (let parent = element.parentElement, depth = 0; parent && depth < 3; parent = parent.parentElement, depth++) {
      if (parent.matches('body,html,main,table,thead')) break;
      const text = read(parent);
      if (text.length > 160) break;
      const start = text.indexOf(label);
      if (start < 0) break;
      const value = text.slice(0, start)+text.slice(start+label.length);
      if (add(label, parent, value.replace(/^\s*[:：]/, ''), 'nearest-result-region')) break;
    }
  }
  return {candidates: found, distinctValues: [...new Set(found.map(item => item.value))], width: innerWidth, height: innerHeight};
}"""

CALCULATOR_PRIMARY_NAMES = '(?:(?:年度|全年|每年|年)[\\u4e00-\\u9fff]{0,8}?(?:费用|成本|支出|花费)|年总计|annual\\s+(?:[a-z]+\\s+){0,3}(?:cost|expense|expenses))'
CHART_PRIMARY_NAMES = r'(?:(?:总(?:用水量|用水|用量|量)|(?:用水量|用水|用量)(?:总计|合计)|总计|合计|总和|total(?:\s+(?:water|usage|consumption))?)(?:\s*[（(]\s*(?:升|公升|L|liters?)\s*[）)])?)'


def primary_result_script(names, kind):
    return '() => (' + LABELLED_PRIMARY_RESULT_SCRIPT + ')(' + json.dumps({'names': names, 'kind': kind}) + ')'


CALCULATOR_PRIMARY_RESULT_SCRIPT = primary_result_script(CALCULATOR_PRIMARY_NAMES, 'currency')
CHART_PRIMARY_RESULT_SCRIPT = primary_result_script(CHART_PRIMARY_NAMES, 'water')


def labelled_primary_result(frame, expected, script, *, timeout=3000):
    """Discover labelled totals before comparing their actual values."""
    from playwright.sync_api import TimeoutError as BrowserTimeout

    def matches(state):
        return bool(state['candidates']) and all(
            math.isclose(item['value'], expected, rel_tol=0, abs_tol=0.005)
            for item in state['candidates'])

    state = frame.evaluate(script)
    if timeout and not matches(state):
        try:
            frame.wait_for_function('expected=>{const state=('+script+')();'
                'return state.candidates.length>0&&state.candidates.every(item=>Math.abs(item.value-expected)<=0.005);}',
                arg=expected, timeout=timeout)
        except BrowserTimeout:
            pass
        state = frame.evaluate(script)
    return {'passed': matches(state), 'expected': expected, **state}


def calculator_primary_result(frame, expected, *, timeout=3000):
    return labelled_primary_result(frame, expected, CALCULATOR_PRIMARY_RESULT_SCRIPT, timeout=timeout)


def chart_primary_result(frame, expected, *, timeout=3000):
    return labelled_primary_result(frame, expected, CHART_PRIMARY_RESULT_SCRIPT, timeout=timeout)


def primary_result_in_viewport(frame, expected, *, task=None):
    if task and task['id'] in {'calculator', 'chart'}:
        reader = calculator_primary_result if task['id'] == 'calculator' else chart_primary_result
        state = reader(frame, expected, timeout=0)
        visible = any(
            box['visible'] and box['width'] > 1 and box['height'] > 1
            and box['top'] >= 0 and box['bottom'] <= state['height'] + 2
            and box['left'] >= 0 and box['right'] <= state['width'] + 2
            for box in (item['rect'] for item in state['candidates']))
        return {**state, 'passed': state['passed'] and visible, 'primary_region_in_viewport': visible}
    layout = frame.get_by_text(number_pattern(expected)).evaluate_all("""es=>({
        width:innerWidth,height:innerHeight,matches:es.map(e=>{
            const r=e.getBoundingClientRect(),s=getComputedStyle(e);
            return {top:r.top,bottom:r.bottom,left:r.left,right:r.right,width:r.width,height:r.height,
                visible:e.getClientRects().length>0&&s.visibility!=='hidden'&&s.display!=='none'&&s.opacity!=='0'};
        })})""")
    visible = any(box['visible'] and box['width'] > 1 and box['height'] > 1
                  and box['top'] >= 0 and box['bottom'] <= layout['height'] + 2
                  and box['left'] >= 0 and box['right'] <= layout['width'] + 2
                  for box in layout['matches'])
    return {'passed': visible, 'expected': expected, **layout}


def business_controls_in_viewport(frame):
    controls = frame.locator('input:not([type="hidden"]),select,textarea,[role="checkbox"],[role="switch"],button[aria-pressed],[role="button"][aria-pressed]').evaluate_all("""es=>es
        .filter(e=>e.getClientRects().length&&getComputedStyle(e).visibility!=='hidden')
        .map(e=>{
            const r=e.getBoundingClientRect();
            return {id:e.id,name:e.getAttribute('aria-label')||e.name,type:e.type,
                top:r.top,bottom:r.bottom,left:r.left,right:r.right,
                passed:r.width>0&&r.height>0&&r.top>=0&&r.bottom<=innerHeight+2&&r.left>=0&&r.right<=innerWidth+2};
        })""")
    return {'passed': bool(controls) and all(c['passed'] for c in controls), 'controls': controls}


def check_restored_business_result(frame, task, expected_value, record, *, modified=True, zero_paints=None):
    """Restored fields must also drive the visible result, not just look filled."""
    if task['id'] in {'calculator', 'chart', 'form'}:
        expected = expected_business_result(task, expected_value, modified=modified)
        text = frame.locator('body').inner_text()
        primary = calculator_primary_result(frame, expected) if task['id'] == 'calculator' else None
        visible_result = primary['passed'] if primary else bool(number_pattern(expected).search(text))
        if task['id'] == 'chart' and expected == 0:
            paints = canvas_paints(frame)
            geometry = chart_evidence(frame, 0, modified=modified)
            visible_canvas = any(item['visible'] for item in paints)
            canvas_restored = not visible_canvas or (zero_paints is not None and paints == zero_paints)
            nonzero_dom_bars = any(plot['tag'] != 'canvas' and plot['visible']
                and sum(bar['visible'] for bar in plot['bars']) >= (4 if modified else 3)
                for plot in geometry['plots'])
            visible_result = visible_result or (empty_result_feedback(text) and canvas_restored and not nonzero_dom_bars)
        record({'name': 'restored-business-result', 'passed': visible_result,
                'detail': {'expected': expected, 'text': text, **({'primary_result': primary} if primary else {})}})


def check_result_order(frame, expected, record, name):
    if expected is not None:
        actual = [item['name'] for item in result_items(frame, 'table')]
        record({'name': name, 'passed': actual == expected, 'expected': expected, 'actual': actual})


def semantic_checks(frame, task, *, modified=False, record=None, inspect_state=None):
    """Assert business semantics through labels/text/roles, allowing varied DOMs."""
    from playwright.sync_api import TimeoutError as BrowserTimeout, expect
    checks = []

    def check(name, passed, detail=None):
        result = {"name": name, "passed": bool(passed), "detail": detail}
        checks.append(result)
        if record:
            record(result)
        if inspect_state and (name == 'keyword-filters-data' or name.endswith('-validation') or 'invalid-input' in name
                              or name == 'invalid-budget-feedback' or 'empty' in name or 'zero' in name):
            # The keyword probe exposes an actual out-of-stock record. Stock-only
            # and empty-result paints cannot reveal its text or row contrast.
            inspect_state(name)

    def text():
        return frame.locator('body').inner_text()

    def change_parameter(locator, value):
        actual = change(locator, value)
        if task['id'] in {'calculator', 'chart'}:
            commit_parameter_changes(frame, task['id'])
        return actual

    def numeric(locator, label):
        try:
            return numeric_control_value(locator, label)
        except MissingBusinessControl:
            check('required-numeric-control', False, label)
            raise

    last_primary_result = None

    def amount_detail():
        return {'text': text(), 'primary_result': last_primary_result} if task['id'] == 'calculator' else text()

    def amount(value, previous_text=None):
        nonlocal last_primary_result
        if task['id'] == 'calculator':
            last_primary_result = calculator_primary_result(frame, value)
            return last_primary_result['passed']
        pattern = number_pattern(value)
        try:
            if previous_text is None:
                expect(frame.locator('body')).to_contain_text(pattern, timeout=3000)
            else:
                frame.wait_for_function("args=>[...document.body.innerText.matchAll(new RegExp(args.pattern,'g'))].length>args.count", arg={'pattern': pattern.pattern, 'count': len(pattern.findall(previous_text))}, timeout=3000)
            return True
        except (AssertionError, BrowserTimeout):
            return False

    def invalid(locator, message, before_text, observation=None):
        return field_validation_feedback(frame, locator, message, before_text, observation=observation)

    field = control(frame, task['control'])
    if task.get('id') == 'form' and field.count() and (not field.is_visible() or not field.is_enabled()):
        reopen_form_through_button(frame)
    try:
        field.wait_for(timeout=15000)
    except BrowserTimeout as error:
        detail = f'No usable accessible control for {task["control"]}.'
        check('required-accessible-control', False, detail)
        raise MissingBusinessControl(detail) from error
    initial = field.input_value()
    if task['id'] in {'calculator', 'chart', 'form', 'comparison'}:
        initial_numeric = numeric(field, task['control'])
    if task['id'] in {'calculator', 'chart', 'form'}:
        expected = task['initial']
        if modified:
            expected = initial_numeric * {'calculator': 12*12*2, 'chart': 460, 'form': 100}[task['id']]
        check('initial-business-result', amount(int(expected) if expected == int(expected) else expected), amount_detail())
    if task['id'] == 'calculator' and not modified:
        return_trips = frame.get_by_label(re.compile('往返'))
        daily_counts = frame.get_by_label(re.compile('每日.*次数|每天.*次数|单程次数')).and_(frame.locator('input'))
        check('single-trip-default', not return_trips.count() or not return_trips.first.is_checked())
        if daily_counts.count():
            check('single-trip-daily-count', numeric(daily_counts.first, '每日单程次数') == 1)
    if task['id'] == 'calculator' and modified:
        return_trip = frame.get_by_label(re.compile('往返')).first
        check('round-trip-default', return_trip.is_checked())
        return_trip.uncheck()
        check('round-trip-changes-formula', amount(12*initial_numeric*12), amount_detail())
        return_trip.check()
        trips = frame.get_by_label(re.compile('每日.*次数|每天.*次数|单程次数')).and_(frame.locator('input')).first
        if trips.count() and trips.is_visible() and trips.is_enabled() and trips.is_editable():
            change_parameter(trips, '3')
            expected = 12*numeric(field, task['control'])*12*(2 if return_trip.is_checked() else 1)
            check('round-trip-controls-daily-count', amount(expected), amount_detail())
            return_trip.uncheck()
            return_trip.check()
    if task['id'] == 'table':
        def items():
            return result_items(frame, 'table')

        def item_names():
            return [item['name'] for item in items()]

        price = None
        if modified:
            price = frame.get_by_label(re.compile('最高价格|价格上限|最高价')).first
            check('new-price-filter-default', numeric(price, '价格上限') == 50)
            change_parameter(field, '')
            check('natural-language-price-filter', set(item_names()).issubset({'笔记本', '水杯'}) and bool(item_names()), items())
            change_parameter(price, '200')
        else:
            check('default-price-order', item_names() == ['笔记本', '水杯', '收纳盒', '台灯'], items())
        stock = stock_filter_control(frame)
        set_stock_filter(stock, False)
        change_parameter(field, '台灯')
        check('keyword-filters-data', item_names() == ['台灯'], items())
        change_parameter(field, '不存在的商品')
        check('empty-data-feedback', not items() and empty_result_feedback(text()), {'items': items(), 'text': text()})
        clear = frame.get_by_role('button', name=re.compile('清除|清空|重置')).first
        if clear.count():
            clear.click()
            check('clear-filter-action', field.input_value() == '' and '水杯' in item_names(), items())
        else:
            check('clear-filter-action', False, 'Missing clear-filter action')
            change_parameter(field, '')  # Continue independent checks through the real input.
        if modified:
            change_parameter(price, '200')
        set_stock_filter(stock, False)
        sorts = frame.get_by_role('combobox')
        sorted_by_select = False
        for index in range(sorts.count()):
            sort = sorts.nth(index)
            options = sort.locator('option').all_text_contents()
            descending = next((v for v in options if re.search('降|高到低|↓|⬇|▼|desc', v, re.I)), None)
            if descending:
                sort.select_option(label=descending)
                check('sort-descending', item_names() == ['台灯', '收纳盒', '水杯', '笔记本'], items())
                sorted_by_select = True
                break
        if not sorted_by_select:
            button = frame.get_by_role('button', name=re.compile('降序|高到低|↓|⬇|▼|descending', re.I)).first
            if not button.count():
                button = frame.get_by_role('button', name=re.compile('价格')).first
            if not button.count():
                button = frame.get_by_role('button', name=re.compile('升序|低到高|↑|⬆|▲|ascending', re.I)).first
            if button.count():
                action = button.element_handle()
                action.click()
                # Toggle buttons can retain descending order from the prior view.
                # Observe their result before the second real click.
                if item_names() == ['笔记本', '水杯', '收纳盒', '台灯']:
                    action.click()
                check('sort-descending', item_names() == ['台灯', '收纳盒', '水杯', '笔记本'], items())
            else:
                check('sort-control', False)
        if set_stock_filter(stock, True):
            check('stock-filter', set(item_names()) == {'收纳盒', '水杯', '笔记本'}, items())
            change_parameter(field, '台灯')
            check('combined-table-filters', not items(), items())
            change_parameter(field, '')
        else:
            check('stock-filter', False)
        if modified:
            change_parameter(price, '50')
            check('natural-language-price-filter', set(item_names()) == {'水杯', '笔记本'}, items())
    elif task['id'] == 'comparison':
        distance = control(frame, '距离')
        if not distance.count():
            distance = frame.get_by_label(re.compile('步行|公里')).and_(frame.locator('input,select')).first
        routes = [('山谷', 120, 2), ('日落', 220, 5), ('城郊', 160, 8)]
        if modified:
            routes.append(('湖畔', 180, 4))

        def expected_routes():
            return {name for name, price, walk in routes
                    if price <= numeric(field, task['control']) and walk <= numeric(distance, '距离')}

        def actual_routes():
            return {item['name'] for item in result_items(frame, 'comparison')}

        check('default-combined-filter', actual_routes() == expected_routes(), result_items(frame, 'comparison'))
        if not modified:
            check('both-route-constraints', numeric(field, task['control']) == 200 and numeric(distance, '距离') == 5
                  and actual_routes() == {'山谷'}, result_items(frame, 'comparison'))
        change_parameter(field, '50')
        apply_filters_if_present(frame)
        check('empty-data-feedback', not actual_routes() and empty_result_feedback(text()), text())
        feedback = check_negative_input(frame, field, commit=lambda: apply_filters_if_present(frame))
        check('invalid-budget-feedback', feedback['passed'], feedback)
        change_parameter(field, '250')
        change_parameter(distance, '3')
        apply_filters_if_present(frame)
        check('distance-filter', actual_routes() == {'山谷'}, result_items(frame, 'comparison'))
        change_parameter(distance, '5')
        apply_filters_if_present(frame)
        check('distance-filter', actual_routes() == expected_routes(), result_items(frame, 'comparison'))
        # Exercise two different choices. Old saved confirmation cannot satisfy
        # either action unless it changes to the record actually clicked.
        options = result_items(frame, 'comparison')
        previous_selection = selected_route_names(frame)
        alternatives = [item for item in options if not any(item['name'] in line for line in previous_selection)]
        choices = (alternatives or options)[-1:]
        if choices:
            choices += next(([item] for item in options if item['name'] != choices[0]['name']), [])
        check('selectable-routes', bool(choices), options)
        for item in choices:
            action = result_item_action(frame, item)
            usable = action is not None and action.is_visible() and action.is_enabled()
            check('route-choice-action', usable, {'name': item['name']})
            if not usable:
                continue
            check('route-choice-keyboard-accessible', action.evaluate('e=>e.tabIndex>=0&&!e.disabled'), {'name': item['name']})
            before_selection = selected_route_names(frame)
            choose_result_item(frame, item)
            feedback = selected_route_names(frame)
            native_checked = action.evaluate('e=>e.type==="radio"&&e.checked') if len(options) == 1 else False
            check('selection-feedback', feedback == [item['name']]
                  and (feedback != before_selection or native_checked),
                  {'chosen': item['name'], 'before': before_selection, 'after': feedback})
    else:
        before_change = text()
        value = task['value']
        if modified and field.input_value() == value:
            value = str(float(value) + 1)
        change_parameter(field, value)
        if task['id'] in {'calculator', 'chart', 'form'}:
            expected = float(value) * {'calculator': 12*12*2, 'chart': 460, 'form': 100}[task['id']] if modified else task['changed']
            check('local-recalculation', amount(expected, before_change), amount_detail())
            if task['id'] == 'calculator':
                money = re.escape(f'{expected:,.2f}').replace(',', '[,， \u00a0\u202f\u2009]?')
                primary_text = '\n'.join(item['text'] for item in last_primary_result['candidates'])
                check('two-decimal-currency', bool(re.search(r'(?<![\d.])'+money+r'(?!\d)', primary_text)), amount_detail())
        if task['id'] in {'calculator', 'chart'}:
            before_zero = text()
            before_paints = canvas_paints(frame) if task['id'] == 'chart' else []
            change_parameter(field, '0')
            if task['id'] == 'chart':
                evidence = chart_zero_state(frame, before_zero, before_paints, modified=modified)
                check('zero-state', evidence['passed'], evidence)
            else:
                check('zero-state', amount(0, before_zero), amount_detail())
            # Independent invalid-input checks start from a valid value rather
            # than reusing an error already displayed by the zero-state check.
            change_parameter(field, task['value'])
            feedback = check_negative_input(frame, field, commit=lambda: commit_parameter_changes(frame, task['id']))
            check('invalid-input-feedback', feedback['passed'], feedback)
        if task['id'] == 'form':
            name, email = control(frame, '姓名'), control(frame, '邮箱')
            submit = frame.get_by_role('button', name=re.compile('报名|提交')).first
            with observe_field_validation(name) as name_observation, \
                 observe_field_validation(email) as email_observation, \
                 observe_field_validation(field) as people_observation:
                before = text()
                name.fill('')
                email.fill('')
                submit.click()
                missing_name = invalid(name, '姓名.*(填|空)|请.*姓名', before, name_observation)
                first_name_error = bool(re.search('姓名.*(填|空)|请.*姓名', text()))
                # Both fields can report errors during the first real submit.
                # Preserve that evidence when an unassociated error is repeated unchanged.
                first_missing_email = invalid(email, '邮箱.*(填|空)|请.*邮箱', before, email_observation)
                before = text()
                name.fill('王小明')
                submit.click()
                missing_email = first_missing_email or invalid(email, '邮箱.*(填|空)|请.*邮箱', before, email_observation)
                # An error restored before this probe can already be visible.
                # Its disappearance after a real valid-name submission proves
                # activity; permanently displayed static help cannot satisfy it.
                missing_name = missing_name or (first_name_error and not re.search('姓名.*(填|空)|请.*姓名', text()))
                check('required-field-validation', missing_name and missing_email, text())
                before = text()
                email.fill('bad-address')
                submit.click()
                check('email-validation', invalid(email, '邮箱.*(错误|格式)|有效.*邮箱', before, email_observation), text())
                email.fill('synthetic@example.invalid')
                before = text()
                name.fill('长中文姓名用于边界验证长中文姓名用于边界验证')
                if len(name.input_value()) > 20:
                    submit.click()
                check('name-length-validation', len(name.input_value()) <= 20 or invalid(name, '20|二十|姓名.*(长|字数)', before, name_observation), text())
                name.fill('王小明')
                domain = None
                if field.evaluate('e=>e.tagName') == 'SELECT':
                    domain = field.locator('option').evaluate_all('''options=>options
                        .filter(e=>!e.disabled&&!e.closest('optgroup[disabled]')).map(e=>e.value)''')
                for value, check_name, message in [
                    ('0', 'people-range-validation', '人数.*(1|一)|至少'),
                    ('6', 'people-maximum-validation', '人数.*(5|五)|最多|不超过'),
                ]:
                    if domain is not None and value not in domain:
                        check(check_name, True, {'unavailable_native_choice': value, 'offered_values': domain})
                        continue
                    before = text()
                    change_parameter(field, value)
                    submit.click()
                    check(check_name, invalid(field, message, before, people_observation), text())
            change_parameter(field, '3')
            # The successful action runs after the view's mode/state checks.
            # A valid confirmation may replace the form entirely.
        change_parameter(field, task['value'])
        if task['id'] == 'calculator':
            fare, months = control(frame, '票价'), control(frame, '月数')
            for label, other in [('票价', fare), ('月数', months)]:
                try:
                    other.wait_for(timeout=15000)
                except BrowserTimeout as error:
                    check('required-accessible-control', False, 'No usable control for '+label)
                    raise MissingBusinessControl('No usable control for '+label) from error
            fare_value, month_value = numeric(fare, '票价'), numeric(months, '月数')
            for name, other, original_value, other_factor in [
                ('fare', fare, fare.input_value(), month_value),
                ('months', months, months.input_value(), fare_value),
            ]:
                previous = text()
                change_parameter(other, '10')
                expected = 10*numeric(field, task['control'])*other_factor*(2 if modified else 1)
                check(name+'-recalculation', amount(expected, previous), amount_detail())
                previous = text()
                change_parameter(other, '0')
                check(name+'-zero-state', amount(0, previous), amount_detail())
                change_parameter(other, original_value)
                feedback = check_negative_input(frame, other, commit=lambda: commit_parameter_changes(frame, task['id']))
                check(name+'-invalid-input', feedback['passed'], feedback)
                change_parameter(other, original_value)
        if task['id'] == 'chart':
            evidence = chart_evidence(frame, numeric(field, task['control']), modified=modified)
            check('chart-visible-bars', evidence['visible_bars'], evidence['plots'])
            check('chart-readable-data', evidence['readable_data'], evidence['details'])
    field.focus()
    check('keyboard-focus', field.evaluate('e=>e===document.activeElement && e.tabIndex>=0 && !e.disabled'))
    check('no-horizontal-overflow', frame.evaluate('document.documentElement.scrollWidth <= innerWidth + 2'))
    return checks, initial


def snapshot_controls(frame):
    return frame.locator(VALUE_CONTROL_SELECTOR).evaluate_all("""es=>es.map(e=>{
        const state={tag:e.tagName,type:e.type,id:e.id,name:e.name,value:e.value,checked:e.checked};
        const role=e.getAttribute('role');
        if(e.tagName!=='INPUT'&&['checkbox','switch'].includes(role)){
            state.type=role;state.checked=e.getAttribute('aria-checked')==='true';
        }else if(e.matches('button[aria-pressed],[role="button"][aria-pressed]')){
            state.type='pressed-button';state.checked=e.getAttribute('aria-pressed')==='true';
        }
        return state;
    })""")


def restore_controls_through_inputs(frame, expected):
    """Undo verifier input actions before feedback, using actual controls only."""
    controls = frame.locator(VALUE_CONTROL_SELECTOR)
    if controls.count() != len(expected):
        return False
    for index, state in enumerate(expected):
        field = controls.nth(index)
        if not field.is_visible() or not field.is_enabled():
            continue
        if state['type'] in {'checkbox', 'switch', 'pressed-button'}:
            if not set_toggle_checked(field, state['checked']):
                return False
        elif state['type'] == 'radio':
            if state['checked']:
                field.check()
        elif state['type'] not in {'file', 'hidden', 'button', 'submit', 'reset'}:
            if field.input_value() != state['value'] and field.is_editable():
                # Leaving the final field with Tab can focus a host control,
                # scroll the component offscreen and legitimately unmount it.
                # Use a real reverse Tab for cleanup inside this same view.
                change(field, state['value'], tab_key='Shift+Tab' if index else 'Tab')
    return True


def restore_table_order_through_button(frame, expected_names):
    """Undo a sort toggle after a failed probe, without touching view state."""
    if [item['name'] for item in result_items(frame, 'table')] == expected_names:
        return True
    buttons = frame.get_by_role('button', name=re.compile('价格|升序|降序|排序|↑|↓|⬆|⬇|▲|▼'))
    for index in range(buttons.count()):
        button = buttons.nth(index).element_handle()
        button.click()
        if [item['name'] for item in result_items(frame, 'table')] == expected_names:
            return True
    return False


def restore_selection_through_button(frame, expected_feedback):
    """Undo a zero-budget probe that legitimately cleared an ineligible choice."""
    if selected_route_names(frame) == expected_feedback:
        return True
    names = [name for name in ['山谷', '日落', '城郊', '湖畔']
             if any(name in line for line in expected_feedback)]
    if len(names) != 1:
        return False
    for item in result_items(frame, 'comparison'):
        if item['name'] == names[0]:
            choose_result_item(frame, item)
            return selected_route_names(frame) == expected_feedback
    return False


def independent_matrix(args):
    """Each sample owns its workspace, memory, profile and Desktop process."""
    output = args.output.resolve()
    if not output.is_relative_to(ROOT):
        raise ValueError('Evidence must stay in this repository')
    output.mkdir(parents=True, exist_ok=False)
    fixture = json.loads(args.task_file.read_text(encoding='utf-8'))
    report = {'source': args.source, 'model': args.model, 'task_version': fixture['version'],
              'task_sha256': hashlib.sha256(args.task_file.read_bytes()).hexdigest(),
              'independent_profiles': True, 'samples': []}
    report.update(report_schema='riu-quality.v2', max_model_repairs=args.max_model_repairs,
                  started_at_utc=datetime.now(timezone.utc).isoformat())
    dump(output / 'matrix.json', report)
    for attempt in range(1, args.attempts + 1):
        for task in fixture['tasks']:
            if task['id'] not in args.tasks:
                continue
            name = f"{task['id']}-{attempt}"
            child = output / name
            report['current_sample'] = {'task': task['id'], 'attempt': attempt,
                                        'started_at_utc': datetime.now(timezone.utc).isoformat()}
            dump(output / 'matrix.json', report)
            command = [sys.executable, str(Path(__file__).resolve()), '--exe', str(args.exe.resolve()),
                       '--output', str(child), '--source', args.source, '--model', args.model,
                       '--task-file', str(args.task_file.resolve()), '--attempts', '1', '--tasks', task['id'],
                       '--timeout', str(args.timeout), '--max-model-repairs', str(args.max_model_repairs), '--shared-profile']
            if args.api_url:
                command += ['--api-url', args.api_url]
            if args.generation_only:
                command += ['--generation-only']
            with (output / f'{name}.txt').open('w', encoding='utf-8') as log:
                completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
            entry = {'task': task['id'], 'attempt': attempt, 'exit_code': completed.returncode,
                     'report': str(child / 'report.json')}
            if (child / 'report.json').exists():
                entry['cases'] = json.loads((child / 'report.json').read_text(encoding='utf-8')).get('cases', [])
            report['samples'].append(entry)
            dump(output / 'matrix.json', report)
            print(json.dumps({'sample': name, 'exit_code': completed.returncode}), flush=True)
    report.pop('current_sample', None)
    report['completed_at_utc'] = datetime.now(timezone.utc).isoformat()
    dump(output / 'matrix.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--source', choices=['sensenova', 'nvidia', 'opencode', 'standard'], default='sensenova')
    parser.add_argument('--api-url', help='Provider Chat API base URL; used only inside the isolated profile.')
    parser.add_argument('--model', default='sensenova-6.8-flash-lite')
    parser.add_argument('--task-file', type=Path, default=TASK_FILE)
    parser.add_argument('--attempts', type=int, default=3)
    parser.add_argument('--tasks', nargs='+', default=['calculator', 'table', 'chart', 'form', 'comparison', 'text'])
    parser.add_argument('--timeout', type=int, default=900, help='Wall-clock deadline per model turn; no output/token cap is added.')
    parser.add_argument('--max-model-repairs', type=int, default=2, help='Maximum normal feedback turns per sample; raw failed stages remain in the report.')
    parser.add_argument('--generation-only', action='store_true', help='Retain generation baseline without semantic/mutation checks.')
    parser.add_argument('--shared-profile', action='store_true', help='Historical comparison only: permit multiple samples to share workspace memory.')
    args = parser.parse_args()
    if args.max_model_repairs < 0:
        parser.error('--max-model-repairs must be nonnegative')
    if not args.shared_profile and (args.attempts > 1 or len(args.tasks) > 1):
        independent_matrix(args)
        return
    from playwright.sync_api import sync_playwright
    from reverie.config import ConfigManager
    from reverie.session.manager import SessionManager
    from reverie.views import ViewStore, visible_view_references

    output = args.output.resolve()
    if not output.is_relative_to(ROOT):
        raise ValueError('Evidence must stay in this repository')
    output.mkdir(parents=True, exist_ok=False)
    shutil.copy2(__file__, output / 'executed-verifier.py')
    temporary = output / 'temp'
    temporary.mkdir()
    os.environ['TEMP'] = os.environ['TMP'] = str(temporary)
    original = ConfigManager(ROOT).load()
    app_root, workspace, home = [output / name for name in ('app-root', 'workspace', 'desktop-home')]
    for directory in (app_root, workspace, home):
        directory.mkdir()
    workspace_isolation = prepare_isolated_workspace(workspace)
    os.environ['REVERIE_APP_ROOT'] = str(app_root)
    os.environ['NO_PROXY'] = '127.0.0.1,localhost'
    cfg = ConfigManager(workspace).load()
    if args.source == 'standard' and not args.api_url:
        parser.error('--source standard requires --api-url')
    configure_model_source(cfg, original, args.source, args.model, api_url=args.api_url)
    active = cfg.active_model
    if not active or active.model != args.model:
        raise ValueError('Configured model not resolved exactly')
    if active.provider not in {'openai-chat', 'openai-sdk'}:
        raise ValueError('This recorder verifies Chat Completions only; Responses/Messages must use their own protocol.')
    upstream = active.base_url.rstrip('/')
    if not upstream.endswith('/chat/completions'):
        upstream += '/chat/completions'
    models_url = None
    if args.source == 'opencode':
        from reverie.opencode import _opencode_models_url
        models_url = _opencode_models_url(cfg.opencode['api_url'])
    recorder = Recorder(output, upstream, active.api_key, models_url=models_url, request_timeout=args.timeout)
    configure_model_source(cfg, original, args.source, args.model, recorder_url=f'http://127.0.0.1:{recorder.server.server_port}/v1')
    cfg.security = copy.deepcopy(original.security)
    cfg.api_proxy = original.api_proxy
    cfg.api_timeout = args.timeout
    cfg.api_max_retries = original.api_max_retries
    cfg.api_initial_backoff = original.api_initial_backoff
    cfg.stream_responses = True
    config = ConfigManager(workspace)
    config.ensure_dirs()
    config.save(cfg)
    manager = SessionManager(config.project_data_dir, project_root=workspace)
    task_file = args.task_file.resolve()
    if not task_file.is_relative_to(ROOT):
        raise ValueError('Task fixtures must stay in this repository')
    fixture = json.loads(task_file.read_text(encoding='utf-8'))
    sessions = {f"{task['id']}-{attempt}": manager.create_session(f"RIU quality {task['id']}-{attempt}") for task in fixture['tasks'] if task['id'] in args.tasks for attempt in range(1, args.attempts+1)}
    dump(output / 'fixed-tasks.json', fixture)
    settings = home / '.reverie/desktop/desktop-settings.json'
    settings.parent.mkdir(parents=True)
    dump(settings, {'coreAppRoot': str(app_root), 'projectRoot': str(workspace), 'ui': {'language': 'zh-CN', 'showReasoning': True, 'expandReasoning': True}})
    report = {'scope': 'Fresh packaged Desktop sessions, real configured model and executor, no test-authored HTML', 'model': active.model, 'source': args.source, 'task_version': fixture['version'], 'task_sha256': hashlib.sha256(task_file.read_bytes()).hexdigest(), 'attempts_per_task': args.attempts, 'cases': [], 'credential_cleanup': False}
    report['generation_only'] = args.generation_only
    report['report_schema'] = 'riu-quality.v2'
    report['workspace_isolation'] = workspace_isolation
    report['max_model_repairs'] = args.max_model_repairs
    report['model_turn_timeout_seconds'] = args.timeout
    report['isolated_http_read_timeout_seconds'] = cfg.api_timeout
    report['authentication'] = 'configured-key' if active.api_key else 'anonymous'
    report['verifier_sha256'] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report['browser_errors'] = []
    process = None
    log = (output / 'electron.log').open('w', encoding='utf-8')

    def save():
        dump(output / 'report.json', report)

    def launch(playwright):
        nonlocal process
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        env = {**os.environ, 'PORTABLE_EXECUTABLE_DIR': str(home)}
        env.pop('ELECTRON_RUN_AS_NODE', None)
        process = subprocess.Popen([str(args.exe.resolve()), '--gui', '--project', str(workspace), f'--remote-debugging-port={port}'], env=env, stdout=log, stderr=log, **launch_options())
        browser, page = wait_for_packaged_page(playwright, process, port)
        page.on('pageerror', lambda error: report['browser_errors'].append({'case': recorder.case, 'at': time.time(), 'error': str(error).replace(active.api_key, '[redacted]') if active.api_key else str(error)}))
        page.set_viewport_size({'width': 1280, 'height': 900})
        page.wait_for_selector('textarea[aria-autocomplete=list]', timeout=120000)
        return browser, page

    try:
        with sync_playwright() as p:
            started = time.perf_counter()
            browser, page = launch(p)
            report['desktop_startup_ms'] = (time.perf_counter()-started)*1000
            report['build'] = page.evaluate('window.reverie.paths()')
            for task in fixture['tasks']:
                if task['id'] not in args.tasks:
                    continue
                for attempt in range(1, args.attempts+1):
                    case_id = f"{task['id']}-{attempt}"
                    case_out = output / case_id
                    case_out.mkdir()
                    session = sessions[case_id]
                    # Production API refreshes the real sidebar after external synthetic-session creation.
                    page.reload()
                    page.locator('.session-item').filter(has_text='RIU quality ' + case_id).click(timeout=120000)
                    page.locator('.session-loading').wait_for(state='hidden', timeout=60000)
                    case = {'id': case_id, 'task': task['id'], 'attempt': attempt, 'session_id': session.id, 'checks': [], 'turns': [], 'stages': [], 'repair_count': 0}
                    report['cases'].append(case)
                    save()
                    recorder.case = case_id
                    start_event_capture(page)
                    print(json.dumps({'stage': case_id, 'model': active.model}), flush=True)

                    def send(prompt, stage):
                        case['phase'] = 'model-' + stage
                        save()
                        started = time.perf_counter()
                        request_start = len(recorder.records)
                        event_start = start_event_capture(page)
                        page_start = page.evaluate('performance.now()')
                        page.locator('textarea[aria-autocomplete=list]').fill(prompt)
                        page.get_by_role('button', name='发送', exact=True).click()
                        stop = page.get_by_role('button', name='停止', exact=True)
                        mismatches = []
                        while True:
                            events = page.evaluate('n=>window.__qualityEvents.slice(n).filter(item=>item.event.type==="executors.changed")', event_start)
                            began, active_lease = execution_state(events, session.id)
                            if began and not active_lease:
                                break
                            elapsed = time.perf_counter()-started
                            if active_lease and not stop.is_visible() and not mismatches:
                                mismatches.append({'at_ms': elapsed*1000, 'event_count': len(events)})
                            if elapsed > args.timeout:
                                case['turns'].append({'stage': stage, 'model_turn_ms': elapsed*1000, 'timeout': True, 'request_indices': list(range(request_start, len(recorder.records)))})
                                raise TimeoutError('Production execution lease did not finish before the turn deadline')
                            page.wait_for_timeout(500)
                        stop.wait_for(state='hidden', timeout=30000)
                        page.wait_for_timeout(250)
                        turn = {'stage': stage, 'model_turn_ms': (time.perf_counter()-started)*1000, 'request_indices': list(range(request_start, len(recorder.records)))}
                        requests = recorder.records[request_start:]
                        if requests:
                            turn['local_before_first_request_ms'] = (requests[0]['started_monotonic']-started)*1000
                            last = requests[-1]
                            if 'complete_ms' in last:
                                turn['local_after_last_response_ms'] = (time.perf_counter()-last['started_monotonic'])*1000-last['complete_ms']
                        turn['active_lease_without_stop_button'] = mismatches
                        turn_events = page.evaluate('n=>window.__qualityEvents.slice(n)', event_start)
                        for item in turn_events:
                            event = item.get('event', {})
                            if event.get('type') == 'prompt.event':
                                event = event.get('event', {})
                            kind = event.get('type')
                            if kind in {'reasoning.delta', 'assistant.delta'} and event.get('text'):
                                turn.setdefault('first-' + kind + '-renderer-event-ms', item['at']-page_start)
                            if kind == 'ui.event':
                                inner = event.get('event', {})
                                if inner.get('event') in {'tool_start', 'tool_result', 'view_ready'}:
                                    turn.setdefault('first-' + inner['event'] + '-renderer-event-ms', item['at']-page_start)
                                if inner.get('event') == 'tool_result' and inner.get('success') is True:
                                    turn.setdefault('first-successful-executor-tool-result-ms', item['at']-page_start)
                        native_errors = inspect_native_model_errors(turn_events, session.id)
                        turn['native_model_errors'] = native_errors['errors']
                        turn['terminal_native_model_error'] = native_errors['terminal_error']
                        case['turns'].append(turn)
                        dump(case_out / (stage + '-events.json'), page.evaluate('window.__qualityEvents'))
                        restored = manager.load_session(session.id)
                        dump(case_out / (stage + '-session.json'), restored.to_dict())
                        save()
                        if native_errors['terminal_error']:
                            error = native_errors['terminal_error']
                            raise RuntimeError(error.get('detail') or error.get('message') or 'Native model request failed')
                        errors = page.locator('.inline-error').all_text_contents()
                        if errors:
                            raise RuntimeError('\n'.join(errors))
                        case['phase'] = 'browser-' + stage
                        return restored

                    def frame(view_ref=None):
                        if view_ref is None:
                            view_ref = latest_published_view_reference(
                                manager.load_session(session.id).messages, ViewStore.for_project(workspace), session.id)
                        if view_ref is None:
                            raise ValueError('No actual published view is registered for this session.')
                        return wait_for_registered_view_frame(page, view_ref, process=process)

                    def inspect_view(saved, stage, record, original=None):
                        from playwright.sync_api import TimeoutError as BrowserTimeout
                        calls = [c for m in saved.messages for c in m.get('tool_calls', [])]
                        names = [c.get('function', {}).get('name') for c in calls]
                        case['tool_names'] = names
                        case['violations'] = tool_scope_violations(names, fixture, task)
                        store = ViewStore.for_project(workspace)
                        ref = latest_published_view_reference(saved.messages, store, session.id)
                        record({'name': 'registered-view', 'passed': ref is not None})
                        if ref is None:
                            page.screenshot(path=str(case_out / (stage + '-no-view.png')), full_page=True)
                            return {}
                        path, manifest = store.resolve_entry(session.id, *ref)
                        payload = {'ref': ref, 'path': path, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                                   'manifest': manifest.to_dict()}
                        if original:
                            record({'name': 'stored-version-history',
                                    'passed': ref[0] == original['ref'][0] and ref[1] > original['ref'][1]
                                              and hashlib.sha256(original['path'].read_bytes()).hexdigest() == original['sha256']})
                            if ref == original['ref']:
                                record({'name': 'modified-view-registration', 'passed': False,
                                        'detail': 'The requested modification did not register a new revision.'})
                                return payload
                        iframe, inside = frame(ref)
                        settle_view(page, inside)
                        page.wait_for_timeout(250)
                        if task['id'] == 'form' and (not control(inside, task['control']).is_visible() or not control(inside, task['control']).is_enabled()):
                            reopen_form_through_button(inside)
                        initial_controls = snapshot_controls(inside)
                        initial_order = [item['name'] for item in result_items(inside, 'table')] if task['id'] == 'table' else None
                        page.screenshot(path=str(case_out / (stage + '.png')), full_page=True)
                        dump(case_out / (stage + '-dom.json'), {
                            'text': inside.locator('body').inner_text(), 'controls': initial_controls})
                        case['local_render_marks'] = page.evaluate("({time_origin:performance.timeOrigin,marks:performance.getEntriesByType('mark').filter(e=>e.name.startsWith('riu-view:')).map(e=>({name:e.name,start_ms:e.startTime}))})")
                        if args.generation_only:
                            return payload
                        iframe.locator('..').locator('[data-view-mode="fullscreen"]').click()
                        settle_view(page, inside)
                        case['business_check_display_mode'] = 'fullscreen'
                        inside.evaluate("window.__qualityInputTimings=[];document.addEventListener('input',e=>{const start=performance.now(),control=e.target.getAttribute('aria-label')||e.target.id||e.target.type;requestAnimationFrame(()=>requestAnimationFrame(()=>window.__qualityInputTimings.push({control,input_to_two_frames_ms:performance.now()-start})))},true)")
                        stage_checks = []
                        def check(value):
                            stage_checks.append(value)
                            record(value)
                        def inspect_state(label):
                            """Read actual validation/empty/confirmation paints in both host themes."""
                            original_theme = page.evaluate('document.documentElement.dataset.theme')
                            expected_state = snapshot_controls(inside)
                            try:
                                for value in [original_theme, 'dark' if original_theme == 'light' else 'light']:
                                    before_style = inside.locator('body').evaluate('e=>({bg:getComputedStyle(e).backgroundColor,color:getComputedStyle(e).color})')
                                    if page.evaluate('document.documentElement.dataset.theme') != value:
                                        page.evaluate('value=>window.reverie.setAppearance(value)', value)
                                        wait_for_body_theme_change(inside, before_style)
                                    settle_view(page, inside)
                                    evidence = swept_text_contrast(inside)
                                    check({'name': 'readable-state-' + label + '-' + value,
                                           'passed': evidence['tested'] > 0 and not evidence['failures'], 'detail': evidence})
                                    actual_state = snapshot_controls(inside)
                                    check({'name': 'theme-state-' + label + '-' + value,
                                           'passed': actual_state == expected_state,
                                           'expected': expected_state, 'actual': actual_state})
                                    iframe.screenshot(path=str(case_out / (stage + '-state-' + label + '-' + value + '.png')))
                            finally:
                                if page.evaluate('document.documentElement.dataset.theme') != original_theme:
                                    before_style = inside.locator('body').evaluate('e=>({bg:getComputedStyle(e).backgroundColor,color:getComputedStyle(e).color})')
                                    page.evaluate('value=>window.reverie.setAppearance(value)', original_theme)
                                    wait_for_body_theme_change(inside, before_style)
                                    settle_view(page, inside)
                        try:
                            semantic_checks(inside, task, modified=original is not None, record=check, inspect_state=inspect_state)
                        except (MissingBusinessControl, BrowserTimeout) as error:
                            check({'name': 'business-controls-operable', 'passed': False,
                                   'detail': type(error).__name__ + ': ' + str(error)})
                            restore_controls_through_inputs(inside, initial_controls)
                            commit_parameter_changes(inside, task['id'])
                            if initial_order is not None:
                                restore_table_order_through_button(inside, initial_order)
                            return payload
                        mode_controls = snapshot_controls(inside)
                        mode_control_value = control(inside, task['control']).input_value()
                        mode_order = [item['name'] for item in result_items(inside, 'table')] if task['id'] == 'table' else None
                        doc_id = inside.evaluate('window.__qualityInstance=String(performance.timeOrigin)+String(Math.random())')
                        for mode in ['fullscreen', 'pip', 'inline']:
                            iframe.locator('..').locator(f'[data-view-mode="{mode}"]').click()
                            settle_view(page, inside)
                            check({'name': 'same-instance-' + mode, 'passed': inside.evaluate('window.__qualityInstance') == doc_id})
                            actual_controls = snapshot_controls(inside)
                            check({'name': 'mode-preserves-controls-' + mode,
                                   'passed': sorted(json.dumps(c, sort_keys=True) for c in actual_controls)
                                             == sorted(json.dumps(c, sort_keys=True) for c in mode_controls)
                                             and control(inside, task['control']).input_value() == mode_control_value,
                                   'expected': mode_controls, 'actual': actual_controls})
                            check_result_order(inside, mode_order, check, 'mode-preserves-result-order-' + mode)
                            inside.evaluate('window.scrollTo(0,0)')
                            layout = control(inside, task['control']).evaluate('e=>({top:e.getBoundingClientRect().top,bottom:e.getBoundingClientRect().bottom,control_height:e.getBoundingClientRect().height,height:innerHeight,width:innerWidth,scroll:document.documentElement.scrollWidth})')
                            check({'name': 'layout-' + mode, 'passed': layout['scroll'] <= layout['width']+2 and (mode != 'pip' or (layout['control_height'] > 0 and 0 <= layout['top'] and layout['bottom'] <= layout['height']+2)), 'detail': layout})
                            if mode == 'pip':
                                inputs = business_controls_in_viewport(inside)
                                check({'name': 'layout-pip-controls', 'passed': inputs['passed'], 'detail': inputs})
                            if mode == 'pip' and task['id'] in {'calculator', 'chart', 'form'}:
                                visibility = primary_result_in_viewport(
                                    inside, expected_business_result(task, mode_control_value, modified=original is not None), task=task)
                                check({'name': 'layout-pip-primary-result', 'passed': visibility['passed'], 'detail': visibility})
                            page.screenshot(path=str(case_out / (stage + '-' + mode + '.png')), full_page=True)
                            iframe.screenshot(path=str(case_out / (stage + '-' + mode + '-frame.png')))
                        contrast = swept_text_contrast(inside)
                        check({'name': 'readable-text-before-theme', 'passed': contrast['tested'] > 0 and not contrast['failures'], 'detail': contrast})
                        iframe.screenshot(path=str(case_out / (stage + '-theme-before-frame.png')))
                        before = inside.locator('body').evaluate('e=>({bg:getComputedStyle(e).backgroundColor,color:getComputedStyle(e).color})')
                        theme = 'dark' if page.evaluate('document.documentElement.dataset.theme') == 'light' else 'light'
                        page.evaluate('v=>window.reverie.setAppearance(v)', theme)
                        settle_view(page, inside)
                        after = wait_for_body_theme_change(inside, before)
                        check({'name': 'live-host-theme', 'passed': before != after, 'detail': {'before': before, 'after': after}})
                        contrast = swept_text_contrast(inside)
                        check({'name': 'readable-text-after-theme', 'passed': contrast['tested'] > 0 and not contrast['failures'], 'detail': contrast})
                        iframe.screenshot(path=str(case_out / (stage + '-theme-after-frame.png')))
                        expected = control(inside, task['control']).input_value()
                        expected_controls = snapshot_controls(inside)
                        expected_order = [item['name'] for item in result_items(inside, 'table')] if task['id'] == 'table' else None
                        expected_selection = selected_route_names(inside) if task['id'] == 'comparison' else None
                        page.wait_for_timeout(1000)
                        case['local_input_samples'] = inside.evaluate('window.__qualityInputTimings || []')
                        iframe, inside = reload_registered_view(
                            page, ref, 'RIU quality ' + case_id, process=process)
                        settle_view(page, inside)
                        page.wait_for_timeout(500)
                        check({'name': 'saved-state-reload', 'passed': control(inside, task['control']).input_value() == expected, 'expected': expected})
                        check({'name': 'all-control-state-reload', 'passed': snapshot_controls(inside) == expected_controls, 'expected': expected_controls, 'actual': snapshot_controls(inside)})
                        check_restored_business_result(inside, task, expected, check, modified=original is not None)
                        check_result_order(inside, expected_order, check, 'sort-state-reload')
                        if expected_selection is not None:
                            check({'name': 'selected-route-state-reload', 'passed': bool(expected_selection) and selected_route_names(inside) == expected_selection})
                        # Zero and unchecked are meaningful values, not missing
                        # state. Restore the positive-case controls afterwards
                        # using the same real input operations as a user.
                        falsy_probe = False
                        if task['id'] in {'calculator', 'chart', 'comparison'}:
                            change(control(inside, task['control']), '0')
                            commit_parameter_changes(inside, task['id'])
                            falsy_probe = True
                        checkboxes = inside.locator(CHECKED_CONTROL_SELECTOR)
                        for index in range(checkboxes.count()):
                            checkbox = checkboxes.nth(index)
                            if checkbox.is_visible() and checkbox.is_enabled():
                                if set_toggle_checked(checkbox, False):
                                    falsy_probe = True
                        if falsy_probe:
                            falsy_controls = snapshot_controls(inside)
                            falsy_order = [item['name'] for item in result_items(inside, 'table')] if task['id'] == 'table' else None
                            page.wait_for_timeout(1000)
                            falsy_canvas_paints = canvas_paints(inside) if task['id'] == 'chart' else None
                            iframe, inside = reload_registered_view(
                                page, ref, 'RIU quality ' + case_id, process=process)
                            settle_view(page, inside)
                            page.wait_for_timeout(500)
                            check({'name': 'falsy-control-state-reload',
                                   'passed': snapshot_controls(inside) == falsy_controls,
                                   'expected': falsy_controls, 'actual': snapshot_controls(inside)})
                            check_result_order(inside, falsy_order, check, 'sort-state-falsy-reload')
                            if task['id'] in {'calculator', 'chart'}:
                                check_restored_business_result(inside, task, '0', check,
                                    modified=original is not None, zero_paints=falsy_canvas_paints)
                            restore_controls_through_inputs(inside, expected_controls)
                            commit_parameter_changes(inside, task['id'])
                            if expected_order is not None and not restore_table_order_through_button(inside, expected_order):
                                raise RuntimeError('Verifier could not restore the result order after its unchecked-stock probe.')
                            if expected_selection is not None:
                                restored_selection = restore_selection_through_button(inside, expected_selection)
                                case.setdefault('probe_cleanup', []).append({'stage': stage, 'selection_restored': restored_selection})
                                if not restored_selection:
                                    raise RuntimeError('Verifier could not restore the selected route after its zero-budget probe.')
                            page.wait_for_timeout(1000)
                        if original:
                            calls = [c for m in saved.messages for c in m.get('tool_calls', []) if c.get('function', {}).get('name') == 'render_view']
                            try:
                                arguments = json.loads(calls[-1]['function']['arguments'])
                                check({'name': 'replacement-version-provenance', 'passed': arguments.get('replaces_view_id') == original['ref'][0]})
                            except (ValueError, IndexError, KeyError):
                                check({'name': 'replacement-version-provenance', 'passed': False})
                            restart_checks(stage, expected, expected_controls, expected_selection, check, expected_order=expected_order)
                            iframe, inside = frame()
                        if task['id'] == 'form':
                            submit_form_confirmation(inside, modified=original is not None, record=check)
                            inspect_state('submission-confirmation')
                            page.screenshot(path=str(case_out / (stage + '-confirmation.png')), full_page=True)
                        if any(not c['passed'] for c in stage_checks):
                            # Restore the values that existed before verifier actions; this is cleanup,
                            # never a pass condition and never a JavaScript write into the model view.
                            if task['id'] == 'form' and (not control(inside, task['control']).is_visible() or not control(inside, task['control']).is_enabled()):
                                reopen_form_through_button(inside)
                            restore_controls_through_inputs(inside, initial_controls)
                            commit_parameter_changes(inside, task['id'])
                            if initial_order is not None:
                                restore_table_order_through_button(inside, initial_order)
                            page.wait_for_timeout(1000)
                        return payload

                    def restart_checks(stage, expected, expected_controls, expected_selection, record, *, expected_order=None):
                        nonlocal browser, page
                        browser.close()
                        stop_process(process)
                        request_count = len(recorder.records)
                        started = time.perf_counter()
                        browser, page = launch(p)
                        page.locator('.session-item').filter(has_text='RIU quality ' + case_id).click(timeout=120000)
                        page.locator('.session-loading').wait_for(state='hidden', timeout=60000)
                        _, inside = frame()
                        settle_view(page, inside)
                        page.wait_for_timeout(500)
                        actual = control(inside, task['control']).input_value()
                        record({'name': 'actual-process-restart-recovery', 'passed': actual == expected,
                                'detail': {'actual': actual, 'expected': expected, 'local_ms': (time.perf_counter()-started)*1000}})
                        record({'name': 'all-control-process-restart-recovery', 'passed': snapshot_controls(inside) == expected_controls,
                                'expected': expected_controls, 'actual': snapshot_controls(inside)})
                        check_restored_business_result(inside, task, expected, record)
                        check_result_order(inside, expected_order, record, 'sort-process-restart-recovery')
                        if expected_selection is not None:
                            record({'name': 'selected-route-process-restart-recovery', 'passed': bool(expected_selection) and selected_route_names(inside) == expected_selection})
                        record({'name': 'restart-makes-no-model-requests', 'passed': len(recorder.records) == request_count})
                        page.screenshot(path=str(case_out / (stage + '-restart.png')), full_page=True)

                    try:
                        prompt = task['prompt'] if task['id'] == 'text' else fixture['common'] + task['prompt']
                        if task['id'] == 'text':
                            saved = send(prompt, 'generation')
                            calls = [c for m in saved.messages for c in m.get('tool_calls', [])]
                            case['tool_names'] = [c.get('function', {}).get('name') for c in calls]
                            case['violations'] = tool_scope_violations(case['tool_names'], fixture, task)
                            answer = assistant_text(saved.messages)
                            case['checks'].append({'name': 'plain-text-answer', 'passed': not calls and bool(number_pattern(3168).search(answer)), 'detail': answer})
                        else:
                            saved, original, checks = run_quality_stage(case, 'generation', prompt, send, inspect_view, args.max_model_repairs, checkpoint=save)
                            case['checks'] = checks
                            case['generation_first_pass'] = case['stages'][0]['passed']
                            case['generation_passed'] = case['stages'][-1]['passed']
                            if original:
                                case['original_revision'] = {'manifest': original['manifest'], 'sha256': original['sha256']}
                            if not case['generation_passed']:
                                case['outcome'] = 'model_no_view' if not original else quality_outcome(checks, case['violations'], case['repair_count'])
                                if not original:
                                    case['error'] = 'Model completed without a registered interactive view after the feedback budget.'
                                continue
                            if not args.generation_only:
                                def assess_modified(saved, stage, record):
                                    return inspect_view(saved, stage, record, original=original)
                                saved, modified, checks = run_quality_stage(case, 'modification', task['modify'], send, assess_modified, args.max_model_repairs, checkpoint=save)
                                case['checks'] += checks
                                if modified:
                                    case['modified_revision'] = {'manifest': modified['manifest'], 'sha256': modified['sha256']}
                        case['outcome'] = quality_outcome(case['checks'], case['violations'], case['repair_count'], generation_only=args.generation_only and task['id'] != 'text')
                    except Exception as error:
                        case['error'] = type(error).__name__ + ': ' + str(error)
                        case['outcome'] = classify_quality_error(error, case.get('phase', ''))
                        try:
                            dump(case_out/'failure-before-cancel-events.json', page.evaluate('window.__qualityEvents'))
                            page.screenshot(path=str(case_out/'failure-before-cancel.png'), full_page=True)
                            stop = page.get_by_role('button', name='停止', exact=True)
                            if stop.is_visible():
                                stop.click()
                                stop.wait_for(state='hidden', timeout=30000)
                            state = page.evaluate('window.reverie.workbench("executors")')
                            if any(entry.get('sessionId') == session.id for entry in state.get('entries', [])):
                                case['host_cancel_fallback'] = 'Execution lease still active after UI cancellation; invoked the same host cancellation action.'
                                page.evaluate('owner=>window.reverie.cancel(owner)', {'projectRoot': str(workspace), 'sessionId': session.id})
                                page.wait_for_function('async id=>!(await window.reverie.workbench("executors")).entries.some(e=>e.sessionId===id)', arg=session.id, timeout=30000)
                            dump(case_out/'failure-events.json', page.evaluate('window.__qualityEvents'))
                            page.screenshot(path=str(case_out/'failure.png'), full_page=True)
                        except Exception as cleanup_error:
                            case['capture_error'] = str(cleanup_error)
                    finally:
                        saved = manager.load_session(session.id)
                        if saved:
                            dump(case_out/'final-session.json', saved.to_dict())
                            final_names = [c.get('function', {}).get('name') for m in saved.messages for c in m.get('tool_calls', [])]
                            case['all_tool_names'] = final_names
                            case['violations'] = tool_scope_violations(final_names, fixture, task)
                            if case['violations']:
                                case['outcome'] = 'model_violation'
                        case['requests'] = [r for r in recorder.records if r['case'] == case_id]
                        forced = [name for r in case['requests'] for name in r.get('response_tool_names', []) if name in case.get('violations', []) and (r.get('tool_choice') or {}).get('function', {}).get('name') == name]
                        case['host_forced_scope_violations'] = forced
                        case['model_scope_violations'] = [name for name in case.get('violations', []) if name not in forced]
                        if forced and not case['model_scope_violations']:
                            case['outcome'] = 'host_routing_violation'
                        record_service_incidents(case)
                        case['final_phase'] = case.get('phase')
                        case['artifacts'] = []
                        artifact_paths = set()
                        for message in saved.messages if saved else []:
                            for call in message.get('tool_calls', []):
                                function = call.get('function', {})
                                if function.get('name') not in {'create_file', 'render_view'}:
                                    continue
                                try:
                                    arguments = json.loads(function.get('arguments', '{}'))
                                    candidate = arguments.get('artifact_path') or arguments.get('path')
                                    if candidate:
                                        artifact_paths.add((workspace / candidate).resolve())
                                except (ValueError, TypeError):
                                    pass
                        for f in sorted(artifact_paths):
                            if not f.is_relative_to(workspace) or not f.is_file() or f.suffix.lower() not in {'.html', '.htm'}:
                                continue
                            snapshot = case_out / 'model-artifacts' / f.relative_to(workspace)
                            snapshot.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(f, snapshot)
                            case['artifacts'].append({'path': str(snapshot), 'workspace_path': str(f), 'sha256': hashlib.sha256(snapshot.read_bytes()).hexdigest(), 'bytes': snapshot.stat().st_size})
                        save()
                        print(json.dumps({'case': case_id, 'outcome': case.get('outcome'), 'checks': len(case['checks']), 'error': case.get('error')}, ensure_ascii=True), flush=True)
                        time.sleep(5)
            browser.close()

    finally:
        if process and process.poll() is None:
            stop_process(process)
        recorder.close()
        log.close()
        cleaned = []
        for f in app_root.rglob('*'):
            if f.is_file() and ('config' in f.name.lower() or f.suffix in {'.json', '.bak'}):
                data = f.read_text(encoding='utf-8', errors='replace')
                if active.api_key and active.api_key in data:
                    f.write_text(data.replace(active.api_key, ''), encoding='utf-8')
                    cleaned.append(str(f))
        report['credential_cleanup'] = {'complete': True, 'files': cleaned}
        save()


if __name__ == '__main__':
    main()
