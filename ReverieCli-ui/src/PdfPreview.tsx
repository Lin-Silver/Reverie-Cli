import { useEffect, useRef, useState } from "react";
import { getDocument, GlobalWorkerOptions } from "pdfjs-dist";
import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { useI18n } from "./i18n";

GlobalWorkerOptions.workerSrc=workerUrl;
export function PdfPreview({url,page,onPage}:{url:string;page:number;onPage:(page:number)=>void}) {
  const {t}=useI18n();const canvas=useRef<HTMLCanvasElement>(null);const [pages,setPages]=useState(0);const [error,setError]=useState("");const [loading,setLoading]=useState(false);const [zoom,setZoom]=useState(1);
  useEffect(()=>{let cancelled=false;setLoading(true);setError("");const bytes=Uint8Array.from(atob(url.slice(url.indexOf(",")+1)),char=>char.charCodeAt(0));const document=getDocument({data:bytes,enableXfa:false});
    void document.promise.then(async pdf=>{if(cancelled)return;setPages(pdf.numPages);const number=Math.max(1,Math.min(pdf.numPages,page));if(number!==page){onPage(number);return;}const current=await pdf.getPage(number);const viewport=current.getViewport({scale:1.25*zoom});const element=canvas.current;if(!element || cancelled)return;element.width=viewport.width;element.height=viewport.height;await current.render({canvas:element,viewport}).promise;if(!cancelled)setLoading(false);}).catch(e=>{if(!cancelled){setError(String(e));setLoading(false);}});return()=>{cancelled=true;void document.destroy();};
  },[url,page,zoom,onPage]);
  return <div className="pdf-preview"><div className="workbench-toolbar"><button type="button" disabled={page<=1} onClick={()=>onPage(page-1)}>{t("上一页")}</button><span>{page} / {pages || "?"}</span><button type="button" disabled={page>=pages} onClick={()=>onPage(page+1)}>{t("下一页")}</button><button type="button" onClick={()=>setZoom(Math.max(.25,zoom-.25))}>−</button><button type="button" onClick={()=>setZoom(1)}>{Math.round(zoom*100)}%</button><button type="button" onClick={()=>setZoom(Math.min(4,zoom+.25))}>+</button></div>{loading && <p role="status">{t("正在加载")}</p>}{error && <p role="alert" className="persistent-error">{error}</p>}<canvas ref={canvas} aria-label={`${t("PDF 页")} ${page}`} /></div>;
}
