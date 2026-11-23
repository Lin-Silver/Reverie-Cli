import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {test} from 'node:test';
import {anchors,check,prose} from './check-docs.mjs';

test('Unicode duplicate headings and explicit anchors ignore fenced examples',()=>{
  const text='# 中文 `API`\n# 中文 API\n<a id="explicit"></a>\n```md\n# hidden\n[missing](bad.md)\n```';
  assert.deepEqual([...anchors(text)],['explicit','中文-api','中文-api-1']);
  assert(!prose(text).includes('[missing]'));
});

test('offline links distinguish missing files, bad anchors, traversal and local build artifacts',()=>{
  const directory=path.resolve('.runtime/rust-3.0/doc-check-tests');fs.mkdirSync(directory,{recursive:true});
  const root=fs.mkdtempSync(path.join(directory,'case-'));const file=path.join(root,'README.md');
  fs.writeFileSync(file,'# title\n[ok](#title)\n[bad](#missing)\n[path](missing.md)\n[out](../outside.md)\n[build](.runtime/artifact.zip)\n[external](https://example.invalid)\n');
  const report=check([file],root);
  assert.equal(report.local_links,5);assert.deepEqual(report.errors.map(error=>error.reason),['missing heading anchor','missing file','outside repository']);
  assert.equal(report.local_artifact_references.length,1);
});
