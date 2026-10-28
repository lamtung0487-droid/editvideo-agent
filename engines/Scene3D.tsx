import React,{useMemo,useEffect,useRef,useState} from 'react';
import {ThreeCanvas} from '@remotion/three';
import {useFrame,useThree} from '@react-three/fiber';
import {useCurrentFrame,staticFile,delayRender,continueRender,cancelRender} from 'remotion';
import {createWorld,drawPose,destroyWorld,disposeSceneAssets,projectLabels,prepareRenderer,renderWorld,loadSceneAssets,sceneAssetIds,THREE} from './scene3d.js';

// Environment reflections and bloom need the live renderer. A priority-1 useFrame takes over drawing,
// and Remotion advances the frameloop once per rendered frame, so output stays frame-deterministic.
const Post=({world,width,height}:any)=>{
 const gl=useThree(s=>s.gl),root=useThree(s=>s.scene);
 useMemo(()=>prepareRenderer(world,gl,width,height,root),[world,gl,root,width,height]);
 useFrame(()=>{if(world.composer)renderWorld(world,gl);},world.data.bloom?1:0);
 return null;
};

// Textures and glTF models load once before any frame is captured (delayRender), never mid-render.
const useSceneAssets=(data:any,media:any,frameSize:number)=>{
 const key=JSON.stringify(sceneAssetIds(data));
 const [assets,setAssets]=useState<any>(()=>sceneAssetIds(data).length?null:{textures:new Map(),models:new Map()});
 const [handle]=useState(()=>sceneAssetIds(data).length?delayRender('Load Scene3D textures/models'):null);
 useEffect(()=>{if(!handle)return;loadSceneAssets(data,(id:string)=>staticFile(media[id].src),staticFile('draco/'),frameSize).then(setAssets).catch(cancelRender);},[key]);
 // Released after the commit that mounted the ThreeCanvas (which holds its own delayRender until created): released
 // together with setAssets, a frame could be captured in between with no canvas (a blank frame where a layer starts).
 const released=useRef(false);
 useEffect(()=>{if(handle&&assets&&!released.current){released.current=true;continueRender(handle);}},[assets]);
 useEffect(()=>()=>disposeSceneAssets(assets),[assets]);
 return assets;
};

export const Scene3D=({data,width,height,media={}}:any)=>{
 const frame=useCurrentFrame();
 const assets=useSceneAssets(data,media,Math.max(width,height));
 const world=useMemo(()=>assets?createWorld(data,assets):null,[JSON.stringify(data),assets]);
 useEffect(()=>()=>{if(world)destroyWorld(world);},[world]);
 if(!world)return <div style={{width,height}}/>;
 drawPose(world,frame,width/height);
 return <div style={{position:'relative',width,height}}><ThreeCanvas width={width} height={height} camera={world.camera} shadows gl={{antialias:true,preserveDrawingBuffer:true,alpha:true}} onCreated={({gl})=>{gl.outputColorSpace=THREE.SRGBColorSpace;gl.toneMapping=THREE.ACESFilmicToneMapping;gl.shadowMap.type=THREE.PCFSoftShadowMap;}}>
  <primitive object={world.scene}/>
  <Post world={world} width={width} height={height}/>
 </ThreeCanvas>{projectLabels(world,width,height).filter(l=>l.visible).map(l=><div key={l.id} style={{position:'absolute',left:l.x,top:l.y,transform:'translateX(-50%)',whiteSpace:'nowrap',fontSize:data.label_font_size,color:data.label_color,fontWeight:600,background:data.background,padding:'4px 10px',borderRadius:4,opacity:l.alpha}}>{l.text}</div>)}</div>;
};
