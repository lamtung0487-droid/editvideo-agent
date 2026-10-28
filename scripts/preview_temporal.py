"""Contact sheet from actual decoded source and completed inpainting task frames."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw,ImageFont
from editvideo import media_tasks,store

def main():
    lama=media_tasks.get('19660503-4930-447b-afe9-23fefaf5ca3a')
    temporal=media_tasks.get('fe6af504-2de7-49f3-a5e8-d2e38d153f1c')
    assert lama['state']==temporal['state']=='completed'
    baseline='LaMa framewise' if not lama['request']['temporal_strength'] else 'LaMa + post flow blend'
    rows=[('Source',media_tasks.folder(temporal['id'])/'source-frames'),
          (baseline,Path(lama['result']['frames_directory'])),
          ('ProPainter bidirectional',Path(temporal['result']['frames_directory']))]
    canvas=Image.new('RGB',(1280,648),'#18212b');draw=ImageDraw.Draw(canvas)
    font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',20)
    for row,(label,folder) in enumerate(rows):
        draw.text((12,row*216+8),label,fill='#f3f7fb',font=font)
        for col,frame in enumerate((5,20,35,50)):
            image=Image.open(folder/f'{frame:06d}.png').convert('RGB').resize((320,180),Image.Resampling.LANCZOS)
            canvas.paste(image,(col*320,row*216+36))
    canvas.save(store.ROOT/'outputs/temporal-comparison.jpg',quality=93)

if __name__=='__main__':main()
