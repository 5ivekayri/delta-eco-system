// Opaque-origin sandbox + restrictive CSP: generated pages cannot access Delta or the network.
export function workspacePreview(assets:Record<string,string>,entry:string):string {
 const doc=new DOMParser().parseFromString(assets[entry]||'<!doctype html><p>Выберите HTML-файл</p>','text/html');
 const resolve=(name:string)=>{try {const url=new URL(name,'https://workspace.invalid/'+entry);return url.origin==='https://workspace.invalid'?decodeURIComponent(url.pathname.slice(1)):'';}catch{return '';}};
 doc.querySelectorAll('base,meta[http-equiv],iframe,object,embed').forEach(e=>e.remove());
 doc.querySelectorAll('link').forEach(el=>{const path=resolve(el.getAttribute('href')||'');if(el.getAttribute('rel')==='stylesheet'&&assets[path]!==undefined){const style=doc.createElement('style');style.textContent=assets[path];el.replaceWith(style);}else el.remove();});
 doc.querySelectorAll('script[src]').forEach(el=>{const path=resolve(el.getAttribute('src')||'');if(assets[path]!==undefined){el.removeAttribute('src');el.textContent=assets[path];}else el.remove();});
 doc.querySelectorAll('[src]').forEach(el=>{const path=resolve(el.getAttribute('src')||'');if(path.endsWith('.svg')&&assets[path])el.setAttribute('src','data:image/svg+xml;charset=utf-8,'+encodeURIComponent(assets[path]));});
 const policy=doc.createElement('meta');policy.httpEquiv='Content-Security-Policy';policy.content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; form-action 'none'; base-uri 'none';";doc.head.prepend(policy);
 const charset=doc.createElement('meta');charset.setAttribute('charset','utf-8');doc.head.prepend(charset);
 return '<!doctype html>'+doc.documentElement.outerHTML;
}
