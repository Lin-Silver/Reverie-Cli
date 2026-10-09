import { expect, it } from "vitest";
import { desktopCommand } from "./desktop-commands";
import { parseReviewFindings, reviewLocations } from "./Workbench";

it("maps settings and preserves quoted review paths, scope and base",()=>{
  expect(desktopCommand("/mode writer")).toEqual({kind:"setting",key:"mode",value:"writer"});
  expect(desktopCommand("/permission mode strict")).toEqual({kind:"setting",key:"permission_mode",value:"strict"});
  expect(desktopCommand('/review "src/中文 file.ts" --scope branch --base "origin/main"')).toEqual({kind:"review",file:"src/中文 file.ts",scope:"branch",base:"origin/main"});
  expect(desktopCommand("/review --scope invalid")).toEqual({kind:"unsupported"});
  expect(desktopCommand("/review file extra")).toEqual({kind:"unsupported"});
  expect(desktopCommand("/provider status")).toEqual({kind:"provider",name:"status"});
  expect(desktopCommand("/provider secret-provider")).toBeNull();
});

it("distinguishes empty findings from invalid JSON and rejects invented file locations",()=>{
  const locations=new Map([["src/file.ts",reviewLocations("@@ -4,2 +4,2 @@\n context\n-old\n+new\n")]]);
  expect(parseReviewFindings("[]",locations)).toEqual({findings:[]});
  expect(parseReviewFindings("I found no issues",locations).formatError).toBeTruthy();
  const valid={priority:"P1",title:"Fault",path:"src/file.ts",line:5,trigger:"Call",expected:"Success",actual:"Fails",evidence:"Code"};
  const parsed=parseReviewFindings(JSON.stringify([valid,{...valid,path:"../elsewhere"},{...valid,line:999}]),locations);
  expect(parsed.findings).toEqual([valid]);
  expect(parsed.formatError).toContain("2 findings");
  expect(parseReviewFindings(JSON.stringify([{...valid,path:"src\\file.ts"}]),locations).findings[0].path).toBe("src/file.ts");
});
