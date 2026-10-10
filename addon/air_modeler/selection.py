"""Idle selector debounce. Receives poses; Blender owns the modeling mode."""
class Selector:
    def __init__(self):
        self.enabled = False
        self.confirmed = 'MOVE'
        self.candidate = None
        self.since = 0.0
        self.last_valid = 0.0
        self.last_input = 0.0

    def observe(self, pose, now, idle):
        self.enabled = True
        self.last_input = now
        mode = {'FIST':'MOVE', 'TWO':'ROTATE', 'THREE':'SCALE', 'OPEN':'EXTRUDE'}.get(pose)
        if mode == self.confirmed:
            self.last_valid = now
        if not idle:
            self.candidate = None
            return
        if mode is None:
            self.candidate = None
            return
        if mode != self.candidate:
            self.candidate, self.since = mode, now
        elif now - self.since >= .3:
            self.confirmed = mode
            self.last_valid = now

    def mode(self, now):
        if now - self.last_valid >= .6 or now - self.last_input >= .6:
            self.confirmed = 'MOVE'
        return self.confirmed
