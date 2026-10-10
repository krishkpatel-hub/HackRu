"""Opt-in bounded landmark/event capture. No pixels, sound, environment or commands."""
import json
import os
import time
from uuid import UUID
from .observations import TwoHandObservations
from .engine import HandEngine
from .config import HandConfig


class Recorder:
    def __init__(self,path,seconds=20,config=None):
        self.file=os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'w')
        self.seconds=seconds;self.start=None;self.count=0
        from dataclasses import asdict
        controls=asdict(config or HandConfig(two_hands=True))
        for key in ('record_landmarks','model_path'):controls.pop(key,None)
        self.file.write(json.dumps({'format':'air-landmarks-0.9','seconds':seconds,'controls':controls})+'\n')
    def write(self,t,detections,aspect,event):
        if self.file is None:return
        if self.start is None:self.start=t
        if t-self.start>self.seconds or self.count>=3600:
            self.close();return
        self.file.write(json.dumps(dict(t=t,detections=detections,aspect=aspect,event=event),allow_nan=False)+'\n')
        self.file.flush();self.count+=1
    def close(self):
        if self.file:self.file.close();self.file=None


def replay_events(path):
    """Recompute measurements, identities and cursor transitions; stable synthetic UUIDs."""
    counter=0
    def new_id():
        nonlocal counter
        counter+=1
        return str(UUID(int=counter))
    previous=-1
    with open(path) as file:
        header=json.loads(file.readline())
        if header.get('format')!='air-landmarks-0.9':
            raise ValueError('Unsupported landmark recording')
        cfg=HandConfig.from_mapping(header['controls'])
        model=TwoHandObservations(cfg)
        model.engines={hand:HandEngine(cfg,new_id) for hand in ('Left','Right')}
        for n,line in enumerate(file):
            if n>=3600 or len(line)>100000:raise ValueError('Recording exceeds bounds')
            row=json.loads(line);t=row['t']
            if t<=previous:raise ValueError('Nonmonotonic recording')
            previous=t
            yield model.update(t,row['detections'],row['aspect'])


def run_replay(path,emit,stop,ready):
    while not ready():
        if stop.wait(.05):return
    session=ready()
    origin=time.monotonic();first=None
    for event in replay_events(path):
        t=event['payload']['t']
        if first is None:first=t
        if stop.wait(max(0,t-first-(time.monotonic()-origin))):return
        if ready()!=session:return  # Never cross a connection/session boundary.
        emit(event)
    print('Landmark replay complete; no live input. Disconnect or quit.',flush=True)
