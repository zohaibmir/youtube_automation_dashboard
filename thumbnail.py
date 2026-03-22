"""thumbnail.py - Professional YouTube thumbnail generator.
Supports faceless mode (stock BG) and hybrid mode (face photo).
Output: 1280x720 JPEG."""
import os
from PIL import Image, ImageDraw, ImageFont

def get_font(size):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ]
    for p in candidates:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def make_faceless_thumbnail(content, bg_path, out="thumbnail.jpg"):
    W, H = 1280, 720
    img = Image.open(bg_path).convert("RGB").resize((W,H), Image.LANCZOS)
    ov = Image.new("RGBA",(W,H),(0,0,0,0))
    from PIL import ImageDraw as ID
    d2 = ID.Draw(ov)
    for x in range(W):
        d2.line([(x,0),(x,H)], fill=(0,0,0,int(190*(1-x/W*0.35))))
    for y in range(H//2,H):
        d2.line([(0,y),(W,y)], fill=(0,0,0,int(150*((y-H//2)/(H//2)))))
    img = Image.alpha_composite(img.convert("RGBA"),ov).convert("RGB")
    draw = ImageDraw.Draw(img)
    draw.rectangle([(0,0),(8,H)], fill=(124,109,250))
    line1 = content.get("thumbnail_text","WATCH THIS").upper()
    line2 = content.get("thumbnail_subtext","")
    badge = content.get("badge","EXCLUSIVE").upper()
    f1,f2,f3 = get_font(108),get_font(72),get_font(30)
    def shadow_text(d,x,y,t,f,col):
        d.text((x+4,y+4),t,font=f,fill=(0,0,0,200))
        d.text((x,y),t,font=f,fill=col)
    shadow_text(draw,60,80,line1,f1,(255,220,50))
    if line2: shadow_text(draw,60,210,line2,f2,(255,255,255))
    bw=len(badge)*14+40
    draw.rounded_rectangle([(60,H-100),(60+bw,H-58)],radius=8,fill=(124,109,250))
    draw.text((60+bw//2,H-79),badge,font=f3,fill=(255,255,255),anchor="mm")
    ch = content.get("channel_name","")
    if ch:
        draw.text((W-40,H-36),"@"+ch,font=get_font(28),fill=(200,200,200),anchor="rs")
    img.save(out,"JPEG",quality=95,optimize=True)
    return out

def make_hybrid_thumbnail(content, face_path, bg_path=None, out="thumbnail.jpg"):
    W, H = 1280, 720
    canvas = Image.new("RGB",(W,H),(10,8,20))
    if bg_path and os.path.exists(bg_path):
        bg = Image.open(bg_path).convert("RGB").resize((W,H),Image.LANCZOS)
        bg_r = bg.crop((W//2,0,W,H))
        dark = Image.new("RGB",bg_r.size,(0,0,0))
        canvas.paste(Image.blend(bg_r,dark,0.65),(W//2,0))
    face_w = int(W*0.45)
    face = Image.open(face_path).convert("RGBA")
    scale = H/face.height
    nw = int(face.width*scale)
    face = face.resize((nw,H),Image.LANCZOS)
    left = max(0,(nw-face_w)//2)
    face = face.crop((left,0,left+face_w,H))
    mask = Image.new("L",(face_w,H),255)
    from PIL import ImageDraw as ID
    md = ID.Draw(mask)
    bs = int(face_w*0.72)
    for x in range(bs,face_w):
        md.line([(x,0),(x,H)],fill=int(255*(1-(x-bs)/(face_w-bs))))
    canvas.paste(face.convert("RGB"),(0,0),mask)
    draw = ImageDraw.Draw(canvas)
    ax = int(W*0.44)
    draw.rectangle([(ax,0),(ax+6,H)],fill=(124,109,250))
    tx = ax+40
    line1 = content.get("thumbnail_text","BREAKING").upper()
    line2 = content.get("thumbnail_subtext","")
    badge = content.get("badge","KAMIL MIR").upper()
    f1,f2,f3 = get_font(100),get_font(66),get_font(26)
    def outlined(d,x,y,t,f,col=(255,220,50)):
        d.text((x,y),t,font=f,fill=(0,0,0),stroke_width=4,stroke_fill=(0,0,0))
        d.text((x,y),t,font=f,fill=col)
    outlined(draw,tx,90,line1,f1)
    if line2: outlined(draw,tx,220,line2,f2,(255,255,255))
    bw=len(badge)*12+40
    draw.rounded_rectangle([(tx,H-100),(tx+bw,H-58)],radius=8,fill=(124,109,250))
    draw.text((tx+bw//2,H-79),badge,font=f3,fill=(255,255,255),anchor="mm")
    canvas.save(out,"JPEG",quality=96,optimize=True)
    return out

def make_thumbnail(content, bg_path, face_path=None, mode="faceless"):
    if mode=="hybrid" and face_path and os.path.exists(face_path):
        return make_hybrid_thumbnail(content,face_path,bg_path)
    return make_faceless_thumbnail(content,bg_path)