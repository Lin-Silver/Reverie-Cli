import { createHash } from "node:crypto";
import { readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),"..");
const target=path.join(root,"dist-electron","reverie-build.json");
const files=[];
async function collect(directory){for(const entry of await readdir(directory,{withFileTypes:true})){const file=path.join(directory,entry.name);if(entry.isDirectory())await collect(file);else if(entry.isFile() && file!==target)files.push(file);}}
await collect(path.join(root,"dist"));await collect(path.join(root,"dist-electron"));
const kernel=path.join(root,"build","generated","reverie-trusted-kernels.json");
try{await readFile(kernel);files.push(kernel);}catch(error){if(error.code!=="ENOENT")throw error;}
const hash=createHash("sha256");for(const file of files.sort()){hash.update(path.relative(root,file).replaceAll(path.sep,"/"));hash.update("\0");hash.update(await readFile(file));}
const {version}=JSON.parse(await readFile(path.join(root,"package.json"),"utf8"));
const record={version,id:hash.digest("hex").slice(0,16),builtAt:new Date().toISOString(),platform:process.platform,arch:process.arch};
await writeFile(target,JSON.stringify(record,null,2)+"\n");
console.log(`Reverie ${version} build ${record.id}`);
