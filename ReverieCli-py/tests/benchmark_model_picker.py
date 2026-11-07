"""Measure the built renderer's model picker in an isolated browser fixture.

Run manually after `npm run build:renderer`; this is a benchmark, not a timing
assertion for ordinary pytest runs. It never contacts a model provider or native
desktop bridge. JSON output records the exact renderer files used.
"""

import argparse
import hashlib
import json
import os
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[2]


def fixture_state(count):
    no_reasoning = {"control": "none", "options": [], "value": ""}
    models = [{
        "id": f"bench-model-{index:05d}",
        "display_name": f"Benchmark Model {index:05d}",
        "description": "A provider model imported from a large live catalog.",
        "transport": "openai-chat", "context_length": 128000,
        "vision": False, "tool_calling": True, "thinking": False,
        "reasoning": no_reasoning, "context_limit": 128000,
        "needs_context_limit": False, "suggested_context_limit": 128000,
    } for index in range(count)]
    provider = {
        "id": "benchmark-provider", "name": "Benchmark Provider",
        "base_url": "https://fixture.invalid/v1", "format": "openai-chat",
        "enabled": True, "active": True, "api_key_configured": False,
        "api_key_source": "none", "api_key_masked": "",
        "selected_model_id": models[0]["id"],
        "selected_model_display_name": models[0]["display_name"],
        "max_context_tokens": 128000, "max_tokens": 8192,
        "supports_vision": False, "thinking": False,
        "model_context_limits": {}, "models": models,
    }
    active = {"id": models[0]["id"], "display_name": models[0]["display_name"], "provider": "openai-chat"}
    return {
        "protocol_version": 1,
        "core": {"version": "benchmark", "interface_version": "1", "release_status": "fixture"},
        "workspace": {
            "project_root": "C:/benchmark-fixture", "project_name": "benchmark-fixture",
            "project_data_dir": "C:/benchmark-fixture/.reverie",
            "config_path": "C:/benchmark-fixture/.reverie/config.json",
            "mode": "reverie", "active_source": "custom", "active_model": active,
            "index_ready": True,
            "context_engine": {"ready": True, "indexing": False, "files": 0, "symbols": 0, "progress": 100, "label": "Ready"},
        },
        "models": {
            "active_source": "custom", "active_model": active,
            "sources": [{
                "id": "custom", "display_name": "Custom Provider", "active": True,
                "selected_model_id": models[0]["id"], "selected_reasoning": no_reasoning,
                "models": models, "config_fields": [], "custom_providers": [provider],
                "custom_provider_formats": [],
            }],
        },
        "settings": {"items": [], "config_path": "fixture", "workspace_mode": True},
        "sessions": {"current_session_id": "", "items": []},
        "plugins": {"summary": {}, "records": []},
        "skills": {
            "count": 0, "invalid_count": 0, "shadowed_count": 0, "records": [],
            "pinned": {"max": 4, "keys": [], "names": [], "unresolved": []},
            "errors": [], "shadowed": [],
        },
        "commands": {"sections": [], "items": []},
        "recovery": {"summary": {}, "checkpoints": [], "operations": []},
    }


STUB = r"""
(() => {
  const state = __FIXTURE_STATE__;
  const preferences = {language:'zh-CN',uiVariant:__VARIANT__,accent:'rose',backgroundPreset:'none'};
  window.reverie = new Proxy({
    platform:'win32', versions:{},
    appearance:async()=>({theme:'dark',resolved:'dark'}),
    uiPreferences:async()=>preferences,
    setUiPreferences:async patch=>({...preferences,...patch}),
    paths:async()=>({projectRoot:state.workspace.project_root,kernelPath:'fixture',coreAppRoot:'fixture',runtimeRoot:'fixture'}),
    gitStatus:async()=>null,
    request:async(action)=>{
      if(action==='initialize'||action==='getState')return {type:'state',state};
      if(action==='getModelSources'||action==='refreshModelSources')return {type:'models',models:state.models};
      if(action==='getContextStatus')return {type:'context.status',context_engine:state.workspace.context_engine};
      if(action==='getContextUsage')return {type:'context.usage',usage:null};
      if(action==='getImageModelSources')return {type:'image-models',imageModels:{sources:[],active_source:'local'}};
      throw new Error('Benchmark fixture does not implement '+action);
    },
    onEvent:()=>()=>{},onAppearance:()=>()=>{},
  },{get(target,name){if(name in target)return target[name];if(String(name).startsWith('on'))return ()=>()=>{};return async()=>null;}});

  const tasks = [];
  const observer = new PerformanceObserver(list=>tasks.push(...list.getEntries().map(item=>({start_ms:item.startTime,duration_ms:item.duration}))));
  observer.observe({type:'longtask',buffered:true});
  const begin = name => window.__pickerBenchmark.phase={name,start_ms:performance.now()};
  window.__pickerBenchmark = {
    begin,
    nextInputPhase:'search',
    finish:async()=>{
      await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
      const phase=window.__pickerBenchmark.phase;
      const end=performance.now();
      return {event_to_two_frames_ms:end-phase.start_ms,
        long_tasks:tasks.filter(task=>task.start_ms+task.duration_ms>=phase.start_ms&&task.start_ms<=end),
        model_row_dom_count:document.querySelectorAll('.model-option-list > button').length,
        document_node_count:document.getElementsByTagName('*').length};
    },
  };
  document.addEventListener('click',event=>{
    if(event.target.closest('.model-trigger'))begin('open');
  },true);
  document.addEventListener('input',event=>{
    if(event.target.closest('.model-search'))begin(window.__pickerBenchmark.nextInputPhase);
  },true);
})();
"""


SCROLL = r"""async duration => {
  const list=document.querySelector('.model-option-list');
  window.__pickerBenchmark.begin('scroll');
  const maximum=list.scrollHeight-list.clientHeight;
  const distance=Math.min(maximum,2400);
  const samples=[];
  let previous, start;
  await new Promise(resolve=>{
    function frame(now){
      if(start===undefined)start=now;
      if(previous!==undefined)samples.push(now-previous);
      previous=now;
      const progress=(now-start)/duration;
      list.scrollTop=distance*(progress<.5?progress*2:Math.max(0,2-progress*2));
      if(progress<1)requestAnimationFrame(frame);else resolve();
    }
    requestAnimationFrame(frame);
  });
  const result=await window.__pickerBenchmark.finish();
  const sorted=[...samples].sort((a,b)=>a-b);
  const sum=samples.reduce((total,gap)=>total+gap,0);
  return {...result,scrollable_pixels:maximum,scroll_distance_pixels:distance,
    frame_count:samples.length,average_fps:1000*samples.length/sum,
    frame_p95_ms:sorted[Math.floor((sorted.length-1)*.95)],
    frame_max_ms:Math.max(...samples),frames_over_33ms:samples.filter(gap=>gap>33.4).length};
}"""


class StaticRenderer(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def measure(browser, url, count, variant, duration, output, run):
    page = browser.new_page(viewport={"width": 1280, "height": 900}, color_scheme="dark")
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.add_init_script(STUB.replace("__FIXTURE_STATE__", json.dumps(fixture_state(count))).replace("__VARIANT__", json.dumps(variant)))
    page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(url) else route.abort())
    try:
        page.goto(url)
        trigger = page.locator(".model-trigger")
        expect(trigger).to_be_visible()
        page.wait_for_timeout(300)
        trigger.click()
        rows = page.locator(".model-option-list > button")
        expect(rows.first).to_be_visible()
        opened = page.evaluate("window.__pickerBenchmark.finish()")
        search = page.locator(".model-search input")
        wanted = f"bench-model-{count-1:05d}"
        search.fill(wanted)
        expect(rows).to_have_count(1)
        expect(rows.first).to_contain_text(f"Benchmark Model {count-1:05d}")
        searched = page.evaluate("window.__pickerBenchmark.finish()")
        page.evaluate("window.__pickerBenchmark.nextInputPhase='restore'")
        search.fill("")
        expect(rows.first).to_contain_text("Benchmark Model 00000")
        restored = page.evaluate("window.__pickerBenchmark.finish()")
        scrolled = page.evaluate(SCROLL, duration)
        page.locator('.model-option-list').evaluate('element => { element.scrollTop = element.scrollHeight; }')
        expect(page.get_by_role('button', name=f'Benchmark Model {count-1:05d}', exact=False)).to_be_visible()
        if run == 0:
            page.screenshot(path=str(output / f"model-picker-{variant}-{count}.png"))
        assert not errors, errors
        return {"models": count, "variant": variant, "run": run,
                "open": opened, "search": searched, "restore": restored,
                "scroll": scrolled, "browser_errors": errors}
    finally:
        page.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--renderer-dir", type=Path, default=ROOT / "ReverieCli-ui" / "dist")
    parser.add_argument("--output", type=Path, default=ROOT / ".runtime" / "provider-configuration-fixes" / "gui-baseline")
    parser.add_argument("--sizes", type=int, nargs="+", default=[400, 2000, 10000])
    parser.add_argument("--variants", nargs="+", choices=["classic", "liquid-glass"], default=["classic", "liquid-glass"])
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--scroll-ms", type=int, default=1800)
    args = parser.parse_args()
    if not (args.renderer_dir / "index.html").is_file():
        parser.error("Build the actual renderer before measuring it.")
    args.output.mkdir(parents=True, exist_ok=True)
    files = [args.renderer_dir / "index.html", *sorted((args.renderer_dir / "assets").glob("index-*"))]
    artifacts = [{"path": str(path.relative_to(args.renderer_dir)), "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                  "modified_ns": path.stat().st_mtime_ns} for path in files if path.is_file()]
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(StaticRenderer, directory=str(args.renderer_dir)))
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    results = []
    try:
        with sync_playwright() as runtime:
            channel = "msedge" if os.name == "nt" else None
            browser = runtime.chromium.launch(channel=channel, headless=True)
            version = browser.version
            try:
                for variant in args.variants:
                    for count in args.sizes:
                        for run in range(args.runs):
                            result = measure(browser, url, count, variant, args.scroll_ms, args.output, run)
                            results.append(result)
                            print(json.dumps(result), flush=True)
                            (args.output / "results.json").write_text(json.dumps({
                                "browser_version": version, "headless": True, "renderer": artifacts,
                                "note": "Real renderer and CSS; isolated bridge fixture. Event-to-two-frames includes automation observation time. Headless RAF data does not establish physical display frame rate.",
                                "results": results,
                            }, indent=2), encoding="utf-8")
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
