import { describe, expect, it } from 'vitest';
import { verificationEvidence } from './task-verification';

describe('task acceptance evidence',()=>{
  it('requires a successful reviewer and specific structured evidence',()=>{
    expect(verificationEvidence({success:true,output_text:'{"passed":true,"evidence":"Read the generated UTF-8 file and matched its requested content."}'}).passed).toBe(true);
    for(const result of [{success:false,output_text:'{"passed":true,"evidence":"done"}'},{success:true,output_text:'{"passed":true}'},{success:true,output_text:'Looks good'},{success:true,output_text:'{"passed":false,"evidence":"Required file missing"}'}])expect(verificationEvidence(result).passed).toBe(false);
  });
  it('accepts a fenced JSON response',()=>expect(verificationEvidence({success:true,output_text:'```json\n{"passed":true,"evidence":"Inspected artifact"}\n```'}).passed).toBe(true));
});
