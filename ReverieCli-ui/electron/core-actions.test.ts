import { describe, expect, it } from "vitest";

import {
  assertCoreAction,
  assertCoreResponse,
  normalizeCorePayload,
} from "./core-actions";

describe("core protocol runtime boundary", () => {
  it("accepts declared actions and object payloads", () => {
    expect(assertCoreAction("initialize")).toBe("initialize");
    expect(assertCoreAction("getState")).toBe("getState");
    expect(normalizeCorePayload({ projectRoot: "C:/workspace" })).toEqual({ projectRoot: "C:/workspace" });
  });

  it("rejects undeclared actions and non-object payloads", () => {
    expect(() => assertCoreAction("typoAction")).toThrow(/Unsupported Reverie core action/);
    expect(() => normalizeCorePayload("not-an-object")).toThrow(/payload must be an object/);
  });

  it("detects response discriminant and required-field drift", () => {
    expect(assertCoreResponse("initialize", { type: "state", state: {} }).type).toBe("state");
    expect(() => assertCoreResponse("initialize", { type: "session", state: {} })).toThrow(/protocol mismatch/);
    expect(() => assertCoreResponse("initialize", { type: "state" })).toThrow(/missing: state/);
    expect(() => assertCoreResponse("compactContext", { type: "context.compacted", success: true })).toThrow(/missing: message, session, sessions, recovery, context_engine/);
  });

  it("keeps user answers separate from permission approvals", () => {
    expect(assertCoreAction("resolveUserInput")).toBe("resolveUserInput");
    expect(assertCoreResponse("resolveUserInput",{type:"user.resolved",question_id:"question"}).question_id).toBe("question");
    expect(() => assertCoreResponse("resolveApproval",{type:"user.resolved",question_id:"question"})).toThrow(/protocol mismatch/);
  });
  it("keeps Connector control distinct from MCP execution and config replies",()=>{
    expect(assertCoreAction('clearConnectorCredentials')).toBe('clearConnectorCredentials');
    expect(()=>assertCoreResponse('listMcp',{type:'mcp',mcp:{},servers:[]})).toThrow(/effective_server_ids/);
    expect(()=>assertCoreResponse('authorizeConnector',{type:'connector.control',authorization_id:'auth',cancelled:true})).toThrow(/protocol mismatch/);
    expect(assertCoreResponse('cancelConnectorAuthorization',{type:'connector.control',authorization_id:'auth',cancelled:true}).cancelled).toBe(true);
  });
  it("keeps prepared plugin content separate from activation and complete inspection",()=>{
    expect(assertCoreAction('preparePlugin')).toBe('preparePlugin');
    expect(assertCoreResponse('preparePlugin',{type:'plugin.prepared',plugin_id:'one',candidate:{},plugins:{}}).type).toBe('plugin.prepared');
    expect(()=>assertCoreResponse('activatePlugin',{type:'plugin.prepared',plugin_id:'one',candidate:{},plugins:{}})).toThrow(/protocol mismatch/);
    expect(()=>assertCoreResponse('inspectPlugin',{type:'plugin.inspect',plugin_id:'one',record:{}})).toThrow(/missing: active, revision/);
    expect(assertCoreResponse('stopPluginOperation',{type:'plugin.control',operation_id:'job',cancelled:true}).cancelled).toBe(true);
  });
});
