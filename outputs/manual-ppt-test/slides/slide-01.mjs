export async function slide01(presentation, ctx) {
  const slide = presentation.slides.add();
  slide.background.fill = {type:'solid', color:'#F8FAFC'};
  const bg = slide.shapes.add({ geometry:'rect', position:{left:0, top:0, width:1280, height:720}, fill:{type:'solid', color:'#F8FAFC'}, line:{fill:{type:'none'}, width:0} });
  bg.sendToBack();
  const t = slide.shapes.add({ geometry:'rect', position:{left:80, top:100, width:900, height:120}, fill:{type:'none'}, line:{fill:{type:'none'}, width:0} });
  t.text.style = {fontSize:52, typeface:'PingFang SC', color:'#0F172A', bold:true, verticalAlignment:'middle'};
  t.text = '明鉴 MingJian';
  const c = slide.shapes.add({ geometry:'roundRect', position:{left:80, top:260, width:300, height:120}, fill:{type:'solid', color:'#DFF7F0'}, line:{fill:'#10B981', width:2} });
  c.text.style = {fontSize:24, typeface:'PingFang SC', color:'#064E3B', bold:true, alignment:'center', verticalAlignment:'middle'};
  c.text = '证据驱动';
  return slide;
}
