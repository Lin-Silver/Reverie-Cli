import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../..');
const ARTIFACTS = new Set(['.runtime','.audit','dist','build','result_images']);
const LINK = /!?\[[^\]\n]*\]\((<[^>\n]+>|[^\s)]+)(?:\s+["'][^\n]*?["'])?\)/g;
const REFERENCE = /^\s{0,3}\[[^\]]+\]:\s*(<[^>]+>|\S+)/gm;

export function prose(text) {
  let fence='';
  return text.replace(/^\uFEFF/,'').split(/\r?\n/).map(line=>{
    const marker=line.match(/^\s{0,3}(`{3,}|~{3,})/)?.[1][0];
    if(marker){if(!fence)fence=marker;else if(fence===marker)fence='';return '';}
    return fence?'':line;
  }).join('\n');
}

export function anchors(text) {
  const result=new Set([...text.matchAll(/\bid=["']([^"']+)["']/g)].map(match=>match[1]));
  const counts=new Map();
  for(const line of prose(text).split('\n')){
    const title=line.match(/^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$/)?.[1];
    if(!title)continue;
    const slug=title.replace(/<[^>]+>/g,'').toLowerCase().replace(/\[([^\]]+)\]\([^)]*\)/g,'$1').replace(/[^\p{L}\p{N}_ -]/gu,'').replaceAll(' ','-');
    const count=counts.get(slug)||0;counts.set(slug,count+1);result.add(count?`${slug}-${count}`:slug);
  }
  return result;
}

function markdownFiles(directory) {
  if(!fs.existsSync(directory))return [];
  return fs.readdirSync(directory,{withFileTypes:true}).flatMap(item=>item.isDirectory()?markdownFiles(path.join(directory,item.name)):item.name.endsWith('.md')?[path.join(directory,item.name)]:[]).sort();
}

export function defaultPaths(root=ROOT) {
  const files=['README.md','SECURITY.md','ReverieCli-py/README.md','ReverieCli-rs/README.md','ReverieCli-ui/README.md','plugins/README.md','plugins/blender/README.md','plugins/game_models/README.md'];
  return [...files.map(file=>path.join(root,file)),...markdownFiles(path.join(root,'docs')),...markdownFiles(path.join(root,'tasks/rust-3.0'))];
}

export function check(paths,root=ROOT) {
  const errors=[];const local_artifact_references=[];const cache=new Map();let local_links=0;
  for(const source of paths){
    const body=prose(fs.readFileSync(source,'utf8'));
    for(const match of [...body.matchAll(LINK),...body.matchAll(REFERENCE)]){
      const target=match[1].replace(/^<|>$/g,'');
      if(/^[a-z][a-z\d+.-]*:|^\/\//i.test(target))continue;
      local_links++;
      const [pathname,fragment]=target.split('#',2);
      const file=path.resolve(path.dirname(source),decodeURIComponent(pathname.split('?')[0]||path.basename(source)));
      const relative=path.relative(root,file);const pieces=relative.split(path.sep);
      const item={source:path.relative(root,source).split(path.sep).join('/'),line:body.slice(0,match.index).split('\n').length,target};
      if(relative==='..'||relative.startsWith(`..${path.sep}`)||path.isAbsolute(relative)){errors.push({...item,reason:'outside repository'});continue;}
      if(ARTIFACTS.has(pieces[0]) || pieces[0]==='ReverieCli-ui'&&['release','.kernel','dist','dist-electron'].includes(pieces[1])){
        local_artifact_references.push({...item,exists_locally:fs.existsSync(file)});continue;
      }
      if(!fs.existsSync(file)){errors.push({...item,reason:'missing file'});continue;}
      if(fragment&&file.toLowerCase().endsWith('.md')){
        if(!cache.has(file))cache.set(file,anchors(fs.readFileSync(file,'utf8')));
        if(!cache.get(file).has(decodeURIComponent(fragment)))errors.push({...item,reason:'missing heading anchor'});
      }
    }
  }
  return {documents:paths.length,local_links,errors,local_artifact_references};
}

if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  const args=process.argv.slice(2);let output;
  const outputIndex=args.indexOf('--json');if(outputIndex>=0){output=path.resolve(args[outputIndex+1]);args.splice(outputIndex,2);}
  const report=check(args.length?args.map(file=>path.resolve(ROOT,file)):defaultPaths());
  if(output){fs.mkdirSync(path.dirname(output),{recursive:true});fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');}
  console.log(`Documents: ${report.documents}; local links: ${report.local_links}; errors: ${report.errors.length}; local artifact references: ${report.local_artifact_references.length}`);
  for(const item of report.errors)console.log(`${item.source}:${item.line}: ${item.reason}: ${item.target}`);
  process.exitCode=report.errors.length?1:0;
}
