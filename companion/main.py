"""One local bridge, optional device workers, and V's typed command parser."""
import argparse
import json
import signal
import sys
import threading

from companion.transport.server import BridgeServer
from companion.voice.service import emit_command, typed_lines
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
    parser.add_argument('--mic', action='store_true', help='Enable optional ElevenLabs microphone worker')
    parser.add_argument('--device', type=int, help='Optional microphone device index')
    parser.add_argument('--synthetic', action='store_true', help='Accept raw type/payload JSON lines for camera-free gesture testing')
    args = parser.parse_args(argv)
    stop = threading.Event()
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
        config = dict(camera_index=args.camera, preview=False, pinch_start=.35,
                      pinch_release=.60, loss_cancel_s=.5)
        if args.model:
            config['model_path'] = args.model
        print(f'Hands config: {config}', flush=True)
        run_hand_tracker(server.emit, stop, config)
    def voice():
        from companion.voice.service import run_voice
        run_voice(server.emit, stop, {'device': args.device})
    try:
        server.start()
    except OSError as exc:
        print(f'Cannot listen on 127.0.0.1:8765: {exc}', file=sys.stderr)
        return 1
    previous = signal.signal(signal.SIGTERM, lambda *_: stop.set())
    if args.camera is not None:
        worker('Hands', hands)
    if args.mic:
        worker('Voice', voice)
    print('Connect in Blender, wait for READY. Type create cube, move, cancel, undo; status; quit.', flush=True)
    try:
        for line in typed_lines(sys.stdin, stop):
            text = line.strip()
            if text in {'quit', '/quit'}:
                break
            if text == 'status':
                print(f'session={server.session_id} status={server.last_status} error={server.last_error}', flush=True)
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
