export function verificationEvidence(result:Record<string,unknown>):{passed:boolean;evidence:string} {
  try {
    const output=String(result.output_text || '').trim();
    const parsed=JSON.parse(output.startsWith('```') ? output.split('\n').slice(1,-1).join('\n') : output);
    return {passed:result.success===true && parsed.passed===true && typeof parsed.evidence==='string' && Boolean(parsed.evidence.trim()),evidence:String(parsed.evidence || '')};
  }catch{return {passed:false,evidence:'The reviewer did not return structured acceptance evidence.'};}
}
