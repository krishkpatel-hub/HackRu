"""Hand-relative metric landmarks: rigid palm orientation, independent articulation.

World coordinates are centered on the hand, never absolute camera translation.
Mirrored camera x-right/y-down/z-away becomes view x-right/y-up/z-toward.
"""
import math
from shared import spatial as s


def invalid(reason):
    return dict(shape_valid=False,shape_error=reason,angle=None,openness=None,
                open_palm=False,extrude_pose=False,pinch_pending=False,
                orientation=None,fingers=None)


def measure(world, previous=None, config=None):
    previous=previous or {}
    used=(0,*range(4,21))  # unused thumb joints 1–3 do not invalidate useful evidence
    if world is None or len(world)!=21 or any(world[i] is None or len(world[i])!=3 or any(
            type(x) not in (float,int) or not math.isfinite(x) for x in world[i]) for i in used):
        return invalid('Reliable 3D hand landmarks unavailable')
    p=[(world[i][0],-world[i][1],-world[i][2]) if i in used else None for i in range(21)]
    try:
        across=s.sub(p[5],p[17]); along=s.sub(p[9],p[0])
        width=math.sqrt(s.dot(across,across)); length=math.sqrt(s.dot(along,along))
        if not .2 < width/length < 2.5: raise ValueError('Palm geometry uncertain')
        y=s.unit(along); a=s.unit(across)
        if math.sqrt(s.dot(s.cross(a,y),s.cross(a,y))) < .3:
            raise ValueError('Palm frame unobservable')
        z=s.unit(s.cross(a,y));x=s.unit(s.cross(y,z))
        q=s.quaternion(x,y,z)
        if previous.get('orientation') and s.dot(q,previous['orientation'])<0:
            q=tuple(-v for v in q)
        def bend(a,b,c):
            u=s.unit(s.sub(p[a],p[b]));v=s.unit(s.sub(p[c],p[b]))
            return math.acos(max(-1,min(1,s.dot(u,v))))
        def clamp(v):return max(0.,min(1.,v))
        fingers=[]
        for m in (5,9,13,17):
            bones=[math.dist(p[i],p[i+1]) for i in range(m,m+3)]
            if min(bones)<.035*length or max(bones)>.9*length:
                raise ValueError('Finger bones uncertain/occluded')
            # Joint bending dominates; normalized extension detects MCP flexion.
            pip,dip=bend(m,m+1,m+2),bend(m+1,m+2,m+3)
            joints=clamp((.65*pip+.35*dip-math.radians(55))/math.radians(115))
            reach=clamp((math.dist(p[m],p[m+3])/sum(bones)-.25)/.7)
            proximal=max(0.,s.dot(s.unit(s.sub(p[m+1],p[m])),y))
            fingers.append(clamp(.65*joints+.20*reach+.15*proximal))
        cutoff=config.finger_open_exit if previous.get('open_palm') else config.finger_open_enter
        extra=config.finger_open_exit if previous.get('extrude_pose') else config.finger_open_enter
        extrude=sorted(fingers[1:],reverse=True)[1]>=extra
        ratio=math.dist(p[4],p[8])/max(width,length)
        return dict(shape_valid=True,shape_error=None,angle=math.atan2(y[1],y[0]),
                    openness=sum(fingers)/4,fingers=fingers,orientation=list(q),
                    open_palm=min(fingers)>=cutoff,extrude_pose=extrude,
                    pinch_pending=extrude and ratio<=config.pinch_approach)
    except (ValueError,ZeroDivisionError):
        return invalid('Palm/finger geometry uncertain; show the whole hand')
