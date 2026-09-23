let token='';
export function setToken(value:string){token=value;}
export async function api<T=any>(path:string,method='GET',body?:unknown):Promise<T>{
  const form=body instanceof FormData;
  const res=await fetch('/api'+path,{method,headers:{...(method!=='GET'?{'X-PaperNest-Token':token}:{}),...(!form&&body!==undefined?{'Content-Type':'application/json'}:{})},body:body===undefined?undefined:form?body:JSON.stringify(body)});
  if(!res.ok){let message='请求失败，请稍后重试';try{const d=await res.json();message=typeof d.detail==='string'?d.detail:JSON.stringify(d.detail);}catch{}throw new Error(message);}
  return res.json();
}
export type Direction={id:string;name:string;description:string;keywords:string[];excludes:string[];categories:string[];authors?:string[];venues?:string[]};
export type Summary={text:string;basis:string;model:string;provider:string;created:string;cached?:boolean;pdf_hash?:string};
export type Paper={id:string;title:string;authors:string[];abstract:string;published:string;source:string;url:string;pdf_url:string;pdf_file:string;pdf_hash:string;doi:string;arxiv_id:string;tags:string[];saved:boolean;status:string;feedback:string;collections:string[];classic:boolean;classic_score?:number;classic_grade?:string;classic_rank?:number;score_scope?:string;score_parts?:{evidence:number;maturity:number;relevance:number};curation?:string;evidence:{label:string;url:string;type:string}[];summary?:Summary;deep_summary?:Summary;reasons?:string[];rank_score?:number;excluded?:string[];analysis?:{summary:string;reason:string;uncertain:string;concepts?:string[]};page_count?:number;pages?:{page:number;text:string}[];read_page?:number;scanned?:boolean;version?:string;pdf_version?:string};
export type Note={id:string;paper_title?:string;paper_id:string;text:string;quote:string;page:number;created:string;rects:{x:number;y:number;w:number;h:number}[];file_hash:string};
export type Course={id:string;title:string;author:string;url:string;platform:string;language:string;level:string;free:string;kind:string;tags:string[];description:string;status:string;saved:boolean;reason:string;verified:string;known:boolean};
export const safeUrl=(url:string)=>/^https?:\/\//i.test(url)?url:'#';
export const split=(s:string)=>s.split(/[,，\n]/).map(s=>s.trim()).filter(Boolean);
