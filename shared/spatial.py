"""Small dependency-free rotation algebra; w,x,y,z quaternions, column frames."""
import math


def dot(a, b): return sum(x*y for x,y in zip(a,b))
def sub(a, b): return tuple(x-y for x,y in zip(a,b))
def cross(a, b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def unit(v):
    n=math.sqrt(dot(v,v))
    if n < 1e-9: raise ValueError('Degenerate palm frame')
    return tuple(x/n for x in v)
def conjugate(q): return (q[0],-q[1],-q[2],-q[3])
def multiply(a,b):
    w,x,y,z=a; v,i,j,k=b
    return (w*v-x*i-y*j-z*k,w*i+x*v+y*k-z*j,w*j-x*k+y*v+z*i,w*k+x*j-y*i+z*v)
def relative(q,reference): return unit(multiply(q,conjugate(reference)))
def angle(q): return 2*math.acos(min(1.,abs(q[0])))
def distance(a,b): return angle(relative(a,b))
def quaternion(x,y,z):
    m=tuple(zip(x,y,z)); trace=sum(m[i][i] for i in range(3))
    if trace>0:
        s=2*math.sqrt(trace+1)
        q=(s/4,(m[2][1]-m[1][2])/s,(m[0][2]-m[2][0])/s,(m[1][0]-m[0][1])/s)
    else:
        i=max(range(3),key=lambda i:m[i][i]); j=(i+1)%3;k=(i+2)%3
        s=2*math.sqrt(1+m[i][i]-m[j][j]-m[k][k]); v=[0.,0.,0.]
        v[i]=s/4;v[j]=(m[j][i]+m[i][j])/s;v[k]=(m[k][i]+m[i][k])/s
        q=((m[k][j]-m[j][k])/s,*v)
    return unit(q)
