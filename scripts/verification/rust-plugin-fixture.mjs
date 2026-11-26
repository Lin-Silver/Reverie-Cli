import fs from 'node:fs';
import path from 'node:path';
import {execFileSync} from 'node:child_process';

export function createPluginFixture(repo,root) {
  const projectRoot=path.join(root,'workspace'),appRoot=path.join(root,'application'),marketRoot=path.join(root,'market-source'),sourceRoot=path.join(marketRoot,'packages/native');
  for(const directory of [projectRoot,path.join(appRoot,'.reverie'),path.join(marketRoot,'.claude-plugin'),path.join(sourceRoot,'commands'),path.join(sourceRoot,'skills/native-skill'),path.join(sourceRoot,'hooks')])fs.mkdirSync(directory,{recursive:true});
  fs.writeFileSync(path.join(projectRoot,'.gitignore'),'.reverie/\n');
  for(const args of [['init','--initial-branch=main'],['add','.gitignore'],['-c','user.name=Reverie verification','-c','user.email=verification@localhost','commit','-m','Independent extension workspace']])execFileSync('git',args,{cwd:projectRoot,windowsHide:true,stdio:'ignore'});
  fs.writeFileSync(path.join(appRoot,'.reverie/config.json'),JSON.stringify({mode:'reverie',auto_index:false,models:[],active_model_source:'standard',active_model_index:0}));
  fs.copyFileSync(path.join(repo,'LICENSE'),path.join(sourceRoot,'LICENSE'));
  fs.writeFileSync(path.join(sourceRoot,'commands/native.md'),'---\nname: native-command\ndescription: Native fixture command.\nallowed-tools: [read_file]\n---\nPLUGIN_COMMAND_FIXTURE中文😀\n');
  fs.writeFileSync(path.join(sourceRoot,'skills/native-skill/SKILL.md'),'---\nname: plugin-native-skill\ndescription: Native installed fixture.\n---\nPLUGIN_SKILL_FIXTURE中文😀\n');
  const marker=path.join(root,'hook-was-run.txt');
  fs.writeFileSync(path.join(sourceRoot,'forbidden-hook.mjs'),`import fs from 'node:fs';fs.writeFileSync(${JSON.stringify(marker)},'unexpected hook execution');\n`);
  fs.writeFileSync(path.join(sourceRoot,'hooks/hooks.json'),JSON.stringify({hooks:{PreToolUse:[{matcher:'Write',hooks:[{type:'command',command:`"${process.execPath}" "\${CLAUDE_PLUGIN_ROOT}/forbidden-hook.mjs"`,permissions:['files.read'],env:{FIXTURE_TOKEN:'PLUGIN_FIXTURE_SECRET'}}]}]}}));
  function writeVersion(version) {
    fs.writeFileSync(path.join(sourceRoot,'plugin.json'),JSON.stringify({name:'native-plugin-fixture',display_name:'Native plugin fixture😀',version,license:'MIT',commands:'./commands',skills:'./skills',hooks:'./hooks/hooks.json',permissions:version==='1.0.0'?['files.read']:['files.read','files.write']}));
  }
  writeVersion('1.0.0');
  fs.writeFileSync(path.join(marketRoot,'.claude-plugin/marketplace.json'),JSON.stringify({name:'native-install-fixture',plugins:[{name:'native-plugin-fixture',version:'1.0.0',description:'Independent native fixture',source:'./packages/native'}]}));
  return {projectRoot,appRoot,marketRoot,sourceRoot,marker,writeVersion};
}
