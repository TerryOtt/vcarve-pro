"""Orthographic scientific view of the actual swept-tool height fields."""
from pathlib import Path
import math
import numpy as np
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parent.parent/'PlanetCNC'
data=np.load(ROOT/'Simulation-Depths.npz')
image=Image.new('RGB',(1880,690),'#f3f1ec')
draw=ImageDraw.Draw(image)
font=ImageFont.truetype(r'C:\Windows\Fonts\segoeui.ttf',25)
small=ImageFont.truetype(r'C:\Windows\Fonts\segoeui.ttf',18)
scale=151
def project(x,y,z,offset):
    return (offset+60+scale*(0.90*x+0.45*y),440+scale*(0.22*x-0.44*y-0.80*z))

for number,piece in enumerate(['maple','walnut']):
    offset=number*940
    color=np.array([222,191,141] if piece=='maple' else [113,73,45])
    depth=data[piece]
    # Downsample only for display. Validation uses the full simulation grid.
    select=np.arange(0,len(data['axis']),3)
    if select[-1]!=len(data['axis'])-1: select=np.r_[select,len(data['axis'])-1]
    axis=data['axis'][select]
    surface=.5-depth[np.ix_(select,select)]
    side=[((0,0,0),(4,0,0),(4,0,.5),(0,0,.5)),
          ((4,0,0),(4,4,0),(4,4,.5),(4,0,.5))]
    for index,face in enumerate(side):
        shade=.64 if index==0 else .50
        draw.polygon([project(*p,offset) for p in face],fill=tuple((color*shade).astype(int)))
    gy,gx=np.gradient(surface,axis,axis)
    cells=[]
    for row in range(len(axis)-1):
        for column in range(len(axis)-1):
            x,y=axis[column],axis[row]
            cells.append((x-2*y,row,column))
    cells.sort()
    light=np.array([-0.35,-0.45,1.0]);light/=np.linalg.norm(light)
    for _,row,column in cells:
        x0,x1=axis[column],axis[column+1]
        y0,y1=axis[row],axis[row+1]
        normal=np.array([-gx[row,column],-gy[row,column],1.0]);normal/=np.linalg.norm(normal)
        brightness=.48+.56*max(0,float(normal@light))
        fill=tuple(np.clip(color*brightness,0,255).astype(int))
        quad=[project(x0,y0,float(surface[row,column]),offset),
              project(x1,y0,float(surface[row,column+1]),offset),
              project(x1,y1,float(surface[row+1,column+1]),offset),
              project(x0,y1,float(surface[row+1,column]),offset)]
        draw.polygon(quad,fill=fill)
    label='Maple pocket' if piece=='maple' else 'Walnut plug - mirrored'
    maximum=.125 if piece=='maple' else .170
    draw.text((offset+45,30),label,font=font,fill='#292522')
    draw.text((offset+45,590),f'4 x 4 x 0.5 inch stock; maximum cut {maximum:.3f} inch',font=small,fill='#514940')
    if piece=='walnut':
        draw.text((offset+45,625),'Outer raised rim must be trimmed off before fitting.',font=small,fill='#514940')
draw.text((45,657),'Independent geometric simulation. Check PlanetCNC preview and test a scrap pair before production.',font=small,fill='#514940')
image.save(ROOT/'Toolpath-3D-Preview.png')
print(ROOT/'Toolpath-3D-Preview.png')
