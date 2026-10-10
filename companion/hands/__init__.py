"""Hand tracking service: webcam -> MediaPipe Hand Landmarker -> gesture events.

Entry point: ``companion.hands.tracker.run_hand_tracker(emit, stop_event, config)``.
Importing this package does not import OpenCV or MediaPipe; only ``tracker`` does.
"""
