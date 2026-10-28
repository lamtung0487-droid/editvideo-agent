import React from 'react';
import {AbsoluteFill, Composition, Img, OffthreadVideo, registerRoot, staticFile} from 'remotion';
const ids:Record<string,string>=__ASSETS__;
type Props={timeline:any;config:any;media:Record<string,any>};
const ink='#10191a',paper='#f0eee5',gold='#e4b866';
const Demo=({media}:Props)=><AbsoluteFill style={{background:ink,color:paper,fontFamily:'Arial, sans-serif'}}>
  <div style={{position:'absolute',left:100,top:48,color:gold,fontSize:24,letterSpacing:3}}>ẢNH THAM CHIẾU → CẢNH VIDEO</div>
  <div style={{position:'absolute',left:100,top:92,fontSize: sixty,fontWeight:700}}>Điều khiển chuyển động bằng ảnh neo</div>
  {(['before','after'] as const).map((name,i)=><div key={name} style={{position:'absolute',left:100+i*890,top:210,width:830}}>
    <div style={{fontSize:30,fontWeight:700,marginBottom:18}}>{i===0?'01  Chỉ ảnh đầu':'02  Có thêm ảnh cuối'}</div>
    <div style={{width:830,height:519,overflow:'hidden',borderRadius:12,border:'1px solid #4b5147'}}>
      <OffthreadVideo muted src={staticFile(media[ids[name]].src)} style={{width:'100%',height:'100%',objectFit:'contain'}}/>
    </div>
    <div style={{fontSize:24,color:'#b8c1b7',marginTop:18}}>{i===0?'Camera tiến nhanh; lá tiền cảnh rời khung.':'Bám hướng kết thúc; cây và ánh nắng giữ liên hệ.'}</div>
  </div>)}
  <div style={{position:'absolute',left:100,top:846,fontSize:22,color:gold}}>Hai ảnh dùng để định hướng cảnh bên phải</div>
  {(['reference_start','reference_end'] as const).map((name,i)=><div key={name} style={{position:'absolute',left:100+i*304,top:884,width:256,height:160,overflow:'hidden',borderRadius:8}}>
    <Img src={staticFile(media[ids[name]].src)} style={{width:'100%',height:'100%',objectFit:'contain'}}/>
    <div style={{position:'absolute',bottom:0,left:0,right:0,background:'#10191ac9',padding:'5px 10px',fontSize:18}}>{i===0?'Ảnh đầu':'Ảnh cuối'}</div>
  </div>)}
  <div style={{position:'absolute',left:760,top:894,width:1000,fontSize:27,lineHeight:1.5,color:'#b8c1b7'}}>Footage AI tạo từ ảnh, không phải cảnh quay thật.<br/>Quan sát cả chuyển động và mức bám ảnh để chọn bản dựng.</div>
</AbsoluteFill>;
const sixty=60;
const Root=()=> <Composition id="AgentVideo" component={Demo} width={1920} height={1080} fps={30} durationInFrames={91} defaultProps={{timeline:{},config:{},media:{}}} calculateMetadata={({props}:any)=>({durationInFrames:props.timeline.total_frames,width:props.timeline.width,height:props.timeline.height,fps:30})}/>;
registerRoot(Root);
