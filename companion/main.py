"""One local bridge, optional device workers, and V's typed command parser."""
import argparse
import json
import signal
import sys
import threading

from companion.transport.server import BridgeServer
from companion.voice.service import VoiceConfig, emit_command, typed_lines
from shared.protocol import SHAPES


def typed_event(text):
    """Use V's parser/UUID contract; retain only the old strict spawn alias."""
    result = []
    words = text.split()
    if len(words) == 2 and words[0] == 'spawn' and words[1] in SHAPES:
        text = 'create ' + words[1]
    emit_command(text, result.append, threading.Event())
    return result[0] if result else None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--camera', type=int, help='Enable hands using an index discovered with companion.hands --list-cameras')
    parser.add_argument('--model', help='Optional hand landmarker model path')
    hand_mode = parser.add_mutually_exclusive_group()
    hand_mode.add_argument('--legacy-hands', action='store_true', help='Explicit single-hand legacy cursor fallback; never selected automatically')
    hand_mode.add_argument('--two-hands', action='store_true', help='Enable Left selection clutch and Right whole-hand MOVE/ROTATE/SCALE or pinch EXTRUDE')
    parser.add_argument('--manipulator-hand', choices=('Right', 'Left'), default='Right')
    parser.add_argument('--mic', action='store_true', help='Enable optional ElevenLabs microphone worker')
    parser.add_argument('--device', type=int, help='Optional microphone device index')
    parser.add_argument('--push-to-talk', action='store_true', help='With --mic, /talk arms audio and /end mutes and commits')
    parser.add_argument('--synthetic', action='store_true', help='Accept raw type/payload JSON lines for camera-free gesture testing')
    parser.add_argument('--record-landmarks', help='New private JSONL file; opt-in landmarks/events only')
    parser.add_argument('--record-seconds', type=float, default=20.)
    parser.add_argument('--replay-landmarks', help='Replay a landmark capture after Blender connects; no camera')
    args = parser.parse_args(argv)
    if args.replay_landmarks and (args.camera is not None or args.mic or args.record_landmarks):
        parser.error('Replay cannot run alongside live capture or recording')
    if args.record_landmarks and not args.two_hands:
        parser.error('--record-landmarks requires --two-hands')
    if not 1 <= args.record_seconds <= 60:parser.error('--record-seconds must be 1–60')
    if args.camera is not None and not (args.two_hands or args.legacy_hands):
        parser.error('--camera requires --two-hands or explicit --legacy-hands')
    if args.legacy_hands and args.camera is None:
        parser.error('--legacy-hands requires --camera')
    if args.two_hands and args.camera is None:
        parser.error('--two-hands requires --camera')
    if args.two_hands and args.manipulator_hand != 'Right':
        parser.error('--two-hands uses anatomical left selection/right manipulation; omit --manipulator-hand Left')
    if args.push_to_talk and not args.mic:
        parser.error('--push-to-talk requires --mic')
    stop = threading.Event()
    gate = threading.Event() if args.push_to_talk else None
    voice_config = VoiceConfig(device=args.device, push_to_talk_event=gate)
    workers = []
    server = BridgeServer(log=lambda message: print(message, flush=True))
    def worker(name, run):
        def guarded():
            try:
                run()
            except Exception as exc:
                # Voice's public exceptions are already secret-safe.
                print(f'{name} stopped: {exc}. Other inputs remain available.', file=sys.stderr, flush=True)
        thread = threading.Thread(target=guarded, name=name, daemon=True)
        thread.start()
        workers.append(thread)
    def hands():
        from companion.hands.tracker import run_hand_tracker
        config = dict(camera_index=args.camera, preview=False, two_hands=args.two_hands,
                      manipulator_hand=args.manipulator_hand, pinch_start=.35,
                      pinch_release=.60, loss_cancel_s=.5,
                      record_landmarks=args.record_landmarks, record_seconds=args.record_seconds)
        if args.model:
            config['model_path'] = args.model
        print(f'Hands config: {config}', flush=True)
        run_hand_tracker(server.emit, stop, config)
    def voice():
        from companion.voice.service import run_voice
        run_voice(server.emit, stop, voice_config)
    try:
        server.start()
    except OSError as exc:
        print(f'Cannot listen on 127.0.0.1:8765: {exc}', file=sys.stderr)
        return 1
    previous = signal.signal(signal.SIGTERM, lambda *_: stop.set())
    if args.camera is not None:
        worker('Hands', hands)
    if args.replay_landmarks:
        from companion.hands.recording import run_replay
        worker('Replay',lambda:run_replay(args.replay_landmarks,server.emit,stop,lambda:server.session_id))
    print('Air Modeler companion 0.9.0; hands profile left_clutch_v3',flush=True)
    if args.mic:
        worker('Voice', voice)
    help_text = ('Connect in Blender, wait for READY. Type create cube/sphere/cylinder/triangular prism, '
                 'rotate x/y/z, scale, extrude/extend, move, cancel, undo; status; help; quit. '
                 'Planes: extrude plane xy axis x; extrude plane auto. Precision: rotate x 45 degrees; scale by 1.5; move x 2 units; extrude 0.5 units. '
                 'With --mic --push-to-talk: /talk arms, /end mutes and commits; wait for committed feedback.')
    if args.two_hands:
        help_text += ' Left pinch selects only. Right open palm MOVE, twist ROTATE, whole-hand close/open SCALE, isolated pinch EXTRUDE.'
    elif args.legacy_hands:
        help_text += ' LEGACY HANDS explicitly enabled: one-hand pinch cursor with typed modes.'
    print(help_text, flush=True)
    if gate is not None:
        print('PTT MUTED', flush=True)
    try:
        for line in typed_lines(sys.stdin, stop):
            text = line.strip()
            if text in {'quit', '/quit'}:
                break
            if text in {'/talk', '/end'}:
                if gate is None:
                    print('PTT unavailable: launch with --mic --push-to-talk. Typed commands remain active.', flush=True)
                else:
                    active = text == '/talk'
                    changed = gate.is_set() != active
                    gate.set() if active else gate.clear()
                    if changed:
                        print('PTT ARMED' if active else 'PTT MUTED', flush=True)
                continue
            if text in {'help', '/help'}:
                print(help_text, flush=True)
                continue
            if text == 'status':
                print(f'session={server.session_id} status={server.last_status} error={server.last_error}', flush=True)
                if gate is not None:
                    print('PTT ARMED' if gate.is_set() else 'PTT MUTED', flush=True)
                continue
            try:
                event = json.loads(text) if args.synthetic and text.startswith('{') else typed_event(text)
                if event is None:
                    if text:
                        print('Ignored: enter one supported command phrase.', flush=True)
                    continue
                accepted = server.emit(event)
                print(f"{'QUEUED' if accepted else 'DISCARDED'} {event}" + (f' ({server.last_error})' if not accepted else ''), flush=True)
            except (ValueError, TypeError) as exc:
                print(f'Input rejected: {exc}', flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        if gate is not None:
            gate.clear()
        # Close transport immediately; Blender restores previews even if a
        # native device driver takes time to stop.
        server.close()
        for thread in workers:
            thread.join(timeout=6)
            if thread.is_alive():
                print(f'{thread.name} native device call did not stop within 6s; process exit releases it.', file=sys.stderr)
        signal.signal(signal.SIGTERM, previous)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
