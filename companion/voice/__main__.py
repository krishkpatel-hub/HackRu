"""Run from the repository root: python -m companion.voice --typed."""

import argparse
import json
import sys
import threading

from .service import (
    VoiceConfig,
    VoiceError,
    emit_command,
    run_voice,
    stderr_feedback,
    typed_lines,
)

_print_lock = threading.Lock()


def print_json(event: dict) -> None:
    with _print_lock:
        print(json.dumps(event, separators=(",", ":")), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Air Modeler voice commands")
    sources = parser.add_mutually_exclusive_group()
    sources.add_argument("--typed", action="store_true", help="Typed commands only (default)")
    sources.add_argument("--mic", action="store_true", help="Microphone plus typed fallback")
    parser.add_argument("--list-devices", action="store_true", help="List PortAudio devices and exit")
    parser.add_argument("--device", help="Input device index or name")
    parser.add_argument("--sample-rate", type=int, default=16000, help="PCM rate (default 16000)")
    parser.add_argument("--push-to-talk", action="store_true", help="Use /talk and /end to gate audio")
    args = parser.parse_args()
    if args.push_to_talk and not args.mic:
        parser.error("--push-to-talk requires --mic")
    if args.list_devices:
        try:
            import sounddevice

            print(sounddevice.query_devices())
            return 0
        except (ImportError, OSError) as error:
            stderr_feedback(f"Cannot list audio devices ({type(error).__name__}); install sounddevice/PortAudio.")
            return 1
    stop = threading.Event()
    gate = threading.Event() if args.push_to_talk else None
    device = int(args.device) if args.device and args.device.isdecimal() else args.device
    config = VoiceConfig(device=device, sample_rate=args.sample_rate, push_to_talk_event=gate)
    worker = None

    def microphone_worker():
        try:
            run_voice(print_json, stop, config)
        except VoiceError as error:
            stderr_feedback(f"Voice unavailable: {error} Typed commands remain active.")
        except Exception as error:
            stderr_feedback(f"Voice failed ({type(error).__name__}). Typed commands remain active.")

    if args.mic:
        worker = threading.Thread(target=microphone_worker, name="air-modeler-voice", daemon=True)
        worker.start()
    stderr_feedback("Enter one command per line; /quit or Ctrl+C exits.")
    if gate is not None:
        stderr_feedback("Push-to-talk: /talk starts, /end releases and commits. Wait for committed feedback.")
    try:
        for text in typed_lines(sys.stdin, stop):
            control = text.strip().casefold()
            if control == "/quit":
                break
            if gate is not None and control in {"/talk", "/end"}:
                if control == "/talk":
                    gate.set()
                    stderr_feedback("Listening. Speak one command, then enter /end.")
                else:
                    gate.clear()
                    stderr_feedback("Released. Waiting for committed speech.")
            elif not emit_command(text, print_json, stop) and text.strip():
                stderr_feedback("Ignored: enter one supported command phrase.")
    except KeyboardInterrupt:
        pass
    except VoiceError as error:
        stderr_feedback(str(error))
        return 1
    finally:
        stop.set()
        if gate is not None:
            gate.clear()
        if worker is not None:
            worker.join(config.operation_timeout + 2)
            if worker.is_alive():
                stderr_feedback("Voice shutdown did not finish; check the microphone driver.")
                return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
