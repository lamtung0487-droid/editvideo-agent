/* Shared typography/color resolver and offline FontFace loader. */
(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.EditVideoDesign=api;})(typeof window==='undefined'?globalThis:window,function(){
 const loaded=new Map();
 function resolve(item,design,width,height){
  const t=design?.typography?.[item.typography_role],colors=design?.color_roles||{},scale=Math.min(width,height)/1080;
  return {...item,color:colors[item.color_role]||item.color,background:colors[item.background_role]||item.background,
   font_size:t?Math.round(t.size*scale):item.font_size,
   _type:{...(t?{fontFamily:`"EV ${t.font_id}", sans-serif`,fontWeight:t.weight,fontStyle:t.italic?'italic':'normal',fontSize:t.size*scale,lineHeight:t.line_height,letterSpacing:t.tracking+'em',fontVariantNumeric:item.typography_role==='data'||item.typography_role==='code'?'tabular-nums':'normal',...(Object.keys(t.variation_axes||{}).length?{fontVariationSettings:Object.entries(t.variation_axes).map(([k,v])=>`"${k}" ${v}`).join(', '),fontOpticalSizing:t.variation_axes.opsz===undefined?'auto':'none'}:{})}:{}),...(item.font_id?{fontFamily:`"EV ${item.font_id}", sans-serif`}:{}),...(item.font_weight?{fontWeight:item.font_weight}:{}),...(item.line_height?{lineHeight:item.line_height}:{})}};
 }
 async function loadFonts(faces,url){
  await Promise.all((faces||[]).map(f=>{
   const key=f.sha256+f.family+f.weight+f.style;
   if(!loaded.has(key))loaded.set(key,(async()=>{
    const face=new FontFace(f.family,`url("${url(f.src)}")`,{weight:f.weight,style:f.style});
    await face.load();document.fonts.add(face);return face;
   })());
   return loaded.get(key);
  }));
  await document.fonts.ready;
 }
 return {resolve,loadFonts};
});
