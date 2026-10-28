"""Create a Vietnamese knowledge-video fixture with local diagrams, then render it."""
import argparse
import sys
import uuid
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from PIL import Image, ImageDraw
from editvideo import store
from editvideo.graphics import font, wrap
from editvideo.models import ProjectInput
from editvideo.media import register, FFMPEG, command
from editvideo.jobs import Worker

SCRIPT = ("Một chiếc lá nhỏ có thể làm một việc đáng kinh ngạc: biến ánh sáng thành năng lượng.\n"
          "Trong quá trình quang hợp, cây sử dụng ánh sáng, nước và khí các-bô-níc để tạo ra chất hữu cơ.\n"
          "Ô-xy được giải phóng như một sản phẩm của quá trình ấy.\n"
          "Vì vậy, bảo vệ cây xanh cũng là chăm sóc môi trường sống của chúng ta.")


def diagram(path,kind):
    w,h=1080,1920
    im=Image.new("RGB",(w,h),"#122421");d=ImageDraw.Draw(im)
    for y in range(h):
        p=y/h;d.line((0,y,w,y),fill=(round(18+7*p),round(36+18*p),round(33+7*p)))
    small=font(28,True);heading=font(74,True);body=font(36)
    d.text((90,160),"KHOA HỌC  /  TỪ NHỮNG ĐIỀU NHỎ",font=small,fill="#b6e981")
    titles={"leaf":"Sức mạnh của\nmột chiếc lá","energy":"Ánh sáng →\nnăng lượng","oxygen":"Một quá trình.\nNhiều sự sống."}
    d.multiline_text((90,260),titles[kind],font=heading,fill="#eff2dd",spacing=22)
    # Schematic leaf: explicit illustration, no claim to be photographic evidence.
    d.ellipse((230,720,880,1280),fill="#406e44",outline="#95bf6c",width=3)
    d.ellipse((280,750,800,1260),fill="#5c8c4f")
    d.line((240,1280,805,795),fill="#bdd89a",width=11)
    for t in range(1,6):
        x=240+t*88;y=1280-t*75
        d.line((x,y,x-80,y-150),fill="#99bd73",width=5)
        d.line((x,y,x+140,y+20),fill="#99bd73",width=5)
    if kind=="energy":
        d.ellipse((765,560,960,755),fill="#e6bf60")
        for a,b in [((803,724),(714,840)),((869,733),(789,852)),((928,705),(859,826))]:
            d.line((*a,*b),fill="#e6bf60",width=7)
        d.rounded_rectangle((85,1310,995,1470),radius=22,fill="#253d32",outline="#607951",width=2)
        d.text((122,1340),"ÁNH SÁNG + NƯỚC + CO₂",font=font(36,True),fill="#e7efcc")
        d.text((122,1400),"→ CHẤT HỮU CƠ + O₂",font=font(36,True),fill="#c5ed8b")
    elif kind=="oxygen":
        for x,y,r in [(755,640,72),(900,810,54),(853,1040,39)]:
            d.ellipse((x-r,y-r,x+r,y+r),fill="#355954",outline="#8dcebd",width=3)
            d.text((x-r*.6,y-r*.5),"O₂",font=font(int(r*.75),True),fill="#d4eee2")
        d.text((90,1370),"CÂY XANH · MÔI TRƯỜNG SỐNG",font=font(34,True),fill="#b6e981")
    else:
        d.text((90,1370),"NHỎ BÉ, NHƯNG KHÔNG TẦM THƯỜNG.",font=font(31,True),fill="#b6e981")
    d.text((90,1640),"Sơ đồ minh họa · Quang hợp",font=body,fill="#819c88")
    im.save(path)


def create_demo():
    project=store.create_project(ProjectInput(title="Sức mạnh của một chiếc lá",script=SCRIPT,voice_rate=-5).model_dump())
    pid=project["id"];assets=store.folder(pid)/"assets";assets.mkdir(exist_ok=True)
    for kind,tags in [("leaf","chiếc lá nhỏ cây xanh bảo vệ môi trường sống"),
                      ("energy","quang hợp ánh sáng năng lượng nước khí các-bô-níc chất hữu cơ"),
                      ("oxygen","ô-xy giải phóng sản phẩm quá trình sự sống")]:
        path=assets/(str(uuid.uuid4())+".png");diagram(path,kind)
        register(pid,path,f"Sơ đồ {kind}",tags,role="illustration")
    music=assets/(str(uuid.uuid4())+".wav")
    # Quiet original synthesized pad; no external music or stock needed.
    command([FFMPEG,"-y","-v","error","-f","lavfi","-i",
             "aevalsrc=0.12*sin(2*PI*130.81*t)+0.05*sin(2*PI*196*t)+0.03*sin(2*PI*261.63*t):s=48000:d=45",
             "-af","lowpass=f=700,afade=t=in:d=3,afade=t=out:st=41:d=4",music])
    a=register(pid,music,"Nhạc nền mẫu · hợp âm tổng hợp","nhạc nền",role="decoration")
    c=store.get_project(pid)["config"];c["music_id"]=a["id"];c["music_volume"]=.08
    store.update_project(pid,c)
    return pid


if __name__=="__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser();parser.add_argument("--render",action="store_true");parser.add_argument("--project")
    args=parser.parse_args()
    # Do not initialize while the server is processing jobs: this would mark them interrupted.
    if not (store.DATA/"studio.db").exists():store.initialize()
    pid=args.project or create_demo()
    print("Project:",pid,flush=True)
    if args.render:
        worker=Worker()
        for kind in ("plan","preview","final"):
            job=store.create_job(pid,kind);worker.run(job["id"])
            done=store.get_job(job["id"]);print(kind,done["state"],done["error"] or "",flush=True)
            if done["state"]!="completed":raise SystemExit(1)
        print("Output:",store.folder(pid)/"jobs"/job["id"]/"final.mp4",flush=True)
