import React from 'react';
import {AbsoluteFill, Composition, Freeze, Loop, OffthreadVideo, Sequence, interpolate, registerRoot, staticFile, useCurrentFrame} from 'remotion';

const ids:Record<string,string>=__ASSETS__;
const bounds:number[]=__BOUNDS__;
const generateFrom:number=__GENERATE_START__;
const generatedRate=Math.min(1,(__GENERATED_FRAMES__-1)/Math.max(1,bounds[5]-bounds[4]-generateFrom));
const green='#c8ff71',ink='#0a1721',white='#f3f7fb',muted='#9bafbd';
type Props={timeline:any;config:any;media:Record<string,any>};
const Title=({index,title,sub}:any)=><div style={{position:'absolute',left:88,top:68,right:88}}>
  <div style={{fontSize:27,fontWeight:600,letterSpacing:3,color:green,marginBottom:21}}>HIỂU VIDEO <span style={{color:muted}}> / {String(index).padStart(2,'0')}</span></div>
  <div style={{fontSize:70,fontWeight:700,letterSpacing:-2,lineHeight:1.1}}>{title}</div>
  {sub&&<div style={{fontSize:31,color:muted,marginTop:18,lineHeight:1.35}}>{sub}</div>}
</div>;
const Media=({name,media,slow=false,frozen}:any)=>{
  const src=media[ids[name]]?.src;
  if(!src)return <AbsoluteFill style={{background:'#132b37',justifyContent:'center',alignItems:'center',fontSize:38}}>Đang chuẩn bị cảnh minh họa</AbsoluteFill>;
  const video=<OffthreadVideo src={staticFile(src)} muted playbackRate={name==='generated'?generatedRate:slow?.5:1} style={{width:'100%',height:'100%',objectFit:name==='generated'?'cover':'contain'}}/>;
  if(frozen!==undefined)return <Freeze frame={frozen}>{video}</Freeze>;
  if(name==='generated')return video;
  return <Loop durationInFrames={slow?120:60}>{video}</Loop>;
};
const Panel=({left,top=298,width=850,height=478,title,tag,children}:any)=><div style={{position:'absolute',left,top,width}}>
  <div style={{display:'flex',justifyContent:'space-between',fontSize:28,fontWeight:600,marginBottom:19}}><span>{title}</span><span style={{color:muted,fontWeight:400}}>{tag}</span></div>
  <div style={{position:'relative',width,height,borderRadius:24,overflow:'hidden',background:'#18303c',border:'1px solid #29414e'}}>{children}</div>
</div>;

const Scene=({index,media,duration}:any)=>{
  const f=useCurrentFrame(),enter=interpolate(Math.min(f,14),[0,14],[0,1]);
  const rise=interpolate(Math.min(f,20),[0,20],[28,0]);
  if(index===0)return <AbsoluteFill style={{background:ink}}>
    <div style={{position:'absolute',inset:0,backgroundImage:'radial-gradient(#264150 1px,transparent 1px)',backgroundSize:'28px 28px',opacity:.32}}/>
    <div style={{position:'absolute',left:96,top:88,color:green,fontSize:29,letterSpacing:4}}>CHUYỂN ĐỘNG LÀ PHÉP THỬ</div>
    <div style={{position:'absolute',left:90,top:190,fontSize:100,fontWeight:750,lineHeight:1.08,letterSpacing:-4,transform:`translateY(${rise}px)`,opacity:enter}}>Đẹp một frame.<br/><span style={{color:green}}>Chưa đủ một video.</span></div>
    {[0,1,2].map(i=><div key={i} style={{position:'absolute',left:1060+i*245,top:275+i*58,width:285,height:360,borderRadius:20,overflow:'hidden',border:'2px solid #547060',transform:`rotate(${(i-1)*7}deg) translateY(${Math.sin(f/32+i)*8}px)`,boxShadow:'0 20px 60px #0008'}}><AbsoluteFill style={{background:'#18303c'}}><Media name="source" media={media} frozen={i*20}/></AbsoluteFill><div style={{position:'absolute',bottom:24,left:24,fontSize:28,color:green}}>FRAME {i*20+1}</div></div>)}
    <div style={{position:'absolute',left:100,top:650,width:900,fontSize:38,color:muted,lineHeight:1.4}}>Tính nhất quán nằm ở mối liên hệ<br/>giữa các khung hình.</div>
  </AbsoluteFill>;
  if(index===1)return <AbsoluteFill style={{background:ink}}>
    <Title index={2} title="Đọc chủ thể trong chuyển động" sub="Một mặt nạ phải theo đúng người, kể cả khi hai chủ thể che khuất nhau."/>
    <Panel left={88} title="Cảnh gốc" tag="2 giây · phát chậm 0,5×"><Media name="source" media={media} slow/></Panel>
    <Panel left={982} title="Theo dõi & phân vùng" tag="Mặt nạ theo từng frame"><Media name="overlay" media={media} slow/></Panel>
    <div style={{position:'absolute',left:94,top:830,fontSize:30,color:muted}}>Chọn chủ thể → đọc mặt nạ → sửa vùng bị nhận nhầm</div>
  </AbsoluteFill>;
  if(index===2)return <AbsoluteFill style={{background:ink}}>
    <Title index={3} title="Cùng một cảnh, hai cách lấp nền" sub="Quan sát hoa văn trên chăn và đường nối của tường khi chủ thể chuyển động."/>
    <Panel left={88} title="LaMa · từng frame" tag="Kết quả chạy thật"><Media name="lama" media={media} slow/></Panel>
    <Panel left={982} title="ProPainter · theo thời gian" tag="Kết quả chạy thật"><Media name="temporal" media={media} slow/></Panel>
    <div style={{position:'absolute',left:94,top:830,fontSize:30,color:muted}}>Hai clip cùng nhịp, cùng mặt nạ · không suy ra chất lượng mọi cảnh từ một ví dụ</div>
  </AbsoluteFill>;
  if(index===3)return <AbsoluteFill style={{background:ink}}>
    <Title index={4} title="Dùng cả hình trước và hình sau" sub="Chuyển động nối những phần nền đã thấy với vùng đang bị che."/>
    {[['TRƯỚC',5],['VÙNG ĐANG BỊ CHE',28],['SAU',50]].map(([label,frame],i)=><div key={i} style={{position:'absolute',left:100+i*595,top:345,width:530,height:355}}>
      <div style={{position:'relative',width:530,height:298,borderRadius:20,overflow:'hidden',border:`2px solid ${i===1?green:'#3b5260'}`}}><Media name={i===1?'overlay':'source'} media={media} frozen={frame}/></div>
      <div style={{fontSize:28,color:i===1?green:muted,textAlign:'center',marginTop:24,letterSpacing:2}}>{label}</div>
    </div>)}
    <svg width="1920" height="260" viewBox="0 0 1920 260" style={{position:'absolute',top:590,left:0,pointerEvents:'none'}}>
      <path d="M365 60 Q550 240 960 100 M1555 60 Q1370 240 960 100" fill="none" stroke={green} strokeWidth="4" strokeDasharray="10 8"/>
      {[0,1].map(i=><circle key={i} cx={i===0?365+(f%60)/60*595:1555-(f%60)/60*595} cy={80+Math.sin((f%60)/60*Math.PI)*90} r="8" fill={green}/>)}
    </svg>
    <div style={{position:'absolute',left:450,right:450,top:817,fontSize:34,textAlign:'center',color:green}}>Đọc chuyển động → truyền thông tin nền → tinh chỉnh vùng thiếu</div>
  </AbsoluteFill>;
  if(index===4){const generating=f>=generateFrom;return <AbsoluteFill style={{background:ink}}>
    <Title index={5} title="Từ đọc footage đến tạo cảnh mới" sub="Claude có thể chỉnh footage sẵn có, rồi bổ sung cảnh minh họa bằng mô tả."/>
    <Panel left={88} top={300} width={1120} height={630} title={generating?'Một cảnh thiên nhiên do AI sinh':'Đọc và tinh chỉnh footage có sẵn'} tag={generating?'LTX-Video local':'Mặt nạ → nền → bản dựng'}>
      {generating?<Sequence from={generateFrom}><Media name="generated" media={media}/></Sequence>:<Media name="temporal" media={media} slow/>}
      {generating&&<div style={{position:'absolute',left:24,bottom:24,fontSize:24,background:'#0a1721da',padding:'10px 18px',borderRadius:10}}>CẢNH MINH HỌA DO AI TẠO</div>}
    </Panel>
    <div style={{position:'absolute',left:1280,right:90,top:348}}>
      <div style={{color:green,fontSize:31,letterSpacing:2,marginBottom:30}}>{generating?'Ý TƯỞNG → CHUYỂN ĐỘNG':'ĐỌC → TINH CHỈNH'}</div>
      <div style={{fontSize:49,lineHeight:1.25,fontWeight:600}}>{generating?<>Ánh nắng sớm.<br/>Rừng xanh yên tĩnh.<br/>Lá chuyển động nhẹ.</>:<>Chọn đúng chủ thể.<br/>Giữ nền liên tục.<br/>Giữ lời thuyết minh.</>}</div>
      <div style={{height:1,background:'#33505b',margin:'42px 0'}}/>
      <div style={{fontSize:30,color:muted,lineHeight:1.5}}>Chữ và lời dẫn được dựng riêng để dễ đọc, dễ sửa và đúng nội dung.</div>
    </div>
  </AbsoluteFill>;}
  return <AbsoluteFill style={{background:ink}}>
    <Title index={6} title="Chất lượng nằm ở cả câu chuyện" sub="Xem kết quả trong chuyển động, cùng với lời dẫn và bố cục."/>
    {[["01","Ổn định","Nền và chủ thể nhất quán"],["02","Dễ đọc","Chữ, tương phản, khoảng thở"],["03","Đúng nhịp","Hình đi cùng lời thuyết minh"]].map(([n,title,sub],i)=><div key={n} style={{position:'absolute',left:94+i*590,top:330,width:548,height:340,padding:40,boxSizing:'border-box',borderRadius:24,border:'1px solid #3a5361',background:'#142733',opacity:Math.min(1,Math.max(0,(f-i*20)/18))}}>
      <div style={{fontSize:30,color:green,marginBottom:42}}>{n}</div><div style={{fontSize:65,fontWeight:700,letterSpacing:-1,marginBottom:24}}>{title}</div><div style={{fontSize:29,lineHeight:1.4,color:muted}}>{sub}</div>
    </div>)}
    <div style={{position:'absolute',left:96,right:96,top:755,fontSize:46,color:green,lineHeight:1.3}}>AI có công cụ mạnh.<br/>Nội dung tốt vẫn cần lựa chọn có chủ đích.</div>
  </AbsoluteFill>;
};

export const AgentVideo=({timeline,config,media}:Props)=>{
  const f=useCurrentFrame();const cue=timeline.cues.find((c:any)=>f>=Math.ceil(c.start*30)&&f<Math.ceil(c.end*30));
  return <AbsoluteFill style={{background:ink,color:white,fontFamily:'Segoe UI, sans-serif'}}>
    {bounds.slice(0,-1).map((b,i)=><Sequence key={i} from={b} durationInFrames={bounds[i+1]-b}><Scene index={i} media={media} duration={bounds[i+1]-b}/></Sequence>)}
    {cue&&<div style={{position:'absolute',left:160,right:160,bottom:39,textAlign:'center',fontSize:44,fontWeight:600,lineHeight:1.32,zIndex:10}}><span style={{background:'#08151eef',padding:'9px 18px',boxDecorationBreak:'clone',borderRadius:8}}>{cue.text}</span></div>}
    <div style={{position:'absolute',bottom:0,left:0,height:5,width:`${f/timeline.total_frames*100}%`,background:green}}/>
  </AbsoluteFill>;
};
const Root=()=> <Composition id="AgentVideo" component={AgentVideo} durationInFrames={30} fps={30} width={1920} height={1080} defaultProps={{timeline:{total_frames:30,cues:[]},config:{},media:{}}} calculateMetadata={({props})=>({durationInFrames:props.timeline.total_frames,width:props.timeline.width,height:props.timeline.height,fps:props.timeline.fps})}/>;
registerRoot(Root);
