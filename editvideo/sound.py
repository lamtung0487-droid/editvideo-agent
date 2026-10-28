"""Local sound-event evidence and deterministic procedural editorial accents."""
import json
import math
import re
import uuid
import wave
from pathlib import Path
import numpy as np
from . import store
from .media import FFMPEG,command,probe,sha256


def read_events(path,start=0,end=None,max_events=24):
    source=Path(path).resolve(strict=True);info=probe(source)
    duration=float(info['format'].get('duration',0));end=min(duration,start+30) if end is None else end
    if not any(s['codec_type']=='audio' for s in info['streams']) or not all(math.isfinite(v) for v in (start,end)) or not 0<=start<end<=duration+.001 or end-start>120 or not 1<=max_events<=60:
        raise ValueError('Audio window within media <=120s; max_events1..60')
    out=store.DATA/'audio-events'/str(uuid.uuid4());out.mkdir(parents=True)
    audio=out/'listen.wav'
    command([FFMPEG,'-y','-v','error','-ss',start,'-i',source,'-t',end-start,'-vn','-ar',16000,'-ac',1,'-c:a','pcm_s16le',audio],timeout=120)
    with wave.open(str(audio)) as wav:
        x=np.frombuffer(wav.readframes(wav.getnframes()),dtype='<i2').astype(np.float32)/32768
    hop=320;size=640;n=max(1,(len(x)-size)//hop+1)
    rms=[];flux=[];previous=None
    for i in range(n):
        window=x[i*hop:i*hop+size]
        if len(window)<size:window=np.pad(window,(0,size-len(window)))
        rms.append(float(np.sqrt(np.mean(window**2))))
        spectrum=np.abs(np.fft.rfft(window*np.hanning(size)))
        flux.append(0. if previous is None else float(np.maximum(spectrum-previous,0).mean()));previous=spectrum
    times=start+np.arange(n)*hop/16000
    threshold=float(np.median(flux)+2*np.median(np.abs(flux-np.median(flux))))
    candidates=[i for i in range(1,n-1) if flux[i]>max(threshold,1e-5) and flux[i]>=flux[i-1] and flux[i]>flux[i+1] and rms[i]>.003]
    selected=[]
    for i in sorted(candidates,key=lambda i:flux[i],reverse=True):
        if all(abs(i-j)>=5 for j in selected):selected.append(i)
        if len(selected)>=max_events:break
    events=[{'timestamp':round(float(times[i]+.02),4),'spectral_flux':round(flux[i],5),'rms_dbfs':round(20*math.log10(max(rms[i],1e-9)),3)} for i in sorted(selected)]
    intervals=[];opened=None
    for i,r in enumerate(rms+[1.]):
        if r<.005 and opened is None:opened=i
        if r>=.005 and opened is not None:
            if (i-opened)*.02>=.3:intervals.append({'start':round(start+opened*.02,4),'end':round(min(end,start+i*.02+.04),4)})
            opened=None
    raw=command([FFMPEG,'-v','info','-ss',start,'-i',source,'-t',end-start,'-vn','-af','loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json','-f','null','-'],timeout=180)
    match=re.search(r'\{\s*"input_i".*?\}',raw,re.S);measurements=json.loads(match.group()) if match else {}
    metrics={k:float(measurements[k]) if k in measurements and math.isfinite(float(measurements[k])) else None for k in ('input_i','input_tp','input_lra')}
    result={'source':str(source),'source_sha256':sha256(source),'window':[start,end],'audio':str(audio),'events':events,'quiet_intervals':intervals,
            'loudness':{'integrated_lufs':metrics['input_i'],'true_peak_dbfs':metrics['input_tp'],'range_lu':metrics['input_lra'],'method':'FFmpeg loudnorm input measurement on selected original channels'},
            'limitations':'Spectral flux finds acoustic change, not semantic meaning, beats or BPM. Quiet intervals include intentional pauses/background and are not deletion instructions. 20ms hop/40ms window estimates, mono/downsampled for events; loudness uses source channels. Listen before cutting dialogue. Silence loudness is null.',
            'manifest':str(out/'audio-events.json')}
    store.write_json(out/'audio-events.json',result);return result


# ---- the literal layer of silent archive (reports/Nâng cấp 3D phim tài liệu.md: Ribicoff's four layers): what the
# picture shows, synthesized so a 1965 reel without sound still has its helicopter, its guns, its sea and its crowd

def _helicopter(t,rng,white,duration):
    """A Huey: two-blade rotor slap at about 10.8 Hz (324 rpm), each pass a band of noise with a low thump; a turbine
    whine above; rotor wash below; the slap breathes with the blade angle (seeded slow modulation)."""
    n=len(t);sig=_band(white,40,700)*.35;rate=rng.uniform(10.2,11.2);k_=max(3,int(duration));slow=np.interp(t,np.linspace(0,duration,k_),rng.uniform(.75,1,k_))
    L=int(.07*48000);tl=np.arange(L)/48000
    for k in range(int(duration*rate)):
     at=k/rate+rng.normal(0,.002);i=int(at*48000);m=min(L,n-i)
     if m<=0 or i<0:continue
     w=(_band(rng.normal(0,1,L),180,1400)*np.exp(-tl/.018)*.9+np.sin(2*np.pi*72*tl)*np.exp(-tl/.03))*slow[i]
     sig[i:i+m]+=w[:m]
    sig+=.05*np.sin(2*np.pi*np.cumsum(2150+20*np.sin(2*np.pi*.3*t))/48000)
    return sig


def _jet(t,rng,white,duration):
    """A jet passing: broadband roar whose band sweeps down as it goes by (Doppler), a low rumble, loudest at the
    middle of the clip."""
    p=t/duration;env=np.sin(np.pi*np.clip(p,0,1))**3;n=len(t);sig=np.zeros(n);seg=4800
    for i in range(0,n,seg):
     c=3200-2500*p[min(i,n-1)];part=_band(white[i:i+seg],c*.5,c*1.5);sig[i:i+len(part)]=part
    return (sig*.8+_band(rng.normal(0,1,n),30,180)*.9)*(.08+env)


def _artillery(t,rng,white,duration):
    """A gun heard across a valley: a crack, a low boom that sags in pitch, then the roll of its echo off the hills."""
    n=len(t);boom=np.sin(2*np.pi*np.cumsum(55+40*np.exp(-t/.08))/48000)*np.exp(-t/.35)
    crack=_band(white,800,5000)*np.exp(-t/.012)
    roll=_band(rng.normal(0,1,n),60,700)*np.exp(-np.clip(t-.25,0,None)/max(.4,duration*.35))*(t>.2)*.45
    return boom+.4*crack+roll


def _gunfire(t,rng,white,duration):
    """Small arms at a distance: bursts of cracks (2-9 rounds, 8-12 a second) with a short echo after each."""
    n=len(t);sig=np.zeros(n);L=int(.25*48000);tl=np.arange(L)/48000;at=rng.uniform(.05,.4)
    while at<duration-.3:
     rate=rng.uniform(8,12)
     for k in range(int(rng.integers(2,10))):
      i=int((at+k/rate)*48000);m=min(L,n-i)
      if m<=0:break
      w=_band(rng.normal(0,1,L),700,4500)*np.exp(-tl/.006)+.35*_band(rng.normal(0,1,L),200,1500)*np.exp(-np.clip(tl-.08,0,None)/.09)*(tl>.08)
      sig[i:i+m]+=w[:m]*rng.uniform(.6,1)
     at+=rng.uniform(.8,2.6)
    return sig


def _waves(t,rng,white,duration):
    """Surf on a beach: swells every 6-11 s that rise, break into hiss and draw back over the sand."""
    n=len(t);env=np.zeros(n);at=-rng.uniform(0,4)
    while at<duration:
     per=rng.uniform(6,11);q=(t-at)/per;env+=np.where((q>=0)&(q<1),np.sin(np.pi*np.clip(q,0,1)**.6)**2,0);at+=per*rng.uniform(.6,.9)
    return _band(white,250,6000)*(.15+env)*.7+_band(rng.normal(0,1,n),40,300)*(.2+.5*env)


def _crowd(t,rng,white,duration):
    """A crowd outdoors: many voices too far to understand, each a band of noise opening and closing at syllable rate
    (3-6 Hz) on its own vowel band, summed into a murmur that swells and falls."""
    n=len(t);sig=np.zeros(n);k_=max(3,int(duration/1.5))
    for v in range(28):
     f=rng.uniform(300,1100);rate=rng.uniform(3,6);ph=rng.uniform(0,6.3)
     syl=np.clip(np.sin(2*np.pi*rate*t+ph+.8*np.sin(2*np.pi*.4*t+v)),0,None)**1.5
     talk=np.interp(t,np.linspace(0,duration,k_),(rng.uniform(0,1,k_)>.35).astype(float))
     sig+=_band(rng.normal(0,1,n),f*.7,f*1.6)*syl*talk*rng.uniform(.4,1)
    return sig*(.7+.3*np.sin(2*np.pi*.05*t+rng.uniform(0,6)))


def _projector(t,rng,white,duration):
    """A 16 mm projector: the shutter's 24 clicks a second, the motor's hum, the hiss of the optical track and its
    crackle; the abstract layer under a projected archive frame."""
    n=len(t);sig=_band(white,1500,8000)*.06+.08*np.sin(2*np.pi*120*t)+.05*np.sin(2*np.pi*240*t)
    L=int(.012*48000);tl=np.arange(L)/48000;click=_band(rng.normal(0,1,L),900,5000)*np.exp(-tl/.003)
    for k in range(int(duration*24)):
     i=int(k/24*48000);m=min(L,n-i)
     if m>0:sig[i:i+m]+=click[:m]*(.35 if k%2 else .5)
    for s_ in rng.uniform(0,duration,int(duration*6)):
     i=int(s_*48000);m=min(300,n-i);sig[i:i+m]+=rng.uniform(.2,.8)*np.exp(-np.arange(m)/40)*rng.choice([-1,1])
    return sig


KINDS=('whoosh','impact','tick','riser','ambient','pop','shutter','drone','room_tone','wind','chime','sub_drop','reverse_cymbal','crunch','braam','suck_out','beat','rain','forest',
       'shepard','heartbeat','tinnitus','siren','clock','morse','typewriter','radio_static','helicopter','jet','artillery','gunfire','waves','crowd','projector')
BEDS=('beat','rain','forest','wind','room_tone','drone','ambient','shepard','heartbeat','siren','clock','morse','typewriter','radio_static','helicopter','gunfire','waves','crowd','projector')  # long beds, up to 60 s
PULSED=('heartbeat','clock')  # report beat_times; tempo may move from bpm to end_bpm (accelerando)


def _tempo_times(duration,bpm,end_bpm):
    """Event times when the tempo moves linearly from bpm to end_bpm across the duration: beat n falls where the
    integrated tempo b0*t + k*t^2/2 (beats per second, k its slope) reaches n, solved exactly."""
    b0,k=bpm/60,(end_bpm-bpm)/60/duration;n=np.arange(int(b0*duration+k*duration*duration/2+1e-9)+1)
    t=n/b0 if abs(k)<1e-12 else (-b0+np.sqrt(b0*b0+2*k*n))/k
    return t[t<duration-1e-6]


def _heartbeat(n,rng,times):
    """Heartbeat: a low 'lub' (S1, a 72->42 Hz thump) and a softer, higher 'dub' (S2) after the systole interval, which
    shortens as the rate rises (about .32 s at 60 bpm, .18 s at 120). A second harmonic keeps it audible on small speakers."""
    sig=np.zeros(n);L=int(.25*48000);tl=np.arange(L)/48000
    def thump(f0,f1,decay):
        f=f1+(f0-f1)*np.exp(-tl/.03);ph=2*np.pi*np.cumsum(f)/48000
        return (np.sin(ph)+.35*np.sin(2*ph))*np.exp(-tl/decay)*np.minimum(1,tl/.004)
    lub,dub=thump(72,42,.055),thump(88,55,.04)*.62
    period=np.diff(np.append(times,times[-1]+(times[-1]-times[-2] if len(times)>1 else 1)))
    for at,per in zip(times,period):
        for off,w in ((0,lub),(min(.32,max(.18,.36*per)),dub)):
            i=int(round((at+off)*48000));m=min(L,n-i)
            if m>0:sig[i:i+m]+=w[:m]*rng.uniform(.9,1.05)
    return sig


def _clock(n,rng,times):
    """Mechanical clock: alternating tick and tock with different body resonances, each a 2 ms click into a short ring."""
    sig=np.zeros(n);L=int(.06*48000);tl=np.arange(L)/48000;click=_band(rng.normal(0,1,L),2500,9000)*np.exp(-tl/.002)
    for k,at in enumerate(times):
        modes=(3150,4200,6300) if k%2==0 else (2350,3300,5100)
        w=click*.6+sum(a*np.sin(2*np.pi*f*tl) for a,f in zip((.6,.35,.2),modes))*np.exp(-tl/.012)+.25*np.sin(2*np.pi*180*tl)*np.exp(-tl/.008)
        i=int(round(at*48000));m=min(L,n-i)
        if m>0:sig[i:i+m]+=w[:m]*(1 if k%2==0 else .8)
    return sig


def _shepard(t,duration,bpm,end_bpm):
    """Shepard-Risset glissando: eight octave-spaced partials under a fixed bell over log-frequency, each gliding up one
    octave every 16 beats, fading out at the top while another fades in at the bottom, so the pitch seems to rise without
    end (the tension device of Dunkirk's score). Each partial wraps where its level is zero, so the jump is inaudible.
    A slight swell rides on top: a rising level is heard as something approaching (looming)."""
    N=8;rate=(bpm+(end_bpm-bpm)*t/duration)/960;climb=np.cumsum(rate)/48000;sig=np.zeros(len(t))
    for i in range(N):
        x=(i+climb)%N;ph=2*np.pi*np.cumsum(36*2**x)/48000
        sig+=(.5-.5*np.cos(2*np.pi*x/N))*(np.sin(ph)+.18*np.sin(2*ph))
    return sig*(.7+.3*t/duration)


def _siren(t,bpm):
    """Air-raid (motor) siren: two rotors about a minor third apart wind up over 40% of each cycle (140->520 Hz), hold,
    then wind down; odd harmonics give the hollow square tone; band-limited with a late reflection, as from across a city.
    One cycle lasts 16 beats (5.3-16 s at 180-60 bpm)."""
    cyc=min(16.,max(4.,16*60/bpm));ph=(t%cyc)/cyc
    rise=np.where(ph<.4,np.sin(np.pi/2*np.clip(ph/.4,0,1))**1.3,np.where(ph<.55,1.,np.cos(np.pi/2*np.clip((ph-.55)/.45,0,1))**1.6))
    f0=140+380*rise;sig=0
    for ratio,a in ((1,1),(1.19,.8)):
        phs=2*np.pi*np.cumsum(f0*ratio)/48000;sig=sig+a*sum(np.sin(k*phs)/k for k in (1,3,5,7,9))
    sig=_band(sig,150,3200);d=int(.23*48000);echo=np.zeros_like(sig);echo[d:]=sig[:-d]*.35
    return (sig+echo)*(.55+.45*rise)


def _rain(t,rng,white):
    """Rain: a hiss of distant drops, a soft low wash and close drops ticking on leaves (seeded Poisson clicks)."""
    n=len(t);sig=_band(white,900,7000)*.55+_band(rng.normal(0,1,n),60,500)*.35
    drop=np.arange(int(.012*48000))/48000
    for at in np.sort(rng.uniform(0,t[-1],int(t[-1]*45))):
     i=int(at*48000);w=_band(rng.normal(0,1,len(drop)),2500,9000)*np.exp(-drop/.0025)*rng.uniform(.3,1.6);m=min(len(w),n-i);sig[i:i+m]+=w[:m]
    return sig


def _forest(t,rng,white,duration):
    """Forest: a breeze in the canopy, an insect band that swells and fades, and seeded bird calls of several kinds
    (rising chirps, falling whistles, two-note calls, fast trills) at varying distances, each note a little different,
    the bed under wildlife footage whose own sound is missing."""
    n=len(t);slow=lambda k:np.interp(t,np.linspace(0,duration,k),rng.uniform(0,1,k))
    sig=_band(white,150,900)*.25*(.6+.4*np.sin(2*np.pi*.07*t+rng.uniform(0,6)))
    sig+=_band(rng.normal(0,1,n),4200,5600)*.05*slow(max(3,int(duration/4)))**2*(.5+.5*np.sin(2*np.pi*23*t))
    def note(at,f0,f1,L,gain):
     tc=np.arange(int(L*48000))/48000;q=tc/L;f=(f0+(f1-f0)*q)*(1+.02*np.sin(2*np.pi*rng.uniform(25,45)*tc))
     w=np.sin(2*np.pi*np.cumsum(f)/48000)*np.sin(np.pi*q)**2*gain;i=int(at*48000);m=min(len(w),n-i)
     if m>0 and i>=0:sig[i:i+m]+=w[:m]
    at=rng.uniform(.2,1.2)
    while at<duration-.6:
     kind=rng.integers(0,4);f0=rng.uniform(1800,4200);gain=rng.uniform(.2,1.0)
     if kind==0:  # rising chirps
      for k in range(int(rng.integers(2,6))):note(at+k*rng.uniform(.12,.22),f0*rng.uniform(.92,1.08),f0*rng.uniform(1.3,1.5),rng.uniform(.05,.12),gain)
     elif kind==1:  # a falling whistle
      note(at,f0*1.3,f0*rng.uniform(.6,.8),rng.uniform(.25,.5),gain*.8)
     elif kind==2:  # a two-note call, repeated once or twice
      for k in range(int(rng.integers(1,3))):
       note(at+k*.5,f0,f0,rng.uniform(.12,.2),gain);note(at+k*.5+.22,f0*rng.uniform(.75,.85),f0*rng.uniform(.75,.85),rng.uniform(.12,.2),gain*.9)
     else:  # a fast trill
      for k in range(int(rng.integers(6,14))):note(at+k*.045,f0*rng.uniform(.97,1.03),f0*rng.uniform(1.05,1.12),.03,gain*.7)
     at+=rng.uniform(1.0,3.6)
    return sig


def _morse(t,rng):
    """Telegraph traffic: a 700 Hz tone keyed in seeded Morse groups at about 18 words a minute (dot .066 s), with the
    soft clicks a real key makes. Period sound for a newsroom, a signals tent, a 1945 broadcast."""
    sig=np.zeros(len(t));dot=.066;at=.15;f=rng.uniform(640,760)
    while at<t[-1]-.3:
     for _ in range(int(rng.integers(3,6))):  # a letter
      d=dot if rng.random()<.55 else 3*dot
      m=(t>=at)&(t<at+d);sig[m]+=np.sin(2*np.pi*f*(t[m]-at))*np.minimum(1,np.minimum(t[m]-at,at+d-t[m])/.004)
      at+=d+dot
     at+=2*dot if rng.random()<.75 else 6*dot  # letter or word gap
    return sig


def _typewriter(t,rng,white,duration):
    """A manual typewriter in a newsroom: bursts of keystrokes (sharp clicks with a body thump), a bell and the carriage
    return at the end of a line."""
    sig=np.zeros(len(t));at=.1
    def hit(s,w,lo,hi,tau):
     i=int(s*48000);seg=_band(white[i:i+int(.05*48000)],lo,hi)*np.exp(-np.arange(min(len(white)-i,int(.05*48000)))/48000/tau)
     sig[i:i+len(seg)]+=w*seg
    while at<duration-.6:
     for _ in range(int(rng.integers(18,42))):
      if at>=duration-.6:break
      hit(at,1.0,1500,7000,.006);hit(at+.004,.5,120,600,.02);at+=rng.uniform(.08,.17)
     if at<duration-.8:
      i=int(at*48000);n=int(.6*48000);tt=np.arange(min(n,len(t)-i))/48000
      sig[i:i+len(tt)]+=.4*np.sin(2*np.pi*2800*tt)*np.exp(-tt/.25)+.6*_band(white[i:i+len(tt)],300,2500)*np.exp(-((tt-.35)/.12)**2)
      at+=rng.uniform(.9,1.6)
    return sig


def _static(t,rng,white,duration):
    """A shortwave receiver between stations: hiss with crackle, a slow fading carrier and a whistle drifting across it."""
    hiss=_band(white,300,5000)*(.6+.4*np.sin(2*np.pi*.23*t+rng.uniform(0,6)))
    crack=np.zeros(len(t))
    for s in rng.uniform(0,duration,int(duration*9)):
     i=int(s*48000);m=min(400,len(t)-i);crack[i:i+m]+=rng.uniform(.5,1.5)*np.exp(-np.arange(m)/60)*rng.choice([-1,1])
    whistle=.25*np.sin(2*np.pi*np.cumsum(900+600*np.sin(2*np.pi*.07*t))/48000)
    return hiss+.6*crack+whistle


def _band(x,lo,hi):
    """Gaussian-shaped band-pass in the frequency domain (deterministic, no filter state)."""
    n=len(x);spec=np.fft.rfft(x);freq=np.fft.rfftfreq(n,1/48000);c,w=(lo+hi)/2,max(1,(hi-lo)/2)
    return np.fft.irfft(spec*np.exp(-((freq-c)/w)**2),n)


def _beat(duration,seed,bpm,rng):
    """A music bed for short-form edits: four-on-the-floor kick, backbeat snare, 8th hats, offbeat bass and a pad on a
    seeded four-chord progression. Deterministic; returns the signal and the beat times."""
    n=round(duration*48000);sig=np.zeros(n);spb=60/bpm;bar=4*spb;beats=np.arange(0,duration-1e-6,spb)
    def add(at,w):
     i=int(round(at*48000));m=min(len(w),n-i)
     if m>0 and i>=0:sig[i:i+m]+=w[:m]
    tk=np.arange(int(.3*48000))/48000;kick=np.sin(2*np.pi*np.cumsum(45+90*np.exp(-tk/.03))/48000)*np.exp(-tk/.12)
    tn=np.arange(int(.18*48000))/48000;snare=(_band(rng.normal(0,1,len(tn)),1500,6000)*.6+.4*np.sin(2*np.pi*190*tn))*np.exp(-tn/.05)
    th=np.arange(int(.05*48000))/48000;hat=_band(rng.normal(0,1,len(th)),7000,14000)*np.exp(-th/.012)
    prog=((0,7,9,5),(9,5,0,7),(0,9,5,7),(2,7,0,5))[seed%4];root=55*2**([0,2,3,5,7,8,10,-2][seed//4%8]/12)
    tb=np.arange(int(spb/2*.9*48000))/48000;tp=np.arange(int(bar*48000))/48000
    for k,b in enumerate(beats):
     add(b,kick*.9);add(b,hat*.12);add(b+spb/2,hat*.25)
     if k%4 in(1,3):add(b,snare*.5)
     f=root*2**(prog[int(b//bar)%4]/12);note=(np.sin(2*np.pi*f*tb)+.3*np.sin(4*np.pi*f*tb))*np.minimum(1,tb/.005)*np.exp(-tb/.18)
     add(b+spb/2,note*.28)
    for j,bs in enumerate(np.arange(0,duration-1e-6,bar)):
     c=prog[j%4];f=root*4*2**(c/12);tri=(0,3 if c in(2,9) else 4,7)
     pad=sum(np.sin(2*np.pi*f*2**(x/12)*tp)+.2*np.sin(4*np.pi*f*2**(x/12)*tp) for x in tri)*np.minimum(1,tp/.25)*np.minimum(1,np.maximum(0,bar-tp)/.2)
     add(bs,pad*.12)
    return sig,beats


_CODE=__import__('hashlib').sha1(Path(__file__).read_bytes()).hexdigest()[:12]


def design(kind='whoosh',duration=.6,seed=7,gain_db=-18,bpm=124,end_bpm=None):
    """Procedural sound effects for editors. Every result reports onset_s and peak_s so a placement can anchor the
    right moment on a picture event: a whoosh or reverse cymbal peaks on the cut, an impact or sub drop starts on it.
    kind beat: a music bed at bpm (60-180) up to 60 s, with its beat times for snap_cuts_to_beats. Beds (beat, rain, forest,
    wind, room_tone, drone, ambient) run up to 60 s; rain and forest stand in for nature sound a source lacks (synthesized,
    so say so in the credits).
    Tension kinds (docs/PRO_WORKFLOWS.md, sound psychology): heartbeat and clock pulse at bpm, moving to end_bpm when
    given (accelerando), with beat_times; shepard rises without end (16 beats per octave, faster toward end_bpm) and stops
    dead at its end so the next sound lands on silence; siren is an air-raid wail; tinnitus is the ring after a blast
    (pair it with a muffled treatment on the rest of the mix)."""
    if end_bpm is not None and kind not in PULSED+('shepard',):
        raise ValueError('end_bpm applies to heartbeat, clock and shepard only')
    end_bpm=bpm if end_bpm is None else end_bpm
    if kind not in KINDS or not .08<=duration<=(60 if kind in BEDS else 12) or not -48<=gain_db<=-3 or type(seed)!=int or not 0<=seed<=2147483647 or not 60<=bpm<=(600 if kind=='clock' else 180) or not 60<=end_bpm<=(600 if kind=='clock' else 180):  # a clock may race (a news montage's pulse, 3 to 9 ticks a second)
        raise ValueError('kind '+'|'.join(KINDS)+'; duration.08..12s (beds '+'/'.join(BEDS)+' <=60),gain_db-48..-3,seeduint31,bpm/end_bpm 60..180 (clock to 600)')
    import hashlib  # same request, same file: a montage asked for one sound twenty times and wrote twenty WAVs
    key=hashlib.sha1(json.dumps([kind,round(duration,4),seed,gain_db,bpm,end_bpm,_CODE]).encode()).hexdigest()[:16]  # new synthesis, new files
    cached=store.DATA/'sound-design'/f'{kind}-{key}'/'sound.json'
    if cached.is_file():
        r=json.loads(cached.read_text(encoding='utf-8'))
        if Path(r['path']).is_file():return r
    n=round(duration*48000);t=np.arange(n)/48000;p=t/duration;rng=np.random.default_rng(seed)
    white=rng.normal(0,1,n)
    # Band-limit procedural noise without loading another model/provider.
    noise=_band(white,0,3600)
    smooth=lambda k:np.interp(t,np.linspace(0,duration,k),rng.normal(0,1,k))  # slow seeded modulation
    if kind=='whoosh':signal=noise*np.sin(np.pi*p)**2
    elif kind=='impact':signal=(np.sin(2*np.pi*(85*t-25*t*t/duration))*.8+noise*.25)*np.exp(-8*p)
    elif kind=='tick':signal=(np.sin(2*np.pi*1700*t)+noise*.1)*np.exp(-35*p)
    elif kind=='riser':signal=(np.sin(2*np.pi*(220*t+500*t*t/duration))*.4+noise*.5)*p**1.5
    elif kind=='pop':signal=(np.sin(2*np.pi*(900*t-500*t*t/max(duration,.05)))+.15*_band(white,2000,8000))*np.exp(-t/.025)  # UI/graphic entrance
    elif kind=='shutter':  # two mechanical clicks (curtain open/close), for stills and screenshots
        signal=sum(_band(white,1500,9000)*np.exp(-np.clip(t-s,0,None)/.006)*(t>=s) for s in (0,min(.08,duration*.5)))
    elif kind=='drone':signal=(sum(np.sin(2*np.pi*f*t+j)*.3 for j,f in enumerate((55,82.6,110.4)))+.25*_band(white,40,400))*(.75+.25*np.sin(2*np.pi*.18*t))
    elif kind=='room_tone':  # brown noise, low-passed, a trace of mains hum: the "air" of a room under dialogue
        brown=np.cumsum(white);brown=brown-np.convolve(brown,np.ones(4800)/4800,mode='same');signal=_band(brown,0,1800)+.02*np.sin(2*np.pi*50*t)
    elif kind=='wind':signal=_band(white,200,1400)*(.55+.45*np.tanh(smooth(max(4,int(duration*1.5)))))
    elif kind=='chime':signal=sum(a*np.sin(2*np.pi*880*r*t)*np.exp(-t/(1.4/r**.5)) for a,r in ((1,1),(.6,2.76),(.35,5.4),(.2,8.93)))*(t>=0)
    elif kind=='sub_drop':  # a 100-140 Hz -> 32-40 Hz sweep, its start, floor and decay drawn from the seed
        f_hi,f_lo,dk=rng.uniform(60,105),rng.uniform(32,40),rng.uniform(1.8,2.8)
        signal=np.sin(2*np.pi*np.cumsum(f_lo+f_hi*np.exp(-5*p))/48000)*np.exp(-dk*p)
    elif kind=='reverse_cymbal':signal=_band(white,3500,14000)*np.power(p,3.2)  # swell that peaks at its end
    elif kind=='crunch':signal=sum(_band(white,600,6000)*np.exp(-np.clip(t-s,0,None)/.004)*(t>=s) for s in np.sort(rng.uniform(0,duration*.7,18)))*np.exp(-2*p)
    elif kind=='braam':  # trailer brass blast: detuned saw stack on G1 + fifth, saturated, slight pitch sag, long decay
        # the seed picks the root (G1 +- a semitone), the sag and the detune, so two braams layered on one hit beat
        # against each other instead of summing in phase (they were byte-identical)
        f0=49*2**(rng.uniform(-1,1)/12)*(1-rng.uniform(.008,.025)*p);ph=2*np.pi*np.cumsum(f0)/48000
        dt=rng.uniform(.002,.006)
        saw=sum((np.sin(k*ph*(1+d))/k) for k in range(1,24) for d in (-dt,0,dt*1.1))
        saw+=.6*sum(np.sin(k*1.4983*ph)/k for k in range(1,16))
        signal=np.tanh(1.8*_band(saw,30,2600)/np.max(np.abs(saw)))*np.minimum(1,t/.035)*np.exp(-1.6*p)+.35*np.sin(ph)*np.exp(-2*p)
    elif kind=='beat':signal,beat_times=_beat(duration,seed,bpm,rng)
    elif kind=='rain':signal=_rain(t,rng,white)
    elif kind=='forest':signal=_forest(t,rng,white,duration)
    elif kind=='suck_out':  # reversed swell that is pulled into silence: ends abruptly at its peak, the beat before a hit
        sweep=np.sin(2*np.pi*np.cumsum(60+260*p**2)/48000)
        signal=(_band(white,80,1400)*.7+.5*sweep)*np.power(p,2.6)
    elif kind in PULSED:
        beat_times=_tempo_times(duration,bpm,end_bpm)
        signal=_heartbeat(n,rng,beat_times) if kind=='heartbeat' else _clock(n,rng,beat_times)
    elif kind=='shepard':signal=_shepard(t,duration,bpm,end_bpm)
    elif kind=='siren':signal=_siren(t,bpm)
    elif kind=='morse':signal=_morse(t,rng)
    elif kind=='typewriter':signal=_typewriter(t,rng,white,duration)
    elif kind=='radio_static':signal=_static(t,rng,white,duration)
    elif kind in ('helicopter','jet','artillery','gunfire','waves','crowd','projector'):
        signal={'helicopter':_helicopter,'jet':_jet,'artillery':_artillery,'gunfire':_gunfire,'waves':_waves,'crowd':_crowd,'projector':_projector}[kind](t,rng,white,duration)
    elif kind=='tinnitus':  # near-pure high ring (seeded 3.4-4.6 kHz) beating slowly against a partner, faint hiss, long decay
        f=rng.uniform(3400,4600);signal=(np.sin(2*np.pi*f*t)+.35*np.sin(2*np.pi*(f+2.7)*t)+.04*_band(white,6000,12000))*np.exp(-1.6*p)*np.minimum(1,t/.06)
    else:signal=sum(np.sin(2*np.pi*f*t+j*.3)*.3 for j,f in enumerate((110,164.8138,220)))
    fade=(min(.5,duration/4) if kind in('rain','forest','siren','helicopter','waves','crowd','projector','gunfire') else min(.02,duration/4)) if kind not in('reverse_cymbal','suck_out') else .002
    fade_in=.001 if kind in('pop','shutter','impact','crunch','sub_drop','braam','heartbeat','clock','artillery') else min(.6,duration/4) if kind=='shepard' else fade
    fade_out=.002 if kind=='shepard' else fade  # the endless rise stops dead: the hit after it lands on silence
    envelope=np.minimum(1,t/max(.001,fade_in))*np.minimum(1,(duration-t)/fade_out)
    signal*=envelope;signal=signal/max(1e-9,np.max(np.abs(signal)))*10**(gain_db/20)
    win=max(1,int(.01*48000));env=np.sqrt(np.convolve(signal*signal,np.ones(win)/win,mode='same'));top=float(env.max())
    onset=int(np.argmax(env>=top*.1)) if top>0 else 0;peak=int(np.argmax(env))
    if kind=='shepard':peak=n-1  # anchored on its dead stop: the sound after it lands on silence
    out=cached.parent;out.mkdir(parents=True,exist_ok=True);path=out/(kind+'.wav')
    with wave.open(str(path),'wb') as f:f.setparams((1,2,48000,0,'NONE','not compressed'));f.writeframes((signal*32767).astype('<i2').tobytes())
    result={'path':str(path),'sha256':sha256(path),'kind':kind,'duration':n/48000,'seed':seed,'peak_dbfs':gain_db,
            'onset_s':round(onset/48000,4),'peak_s':round(peak/48000,4),
            **({'bpm':bpm,'beat_times':[round(float(b),4) for b in beat_times[:480]],'bar_s':round(4*60/bpm,4)} if kind=='beat' else {}),
            **({'bpm':bpm,'end_bpm':end_bpm,'beat_times':[round(float(b),4) for b in beat_times[:480]]} if kind in PULSED else {}),
            **({'bpm':bpm,'end_bpm':end_bpm,'octave_s':round(960/bpm,3)} if kind=='shepard' else {}),
            'method':'deterministic procedural synthesis, no generative model/download','use':'Import with preserve_plan/current revision, place upsert_audio at an intentional event, keep dialogue dominant, listen to mixed output.'}
    store.write_json(out/'sound.json',result);return result
