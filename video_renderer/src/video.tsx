import React from 'react';
import {AbsoluteFill, Img, Sequence, interpolate, staticFile, useCurrentFrame} from 'remotion';
import type {CSSProperties} from 'react';
import type {InfographicPage, InfographicVideoProps, TimedCue} from './types';

type Palette = {paper:string;ink:string;muted:string;accent:string;second:string;line:string};
type NodeVariant = 'numbered' | 'tag' | 'evidence' | 'checkpoint' | 'plain';

const palette = (style:string):Palette => {
  if (style === '黑金科技发布会风') return {paper:'#18191c',ink:'#efe8d3',muted:'#aca99e',accent:'#d8ae54',second:'#8f7b50',line:'#5f584b'};
  if (style === '赛博霓虹漫画风') return {paper:'#18191c',ink:'#efe8d3',muted:'#aca99e',accent:'#31e2dc',second:'#b14d97',line:'#5f584b'};
  if (style === '爆款高热吸睛风') return {paper:'#fce042',ink:'#23201d',muted:'#5b3d2d',accent:'#e5412a',second:'#235bb2',line:'#5b3d2d'};
  if (style === '极简商务涂鸦风') return {paper:'#f4f7f6',ink:'#1f3542',muted:'#5d6f71',accent:'#2268aa',second:'#268974',line:'#adbcbb'};
  if (style === '极简粗线简笔白板风') return {paper:'#fdfcf8',ink:'#232321',muted:'#696860',accent:'#e1662f',second:'#315cb2',line:'#c6c3b8'};
  if (style === '粗线扁平国风卡通') return {paper:'#f7eedb',ink:'#373028',muted:'#695b4d',accent:'#b13e2b',second:'#356754',line:'#c2ab8b'};
  if (style === '清新治愈手账风') return {paper:'#fcf7eb',ink:'#434841',muted:'#737769',accent:'#d6796f',second:'#6f916f',line:'#cdc2ae'};
  if (style === '复古报纸拼贴风') return {paper:'#e5d9c2',ink:'#2b2823',muted:'#5d5448',accent:'#9d3127',second:'#3e3c35',line:'#9b8b71'};
  if (style === '漫画墨线解释风') return {paper:'#f4efe5',ink:'#24231f',muted:'#6e6a61',accent:'#cf693e',second:'#4f7895',line:'#b9b1a3'};
  if (style === '3D黏土趣味风') return {paper:'#faefd7',ink:'#413932',muted:'#74665a',accent:'#de684c',second:'#359187',line:'#cdb591'};
  return {paper:'#f6f1e5',ink:'#2b302f',muted:'#65635b',accent:'#b14434',second:'#31484e',line:'#beb5a3'};
};

const progressAt = (frame:number,start:number,duration=11) => interpolate(frame,[start,start+duration],[0,1],{extrapolateLeft:'clamp',extrapolateRight:'clamp'});
const cueFor = (page:InfographicPage,id:string):TimedCue|undefined => page.cues.find((cue)=>cue.enterIds.includes(id));
const activeCue = (page:InfographicPage,frame:number):TimedCue|undefined => page.cues.filter((cue)=>frame>=cue.startFrame).at(-1);
const nodeIndex = (id:string) => Number(id.replace('node-','')) - 1;
const characterCount = (text:string) => Array.from(text).length;
const textColumnWidth = (page:InfographicPage) => {
  const longest = Math.max(1,...page.nodes.map(characterCount));
  return Math.min(620,Math.max(300,130+longest*30));
};

const elementMotion = (page:InfographicPage,id:string,frame:number):CSSProperties => {
  const cue = cueFor(page,id);
  if (!cue) return {opacity:0};
  const progress = progressAt(frame,cue.startFrame);
  const focused = activeCue(page,frame)?.focusId === id;
  let x = 0;
  let y = (1-progress)*18;
  let scale = 0.96 + progress*0.04;
  let rotate = 0;
  if (page.layoutType === 'comparison' && id.startsWith('node-')) {
    x = (1-progress) * (nodeIndex(id) < Math.ceil(page.nodes.length/2) ? -46 : 46);
    y = 0;
  } else if (['path','flow','cause','timeline'].includes(page.layoutType) && id.startsWith('node-')) {
    y = (1-progress)*28;
    scale = 0.72 + progress*0.28;
  } else if (page.layoutType === 'layers' && id.startsWith('node-')) {
    x = (1-progress)*-34;
    y = 0;
  } else if (page.layoutType === 'cycle' && id.startsWith('node-')) {
    scale = 0.68 + progress*0.32;
    rotate = (1-progress)*(nodeIndex(id)%2 ? 5 : -5);
    y = 0;
  } else if (page.layoutType === 'question') {
    scale = 0.84 + progress*0.16;
    y = 0;
  } else if (id === 'illustration') {
    scale = 0.9 + progress*0.1;
    y = (1-progress)*12;
  }
  return {
    opacity: progress*(focused ? 1 : 0.9),
    transform:`translate(${x}px, ${y}px) scale(${focused ? scale*1.035 : scale}) rotate(${rotate}deg)`,
    filter:focused?'none':'saturate(0.94)',
  };
};

const Header:React.FC<{page:InfographicPage;frame:number;colors:Palette}> = ({page,frame,colors}) => {
  const first = page.cues[0]?.startFrame ?? 0;
  const seriesOpacity = page.seriesPersistent ? 1 : progressAt(frame,first,8);
  const chapterOpacity = page.chapterPersistent ? 1 : progressAt(frame,first,8);
  return <>
    <div style={{position:'absolute',left:58,top:48,width:9,height:62,background:colors.accent}}/>
    <div style={{position:'absolute',left:94,top:43,right:94,fontFamily:'Microsoft YaHei, Noto Sans SC, sans-serif',fontSize:43,fontWeight:750,color:colors.ink,opacity:seriesOpacity}}>{page.seriesTitle}</div>
    <div style={{position:'absolute',left:58,right:58,top:128,height:2,background:colors.line}}/>
    <div style={{position:'absolute',left:118,right:118,top:151,textAlign:'center',fontFamily:'SimSun, Noto Serif SC, serif',fontSize:29,fontWeight:700,color:colors.ink,opacity:chapterOpacity}}>{page.chapterTitle}</div>
  </>;
};

const Art:React.FC<{page:InfographicPage;frame:number;style?:CSSProperties}> = ({page,frame,style}) => <div style={{...elementMotion(page,'illustration',frame),width:'100%',height:'100%',minWidth:0,minHeight:0,overflow:'hidden',display:'flex',alignItems:'center',justifyContent:'center',...style}}>
  <Img src={staticFile(page.image)} style={{width:'100%',height:'100%',objectFit:'contain',WebkitMaskImage:'radial-gradient(ellipse 80% 78% at center,#000 58%,transparent 100%)',maskImage:'radial-gradient(ellipse 80% 78% at center,#000 58%,transparent 100%)'}}/>
</div>;

const Node:React.FC<{page:InfographicPage;frame:number;text:string;index:number;colors:Palette;variant?:NodeVariant;align?:CSSProperties['textAlign']}> = ({page,frame,text,index,colors,variant='numbered',align='left'}) => {
  const motion = elementMotion(page,`node-${index+1}`,frame);
  if (variant === 'tag') return <div style={{...motion,display:'inline-flex',width:'fit-content',maxWidth:'100%',alignItems:'center',justifyContent:'center',padding:'15px 25px',border:`2px solid ${index%2?colors.second:colors.accent}`,color:index%2?colors.second:colors.accent,fontFamily:'Microsoft YaHei, Noto Sans SC, sans-serif',fontSize:29,fontWeight:750,lineHeight:1.25,background:`${colors.paper}dd`}}>{text}</div>;
  if (variant === 'checkpoint') return <div style={{...motion,display:'flex',flexDirection:'column',alignItems:'center',gap:13,minWidth:0}}>
    <span style={{width:28,height:28,borderRadius:'50%',background:index%2?colors.second:colors.accent,border:`6px solid ${colors.paper}`,boxShadow:`0 0 0 2px ${colors.line}`}}/>
    <div style={{fontFamily:'Microsoft YaHei, Noto Sans SC, sans-serif',fontSize:27,fontWeight:750,lineHeight:1.25,textAlign:'center',color:colors.ink,maxWidth:240}}>{text}</div>
  </div>;
  if (variant === 'evidence') return <div style={{...motion,display:'inline-grid',width:Math.min(540,Math.max(250,105+characterCount(text)*30)),maxWidth:'100%',gridTemplateColumns:'12px 1fr',gap:17,alignItems:'stretch',padding:'13px 18px',borderTop:`1px solid ${colors.line}`,borderBottom:`1px solid ${colors.line}`,background:`${colors.paper}b8`}}>
    <span style={{background:index%2?colors.second:colors.accent}}/>
    <div style={{fontFamily:'Microsoft YaHei, Noto Sans SC, sans-serif',fontSize:30,fontWeight:700,lineHeight:1.35,color:colors.ink}}>{text}</div>
  </div>;
  if (variant === 'plain') return <div style={{...motion,fontFamily:'SimSun, Noto Serif SC, serif',fontSize:35,fontWeight:700,lineHeight:1.35,textAlign:align,color:colors.ink,borderBottom:`2px solid ${colors.line}`,padding:'0 8px 10px'}}>{text}</div>;
  return <div style={{...motion,display:'flex',width:'fit-content',maxWidth:'100%',alignItems:'flex-start',gap:16,minWidth:0}}>
    <span style={{flex:'0 0 auto',width:35,height:35,borderRadius:'50%',background:index%2?colors.second:colors.accent,color:colors.paper,fontFamily:'Arial',fontSize:18,fontWeight:700,lineHeight:'35px',textAlign:'center'}}>{index+1}</span>
    <div style={{minWidth:0,textAlign:align,fontFamily:'Microsoft YaHei, Noto Sans SC, sans-serif',fontSize:32,fontWeight:700,lineHeight:1.35,color:colors.ink,borderBottom:`2px solid ${colors.line}`,paddingBottom:10}}>{text}</div>
  </div>;
};

const SplitLayout:React.FC<{page:InfographicPage;frame:number;colors:Palette;variant?:NodeVariant}> = ({page,frame,colors,variant='numbered'}) => {
  const artFirst = page.composition === 'split-left';
  const topBottom = page.composition === 'top-bottom';
  const columnWidth = textColumnWidth(page);
  const nodes = <div style={{display:'flex',flexDirection:'column',alignItems:'flex-start',gap:22,justifyContent:'center',minWidth:0}}>{page.nodes.map((text,index)=><Node key={`${text}-${index}`} page={page} frame={frame} text={text} index={index} colors={colors} variant={variant}/>)}</div>;
  const art = <Art page={page} frame={frame}/>;
  if (topBottom) return <div style={{display:'grid',gridTemplateRows:'1.15fr .85fr',gap:22,height:'100%',minHeight:0}}>{art}<div style={{display:'grid',gridTemplateColumns:`repeat(${Math.min(3,page.nodes.length)},1fr)`,gap:24,alignItems:'center'}}>{page.nodes.map((text,index)=><Node key={`${text}-${index}`} page={page} frame={frame} text={text} index={index} colors={colors} variant="tag" align="center"/>)}</div></div>;
  return <div style={{display:'grid',gridTemplateColumns:artFirst?`minmax(0,1fr) ${columnWidth}px`:`${columnWidth}px minmax(0,1fr)`,gap:48,height:'100%',minHeight:0,alignItems:'center'}}>{artFirst?<>{art}{nodes}</>:<>{nodes}{art}</>}</div>;
};

const OverviewLayout:React.FC<{page:InfographicPage;frame:number;colors:Palette}> = ({page,frame,colors}) => <SplitLayout page={page} frame={frame} colors={colors}/>;

const QuestionLayout:React.FC<{page:InfographicPage;frame:number;colors:Palette}> = ({page,frame,colors}) => <div style={{height:'100%',display:'grid',gridTemplateColumns:'1fr 1.15fr',gap:40,alignItems:'center'}}>
  <div style={{display:'flex',flexWrap:'wrap',gap:18,justifyContent:'center',alignContent:'center'}}>{page.nodes.map((text,index)=><Node key={`${text}-${index}`} page={page} frame={frame} text={text} index={index} colors={colors} variant="tag"/>)}</div>
  <Art page={page} frame={frame}/>
</div>;

const PrincipleLayout:React.FC<{page:InfographicPage;frame:number;colors:Palette}> = ({page,frame,colors}) => <div style={{position:'relative',height:'100%',display:'grid',placeItems:'center'}}>
  <Art page={page} frame={frame} style={{position:'absolute',inset:'5% 25%',width:'50%',height:'90%',opacity:0.34}}/>
  <div style={{position:'relative',zIndex:2,width:'100%',display:'grid',gridTemplateColumns:`repeat(${Math.min(3,page.nodes.length)},1fr)`,gap:38,alignItems:'center'}}>{page.nodes.map((text,index)=><Node key={`${text}-${index}`} page={page} frame={frame} text={text} index={index} colors={colors} variant="tag" align="center"/>)}</div>
</div>;

const ComparisonLayout:React.FC<{page:InfographicPage;frame:number;colors:Palette}> = ({page,frame,colors}) => {
  const split = Math.ceil(page.nodes.length/2);
  return <div style={{position:'relative',height:'100%',display:'grid',gridTemplateColumns:'1fr 2px 1fr',gap:46,alignItems:'stretch'}}>
    <div style={{display:'flex',flexDirection:'column',justifyContent:'center',gap:25,padding:'22px 30px',borderTop:`5px solid ${colors.second}`,background:`${colors.second}0d`}}>{page.nodes.slice(0,split).map((text,index)=><Node key={`${text}-${index}`} page={page} frame={frame} text={text} index={index} colors={colors} variant="evidence"/>)}</div>
    <div style={{background:colors.line}}/>
    <div style={{display:'flex',flexDirection:'column',justifyContent:'center',gap:25,padding:'22px 30px',borderTop:`5px solid ${colors.accent}`,background:`${colors.accent}0d`}}>{page.nodes.slice(split).map((text,index)=>{const actual=index+split;return <Node key={`${text}-${actual}`} page={page} frame={frame} text={text} index={actual} colors={colors} variant="evidence"/>;})}</div>
    <Art page={page} frame={frame} style={{position:'absolute',left:'35%',right:'35%',top:'18%',bottom:'18%',width:'30%',height:'64%',opacity:0.2}}/>
  </div>;
};

const EvidenceLayout:React.FC<{page:InfographicPage;frame:number;colors:Palette}> = ({page,frame,colors}) => <SplitLayout page={page} frame={frame} colors={colors} variant="evidence"/>;

const LayersLayout:React.FC<{page:InfographicPage;frame:number;colors:Palette}> = ({page,frame,colors}) => <div style={{height:'100%',display:'grid',gridTemplateColumns:`${Math.min(650,textColumnWidth(page)+90)}px minmax(0,1fr)`,gap:42,alignItems:'center'}}>
  <div style={{display:'flex',flexDirection:'column-reverse',alignItems:'flex-start',gap:13,justifyContent:'center'}}>{page.nodes.map((text,index)=><div key={`${text}-${index}`} style={{marginLeft:`${index*24}px`,padding:'2px 0',maxWidth:'100%'}}><Node page={page} frame={frame} text={text} index={index} colors={colors} variant="evidence"/></div>)}</div>
  <Art page={page} frame={frame}/>
</div>;

const CaseLayout:React.FC<{page:InfographicPage;frame:number;colors:Palette}> = ({page,frame,colors}) => <div style={{height:'100%',display:'grid',gridTemplateRows:'1.35fr .65fr',gap:16,minHeight:0}}>
  <Art page={page} frame={frame}/>
  <div style={{display:'grid',gridTemplateColumns:`repeat(${Math.min(4,page.nodes.length)},1fr)`,gap:22,alignItems:'center'}}>{page.nodes.map((text,index)=><Node key={`${text}-${index}`} page={page} frame={frame} text={text} index={index} colors={colors} variant="evidence" align="center"/>)}</div>
</div>;

const PathLayout:React.FC<{page:InfographicPage;frame:number;colors:Palette}> = ({page,frame,colors}) => {
  const directional = page.relationshipType === 'sequence' || page.relationshipType === 'cause';
  return <div style={{height:'100%',display:'grid',gridTemplateRows:'1.05fr .95fr',gap:10,minHeight:0}}>
    <Art page={page} frame={frame}/>
    <div style={{position:'relative',display:'grid',gridTemplateColumns:`repeat(${page.nodes.length},1fr)`,gap:26,alignItems:'start',paddingTop:15}}>
      <div style={{position:'absolute',left:'7%',right:'7%',top:29,height:3,background:colors.line}}/>
      {page.nodes.map((text,index)=><div key={`${text}-${index}`} style={{position:'relative'}}>
        <Node page={page} frame={frame} text={text} index={index} colors={colors} variant="checkpoint" align="center"/>
        {directional && index<page.nodes.length-1?<span style={{position:'absolute',right:-18,top:20,width:0,height:0,borderTop:'8px solid transparent',borderBottom:'8px solid transparent',borderLeft:`12px solid ${colors.second}`,opacity:elementMotion(page,`node-${index+2}`,frame).opacity as number}}/>:null}
      </div>)}
    </div>
  </div>;
};

const CycleLayout:React.FC<{page:InfographicPage;frame:number;colors:Palette}> = ({page,frame,colors}) => {
  const positions = [{left:'4%',top:'8%'},{right:'4%',top:'8%'},{right:'3%',bottom:'7%'},{left:'3%',bottom:'7%'},{left:'39%',top:'2%'}];
  return <div style={{position:'relative',height:'100%'}}>
    <Art page={page} frame={frame} style={{position:'absolute',left:'29%',right:'29%',top:'13%',bottom:'13%',width:'42%',height:'74%'}}/>
    {page.nodes.map((text,index)=><div key={`${text}-${index}`} style={{position:'absolute',width:'29%',...(positions[index%positions.length] as CSSProperties)}}><Node page={page} frame={frame} text={text} index={index} colors={colors} variant="tag" align="center"/></div>)}
  </div>;
};

const SummaryLayout:React.FC<{page:InfographicPage;frame:number;colors:Palette}> = ({page,frame,colors}) => <SplitLayout page={page} frame={frame} colors={colors} variant="numbered"/>;

const Layout:React.FC<{page:InfographicPage;frame:number;colors:Palette}> = ({page,frame,colors}) => {
  switch (page.layoutType) {
    case 'overview': return <OverviewLayout page={page} frame={frame} colors={colors}/>;
    case 'question': return <QuestionLayout page={page} frame={frame} colors={colors}/>;
    case 'principle': return <PrincipleLayout page={page} frame={frame} colors={colors}/>;
    case 'comparison': return <ComparisonLayout page={page} frame={frame} colors={colors}/>;
    case 'evidence': return <EvidenceLayout page={page} frame={frame} colors={colors}/>;
    case 'layers': return <LayersLayout page={page} frame={frame} colors={colors}/>;
    case 'case': return <CaseLayout page={page} frame={frame} colors={colors}/>;
    case 'path': case 'flow': case 'cause': case 'timeline': return <PathLayout page={page} frame={frame} colors={colors}/>;
    case 'cycle': return <CycleLayout page={page} frame={frame} colors={colors}/>;
    case 'summary': return <SummaryLayout page={page} frame={frame} colors={colors}/>;
    default: return <SplitLayout page={page} frame={frame} colors={colors} variant="tag"/>;
  }
};

const Page:React.FC<{page:InfographicPage;style:string;subtitlesEnabled:boolean}> = ({page,style,subtitlesEnabled}) => {
  const frame = useCurrentFrame();
  const colors = palette(style);
  const oilVisual = style === '漫画墨线解释风';
  const titleSize = page.layoutType === 'question' ? 68 : page.layoutType === 'principle' ? 60 : 54;
  return <AbsoluteFill style={{backgroundColor:colors.paper,color:colors.ink,overflow:'hidden'}}>
    <div style={oilVisual?{position:'absolute',inset:0,backgroundImage:`radial-gradient(circle,${colors.ink} 0 1px,transparent 1.15px)`,backgroundSize:'11px 11px',opacity:0.08,WebkitMaskImage:'linear-gradient(125deg,#000 0 18%,transparent 42% 63%,#000 88%)',maskImage:'linear-gradient(125deg,#000 0 18%,transparent 42% 63%,#000 88%)'}:{position:'absolute',inset:0,background:`radial-gradient(circle at 22% 76%,${colors.line}22,transparent 27%),radial-gradient(circle at 82% 18%,${colors.second}12,transparent 23%)`}}/>
    <Header page={page} frame={frame} colors={colors}/>
    <div style={{position:'absolute',left:112,right:112,top:215,bottom:page.conclusion?(subtitlesEnabled?205:142):(subtitlesEnabled?132:76),display:'flex',flexDirection:'column',gap:24,minHeight:0}}>
      <div style={{...elementMotion(page,'page-title',frame),fontFamily:'SimSun, Noto Serif SC, serif',fontSize:titleSize,fontWeight:750,lineHeight:1.18,textAlign:'center',color:colors.accent,maxWidth:1540,alignSelf:'center'}}>{page.pageTitle}</div>
      <div style={{flex:1,minHeight:0}}><Layout page={page} frame={frame} colors={colors}/></div>
    </div>
    {page.conclusion?<div style={{...elementMotion(page,'conclusion',frame),position:'absolute',left:160,right:160,bottom:subtitlesEnabled?128:58,textAlign:'center',fontFamily:'SimSun, Noto Serif SC, serif',fontSize:33,fontWeight:750,color:colors.accent,borderTop:`1px solid ${colors.line}`,paddingTop:17}}>{page.conclusion}</div>:null}
  </AbsoluteFill>;
};

export const InfographicVideo:React.FC<InfographicVideoProps> = ({pages,style,subtitlesEnabled=false}) => <AbsoluteFill>
  {pages.map((page)=><Sequence key={page.id} from={page.startFrame} durationInFrames={Math.max(1,page.endFrame-page.startFrame)} layout="none">
    <Page page={{...page,composition:page.composition||'split-right',cues:page.cues.map((cue)=>({...cue,startFrame:cue.startFrame-page.startFrame,endFrame:cue.endFrame-page.startFrame}))}} style={style} subtitlesEnabled={subtitlesEnabled}/>
  </Sequence>)}
</AbsoluteFill>;
