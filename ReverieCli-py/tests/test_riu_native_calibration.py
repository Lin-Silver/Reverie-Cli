"""Regression fixtures for native evidence calibration; never model-quality samples."""
import importlib.util
import json
from pathlib import Path
import shutil

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('riu_calibration', ROOT/'scripts/verification/riu_quality_benchmark.py')
benchmark = importlib.util.module_from_spec(spec)
spec.loader.exec_module(benchmark)


@pytest.fixture(scope='module')
def browser():
    from playwright.sync_api import sync_playwright
    executable = shutil.which('chromium') or shutil.which('chromium-browser')
    if not executable:
        pytest.skip('Chromium is required for actual DOM calibration fixtures')
    with sync_playwright() as playwright:
        instance = playwright.chromium.launch(executable_path=executable, headless=True)
        yield instance
        instance.close()


@pytest.mark.parametrize('separator', ['', ',', '，', ' ', '\u00a0', '\u202f', '\u2009'])
def test_correct_numeric_answers_accept_standard_grouping_without_rewriting(separator):
    answer = '答案：\u202f3' + separator + '168.00 元'
    assert benchmark.number_pattern(3168).search(answer)


@pytest.mark.parametrize('answer', ['13168', '31680', '-3168', '3168.5', '3 16 8', '3\u202f167'])
def test_numeric_answer_matching_rejects_wrong_values_and_digit_boundaries(answer):
    assert not benchmark.number_pattern(3168).search(answer)


@pytest.mark.parametrize('value', [2.5, 12.75, .5])
def test_decimal_point_is_literal_and_trailing_zeros_keep_the_same_value(value):
    pattern = benchmark.number_pattern(value)
    assert pattern.search(str(value) + '00')
    assert not pattern.search(str(value).replace('.', 'x'))
    assert not pattern.search(str(value) + '.0')


@pytest.mark.parametrize('text', ['未匹配到商品。', '没有匹配的路线', '暂无数据', 'No matching results', 'Nothing found'])
def test_equivalent_empty_result_feedback_is_recognized(text):
    assert benchmark.empty_result_feedback(text)


@pytest.mark.parametrize('text', ['姓名无效', '价格200元', '关键词没有填写', '没有错误', '无障碍导航'])
def test_unrelated_prose_is_not_empty_result_feedback(text):
    assert not benchmark.empty_result_feedback(text)


def test_missing_numeric_values_are_semantic_failures_while_actual_zero_is_valid(browser):
    page = browser.new_page()
    try:
        page.set_content('<label>天数<input type=number placeholder=22></label>')
        field = page.get_by_label('天数')
        with pytest.raises(benchmark.MissingBusinessControl) as error:
            benchmark.numeric_control_value(field, '天数')
        assert benchmark.classify_quality_error(error.value, 'browser-generation') == 'semantic_failure'
        checks = []
        task = json.loads(benchmark.TASK_FILE.read_text())['tasks'][0]
        with pytest.raises(benchmark.MissingBusinessControl):
            benchmark.semantic_checks(page, task, record=checks.append)
        assert any(item['name'] == 'required-numeric-control' and not item['passed'] for item in checks)
        field.fill('0')
        assert benchmark.numeric_control_value(field, '天数') == 0
        field.fill('2.5')
        assert benchmark.numeric_control_value(field, '天数') == 2.5
    finally:
        page.close()


@pytest.mark.parametrize('works', [True, False])
def test_actual_apply_button_drives_chart_and_zero_state_but_inert_button_does_not(browser, works):
    page = browser.new_page()
    try:
        page.set_content('''<label>倍率<input id=n type=number value=1></label>
          <button id=apply type=button>应用</button><p id=message></p><output id=total></output>
          <svg width=300 height=170 role=img aria-label=用水图></svg><table><tbody></tbody></table>
          <script>
          const months=['一月','二月','三月'],values=[120,80,160];
          const field=document.querySelector('input'),svg=document.querySelector('svg'),body=document.querySelector('tbody');
          function render(){const multiplier=Number(field.value),valid=multiplier>0;
            document.querySelector('#message').textContent=multiplier===0?'没有用水数据。':multiplier<0?'倍率负数不合理。':'';
            svg.style.display=valid?'block':'none';
            document.querySelector('output').textContent=valid?'总量 '+360*multiplier:'';
            svg.innerHTML=valid?values.map((value,index)=>'<rect x="'+(20+index*80)+'" y="'+(150-value*.7)+'" width="40" height="'+value*.7+'" fill="blue"/>').join(''):'';
            body.innerHTML=valid?values.map((value,index)=>'<tr><td>'+months[index]+'</td><td>'+value*multiplier+'</td></tr>').join(''):'';
          }
          render();
          </script>''')
        if works:
            page.evaluate('()=>document.querySelector("button").addEventListener("click",render)')
        task = next(task for task in json.loads(benchmark.TASK_FILE.read_text())['tasks'] if task['id'] == 'chart')
        checks, _ = benchmark.semantic_checks(page, task)
        by_name = {item['name']: item for item in checks}
        for name in ['local-recalculation', 'zero-state', 'invalid-input-feedback', 'chart-readable-data']:
            assert by_name[name]['passed'] is works, (name, by_name[name])
    finally:
        page.close()


@pytest.mark.parametrize('clear_pixels', [True, False])
def test_canvas_zero_needs_changed_pixels_and_feedback_and_restores_the_observed_zero_paint(browser, clear_pixels):
    page = browser.new_page()
    try:
        page.set_content('''<canvas width=100 height=100></canvas><p id=message>总量360</p>
          <button type=button id=zero>清零</button><button type=button id=positive>恢复图</button>
          <script>
          const context=document.querySelector('canvas').getContext('2d');
          const positive=()=>{context.fillStyle='red';context.fillRect(0,0,100,100)};
          positive();document.querySelector('#positive').onclick=positive;
          </script>''')
        page.locator('#zero').evaluate('''(button,clear)=>button.onclick=()=>{
            document.querySelector('#message').textContent='没有用水数据。';
            if(clear)document.querySelector('canvas').getContext('2d').clearRect(0,0,100,100);
        }''', clear_pixels)
        before = page.locator('body').inner_text()
        paints = benchmark.canvas_paints(page)
        page.get_by_role('button', name='清零').click()
        evidence = benchmark.chart_zero_state(page, before, paints, modified=False)
        assert evidence['passed'] is clear_pixels
        if clear_pixels:
            zero_paints = benchmark.canvas_paints(page)
            checks = []
            benchmark.check_restored_business_result(page, {'id': 'chart'}, '0', checks.append,
                modified=False, zero_paints=zero_paints)
            assert checks[-1]['passed']
            page.get_by_role('button', name='恢复图').click()
            benchmark.check_restored_business_result(page, {'id': 'chart'}, '0', checks.append,
                modified=False, zero_paints=zero_paints)
            assert not checks[-1]['passed'], 'A restored zero caption cannot borrow a stale positive plot'
    finally:
        page.close()


@pytest.mark.parametrize('label', ['筛选', '筛选路线', '应用筛选'])
@pytest.mark.parametrize('confirms', [True, False])
def test_filter_and_two_step_native_radio_confirmation_use_real_actions(browser, label, confirms):
    page = browser.new_page()
    try:
        page.set_content('''<label>预算<input id=budget type=number value=200></label>
          <label>距离<input id=distance type=number value=5></label>
          <button id=clear>清除筛选</button><button id=filter></button>
          <p id=message></p><div id=rows></div><button id=confirm disabled>确认选择</button><p id=chosen></p>
          <script>
          window.confirmedNames=[];window.clearClicks=0;
          const routes=[['山谷',120,2],['日落',220,5],['城郊',160,8]];
          const budget=document.querySelector('#budget'),distance=document.querySelector('#distance'),rows=document.querySelector('#rows');
          function render(){const matches=routes.filter(r=>r[1]<=Number(budget.value)&&r[2]<=Number(distance.value));
            document.querySelector('#message').textContent=Number(budget.value)<0?'预算负数不合理':matches.length?'':'没有匹配的路线';
            rows.innerHTML=matches.map(r=>'<label><input type=radio name=route value="'+r[0]+'">'+r[0]+' '+r[1]+'元 '+r[2]+'公里</label>').join('');
            document.querySelector('#chosen').textContent='';document.querySelector('#confirm').disabled=true;
          }
          rows.onchange=()=>document.querySelector('#confirm').disabled=false;
          document.querySelector('#clear').onclick=()=>{clearClicks++;budget.value=200;distance.value=5;render()};
          document.querySelector('#filter').onclick=render;render();
          </script>''')
        page.locator('#filter').evaluate('(element,text)=>element.textContent=text', label)
        if confirms:
            page.locator('#confirm').evaluate('''element=>element.onclick=()=>{
                const name=document.querySelector('input:checked').value;confirmedNames.push(name);
                document.querySelector('#chosen').textContent='已选择路线：'+name;
            }''')
        task = next(task for task in json.loads(benchmark.TASK_FILE.read_text())['tasks'] if task['id'] == 'comparison')
        checks, _ = benchmark.semantic_checks(page, task)
        choice_checks = [item for item in checks if item['name'] == 'selection-feedback']
        assert len(choice_checks) == 2
        assert all(item['passed'] is confirms for item in choice_checks)
        assert page.evaluate('clearClicks') == 0, 'Clear-filter is not the apply action'
        assert page.evaluate('confirmedNames') == (['日落', '山谷'] if confirms else [])
    finally:
        page.close()


def test_frame_wait_binds_the_requested_revision_and_locator_follows_a_real_dom_move(browser):
    page = browser.new_page()
    try:
        page.set_content('''<div class=interactive-view-anchor data-view-key="scope:session:vexpected:1">
            <section><button data-view-mode=inline>Inline</button>
            <iframe data-view-id=vexpected src="about:blank#older" srcdoc="wrong-older-revision"></iframe></section></div>
          <div class=interactive-view-anchor data-view-key="scope:session:vexpected:2" style="min-height:40px"></div>
          <div id=portal></div><script>
          setTimeout(()=>{const iframe=document.createElement('iframe');iframe.dataset.viewId='vexpected';
            iframe.sandbox='allow-scripts';iframe.src='about:blank#revision-two';iframe.srcdoc='<body>actual-revision-two</body>';
            document.querySelector('[data-view-key$=":2"]').appendChild(iframe);
          },200);
          </script>''')
        iframe, inside = benchmark.wait_for_registered_view_frame(page, ('vexpected', 2), timeout_ms=5000)
        assert inside.locator('body').inner_text() == 'actual-revision-two'
        page.locator('#portal').evaluate('(container,element)=>container.appendChild(element)', iframe.element_handle())
        assert iframe.locator('..').get_attribute('id') == 'portal'
        assert page.locator('iframe').count() == 2, 'No surrogate target was created'
    finally:
        page.close()


@pytest.mark.parametrize('state', ['missing', 'exited', 'closed'])
def test_frame_wait_is_bounded_and_does_not_create_a_surrogate(browser, state):
    from types import SimpleNamespace
    page = browser.new_page()
    try:
        page.set_content('<div class=interactive-view-anchor data-view-key="scope:s:vexpected:1" style="min-height:40px"></div>')
        process = SimpleNamespace(poll=lambda: 0 if state == 'exited' else None)
        if state == 'closed':
            page.close()
        expected = {'missing': 'child frame became ready', 'exited': 'Desktop exited', 'closed': 'page closed'}[state]
        with pytest.raises(RuntimeError, match=expected):
            benchmark.wait_for_registered_view_frame(page, ('vexpected', 1), process=process, timeout_ms=250)
        if state != 'closed':
            assert page.locator('iframe').count() == 0
    finally:
        if not page.is_closed():
            page.close()


def test_documented_mount_redraws_canvas_after_palette_changes_without_saving_private_state(browser):
    from reverie.agent.system_prompt import build_system_prompt
    example = build_system_prompt(runtime_surface='desktop').split('### Offline host integration example', 1)[1]
    helper = example.split('```javascript\n', 1)[1].split('\n```', 1)[0]
    controls = example.split('#### Wiring actual controls', 1)[1]
    markup = controls.split('```html\n', 1)[1].split('\n```', 1)[0]
    wiring = controls.split('```javascript\n', 1)[1].split('\n```', 1)[0]
    # Add canvas work around the documented renderer without depending on its
    # exact body; that renderer also updates validation after inputs/restoration.
    marker = 'mountView({restore, render, read, subscribe, onError:showError})'
    assert marker in wiring
    wiring = wiring.replace(marker, """const renderFields = render;
    render = function() {
        renderFields();
        const canvas=document.querySelector('canvas'),context=canvas.getContext('2d');
        context.fillStyle=getComputedStyle(document.documentElement).getPropertyValue('--color-text-primary').trim()||'#000';
        context.fillRect(0,0,canvas.width,canvas.height);
    };
    """ + marker, 1)
    page = browser.new_page()
    try:
        page.set_content('<iframe sandbox="allow-scripts"></iframe>')
        page.evaluate('''()=>{
          window.saved=[];let revision=4;
          window.contextFor=theme=>({theme,locale:'zh-CN',displayMode:'pip',styles:{variables:{
            '--color-text-primary':theme==='light'?'rgb(10,20,30)':'rgb(230,231,232)'}}});
          addEventListener('message',event=>{
            const message=event.data;
            const reply=result=>event.source.postMessage({jsonrpc:'2.0',id:message.id,result},'*');
            if(message.method==='ui/initialize')reply({capability:'fixture-capability',
              reverieViewState:{revision,state:{label:'',enabled:false}},hostContext:contextFor('light')});
            else if(message.method==='ui/notifications/initialized')window.initialized=true;
            else if(message.method==='reverie/view-state'){
              if(message.capability!=='fixture-capability'||message.params.baseRevision!==revision)throw Error('Ownership or revision changed');
              saved.push(message.params.state);reply({revision:++revision});
            }
          });
        }''')
        page.locator('iframe').evaluate('(element,html)=>element.srcdoc=html',
            markup+'<canvas width=8 height=8></canvas><script>'+helper+'\n'+wiring+'</script>')
        page.wait_for_function('()=>window.initialized===true')
        frame = page.locator('iframe').element_handle().content_frame()
        pixel = "()=>[...document.querySelector('canvas').getContext('2d').getImageData(0,0,1,1).data]"
        assert frame.evaluate(pixel) == [10, 20, 30, 255]
        assert page.evaluate('saved.length') == 0
        frame.get_by_label('Label', exact=True).fill('actual input')
        page.wait_for_function('()=>saved.length===1')
        page.evaluate('''()=>document.querySelector('iframe').contentWindow.postMessage({jsonrpc:'2.0',
            method:'ui/notifications/host-context-changed',params:contextFor('dark')},'*')''')
        frame.wait_for_function("()=>document.documentElement.dataset.theme==='dark'")
        assert frame.evaluate(pixel) == [230, 231, 232, 255]
        assert page.evaluate('saved.length') == 1, 'A theme-only redraw must not save'
        assert frame.get_by_label('Label', exact=True).input_value() == 'actual input'
        assert not frame.get_by_role('checkbox').is_checked()
        frame.get_by_role('checkbox').check()
        page.wait_for_function('()=>saved.length===2')
        assert frame.locator('output').inner_text() == 'actual input'
        assert page.evaluate('saved') == [{'label': 'actual input', 'enabled': False},
                                           {'label': 'actual input', 'enabled': True}]
    finally:
        page.close()


@pytest.fixture
def publication_store(tmp_path, monkeypatch):
    from reverie import views
    store = views.ViewStore(tmp_path/'views')
    artifact = tmp_path/'generic.html'
    artifact.write_text('<!doctype html><title>Protocol fixture</title><p>Generic content</p>')

    def register(call, identifier, replaces=None):
        monkeypatch.setattr(views, '_new_view_id', lambda: identifier)
        return store.register(artifact_path=artifact, workspace_root=tmp_path,
            identity=views.ViewIdentity('fixture-session', 'turn', call),
            title='Protocol fixture', summary='Generic content', replaces_view_id=replaces)

    return store, register


def publication(manifest, suffix=''):
    return [{'role': 'Reverie', 'tool_calls': [{'id': manifest.tool_call_id,
        'function': {'name': 'render_view', 'arguments': '{}'}}]},
        {'role': 'tool', 'tool_call_id': manifest.tool_call_id,
         'content': f'Interactive view ready: "Fixture" (view_id={manifest.view_id}, revision={manifest.revision}).'+suffix}]


def test_publication_order_uses_real_store_ownership_and_ignores_untrusted_reference_text(publication_store):
    store, register = publication_store
    old = register('old-call', 'vzz-old')
    new = register('new-call', 'vaa-new')
    history = publication(old)+publication(new)
    assert benchmark.latest_published_view_reference(history, store, 'fixture-session') == ('vaa-new', 1)
    revised = register('revision-call', 'unused', replaces=new.view_id)
    history += publication(revised, ' Summary: view_id=vzz-old, revision=1')
    history += [{'role': 'Reverie', 'content': 'view_id=vzz-old, revision=1'},
        {'role': 'Reverie', 'tool_calls': [{'id': 'read', 'function': {'name': 'read_file'}}]},
        {'role': 'tool', 'tool_call_id': 'read', 'content': 'view_id=vzz-old, revision=1'},
        {'role': 'tool', 'tool_call_id': 'unmatched', 'content': 'view_id=vzz-old, revision=1'},
        {'role': 'Reverie', 'tool_calls': [{'id': 'failed', 'function': {'name': 'render_view'}}]},
        {'role': 'tool', 'tool_call_id': 'failed', 'content': 'Error: missing artifact'}]
    assert benchmark.latest_published_view_reference(history, store, 'fixture-session') == ('vaa-new', 2)
    assert benchmark.latest_published_view_reference([{'role':'user','content':'view_id=vzz-old, revision=1'}], store, 'fixture-session') is None


@pytest.mark.parametrize('failure', ['wrong-owner', 'ambiguous', 'missing', 'hidden'])
def test_broken_latest_registration_never_silently_selects_an_older_view(publication_store, failure):
    store, register = publication_store
    old = register('old-call', 'vzz-old')
    latest = register('new-call', 'vaa-new')
    history = publication(old)
    if failure == 'wrong-owner':
        history += [{'role':'Reverie','tool_calls':[{'id':'forged','function':{'name':'render_view'}}]},
                    {'role':'tool','tool_call_id':'forged','content':'view_id=vzz-old, revision=1'}]
    elif failure == 'ambiguous':
        other = register('new-call', 'vother')
        history += publication(latest, f' view_id={other.view_id}, revision=1')
    else:
        history += publication(latest)
        if failure == 'missing':
            (store.view_directory('fixture-session', latest.view_id, 1)/'manifest.json').unlink()
        else:
            store.restrict_visible('fixture-session', [(old.view_id, 1)])
    with pytest.raises((OSError, ValueError)):
        benchmark.latest_published_view_reference(history, store, 'fixture-session')


@pytest.mark.parametrize('scenario,terminal,count', [
    ('terminal', True, 1), ('recovered', False, 1), ('wrong-session', False, 0),
    ('wrong-run', False, 0), ('assistant-text', False, 0), ('warning', False, 0),
    ('unbound', False, 0), ('after-headers', True, 1), ('malformed-ui', False, 0),
])
def test_native_errors_are_scoped_to_the_actual_turn_run_and_recovery(scenario, terminal, count):
    error = {'event':'model_error','status':'error','detail':'[empty-provider-stream] no model events'}

    def event(kind, model=None, session='session', run='parent'):
        inner = {'type':kind,'session_id':session,'run_id':run}
        if model is not None:
            inner['event'] = model
        return {'event':{'type':'prompt.event','event':inner}}

    start = event('run.started')
    failed = event('ui.event', error)
    success = event('ui.event', {'event':'model_response','status':'success'})
    cases = {
        'terminal':[start, failed], 'recovered':[start, failed, success],
        'wrong-session':[start, event('ui.event', error, session='other')],
        'wrong-run':[start, event('ui.event', error, run='child')],
        'assistant-text':[start, {'event':{'type':'assistant.delta','text':'model_error HTTP 500'}}],
        'warning':[start, event('ui.event', {'status':'warning','detail':error['detail']})],
        'unbound':[failed], 'after-headers':[start, success, failed],
        'malformed-ui':[start, event('ui.event', 'not a native model event')],
    }
    observed = benchmark.inspect_native_model_errors(cases[scenario], 'session')
    assert bool(observed['terminal_error']) is terminal
    assert len(observed['errors']) == count
    if terminal:
        assert benchmark.classify_quality_error(RuntimeError(observed['terminal_error']['detail']), 'model-fixture') == 'service_transport_error'


def test_real_reload_rebinds_both_locators_to_the_new_resource_instance(browser):
    page = browser.new_page()
    serial = 0

    def document(route):
        nonlocal serial
        serial += 1
        route.fulfill(content_type='text/html', body=f'''<button class=session-item>Fixture session</button>
          <div class=interactive-view-anchor data-view-key="scope:session:vreload:7">
          <iframe data-view-id=vreload sandbox="allow-scripts" src="about:blank#instance-{serial}"
            srcdoc="<body>Actual instance {serial}</body>"></iframe></div>''')

    try:
        page.route('http://riu-reload.test/', document)
        page.goto('http://riu-reload.test/')
        old, inside = benchmark.wait_for_registered_view_frame(page, ('vreload', 7))
        assert inside.locator('body').inner_text() == 'Actual instance 1'
        source = old.get_attribute('src')
        current, inside = benchmark.reload_registered_view(page, ('vreload', 7), 'Fixture session')
        assert current.get_attribute('src') != source
        assert old.count() == 0
        assert inside.locator('body').inner_text() == 'Actual instance 2'
        assert current.screenshot().startswith(b'\x89PNG')
        assert page.locator('iframe').count() == 1
    finally:
        page.close()


@pytest.mark.parametrize('mode', ['bars', 'equal-cards', 'covered'])
def test_css_bars_with_image_roles_on_each_bar_still_need_painted_geometry(browser, mode):
    page = browser.new_page()
    try:
        pieces = []
        for month, amount in [('一月',240), ('二月',160), ('三月',320)]:
            height = amount/2 if mode != 'equal-cards' else 80
            pieces.append(f'<div><p>{amount}</p><div role=img aria-label="{month} {amount}" '
                          f'style="width:36px;height:{height}px;background:blue"></div><span>{month}</span></div>')
        page.set_content('<div style="display:flex;align-items:flex-end;gap:24px;width:300px;height:240px">'
                         +''.join(pieces)+'</div>')
        if mode == 'covered':
            page.locator('body').evaluate("e=>e.insertAdjacentHTML('beforeend','<div style=\"position:fixed;inset:0;background:white;z-index:999\"></div>')")
        evidence = benchmark.chart_evidence(page, 2, modified=False)
        assert evidence['visible_bars'] is (mode == 'bars')
        if mode == 'bars':
            assert any(plot['css_inferred'] and len(plot['bars']) >= 3 for plot in evidence['plots'])
            assert evidence['readable_data']
    finally:
        page.close()


@pytest.mark.parametrize('text', [
    '没有符合预算（≤50元）和距离（≤5公里）的路线',
    '没有符合多个约束条件并同时满足所列全部要求的记录',
    '未找到满足当前价格范围与库存条件并符合关键字的商品',
])
def test_qualified_empty_feedback_is_not_limited_to_eighteen_characters(text):
    assert benchmark.empty_result_feedback(text)


@pytest.mark.parametrize('text', ['没有错误，目前按照指定条件列出全部路线',
                                  '未找到异常，本工具可以展示商品记录', '无问题，以下是数据'])
def test_no_error_status_with_an_entity_is_not_an_empty_result(text):
    assert not benchmark.empty_result_feedback(text)


@pytest.mark.parametrize('kind', ['native', 'switch', 'checkbox'])
def test_stock_toggles_use_actual_accessible_actions_and_restore_false(browser, kind):
    page = browser.new_page()
    try:
        widget = ('<label>只看有库存<input id=stock type=checkbox></label>' if kind == 'native' else
                  f'<button type=button id=stock role={kind} aria-checked=false>只看有库存</button>')
        page.set_content(widget+'''<table><tbody></tbody></table><script>
          const stock=document.querySelector('#stock');window.actions=0;
          const read=()=>stock.tagName==='INPUT'?stock.checked:stock.getAttribute('aria-checked')==='true';
          function render(){document.querySelector('tbody').innerHTML='<tr><td>Available</td></tr>'+
              (read()?'':'<tr><td>Unavailable</td></tr>')}
          stock.addEventListener(stock.tagName==='INPUT'?'change':'click',()=>{
            actions++;if(stock.tagName!=='INPUT')stock.setAttribute('aria-checked',String(!read()));render();
          });render();</script>''')
        initial = benchmark.snapshot_controls(page)
        field = benchmark.stock_filter_control(page)
        assert field.count() == 1
        assert initial[0]['checked'] is False
        assert benchmark.set_stock_filter(field, True)
        assert page.locator('tbody tr').count() == 1
        assert benchmark.snapshot_controls(page)[0]['checked'] is True
        assert benchmark.restore_controls_through_inputs(page, initial)
        assert page.locator('tbody tr').count() == 2
        assert benchmark.snapshot_controls(page) == initial
        actions = page.evaluate('actions')
        assert benchmark.restore_controls_through_inputs(page, initial)
        assert page.evaluate('actions') == actions, 'Unchanged state must not cause another action'
        assert benchmark.business_controls_in_viewport(page)['passed']
    finally:
        page.close()


@pytest.mark.parametrize('value', ['false', 'mixed'])
def test_role_and_label_alone_do_not_make_an_inert_switch_pass(browser, value):
    page = browser.new_page()
    try:
        page.set_content(f'<button role=switch aria-checked={value}>只看有库存</button>')
        field = benchmark.stock_filter_control(page)
        assert not benchmark.set_stock_filter(field, True)
        assert field.get_attribute('aria-checked') == value
    finally:
        page.close()
