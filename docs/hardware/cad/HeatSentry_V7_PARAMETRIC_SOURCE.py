import cadquery as cq
from cadquery import exporters
from pathlib import Path
import json, math, os, traceback

OUT = Path('/mnt/data/HeatSentry_V7_TRUE_FINAL')
OUT.mkdir(parents=True, exist_ok=True)

# -------------------------
# Global parameters (mm)
# -------------------------
P = {
    'overall_x': 240.0,
    'overall_y': 72.0,
    'overall_z': 90.0,
    'half_x': 120.0,
    'wall': 2.4,
    'separator_center_y': -1.5,
    'separator_thickness': 2.4,
    'fan_size': 40.0,
    'fan_thickness': 10.3,
    'fan_pocket': 41.0,
    'fan_x': [-52.0, 52.0],
    'fan_z': 42.0,
    'fan_hole_pitch': 32.0,
    'top_port_capsule_x': 40.0,
    'top_port_capsule_y': 26.0,
    'top_riser_outer_x': 44.0,
    'top_riser_outer_y': 30.0,
    'top_port_y': -18.0,
    'top_riser_height': 18.0,
    'service_open_x': 204.0,
    'service_open_z': 74.0,
    'service_cover_x': 216.0,
    'service_cover_z': 82.0,
    'service_cover_t': 2.8,
    'powerbank_ref': [140.0, 15.0, 70.0], # X,Y,Z
    'esp_ref': [30.0, 25.0, 55.0],       # X,Y,Z
    'pcm_ref': [160.0, 8.0, 64.0],
    'belt_webbing_width': 50.0,
    'belt_webbing_gap': 5.0,
    'nominal_insert_pilot_m3': 4.2,
    'nominal_clearance_m3': 3.5,
}

XH=P['half_x']; YH=P['overall_y']/2; ZH=P['overall_z']; W=P['wall']
SEP_C=P['separator_center_y']; SEP_T=P['separator_thickness']; SEP_F=SEP_C-SEP_T/2; SEP_R=SEP_C+SEP_T/2
REAR_IN=YH-W; FRONT_IN=-YH+W

# -------------------------
# Geometry helpers
# -------------------------
def box(x0,x1,y0,y1,z0,z1):
    x0,x1=min(x0,x1),max(x0,x1); y0,y1=min(y0,y1),max(y0,y1); z0,z1=min(z0,z1),max(z0,z1)
    return cq.Solid.makeBox(x1-x0,y1-y0,z1-z0,cq.Vector(x0,y0,z0))

def cyl_y(r, y0, y1, x, z):
    y0,y1=min(y0,y1),max(y0,y1)
    return cq.Solid.makeCylinder(r,y1-y0,cq.Vector(x,y0,z),cq.Vector(0,1,0))

def cyl_x(r, x0, x1, y, z):
    x0,x1=min(x0,x1),max(x0,x1)
    return cq.Solid.makeCylinder(r,x1-x0,cq.Vector(x0,y,z),cq.Vector(1,0,0))

def cyl_z(r, z0, z1, x, y):
    z0,z1=min(z0,z1),max(z0,z1)
    return cq.Solid.makeCylinder(r,z1-z0,cq.Vector(x,y,z0),cq.Vector(0,0,1))

def capsule_z(total_x,total_y,z0,z1,cx=0,cy=0):
    # stadium/capsule elongated along X; total_y = 2r, total_x >= total_y
    r=total_y/2
    straight=max(0.0,total_x-2*r)
    parts=[]
    if straight>0:
        parts.append(box(cx-straight/2,cx+straight/2,cy-r,cy+r,z0,z1))
        off=straight/2
        parts.append(cyl_z(r,z0,z1,cx-off,cy))
        parts.append(cyl_z(r,z0,z1,cx+off,cy))
    else:
        parts.append(cyl_z(r,z0,z1,cx,cy))
    s=parts[0]
    for p in parts[1:]: s=s.fuse(p)
    return s

def ring_capsule_z(outer_x,outer_y,inner_x,inner_y,z0,z1,cx,cy):
    return capsule_z(outer_x,outer_y,z0,z1,cx,cy).cut(capsule_z(inner_x,inner_y,z0-0.2,z1+0.2,cx,cy))

def triangle_prism_x(x0,x1, pts_yz):
    # pts as list of (y,z), extrude along +X
    wp = cq.Workplane('YZ', origin=(x0,0,0)).polyline(pts_yz).close().extrude(x1-x0)
    return wp.val()

def solid_union(parts):
    s=parts[0]
    for p in parts[1:]: s=s.fuse(p)
    return s

def make_half(side='L'):
    assert side in ('L','R')
    if side=='L':
        x0,x1=-120.0,0.0; xi0,xi1=-120+W,-W
        fan_x=-52.0
    else:
        x0,x1=0.0,120.0; xi0,xi1=W,120-W
        fan_x=52.0

    s = box(x0,x1,-YH,YH,0,ZH)

    # Main air and electronics cavities. These leave an integral 2.4 mm separator.
    air = box(xi0,xi1,FRONT_IN,SEP_F,W,ZH-W)
    elec = box(xi0,xi1,SEP_R,REAR_IN,W,ZH-W)
    s = s.cut(air).cut(elec)

    # Open the electronics chamber across the center seam, but retain bottom/top seam frame.
    if side=='L':
        seam_open = box(-3.2,0.4,SEP_R-0.2,REAR_IN+0.2,6.0,84.0)
    else:
        seam_open = box(-0.4,3.2,SEP_R-0.2,REAR_IN+0.2,6.0,84.0)
    s=s.cut(seam_open)

    # Rear service opening; one combined opening under a one-piece cover.
    if side=='L':
        ropen=box(-102.0,0.4,REAR_IN-0.3,YH+0.3,8.0,82.0)
    else:
        ropen=box(-0.4,102.0,REAR_IN-0.3,YH+0.3,8.0,82.0)
    s=s.cut(ropen)

    # Fan service pocket: front-loading fan, with sleeve, backer, and M3 insert bosses.
    fz=P['fan_z']; pocket=P['fan_pocket']; ph=pocket/2
    # Through/open pocket to backer front plane.
    pocket_cut=box(fan_x-ph,fan_x+ph,-YH-0.2,-25.25,fz-ph,fz+ph)
    s=s.cut(pocket_cut)

    # pocket sleeve around 41 mm fan, attaches front wall to backer
    outer=45.0/2; inner=41.0/2
    sleeve_parts=[
        box(fan_x-outer,fan_x-inner,-33.8,-25.2,fz-outer,fz+outer),
        box(fan_x+inner,fan_x+outer,-33.8,-25.2,fz-outer,fz+outer),
        box(fan_x-inner,fan_x+inner,-33.8,-25.2,fz-outer,fz-inner),
        box(fan_x-inner,fan_x+inner,-33.8,-25.2,fz+inner,fz+outer),
    ]
    s=s.fuse(solid_union(sleeve_parts))

    # backer plate
    backer=box(fan_x-outer,fan_x+outer,-25.45,-23.25,fz-outer,fz+outer)
    backer=backer.cut(cyl_y(18.5,-25.7,-22.9,fan_x,fz))
    s=s.fuse(backer)
    # 4 screw bosses, 32x32 pitch
    boss_parts=[]
    for dx in (-16,16):
        for dz in (-16,16):
            boss_parts.append(cyl_y(4.1,-25.5,-17.5,fan_x+dx,fz+dz))
    s=s.fuse(solid_union(boss_parts))
    # M3 insert pilots from fan side
    for dx in (-16,16):
        for dz in (-16,16):
            s=s.cut(cyl_y(P['nominal_insert_pilot_m3']/2,-25.8,-17.2,fan_x+dx,fz+dz))

    # Dedicated 56 mm airflow channel walls.
    for xw in (fan_x-28.0, fan_x+28.0):
        s=s.fuse(box(xw-1.0,xw+1.0,-24.2,SEP_F+0.2,W-0.2,ZH-W+0.2))

    # Thin 45-degree turning vane / ramp, attached to separator and channel walls.
    guide=triangle_prism_x(fan_x-27.2,fan_x+27.2,[(-17.0,50.0),(SEP_F+0.1,65.5),(SEP_F+0.1,70.0),(-17.0,54.2)])
    s=s.fuse(guide)

    # Large top outlet: 40x26 capsule; outlet area ~ fan opening rather than ~half.
    port_hole=capsule_z(P['top_port_capsule_x'],P['top_port_capsule_y'],ZH-W-0.5,ZH+0.5,fan_x,P['top_port_y'])
    s=s.cut(port_hole)
    riser=ring_capsule_z(P['top_riser_outer_x'],P['top_riser_outer_y'],P['top_port_capsule_x'],P['top_port_capsule_y'],ZH,ZH+P['top_riser_height'],fan_x,P['top_port_y'])
    s=s.fuse(riser)

    # Fan cable grommet: true through-hole across separator, seal with 8 mm grommet/RTV.
    s=s.cut(cyl_y(4.1,SEP_F-0.5,SEP_R+0.5,fan_x,15.0))

    # Battery cradle bosses: M3 heat-set inserts, four total across both halves.
    # Each half gets x=+/-66 at z=14 and 76.
    bx=-66.0 if side=='L' else 66.0
    for bz in (14.0,76.0):
        s=s.fuse(cyl_y(4.2,SEP_R-0.1,SEP_R+6.0,bx,bz))
        # blind pilot, open from rear of boss, does not pierce separator
        s=s.cut(cyl_y(2.1,SEP_R+0.7,SEP_R+6.3,bx,bz))

    # ESP universal sled bosses on right half only, shallow/blind M2.5 self-tap pilots.
    if side=='R':
        for ex in (82.0,108.0):
            for ez in (18.0,72.0):
                s=s.fuse(cyl_y(3.1,SEP_R-0.1,SEP_R+1.9,ex,ez))
                # blind from rear, leave >=0.5 mm air-side wall
                s=s.cut(cyl_y(1.0,SEP_F+0.55,SEP_R+2.1,ex,ez))

    # Service-cover heat-set insert bosses: 4 top + 4 bottom + one side per half.
    topbottom_x = (-88.0,-30.0) if side=='L' else (30.0,88.0)
    for sx in topbottom_x:
        for sz in (6.0,84.0):
            s=s.fuse(cyl_y(4.6,28.0,YH+0.1,sx,sz))
            s=s.cut(cyl_y(2.1,30.0,YH+0.3,sx,sz))
    side_x=-104.5 if side=='L' else 104.5
    s=s.fuse(cyl_y(4.6,29.0,YH+0.1,side_x,45.0))
    s=s.cut(cyl_y(2.1,30.5,YH+0.3,side_x,45.0))

    # Center bridge bosses, top & bottom. M3 self-tap / insert depending process.
    cbx=-12.0 if side=='L' else 12.0
    for cz in (7.0,83.0):
        s=s.fuse(cyl_y(4.3,29.0,34.3,cbx,cz))
        s=s.cut(cyl_y(2.1,29.0,34.5,cbx,cz))

    # Belt-loop mount bosses on outer side, 4 M3 insert locations per side.
    # Axis X, accessible from outside. 2 top + 2 bottom.
    x_axis0,x_axis1 = (-120.2,-112.5) if side=='L' else (112.5,120.2)
    for by in (7.0,19.0):
        for bz in (16.0,74.0):
            s=s.fuse(cyl_x(4.4,x_axis0,x_axis1,by,bz))
            s=s.cut(cyl_x(2.1,x_axis0-0.2,x_axis1+0.2,by,bz))

    # Two actual bottom electronics cable-gland/grommet ports (right half only), fully through.
    if side=='R':
        for gx in (92.0,108.0):
            gy=18.0
            s=s.fuse(cyl_z(7.0,-5.5,2.7,gx,gy))
            s=s.cut(cyl_z(4.25,-5.8,4.0,gx,gy))

    # Integrated alignment tongues on LEFT; matching pockets on RIGHT.
    tongues=[
        (-30,-23,8,16),
        (-30,-23,74,82),
        (10,20,0.0,4.5),
        (10,20,85.5,90.0),
    ]
    if side=='L':
        for ya,yb,za,zb in tongues:
            s=s.fuse(box(-0.6,4.0,ya,yb,za,zb))
    else:
        for ya,yb,za,zb in tongues:
            s=s.cut(box(-0.4,4.45,ya-0.25,yb+0.25,za-0.25,zb+0.25))

    return s.clean()

def make_service_cover(with_pcm_bosses=True):
    xh=P['service_cover_x']/2; z0=(ZH-P['service_cover_z'])/2; z1=z0+P['service_cover_z']
    y0=YH+0.25; y1=y0+P['service_cover_t']
    s=box(-xh,xh,y0,y1,z0,z1)
    # 10 M3 clearance holes matching shell bosses
    for sx in (-88.0,-30.0,30.0,88.0):
        for sz in (6.0,84.0):
            s=s.cut(cyl_y(P['nominal_clearance_m3']/2,y0-0.2,y1+0.2,sx,sz))
    for sx in (-104.5,104.5):
        s=s.cut(cyl_y(P['nominal_clearance_m3']/2,y0-0.2,y1+0.2,sx,45.0))

    # Rectangular gasket groove on shell-facing surface. 2.5 wide x 0.9 deep.
    gd=0.9; gy0=y0-0.05; gy1=y0+gd
    # around service opening x +/-102, z 8..82
    s=s.cut(box(-104.8,104.8,gy0,gy1,5.2,7.8))
    s=s.cut(box(-104.8,104.8,gy0,gy1,82.2,84.8))
    s=s.cut(box(-104.8,-102.2,gy0,gy1,7.5,82.5))
    s=s.cut(box(102.2,104.8,gy0,gy1,7.5,82.5))

    # 4 external PCM carrier bosses with blind M3 insert pilots.
    if with_pcm_bosses:
        for px in (-65.0,65.0):
            for pz in (20.0,70.0):
                s=s.fuse(cyl_y(4.2,y1-0.1,y1+6.0,px,pz))
                s=s.cut(cyl_y(2.1,y1+0.4,y1+6.2,px,pz))
    return s.clean()

def make_battery_cradle():
    # Assembly coordinates: plate just behind separator, battery centered on it.
    y0=SEP_R+6.1; y1=y0+2.4
    s=box(-73,73,y0,y1,9,81)
    # Lighten middle while retaining 12 mm perimeter and 3 cross ribs.
    s=s.cut(box(-59,59,y0-0.2,y1+0.2,20,70))
    # re-add three thin ribs across window for stiffness
    for zc in (25,45,65):
        s=s.fuse(box(-60,60,y0,y1,zc-2,zc+2))
    # M3 mount holes at shell bosses
    for x in (-66,66):
        for z in (14,76):
            s=s.cut(cyl_y(1.75,y0-0.2,y1+0.2,x,z))
    # 20-25 mm velcro slots, two straps
    for x in (-42,42):
        for z in (14,76):
            s=s.cut(box(x-12,x+12,y0-0.2,y1+0.2,z-2,z+2))
    # bottom support lip and small side keepers, battery remains strap-removable
    s=s.fuse(box(-71,71,y1-0.1,y1+6.0,7.5,9.5))
    s=s.fuse(box(-73,-70.4,y1-0.1,y1+4.5,12,78))
    s=s.fuse(box(70.4,73,y1-0.1,y1+4.5,12,78))
    return s.clean()

def make_esp_sled():
    # Right-side universal plate, kept thin to preserve >=5 mm depth clearance for 25 mm ref body.
    x0,x1=78.0,114.0; z0,z1=14.0,76.0
    y0=SEP_R+1.90; y1=y0+1.6
    s=box(x0,x1,y0,y1,z0,z1)
    # Mount holes to shallow self-tap bosses
    for x in (82.0,108.0):
        for z in (18.0,72.0):
            s=s.cut(cyl_y(1.35,y0-0.2,y1+0.2,x,z))
    # universal cable-tie slots, avoid assumptions about board hole pattern
    for z in (29.0,61.0):
        s=s.cut(box(81,87,y0-0.2,y1+0.2,z-1.8,z+1.8))
        s=s.cut(box(105,111,y0-0.2,y1+0.2,z-1.8,z+1.8))
    return s.clean()

def make_bridge_plate():
    # One part used twice (top and bottom); exported near origin for printing.
    s=box(-20,20,0,3.0,-5,5)
    for x in (-12,12):
        s=s.cut(cyl_y(1.75,-0.2,3.2,x,0))
    return s.clean()

def make_belt_loop(side='R'):
    # Assembly coordinates. Four screws + external vertical bar create sealed 50 mm webbing loop.
    sign=1 if side=='R' else -1
    wallx=120.0*sign
    outx=129.0*sign
    # mounting ear/slabs at top/bottom, plus outer bar and spacer arms
    parts=[]
    # two mounting pads at z~16 and74, y 2..24, thickness 4.0 outward
    if side=='R':
        parts += [box(120.2,124.2,2,24,10,22), box(120.2,124.2,2,24,68,80)]
        # spacer arms bridge to outer bar, leave 5 mm clear x-gap from shell
        parts += [box(123.8,129.0,7,19,13,19), box(123.8,129.0,7,19,71,77)]
        parts += [box(128.0,132.0,7,19,19,71)]
        s=solid_union(parts)
        for by in (7,19):
            for bz in (16,74): s=s.cut(cyl_x(1.75,119.8,124.6,by,bz))
    else:
        parts += [box(-124.2,-120.2,2,24,10,22), box(-124.2,-120.2,2,24,68,80)]
        parts += [box(-129.0,-123.8,7,19,13,19), box(-129.0,-123.8,7,19,71,77)]
        parts += [box(-132.0,-128.0,7,19,19,71)]
        s=solid_union(parts)
        for by in (7,19):
            for bz in (16,74): s=s.cut(cyl_x(1.75,-124.6,-119.8,by,bz))
    return s.clean()

def make_fan_grille(fan_x=0.0, fan_z=0.0, assembly=False):
    # Print part in assembly coordinates if assembly=True; otherwise centered around origin in X/Z.
    cx=fan_x if assembly else 0.0; cz=fan_z if assembly else 0.0
    y0=-39.0 if assembly else 0.0; y1=-36.0 if assembly else 3.0
    # outer 48 square plate, center Ø38 opening + bars
    s=box(cx-24,cx+24,y0,y1,cz-24,cz+24)
    s=s.cut(cyl_y(19.0,y0-0.2,y1+0.2,cx,cz))
    # add protective cross bars over aperture (2.0 mm wide)
    s=s.fuse(box(cx-19,cx+19,y0,y1,cz-1.1,cz+1.1))
    s=s.fuse(box(cx-1.1,cx+1.1,y0,y1,cz-19,cz+19))
    # corner air reliefs / filter exposure keep ring modest
    # screw holes 32 pitch
    for dx in (-16,16):
        for dz in (-16,16):
            s=s.cut(cyl_y(1.75,y0-0.2,y1+0.2,cx+dx,cz+dz))
    return s.clean()

def make_pcm_carrier():
    # Universal carrier for up to ~160x64x8 mm PCM pack, secured by Velcro.
    # Assembly coordinates body-side of service cover. Pack rests against service cover;
    # this part is a perimeter keeper/strap carrier, not a sealed PCM box.
    y0=YH+0.25+P['service_cover_t']+6.05; y1=y0+2.4
    s=box(-86,86,y0,y1,7,83)
    # Large central lightening/contact window; mounting zones remain solid.
    s=s.cut(box(-75,75,y0-0.2,y1+0.2,27,63))
    # edge lips, sized for up to 8 mm nominal PCM thickness
    lip_h=8.0
    s=s.fuse(box(-86,-82,y1-0.1,y1+lip_h,9,81))
    s=s.fuse(box(82,86,y1-0.1,y1+lip_h,9,81))
    s=s.fuse(box(-82,82,y1-0.1,y1+lip_h,7,11))
    s=s.fuse(box(-82,82,y1-0.1,y1+lip_h,79,83))
    # M3 clearance holes matching the four service-cover PCM bosses.
    for px in (-65,65):
        for pz in (20,70):
            s=s.cut(cyl_y(1.75,y0-0.2,y1+0.2,px,pz))
    # 24 mm Velcro slots, two straps; located in solid top/bottom bands.
    for x in (-55,55):
        for z in (14,76):
            s=s.cut(box(x-12,x+12,y0-0.2,y1+0.2,z-1.8,z+1.8))
    return s.clean()

def make_ref_fan(cx,cz):
    # Simplified 40x40x10.3 body occupying pocket; y front -35.7 to -25.4
    return box(cx-20,cx+20,-35.9,-25.6,cz-20,cz+20)

def make_ref_battery():
    # 140 x 70 x 15, placed on cradle; X,Z planar, Y thickness.
    y0=SEP_R+8.7; y1=y0+15.0
    return box(-70,70,y0,y1,10,80)

def make_ref_esp():
    # 30 x 55 x 25, right side. Mounted directly against universal sled.
    y0=SEP_R+3.50; y1=y0+25.0
    return box(81,111,y0,y1,17.5,72.5)

def make_ref_pcm():
    y0=YH+P['service_cover_t']+9.0; y1=y0+8.0
    return box(-80,80,y0,y1,13,77)

# Optional adapters: capsule socket -> round socket.
def make_duct_adapter(round_id=32.4, print_center=True):
    # Standalone sealed step adapter. Bottom is a capsule socket that slips over the
    # integrated 44x30 riser; top is a circular socket for the stated hose OD.
    z0=0.0
    outer_x,outer_y=50.0,38.0
    inner_x,inner_y=44.5,30.5  # ~0.25 mm nominal side clearance over 44x30 riser
    sleeve=ring_capsule_z(outer_x,outer_y,inner_x,inner_y,z0,6.2,0,0)
    # sealed transition plate with a round flow aperture
    plate=capsule_z(outer_x,outer_y,5.7,7.7,0,0).cut(cyl_z(round_id/2,5.5,7.9,0,0))
    # top circular socket, 2 mm wall
    top_outer=round_id+4.0
    tube=cyl_z(top_outer/2,7.2,20.0,0,0).cut(cyl_z(round_id/2,7.0,20.2,0,0))
    return sleeve.fuse(plate).fuse(tube).clean()

# -------------------------
# Build
# -------------------------
print('Building shells...')
left=make_half('L'); print(' left solids',len(left.Solids()),'vol',left.Volume())
right=make_half('R'); print(' right solids',len(right.Solids()),'vol',right.Volume())
cover=make_service_cover(True); cover_flat=make_service_cover(False); print(' cover solids',len(cover.Solids()),'flat',len(cover_flat.Solids()))
battery_cradle=make_battery_cradle(); print(' battery cradle',len(battery_cradle.Solids()))
esp_sled=make_esp_sled(); print(' esp sled',len(esp_sled.Solids()))
bridge=make_bridge_plate(); print(' bridge',len(bridge.Solids()))
beltL=make_belt_loop('L'); beltR=make_belt_loop('R')
grille=make_fan_grille(); pcm=make_pcm_carrier()

# adapters may fail on some OCC versions; build with fallback rings if needed
adapters={}
for d in (32.4,25.4):
    try:
        adapters[d]=make_duct_adapter(d)
        print(' adapter',d,'solids',len(adapters[d].Solids()))
    except Exception as e:
        print(' adapter loft failed',d,e)

parts={
    '01_LEFT_SHELL_V7':left,
    '02_RIGHT_SHELL_V7':right,
    '03_SERVICE_COVER_PCM_READY_V7':cover,
    '03B_SERVICE_COVER_FLAT_NO_PCM_V7':cover_flat,
    '04_BATTERY_CRADLE_140x70_V7':battery_cradle,
    '05_ESP_UNIVERSAL_SLED_V7':esp_sled,
    '06_CENTER_BRIDGE_PLATE_PRINT_2X_V7':bridge,
    '07_BELT_LOOP_LEFT_50mm_V7':beltL,
    '08_BELT_LOOP_RIGHT_50mm_V7':beltR,
    '09_FAN_FILTER_GRILLE_40mm_PRINT_2X_V7':grille,
    '10_PCM_CARRIER_UNIVERSAL_V7':pcm,
}
if 32.4 in adapters: parts['11_DUCT_ADAPTER_TO_32mm_OD_HOSE_V7']=adapters[32.4]
if 25.4 in adapters: parts['12_DUCT_ADAPTER_TO_25mm_OD_HOSE_COMPAT_V7']=adapters[25.4]

# Export each part
for name,shape in parts.items():
    step=OUT/(name+'.step'); stl=OUT/(name+'.stl')
    exporters.export(shape,str(step))
    exporters.export(shape,str(stl),tolerance=0.08,angularTolerance=0.1)
    print(' exported',name)

# Reference components
refs={
    'REF_FAN_LEFT_40x40x10p3':make_ref_fan(-52,42),
    'REF_FAN_RIGHT_40x40x10p3':make_ref_fan(52,42),
    'REF_POWERBANK_140x70x15':make_ref_battery(),
    'REF_ESP_30x55x25':make_ref_esp(),
    'REF_PCM_160x64x8':make_ref_pcm(),
}
for name,shape in refs.items(): exporters.export(shape,str(OUT/(name+'.step')))

# Assembly components in actual positions.
assy=cq.Assembly(name='HeatSentry_V7_TRUE_FINAL_ASSEMBLY')
assy.add(left,name='LeftShell')
assy.add(right,name='RightShell')
assy.add(cover,name='ServiceCover')
assy.add(battery_cradle,name='BatteryCradle')
assy.add(esp_sled,name='ESPSled')
assy.add(make_belt_loop('L'),name='BeltLoopL')
assy.add(make_belt_loop('R'),name='BeltLoopR')
assy.add(make_fan_grille(-52,42,assembly=True),name='FanGrilleL')
assy.add(make_fan_grille(52,42,assembly=True),name='FanGrilleR')
# bridge plates transformed into assembly positions: local bridge has y 0..3, z -5..5
# top/bottom plates sit inside rear, y 28.7..31.7, centers z=7/83
for i,zc in enumerate((7.0,83.0),1):
    loc=cq.Location(cq.Vector(0,26.0,zc))
    assy.add(bridge,name=f'CenterBridge{i}',loc=loc)
# PCM carrier already in assembly coordinates; include optional
assy.add(pcm,name='PCMCarrier')
# refs
for name,shape in refs.items(): assy.add(shape,name=name)
assy.save(str(OUT/'HeatSentry_V7_TRUE_FINAL_ASSEMBLY.step'),exportType='STEP',mode='default')

# Exploded assembly (simple manual translations for visibility)
exp=cq.Assembly(name='HeatSentry_V7_TRUE_FINAL_EXPLODED')
exp.add(left,name='LeftShell',loc=cq.Location(cq.Vector(-8,0,0)))
exp.add(right,name='RightShell',loc=cq.Location(cq.Vector(8,0,0)))
exp.add(cover,name='ServiceCover',loc=cq.Location(cq.Vector(0,25,0)))
exp.add(battery_cradle,name='BatteryCradle',loc=cq.Location(cq.Vector(0,15,0)))
exp.add(esp_sled,name='ESPSled',loc=cq.Location(cq.Vector(0,12,0)))
exp.add(beltL,name='BeltLoopL',loc=cq.Location(cq.Vector(-8,0,0)))
exp.add(beltR,name='BeltLoopR',loc=cq.Location(cq.Vector(8,0,0)))
exp.add(make_fan_grille(-52,42,assembly=True),name='FanGrilleL',loc=cq.Location(cq.Vector(0,-10,0)))
exp.add(make_fan_grille(52,42,assembly=True),name='FanGrilleR',loc=cq.Location(cq.Vector(0,-10,0)))
exp.add(pcm,name='PCMCarrier',loc=cq.Location(cq.Vector(0,35,0)))
exp.save(str(OUT/'HeatSentry_V7_TRUE_FINAL_EXPLODED.step'),exportType='STEP',mode='default')

# Param JSON
with open(OUT/'V7_PARAMETERS.json','w',encoding='utf-8') as f: json.dump(P,f,indent=2,ensure_ascii=False)

# Validation primitive calculations
fan_open_area=math.pi*(37.0/2)**2
r=P['top_port_capsule_y']/2
straight=P['top_port_capsule_x']-P['top_port_capsule_y']
top_area=straight*P['top_port_capsule_y']+math.pi*r*r
validation={
    'left_shell_solids':len(left.Solids()),
    'right_shell_solids':len(right.Solids()),
    'left_bbox':[left.BoundingBox().xlen,left.BoundingBox().ylen,left.BoundingBox().zlen],
    'right_bbox':[right.BoundingBox().xlen,right.BoundingBox().ylen,right.BoundingBox().zlen],
    'service_cover_bbox':[cover.BoundingBox().xlen,cover.BoundingBox().ylen,cover.BoundingBox().zlen],
    'air_chamber_depth':SEP_F-FRONT_IN,
    'electronics_depth':REAR_IN-SEP_R,
    'fan_back_plenum_depth':SEP_F-(-23.25),
    'fan_backer_open_area_mm2':fan_open_area,
    'top_port_open_area_mm2':top_area,
    'top_to_fan_area_ratio':top_area/fan_open_area,
    'esp_nominal_clearance_to_rear_inner_mm':REAR_IN-(SEP_R+3.55+25.0),
    'battery_nominal_clearance_to_rear_inner_mm':REAR_IN-(SEP_R+8.9+15.0),
}
with open(OUT/'V7_VALIDATION_RAW.json','w',encoding='utf-8') as f: json.dump(validation,f,indent=2)

print('DONE',OUT)
