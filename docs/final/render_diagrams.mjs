// Reproducible local diagram rendering. No public site is created.
// Install mermaid@12.3.0 separately, set MERMAID_DIST, and install frontend Playwright dependencies.
import fs from 'node:fs/promises';
import path from 'node:path';
import http from 'node:http';
import crypto from 'node:crypto';
import { pathToFileURL, fileURLToPath } from 'node:url';
const folder=path.dirname(fileURLToPath(import.meta.url));
const root=path.resolve(folder,'../..');
const dist=path.resolve(process.env.MERMAID_DIST||path.join(root,'work/report-tools/node_modules/mermaid/dist'));
const {chromium}=await import(pathToFileURL(process.env.PLAYWRIGHT_MODULE||path.join(root,'frontend/node_modules/playwright/index.mjs')).href);
const markdown=await fs.readFile(path.join(folder,'EraseProof-X-Complete-Technical-Report.md'),'utf8');
const sources=[...markdown.matchAll(/```mermaid\n([\s\S]*?)```/g)].map(m=>m[1]);
const output=path.join(folder,'diagrams');await fs.mkdir(output,{recursive:true});
const server=http.createServer(async(req,res)=>{
 try {
  if(req.url==='/') {res.setHeader('Content-Type','text/html');res.end('<!doctype html><html><body style="margin:20px;background:white"><div id="figure"></div><script type="module">import mermaid from "/mermaid.esm.min.mjs";window.mermaid=mermaid;</script></body></html>');return;}
  const target=path.resolve(dist,'.'+decodeURIComponent(new URL(req.url,'http://localhost').pathname));
  if(!target.startsWith(dist+path.sep))throw Error('invalid path');
  res.setHeader('Content-Type',target.endsWith('.mjs')||target.endsWith('.js')?'text/javascript':'application/octet-stream');res.end(await fs.readFile(target));
 }catch {res.statusCode=404;res.end('Not found');}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1800,height:1400},deviceScaleFactor:2});
const manifest={renderer:'mermaid@12.3.0 + actual Chromium',layout:'flowchart LR rendered TB for readable portrait PDF; edges and labels unchanged',figures:[]};
try {
 await page.goto(`http://127.0.0.1:${server.address().port}/`);await page.waitForFunction(()=>!!window.mermaid);
 await page.evaluate(()=>window.mermaid.initialize({startOnLoad:false,securityLevel:'strict',theme:'base',layout:'dagre',fontFamily:'Arial',themeVariables:{fontFamily:'Arial',fontSize:'18px',primaryColor:'#eef3fb',primaryTextColor:'#17243a',primaryBorderColor:'#5276ab',lineColor:'#526983',secondaryColor:'#e8f4ee',tertiaryColor:'#f5f6f9'},flowchart:{htmlLabels:false,nodeSpacing:24,rankSpacing:40,wrappingWidth:190},sequence:{actorMargin:35,wrap:true,messageFontSize:16},er:{fontSize:16}}));
 for(let n=0;n<sources.length;n++){
  const code=sources[n].replace(/^flowchart LR/m,'flowchart TB');
  const svg=await page.evaluate(async({code,n})=>{document.getElementById('figure').innerHTML='';const {svg}=await window.mermaid.render('diagram'+n,code);document.getElementById('figure').innerHTML=svg;const element=document.querySelector('#figure svg');const box=element.viewBox.baseVal;element.style.maxWidth='none';element.style.width=box.width+'px';element.style.height=box.height+'px';return element.outerHTML;},{code,n});
  const name=`figure-${String(n+1).padStart(2,'0')}`;
  await fs.writeFile(path.join(output,name+'.svg'),svg);
  const locator=page.locator('#figure svg');await locator.screenshot({path:path.join(output,name+'.png')});
  const box=await locator.boundingBox();manifest.figures.push({index:n+1,source_sha256:crypto.createHash('sha256').update(sources[n]).digest('hex'),png:name+'.png',svg:name+'.svg',width_css:box.width,height_css:box.height});
 }
 await fs.writeFile(path.join(output,'manifest.json'),JSON.stringify(manifest,null,2));console.log('Rendered',sources.length,'actual diagrams from report source');
}finally{await browser.close();await new Promise(resolve=>server.close(resolve));}
