/* Verify actual Chromium FontFace loading from exported offline Hyperframes source. */
import {openBrowser} from '@remotion/renderer';
import http from 'node:http';
import fs from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const [sourceArg,outputArg]=process.argv.slice(2);
if(!sourceArg||!outputArg)throw Error('source directory and report path required');
const root=path.resolve(sourceArg),output=path.resolve(outputArg),requests=[];
// Share the cache used by render-remotion.mjs; don't download a second copy in caller cwd.
process.chdir(path.dirname(fileURLToPath(import.meta.url)));
const server=http.createServer(async(req,res)=>{
 try{
  const pathname=decodeURIComponent(new URL(req.url,'http://localhost').pathname);
  const filename=path.resolve(root,'.'+(pathname==='/'?'/index.html':pathname));
  if(!filename.startsWith(root+path.sep))throw Error('outside source');
  const bytes=await fs.readFile(filename);requests.push(pathname);
  res.setHeader('Content-Type',({'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.ttf':'font/ttf','.json':'application/json'})[path.extname(filename)]||'application/octet-stream');res.end(bytes);
 }catch(error){res.statusCode=404;res.end('not found');}
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
let browser;
try{
 browser=await openBrowser('chrome');
 const page=await browser.newPage({context:()=>null,logLevel:'error',indent:false,pageIndex:0,onBrowserLog:null,onLog:()=>{}});
 await page.goto({url:`http://127.0.0.1:${server.address().port}/`,timeout:30000,options:{waitUntil:'load'}});
 const result=await page.evaluate(async()=>{
  const until=Date.now()+20000;
  while(!window.EditVideoDraw){if(Date.now()>until)throw Error('Font loader/runtime did not finish');await new Promise(resolve=>setTimeout(resolve,50));}
  const input=window.EditVideoInput;
  const faces=Array.from(document.fonts).map(face=>({family:face.family,weight:face.weight,style:face.style,status:face.status}));
  const canvas=document.createElement('canvas'),ctx=canvas.getContext('2d'),sample='Tiếng Việt: Nguyễn Ánh, kỹ thuật, 0123456789';
  const widths=Array.from(new Set(input.fonts.map(f=>f.family))).map(family=>{
   ctx.font=`400 54px "${family}", monospace`;const local=ctx.measureText(sample).width;
   ctx.font='400 54px monospace';return {family,local_width:local,fallback_width:ctx.measureText(sample).width};
  });
  const span=document.createElement('span');span.textContent=sample;Object.assign(span.style,{position:'absolute',visibility:'hidden',whiteSpace:'pre',fontFamily:'"EV notosans"',fontSize:'54px',fontWeight:'400'});document.body.appendChild(span);
  const variation={};for(const wdth of [75,100]){span.style.fontVariationSettings=`"wdth" ${wdth}`;variation[wdth]=span.getBoundingClientRect().width;}span.remove();
  return {faces,widths,variation_widths:variation,variation_narrower:variation[75]<variation[100],expected_faces:input.fonts.length,local_faces_loaded:faces.length===input.fonts.length&&faces.every(f=>f.status==='loaded'),no_fallback_widths:widths.every(f=>Math.abs(f.local_width-f.fallback_width)>.1),pages:input.timeline.total_frames/60};
 });
 result.loopback_asset_requests=requests;
 result.scope='Real Chromium loading and glyph metrics from exported HTML source; all requested faces must load. Different widths distinguish this fixture from monospace fallback, not every Unicode glyph or total aesthetic quality.';
 if(!result.local_faces_loaded||!result.no_fallback_widths||!result.variation_narrower)throw Error('Fonts did not load as expected');
 await fs.writeFile(output,JSON.stringify(result,null,2));console.log(JSON.stringify({faces:result.faces.length,families:result.widths.length,loaded:result.local_faces_loaded,no_fallback:result.no_fallback_widths}));
}finally{if(browser)await browser.close({silent:true});server.close();}
