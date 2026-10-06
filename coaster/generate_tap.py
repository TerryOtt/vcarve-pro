"""Generate and geometrically inspect a six-file, pointed-V-bit wood inlay.

This is an independent CAM implementation. It does not reproduce or claim to
have executed VCarve's toolpaths. All coordinates are inches in the active work
coordinate system, with Z=0 on the original stock top.
"""
from pathlib import Path
import json
import math
import re
import sys
import time
import zipfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / '.tools' / 'cam'))
import numpy as np
import shapely
from shapely import affinity
from shapely.geometry import Polygon, LineString, box
from shapely.ops import unary_union
from scipy.ndimage import binary_dilation, grey_erosion, map_coordinates
from PIL import Image, ImageDraw

OUTPUT = ROOT.parent / 'PlanetCNC'
OUTPUT.mkdir(exist_ok=True)
TAN = math.tan(math.radians(30))
D = 0.125
GAP = 0.005
INSERTION = D - GAP
SURFACE_GAP = 0.050
PLUG_CUT = INSERTION + SURFACE_GAP
SIDE_FIT = 0.0005
STOCK = box(0, 0, 4, 4)
SAFE_Z = 1.0
APPROACH_Z = 0.05
RPM = 18000
LEAVE = 0.002
V_INCREMENT = 0.005
GRID = 0.004
V_FLAT_STEP = 0.0025
FINISH_ROW = 0.001
FINISH_SAMPLE = 0.001
FINISH_INCREMENT = 0.0125
REPORT = {}


def log(message):
    print(message, flush=True)


def buffer(geometry, amount):
    return geometry.buffer(amount, quad_segs=32)


def load_shape():
    svg = ET.parse(ROOT / 'purdue-coaster-logo-3in.svg').getroot()
    shape = Polygon()
    for path in svg.findall('.//{http://www.w3.org/2000/svg}path'):
        for loop in re.findall(r'M\s+(.*?)\s+Z', path.attrib['d']):
            coords = [tuple(float(v) for v in point.split(',')) for point in loop.split(' L ')]
            shape = shape.symmetric_difference(Polygon([(x, 4-y) for x, y in coords]))
    assert shape.is_valid
    assert np.allclose(shape.bounds, [0.5, 1.19717288, 3.5, 2.80282712], atol=1e-7)
    return shape


MAPLE_SHAPE = load_shape()
WALNUT_SHAPE = buffer(affinity.scale(MAPLE_SHAPE, xfact=-1, yfact=1, origin=(2, 2)), -SIDE_FIT)
x0, y0, x1, y1 = MAPLE_SHAPE.bounds
PLUG_BOUNDARY = box(x0-0.25, y0-0.25, x1+0.25, y1+0.25)
assert STOCK.covers(PLUG_BOUNDARY)


def polygons(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == 'Polygon':
        return [geometry]
    result = []
    for member in getattr(geometry, 'geoms', []):
        result.extend(polygons(member))
    return result


def lines(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type in ('LineString', 'LinearRing'):
        return [list(geometry.coords)]
    result = []
    for member in getattr(geometry, 'geoms', []):
        result.extend(lines(member))
    return result


def boundary_paths(geometry):
    result = []
    for polygon in polygons(geometry):
        result.append(list(polygon.exterior.coords))
        result.extend(list(ring.coords) for ring in polygon.interiors)
    return result


def raster_paths(geometry, step):
    if geometry.is_empty:
        return []
    xmin, ymin, xmax, ymax = geometry.bounds
    rows = np.arange(math.ceil(ymin / step) * step, ymax + 1e-10, step)
    result = []
    for row, y in enumerate(rows):
        pieces = lines(geometry.intersection(LineString([(xmin-1, y), (xmax+1, y)])))
        pieces.sort(key=lambda p: p[0][0], reverse=bool(row % 2))
        for piece in pieces:
            if LineString(piece).length < 1e-5:
                continue
            a, b = piece[0], piece[-1]
            result.append([b, a] if row % 2 else [a, b])
    return result


def depths(limit, increment):
    return [min(limit, (i+1)*increment) for i in range(math.ceil(limit/increment - 1e-10))]


def target_region(piece, depth):
    if piece == 'Maple':
        return buffer(MAPLE_SHAPE, -depth*TAN)
    island = buffer(WALNUT_SHAPE, (depth-INSERTION)*TAN)
    return PLUG_BOUNDARY.difference(island)


def signed_distance(x, y, geometry):
    points = shapely.points(np.asarray(x), np.asarray(y))
    distance = shapely.distance(points, geometry.boundary)
    return np.where(shapely.contains(geometry, points), -distance, distance)


def desired_depth(piece, x, y):
    if piece == 'Maple':
        return np.clip(-signed_distance(x, y, MAPLE_SHAPE)/TAN, 0, D)
    result = np.clip(INSERTION + signed_distance(x, y, WALNUT_SHAPE)/TAN, 0, PLUG_CUT)
    return np.where(shapely.contains(PLUG_BOUNDARY, shapely.points(np.asarray(x), np.asarray(y))), result, 0)


def simplify_3d(points, tolerance=0.00001):
    array=np.array(points,dtype=float)
    if len(array)<=2: return list(map(tuple,array))
    delta=array[-1]-array[0]
    length2=float(delta@delta)
    if length2<1e-20:
        distance=np.linalg.norm(array-array[0],axis=1)
    else:
        fraction=np.clip((array-array[0])@delta/length2,0,1)
        distance=np.linalg.norm(array-array[0]-fraction[:,None]*delta,axis=1)
    split=int(np.argmax(distance))
    if distance[split]<=tolerance: return [tuple(array[0]),tuple(array[-1])]
    return simplify_3d(array[:split+1],tolerance)[:-1]+simplify_3d(array[split:],tolerance)


class Program:
    def __init__(self, piece, suffix, diameter, feed, plunge, pass_depth, stepover, vbit=False):
        self.piece, self.suffix, self.diameter = piece, suffix, diameter
        self.feed, self.plunge = feed, plunge
        self.pass_depth, self.stepover, self.vbit = pass_depth, stepover, vbit
        self.commands = []
        self.paths = []
        self.position = None
        self.max_depth = 0
        self.chip_distance = 0.0
        self.feed_seconds = 0.0
        self.path_count = 0
        self.fast_entries = 0

    @property
    def filename(self):
        return f'{self.piece}_{self.suffix}.tap'

    def move(self, mode, x=None, y=None, z=None, feed=None):
        old = self.position
        current = [None, None, None] if old is None else list(old)
        values = [x, y, z]
        fields = [mode]
        for index, (axis, value) in enumerate(zip('XYZ', values)):
            if value is not None:
                value = float(f'{value:.6f}')
                fields.append(f'{axis}{value:.6f}')
                current[index] = value
        if feed is not None:
            fields.append(f'F{feed:.3f}')
        self.commands.append(' '.join(fields))
        self.position = tuple(current)
        if old is not None and all(v is not None for v in old + self.position):
            if mode=='G1':
                length = float(np.linalg.norm(np.array(current)-np.array(old)))
                self.feed_seconds += length/float(feed)*60
            if mode == 'G1' and min(old[2], current[2]) < 0:
                self.paths.append((old, self.position))
                self.chip_distance += length
        if z is not None:
            self.max_depth = max(self.max_depth, -float(z))

    def start_path(self, point, cleared_depth=0, link=None):
        if link is not None:
            self.move('G0',z=link[0][2])
            for x,y,z in link[1:]:
                self.move('G1',x=x,y=y,z=z,feed=self.feed)
            if cleared_depth>0.01:
                self.move('G0',z=-cleared_depth)
        else:
            self.move('G0', z=SAFE_Z)
            self.move('G0', x=point[0], y=point[1])
            self.move('G0', z=-cleared_depth if cleared_depth>0.01 else APPROACH_Z)
        self.path_count += 1
        if cleared_depth>0.01: self.fast_entries+=1

    def cut_path(self, coordinates, depth, previous_depth=0, legal_region=None):
        if len(coordinates) < 2:
            return
        coordinates = [(float(x), float(y)) for x, y in coordinates]
        if self.position and abs(self.position[2]+depth)<1e-6 and legal_region is not None:
            connector=LineString([self.position[:2],coordinates[0]])
            if connector.length<1.0 and legal_region.covers(connector):
                self.move('G1',x=coordinates[0][0],y=coordinates[0][1],z=-depth,feed=self.feed)
                for x,y in coordinates[1:]:
                    self.move('G1',x=x,y=y,z=-depth,feed=self.feed)
                return
        self.start_path(coordinates[0])
        if self.vbit:
            self.move('G1', z=-depth, feed=self.plunge)
            for x, y in coordinates[1:]:
                self.move('G1', x=x, y=y, feed=self.feed)
            return
        # Feed to the preceding layer, then ramp at <=2 degrees along this
        # same allowed centerline. No through-cut or tool-change macro.
        self.move('G1', z=-previous_depth, feed=self.plunge)
        remaining = (depth-previous_depth)/math.tan(math.radians(2))
        route = LineString(coordinates)
        if route.length < 1e-8:
            return
        if route.length < 0.005:
            # A tiny center-locus island has insufficient room for a ramp.
            # Use slow 0.005 inch pecks rather than thousands of reversals.
            for small_depth in depths(depth-previous_depth,0.005):
                self.move('G1',z=-(previous_depth+small_depth),feed=min(5,self.plunge))
            for x,y in coordinates[1:]:
                self.move('G1',x=x,y=y,z=-depth,feed=self.feed)
            return
        closed = np.linalg.norm(np.array(coordinates[0])-coordinates[-1]) < 1e-8
        traversed, forward = 0.0, True
        current_depth = previous_depth
        cycles = 0
        while remaining > 1e-8:
            sequence = coordinates if forward else list(reversed(coordinates))
            for a, b in zip(sequence, sequence[1:]):
                length = math.dist(a, b)
                if length < 1e-9:
                    continue
                use = min(length, remaining)
                fraction = use/length
                point = np.array(a)+(np.array(b)-a)*fraction
                current_depth += use*math.tan(math.radians(2))
                self.move('G1', x=point[0], y=point[1], z=-min(depth,current_depth), feed=min(20,self.feed))
                remaining -= use
                if remaining <= 1e-8:
                    break
            cycles += 1
            if not closed:
                forward = not forward
            assert cycles < 10000
        # Finish the full line/loop from the current position, following the
        # existing route so the connector cannot cross an island.
        if closed:
            segment = min(range(len(coordinates)-1), key=lambda i: LineString(coordinates[i:i+2]).distance(shapely.Point(self.position[:2])))
            finish = coordinates[segment+1:] + coordinates[1:segment+1] + [self.position[:2]]
        else:
            finish = [coordinates[0], coordinates[-1]]
        for x, y in finish:
            self.move('G1', x=x, y=y, z=-depth, feed=self.feed)

    def cut_variable(self, coordinates, cleared_depth=0, link=None):
        if len(coordinates) < 2:
            return
        coordinates=simplify_3d(coordinates)
        self.start_path(coordinates[0][:2],cleared_depth,link)
        self.move('G1', z=-coordinates[0][2], feed=self.plunge)
        for x, y, depth in coordinates[1:]:
            self.move('G1', x=x, y=y, z=-depth, feed=self.feed)

    def text(self):
        limit = D if self.piece == 'Maple' else PLUG_CUT
        header = [
            f'(PURDUE COASTER - {self.filename})',
            '(INDEPENDENT CAM - NOT A VCARVE EXPORT)',
            '(STOCK 4 X 4 X 0.5 INCH)',
            '(XY ZERO LOWER LEFT - Z ZERO ORIGINAL STOCK TOP)',
            f'(INSTALL {self.diameter:.3f} END MILL)' if not self.vbit else '(INSTALL POINTED 60 DEG V-BIT - 3 FLUTES - QUARTER SHANK)',
            f'(RUN ORDER QUARTER THEN EIGHTH THEN V60 FOR THIS STOCK)',
            f'(MAX CUT {limit:.3f} INCH - SAFE Z {SAFE_Z:.3f} INCH)',
            '(V-BIT MUST HAVE AT LEAST 0.170 INCH USABLE CUTTING HEIGHT)',
            '(TEST PAIR AND CHECK TOOL GEOMETRY AND WORKHOLDING BEFORE PRODUCTION)',
            'G20', 'G90', 'G17', 'G94', 'G40', 'G80',
            f'G0 Z{SAFE_Z:.6f}', f'S{RPM} M3', 'G4 P3',
        ]
        return '\r\n'.join(header+self.commands+[f'G0 Z{SAFE_Z:.6f}', 'M5', 'M30', ''])

    def save(self):
        (OUTPUT/self.filename).write_bytes(self.text().encode('ascii'))


def make_clearance(piece, diameter, step, feed, plunge, increment, suffix, previous=None):
    program = Program(piece, suffix, diameter, feed, plunge, increment, step)
    limit = D if piece == 'Maple' else PLUG_CUT
    coverage = []
    prior_depth = 0
    for depth in depths(limit, increment):
        center_region = buffer(target_region(piece, depth), -(diameter/2+LEAVE))
        legal_region=buffer(center_region,0.0000015)
        shapely.prepare(legal_region)
        if previous:
            emptied = unary_union([shape for cut_depth,shape in previous if cut_depth+1e-8 >= depth])
            if not emptied.is_empty:
                center_region = center_region.difference(buffer(emptied, -diameter/2))
        if not center_region.is_empty:
            for path in boundary_paths(center_region)+raster_paths(center_region,step):
                program.cut_path(path,depth,prior_depth,legal_region)
            coverage.append((depth,buffer(center_region,diameter/2)))
        prior_depth = depth
    log(f'{program.filename}: {program.path_count} paths, {len(program.paths)} cutting segments')
    return program,coverage


def make_vbit(piece, coverage):
    program = Program(piece,'03_V60',0.25,50,15,FINISH_INCREMENT,V_FLAT_STEP,True)
    limit = D if piece == 'Maple' else PLUG_CUT
    for depth in depths(limit,V_INCREMENT):
        if piece == 'Maple':
            center_shape = buffer(MAPLE_SHAPE,-depth*TAN)
            paths = boundary_paths(center_shape)
            legal_region=buffer(center_shape,0.0000015)
        else:
            center_shape = buffer(WALNUT_SHAPE,(depth-INSERTION)*TAN)
            allowed = buffer(PLUG_BOUNDARY,-depth*TAN)
            paths = []
            for path in boundary_paths(center_shape):
                paths.extend(lines(LineString(path).intersection(allowed)))
            legal_region=buffer(allowed.difference(center_shape),0.0000015)
        shapely.prepare(legal_region)
        for path in paths:
            program.cut_path(path,depth,legal_region=legal_region)
    # Flat remnants are finished from the swept-volume result rather than
    # repeatedly plunging into every tiny boolean polygon at every depth.
    log(f'{program.filename}: rough contours, {len(program.paths)} segments')
    return program


class Simulation:
    def __init__(self,piece):
        self.piece = piece
        self.axis = np.arange(0,4+GRID/2,GRID)
        self.surface = np.zeros((len(self.axis),len(self.axis)),dtype=np.float32)
        self.X,self.Y = np.meshgrid(self.axis,self.axis)
        self.ideal = desired_depth(piece,self.X,self.Y)

    def apply(self,program,start=0):
        for a,b in program.paths[start:]:
            h0,h1 = -a[2],-b[2]
            radius = max(h0,h1,0)*TAN if program.vbit else program.diameter/2
            xmin,xmax = min(a[0],b[0])-radius,max(a[0],b[0])+radius
            ymin,ymax = min(a[1],b[1])-radius,max(a[1],b[1])+radius
            ix0,ix1 = max(0,math.ceil(xmin/GRID)),min(len(self.axis),math.floor(xmax/GRID)+1)
            iy0,iy1 = max(0,math.ceil(ymin/GRID)),min(len(self.axis),math.floor(ymax/GRID)+1)
            if ix0>=ix1 or iy0>=iy1:
                continue
            x=self.X[iy0:iy1,ix0:ix1]; y=self.Y[iy0:iy1,ix0:ix1]
            dx,dy=b[0]-a[0],b[1]-a[1]
            length=math.hypot(dx,dy)
            if length<1e-10:
                distance=np.hypot(x-a[0],y-a[1])
                cut=max(h0,h1)-distance/TAN if program.vbit else np.where(distance<=radius,max(h0,h1),0)
            else:
                parallel=((x-a[0])*dx+(y-a[1])*dy)/length
                perpendicular=np.abs((x-a[0])*dy-(y-a[1])*dx)/length
                slope=(h1-h0)/length
                if program.vbit:
                    if abs(slope)<1/TAN-1e-10:
                        along=np.clip(parallel+slope*perpendicular/math.sqrt(1/TAN**2-slope**2),0,length)
                    else:
                        along=np.full_like(parallel,length if slope>0 else 0)
                    distance=np.hypot(parallel-along,perpendicular)
                    cut=h0+slope*along-distance/TAN
                else:
                    feasible=perpendicular<=radius
                    spread=np.sqrt(np.maximum(0,radius**2-perpendicular**2))
                    low=np.maximum(0,parallel-spread); high=np.minimum(length,parallel+spread)
                    along=high if slope>=0 else low
                    cut=np.where(feasible&(low<=high),h0+slope*along,0)
            target=self.surface[iy0:iy1,ix0:ix1]
            np.maximum(target,np.maximum(0,cut),out=target)

    def refine(self,program,threshold=0.00035):
        # Locate residual stock from actual swept-tool simulation, then finish
        # only those neighborhoods with exact-distance variable-depth scans.
        mask=(self.ideal-self.surface)>threshold
        if self.piece=='Walnut':
            # The outer clearance rectangle is a workholding boundary, not
            # part of the mating inlay. Its deliberately retained corner
            # remnants do not belong in the V-bit's finishing area.
            legal=buffer(PLUG_BOUNDARY,-PLUG_CUT*TAN-0.0001)
            mask &= shapely.contains(legal,shapely.points(self.X,self.Y))
        mask=binary_dilation(mask,iterations=2)
        xy_allowed=MAPLE_SHAPE if self.piece=='Maple' else PLUG_BOUNDARY
        maximum=D if self.piece=='Maple' else PLUG_CUT
        cells=math.ceil(maximum*TAN/GRID)+1
        yy,xx=np.mgrid[-cells:cells+1,-cells:cells+1]
        radial=np.hypot(xx,yy)*GRID
        self.cone_field=grey_erosion(self.surface,footprint=radial<=maximum*TAN+GRID,
                                     structure=-radial/TAN,mode='constant',cval=0)
        added_before=len(program.paths)
        active_rows=np.flatnonzero(mask.any(axis=1))
        for row in active_rows:
            changes=np.flatnonzero(np.diff(np.r_[False,mask[row],False].astype(int)))
            intervals=list(zip(changes[::2],changes[1::2]))
            # Four fine rows fill each coarse simulation band.
            for y in self.axis[row]+np.arange(-GRID/2,GRID/2,FINISH_ROW):
                for begin,end in intervals:
                    xmin=max(0,(begin-0.5)*GRID); xmax=min(4,(end-0.5)*GRID)
                    x=np.linspace(xmin,xmax,max(2,math.ceil((xmax-xmin)/FINISH_SAMPLE)+1))
                    yy=np.full_like(x,y)
                    depth=desired_depth(self.piece,x,yy)
                    inside=shapely.contains(xy_allowed,shapely.points(x,yy))
                    if self.piece=='Walnut':
                        edge=shapely.distance(shapely.points(x,yy),PLUG_BOUNDARY.boundary)
                        inside &= edge>=depth*TAN+0.00002
                    # An extra 0.000020 inch stays above the exact target;
                    # numerical chord error is checked again by simulation.
                    depth=np.maximum(0,depth-0.000020)
                    inside &= depth>0.00001
                    transitions=np.flatnonzero(np.diff(np.r_[False,inside,False].astype(int)))
                    for first,last in zip(transitions[::2],transitions[1::2]):
                        pts=list(zip(x[first:last],yy[first:last],depth[first:last]))
                        if row%2: pts.reverse()
                        if len(pts)>=2:
                            # Estimate the already-empty cone depth on a
                            # <=0.004 inch sampling interval. The 0.010 inch
                            # total spatial guard bounds interpolation/grid
                            # uncertainty. Increase actual cone penetration
                            # at most 0.010 inch per additional finishing pass.
                            array=np.array(pts)
                            existing=self.existing_cone_depth_array(array[:,0],array[:,1],array[:,2])
                            passes=max(1,math.ceil(float(np.max(array[:,2]-existing))/FINISH_INCREMENT))
                            previous=existing
                            for number in range(1,passes+1):
                                stage=np.minimum(array[:,2],existing+number*FINISH_INCREMENT)
                                current=list(zip(array[:,0],array[:,1],stage))
                                cleared_depth=max(0,min(stage[0]-0.010,previous[0]-0.006))
                                link=self.feed_link(program,current[0])
                                program.cut_variable(current,cleared_depth,link)
                                previous=stage
        self.apply(program,added_before)
        log(f'{program.filename}: adaptive finish added {len(program.paths)-added_before} segments')

    def existing_cone_depth(self,x,y,requested):
        # Bound rapid approach by the simulated volume already cut by this
        # same V-bit. A 0.006 inch guard exceeds the coarse grid's spatial
        # uncertainty; keep a further 0.010 inch above the requested finish.
        radius=requested*TAN
        ix0=max(0,math.ceil((x-radius)/GRID)); ix1=min(len(self.axis),math.floor((x+radius)/GRID)+1)
        iy0=max(0,math.ceil((y-radius)/GRID)); iy1=min(len(self.axis),math.floor((y+radius)/GRID)+1)
        if ix0>=ix1 or iy0>=iy1: return 0
        distance=np.hypot(self.X[iy0:iy1,ix0:ix1]-x,self.Y[iy0:iy1,ix0:ix1]-y)
        bound=float(np.min(self.surface[iy0:iy1,ix0:ix1]+distance/TAN))-0.006
        return max(0,min(requested,bound))

    def existing_cone_depth_array(self,x,y,requested):
        # Bilinear lookup avoids artificial grid-period depth oscillation.
        # 0.011 inch guard covers both swept-height sampling and bilinear
        # interpolation uncertainty at this 0.004 inch grid resolution.
        coordinate=np.vstack((np.asarray(y)/GRID,np.asarray(x)/GRID))
        bound=map_coordinates(self.cone_field,coordinate,order=1,mode='nearest')-0.011
        return np.maximum(0,np.minimum(requested,bound))

    def feed_link(self,program,first):
        if not program.position or program.position[2] is None: return None
        a=np.array(program.position[:2]); b=np.array(first[:2])
        length=float(np.linalg.norm(b-a))
        if length>0.25 or program.position[2]>0: return None
        count=max(2,math.ceil(length/0.005)+1)
        fraction=np.linspace(0,1,count)
        xy=a[None,:]+fraction[:,None]*(b-a)[None,:]
        requested=np.full(count,min(first[2],max(0,-program.position[2])))
        cleared=self.existing_cone_depth_array(xy[:,0],xy[:,1],requested)
        cleared=np.maximum(0,cleared-length/(count-1)/(2*TAN))
        # Short connectors stay inside the machining rectangle. Feed through
        # the proven empty cone volume; where none exists, feed 0.025 inch
        # above the original stock. Workholding must be outside this area.
        z=np.where(cleared>0.002,-cleared,0.025)
        pts=list(zip(xy[:,0],xy[:,1],z))
        return simplify_3d(pts,0.000005)


def check_program(program):
    text=program.text()
    current=[None,None,None]
    segments=0
    for line in text.splitlines():
        if not line or line.startswith('('): continue
        if line.startswith(('G0 ','G1 ')):
            previous=list(current)
            for axis,value in re.findall(r'([XYZ])(-?\d+(?:\.\d+)?)',line):
                current['XYZ'.index(axis)]=float(value)
            if current[0] is not None: assert -1e-6<=current[0]<=4+1e-6
            if current[1] is not None: assert -1e-6<=current[1]<=4+1e-6
            if current[2] is not None: assert current[2]>=-(D if program.piece=='Maple' else PLUG_CUT)-1e-6
            if line.startswith('G0 ') and previous[0] is not None and current[0] is not None:
                if current[:2]!=previous[:2]: assert current[2]>=APPROACH_Z
            if line.startswith('G1 '):
                assert re.search(r'F\d',line)
                segments+=1
    assert 'G20\r\n' in text and 'G90\r\n' in text
    assert 'M6' not in text and 'G92' not in text and 'G53' not in text
    assert text.endswith('M5\r\nM30\r\n')
    assert program.max_depth<0.5
    return {'filename':program.filename,'maximum_cut_depth_in':program.max_depth,
            'tool_diameter_in':program.diameter,'feed_ipm':program.feed,
            'plunge_ipm':program.plunge,'rpm':RPM,'pass_depth_in':program.pass_depth,
            'paths':program.path_count,'cutting_segments':len(program.paths),
            'guarded_finish_approaches':program.fast_entries,
            'cutting_length_in':program.chip_distance,
            'feed_motion_minutes':program.feed_seconds/60,
            'bytes':len(text.encode('ascii'))}


def save_preview(simulations):
    panel=650; image=Image.new('RGB',(panel*2, panel+70),'#f5f5f3')
    draw=ImageDraw.Draw(image)
    for i,piece in enumerate(['Maple','Walnut']):
        sim=simulations[piece]
        limit=D if piece=='Maple' else PLUG_CUT
        fraction=np.clip(sim.surface/limit,0,1)
        base=np.array([232,206,160]) if piece=='Maple' else np.array([102,64,40])
        factor=1-0.30*fraction
        color=np.clip(base[None,None,:]*factor[:,:,None],0,255).astype(np.uint8)
        # Surface-gradient shading reveals the actual swept tapered cuts.
        gy,gx=np.gradient(sim.surface,GRID)
        shade=np.clip((1+0.12*gx-0.16*gy)/np.sqrt(1+0.02*(gx*gx+gy*gy)),0.5,1.2)
        color=np.clip(color*shade[:,:,None],0,255).astype(np.uint8)
        picture=Image.fromarray(color[::-1]).resize((panel-30,panel-30),Image.Resampling.LANCZOS)
        image.paste(picture,(i*panel+15,45))
        draw.text((i*panel+18,15),f'{piece}: actual swept-tool depth preview',fill='#222222')
        draw.text((i*panel+18,panel+23),f'Maximum depth {limit:.3f} inch',fill='#222222')
    image.save(OUTPUT/'Toolpath-Simulation.png')


def main():
    started=time.monotonic()
    all_programs=[]; simulations={}
    for piece in ['Maple','Walnut']:
        log(f'Calculating {piece} clearance geometry...')
        quarter,q_coverage=make_clearance(piece,0.25,0.10,80,15,0.04,'01_quarter')
        eighth,e_coverage=make_clearance(piece,0.125,0.0375,50,10,0.02,'02_eighth',q_coverage)
        vbit=make_vbit(piece,q_coverage+e_coverage)
        log(f'Simulating {piece} material removal...')
        simulation=Simulation(piece)
        for program in [quarter,eighth,vbit]: simulation.apply(program)
        simulation.refine(vbit)
        simulations[piece]=simulation
        all_programs.extend([quarter,eighth,vbit])
        error=simulation.surface-simulation.ideal
        legal=MAPLE_SHAPE if piece=='Maple' else buffer(PLUG_BOUNDARY,-PLUG_CUT*TAN-0.0002)
        mask=shapely.contains(legal,shapely.points(simulation.X,simulation.Y))
        REPORT[piece]={'maximum_overcut_in':float(np.max(error)),
                       'maximum_residual_in_mating_area':float(np.max(-error[mask])),
                       'mean_residual_in_mating_area':float(np.mean(np.maximum(0,-error[mask])))}
        log(f'{piece} simulation: {REPORT[piece]}')
    # Flip the male horizontally back into female coordinates. Original male
    # top seats INSERTION below maple top. Sum of their cut depths must reach
    # that insertion for the mating surfaces to avoid material overlap.
    female=simulations['Maple']; male=simulations['Walnut']
    male_depth=male.surface[:,::-1]
    inside=shapely.contains(MAPLE_SHAPE,shapely.points(female.X,female.Y))
    interference=INSERTION-female.surface-male_depth
    REPORT['assembled_fit']={'nominal_insertion_in':INSERTION,
                             'max_sampled_interference_in':float(np.max(interference[inside])),
                             'fraction_with_interference_over_0_001_in':float(np.mean(interference[inside]>0.001)),
                             'side_fit_allowance_in':SIDE_FIT}
    REPORT['grid_resolution_in']=GRID
    REPORT['programs']=[check_program(program) for program in all_programs]
    REPORT['parameters']={'maple_stock_in':[4,4,0.5],'walnut_stock_in':[4,4,0.5],
                          'pocket_depth_in':D,'glue_gap_in':GAP,'surface_gap_in':SURFACE_GAP,
                          'male_background_depth_in':PLUG_CUT,'xy_zero':'lower_left',
                          'z_zero':'original_stock_top','safe_z_in':SAFE_Z,
                          'short_feed_link_air_height_in':0.025,
                          'vbit_rough_contour_increment_in':V_INCREMENT,
                          'vbit_finish_cone_increment_limit_in':FINISH_INCREMENT,
                          'vbit_angle_deg':60,'vbit_flutes':3,'vbit_brand':'unidentified',
                          'vbit_label_code':'CXZ20260121','tip_model':'pointed',
                          'vbit_minimum_usable_cutting_height_in':PLUG_CUT,
                          'manufacturer_feeds_verified':False,
                          'controller':'PlanetCNC standard G-code','uses_vcarve_postprocessor':False}
    REPORT['validation_limits']=['No machine execution or physical test fit performed.',
                                  'Geometry simulation does not model bit stress, runout, grain, or workholding.',
                                  'Pointed 60 degree tip and sufficient usable cutting height must be checked physically.']
    REPORT['elapsed_seconds']=time.monotonic()-started
    (OUTPUT/'Validation-Report.json').write_text(json.dumps(REPORT,indent=2)+'\n',encoding='utf-8')
    save_preview(simulations)
    # Do not emit a cutting program if an unresolved gross geometry error exists.
    assert all(REPORT[p]['maximum_overcut_in']<0.001 for p in ['Maple','Walnut']), REPORT
    assert REPORT['assembled_fit']['max_sampled_interference_in']<0.0015, REPORT['assembled_fit']
    for program in all_programs: program.save()
    np.savez_compressed(OUTPUT/'Simulation-Depths.npz',maple=female.surface,walnut=male.surface,axis=female.axis)
    log('All six cutting programs generated and checked.')
    log(json.dumps(REPORT['assembled_fit']))


if __name__=='__main__':
    main()
