> Current release is **0.15.0**. See [Edit Mode installation and verification](edit_mode_handoff.md).
> The 0.14 voice contract and historical results below remain valid records;
> all current physical checks remain NOT RUN.

# Air Modeler 0.14.0: automatic CREATE/REMOVE voice

Normal companion launches automatically listen through the existing ElevenLabs
stream after Blender is READY. Say one complete phrase, then pause for its committed
transcript and visible result. No `/talk` or `/end` is needed. The speech allowlist is
`create` or `remove` followed by `cube`, `sphere`, `cylinder`, `prism`, or
`triangular prism`. Case, whitespace and harmless punctuation normalize; articles,
conversation, combined commands and all other spoken tools are ignored. Partial
and plain committed transcript notifications do not execute; only the existing
timestamped committed delivery executes. Typed commands, keyboard/sidebar controls
and hand gestures retain their broader behavior.

## Removal and command safety

Removal requires exactly one selected object, also active, with matching creation
metadata written by 0.14 (`air_modeler_shape_version=1`, `air_modeler_shape`). Names
are irrelevant. Metadata records the original shape and survives renaming and later
modeling. Untagged/pre-0.14 objects are never guessed or migrated. The target must be
a visible editable local mesh in one scene, with no children. A mismatched, absent,
multiple, linked or otherwise unsupported selection produces an instruction and no
deletion. Enable Blender Global Undo; removal rejects when it is disabled.

The main-thread `air_modeler.remove_primitive` operator removes only that object;
shared meshes and other objects remain. One native Undo restores the object and
its mesh sharing. Rejection adds no Undo step. Existing creation is reused.
CREATE/REMOVE reject during selection/active previews, including extrusion dwell;
they are discarded rather than delayed until release. Consumer validation and UUID
dedup apply even to rejected commands. Provider audio-span/text dedup prevents a
duplicate transcript delivery; separate utterances get new UUIDs and execute once
each. Terminal `Accepted speech command` means queued, not scene completion;
Blender status `message`/`last_error` reports the result.

Each audio stream is bound to one ready Blender session. Disconnect invalidates
its callbacks and closes its microphone/SDK/HTTP resources before a replacement
opens. A final atomic session check rejects old callbacks racing with reconnect.
Offline or rejected commands are never replayed. This reuses one microphone stream
and the existing local TCP pipeline; no voice worker imports `bpy`.

## Install and launch

Save a separate rehearsal scene first, preserving existing `.blend` files. Stop
the old companion and disconnect Blender. Update from
`/Users/krishpatel/HackRu/dist/air_modeler.zip`, restart Blender to clear old modules,
and confirm add-on **0.15.0**. Use Object Mode and Global Undo. Installation detail:
[current setup](clutch_handoff.md#install-and-launch).

If the authorized replacement key is not in this Terminal's environment, enter it
privately in zsh (never paste its value into chat, command arguments or files):

```zsh
set +x
read -rs 'ELEVENLABS_API_KEY?ElevenLabs API key (hidden): '
export ELEVENLABS_API_KEY
printf '\n'
```

Use the existing interpreter and user-confirmed camera **0**, microphone **0
(MacBook Air Microphone)**:

```sh
cd /Users/krishpatel/HackRu && /Users/krishpatel/HackRu/.venv/bin/python -m companion.main --camera 0 --model /Users/krishpatel/HackRu/companion/hands/models/hand_landmarker.task --two-hands --device 0
```

The hand worker retains `preview=False`. Connect from the intended Blender viewport.
Require **Connected/READY**, actual fresh hand observations, and **VOICE LISTENING
— CREATE/REMOVE ONLY** separately. Starting a process or seeing Scribe-ready alone
does not establish microphone readiness.

| Voice state | Meaning |
| --- | --- |
| CONNECTING | Waiting for a ready Blender session, then the existing Scribe stream |
| LISTENING — CREATE/REMOVE ONLY | Scribe ready and the microphone stream active |
| MUTED | `--no-mic`/`--typed`, or optional PTT gate off |
| VOICE UNAVAILABLE | Credential, microphone or speech service failure; hands/TCP/typed input continue |

`--mic` remains compatible; `--no-mic` (alias `--typed`) disables audio. Adding
`--push-to-talk` restores the existing optional `/talk`/`/end` gate, with the same
CREATE/REMOVE speech restriction. PTT `/end` commits buffered audio, not cancellation;
wait for feedback. Synthetic/replay launches default to no mic, preserving device-free
tests. Standalone voice diagnostics retain their explicit `--mic` option.

On a voice failure, read the public error, fix permission/device/key/account/network
access and restart the companion. Keys are environment-only and errors do not echo
SDK secrets. The integrated stream uses 16 kHz as before; dependencies were not
reinstalled. `status` and `help` remain available. `quit`/Ctrl+C stops workers and
restores unfinished previews. Check camera off/prompt returned, then
`unset ELEVENLABS_API_KEY`. The owner must revoke the previously exposed key;
revocation and sponsor attribution remain unconfirmed.

## Historical 0.14 automated evidence and preserved work

Baseline: `a9e7e9b7a94d2887de990d22ca5028c3ac022a57`, add-on 0.13.0. Backup ZIP:
`dist/air_modeler-baseline-0.13.0.zip`, SHA-256
`581b03aed347be4d893689c12a1e1502731cc04365a5a2c8bb8e8f3144e05c1d`.
The two-second face dwell, observation smoothing, gesture arbitration, signed
geometry, hand roles and cursor mapping are preserved. No hand module, dependency
or scene file changed. Envelope v1 and hand profile v3 remain; REMOVE and optional
status `message` are consistently added to the one shared validator and packaged
copy. Install the matching companion and ZIP.

Historical 0.14 Python suite: **369 tests + 78 subtests passed**, `/tmp/air14-python.log`.
Coverage includes all ten phrase variants, normalization, conversation/unsupported
speech, partials, duplicate versus intentional repeats, default hands-free startup,
PTT and typed compatibility, voice-failure isolation, session-bound callback disposal,
resource closure, transport validation and existing hand/dwell tests. Audio inputs
are mocked; these are not live microphone results.

Native Blender **5.2.2 LTS** checks use separate factory-startup profiles and
actual local TCP, operators and Undo, with generated hand input and no microphone.
**All four scripts passed, 45 PASS groups:** `smoke_check.py` (6),
`remove_check.py` (6), `bridge_check.py` (16), `clutch_check.py` (17). The full clutch
check covers all existing transforms, real two-second dwell/reset/lock, signed
extrusion, release orders, native Undo, cancellation, tracking loss and shutdown.
Removal covers all four metadata shapes, renamed/untagged objects, wrong/missing/
multiple selection, shared meshes, distinct versus duplicate UUIDs, one-step Undo,
disabled Global Undo, selection/dwell/MOVE rejection and no execution after cancel.

A development removal check exposed a harness shutdown issue: synthetic frames
continued after its companion stopped. The test now stops its generator before
shutdown. Two clutch attempts exposed fixed-delay assumptions: an absent-hand assertion
and a deliberate capture gap could be checked before pending observations arrived.
Both now synchronize with consumption of submitted frames, using 350 ms test
delivery deadlines. The gap assertion still requires reset after a 300 ms pause.
Another run had a measured 512 ms capture gap and correctly triggered unchanged
500 ms tracking-loss cancellation. The full rerun passed. Production dwell/gesture
code and deadlines were not changed. Development logs are
`/tmp/air14-clutch-attempt1.log`, `/tmp/air14-clutch-attempt2.log`, and
`/tmp/air14-clutch-attempt3.log`; passing logs: `/tmp/air14-final-<script>.log`.

Package: **16 runtime entries**, actual version **0.14.0**, byte-identical to runtime
source plus the shared protocol/spatial copies. Compile and diff checks passed.
ZIP SHA-256: `6a027f94eb5701368473ab094940adb26979a89cf9eb7b4606cec59d39ea3bf7`.
Historical **334 tests + 78 subtests / 12 scripts / 131 PASS groups** belong to 0.13;
the original **67-test/78-subtest** baseline and earlier standalone 11-command voice
report remain historical. Neither proves this release's live combined operation.
The prepared PR description remains `/tmp/air-modeler-integration-pr.md`; known
GitHub PR permission failure is not retried. Only `feature/blender` is to be pushed;
no main merge or scene edits.

## Short live acceptance — NOT RUN

After installation and readiness, perform **one action per reply**:

1. With both hands released, say **“create cube”** once. Wait for one new selected
   cube and report what appeared; do not advance while transcription is pending.
2. Say **“remove cube”** once. Wait for only that cube to disappear.
3. Use **Blender Undo** (not spoken Undo). The same cube must return after one Undo.

Record actual observations. No live microphone or combined pass is claimed here.
For gesture regression, cancellation, tracking loss, reconnect and shutdown, use
the separate [physical acceptance](physical_acceptance.md) and
[combined rehearsal](demo_handoff.md) records; all current physical results remain
**NOT RUN** until observed.
