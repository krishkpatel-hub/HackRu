"""Speech policy/session regressions use fake audio, never live microphone proof."""
import asyncio
import threading
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

import pytest

from companion.voice.parser import parse_command, parse_microphone_command
from companion.voice.service import VoiceConfig, run_voice
from companion.voice.transcripts import TranscriptHandler
from companion.voice import microphone
from companion.transport.server import BridgeServer
from shared.protocol import ProtocolError, Session, validate_event
from test_voice_transcripts import committed
from test_voice_microphone import FakeAudio, FakeClient, FakeConnection


@pytest.mark.parametrize('verb,action',[('create','spawn'),('remove','remove')])
@pytest.mark.parametrize('phrase,shape',[('cube','cube'),('sphere','sphere'),('cylinder','cylinder'),('prism','prism'),('triangular prism','prism')])
def test_complete_spoken_commands_and_harmless_normalization(verb,action,phrase,shape):
    text=f'  “{verb.upper()},  {phrase}!”  '
    assert parse_microphone_command(text)=={'action':action,'shape':shape}
    emitted=[];handler=TranscriptHandler(emitted.append,threading.Event(),lambda _:None)
    event=committed(text)
    handler.handle(dict(event,message_type='partial_transcript'))
    handler.handle(dict(event,message_type='committed_transcript'))
    assert not emitted
    handler.handle(event);handler.handle(event)
    handler.handle(committed(text,start=5))
    assert len(emitted)==2 and emitted[0]['payload']['id']!=emitted[1]['payload']['id']
    for value in emitted:validate_event(value)


@pytest.mark.parametrize('text',['cube','remove','Should we create a cube later?',
    'please create cube','do not remove cube','remove all cubes','create cube and remove sphere',
    'create cube. remove sphere.','rotate','rotate x 45 degrees','scale','scale by 2','move',
    'undo','cancel','extrude','add cube','remove cone'])
def test_conversation_partial_words_and_non_allowlisted_speech_are_ignored(text):
    emitted=[];handler=TranscriptHandler(emitted.append,threading.Event(),lambda _:None)
    handler.handle(committed(text));assert not emitted
    assert parse_microphone_command(text) is None


def test_typed_grammar_retains_transform_undo_cancel_and_add():
    for phrase in ('rotate','rotate x 45 degrees','scale','move','undo','cancel','extrude','add cube'):
        assert parse_command(phrase) is not None
    assert parse_command('remove triangular prism')==dict(action='remove',shape='prism')


def test_remove_schema_and_per_session_uuid_dedup():
    sender,receiver=Session('server'),Session('client')
    _,reply=sender.accept(receiver.wrap(dict(type='hello',payload={})));receiver.accept(reply)
    event=dict(type='command',payload=dict(id=str(uuid4()),action='remove',shape='cube'))
    assert receiver.accept(sender.wrap(event))[0]==event
    assert receiver.accept(sender.wrap(event))[0] is None
    for changes in ({'shape':'cone'},{'all':True},{'id':'bad'}):
        with pytest.raises(ProtocolError):validate_event(dict(event,payload=dict(event['payload'],**changes)))


def test_transport_session_bound_audio_cannot_cross_reconnect_or_queue_during_drag():
    server=BridgeServer();server._session_id=str(uuid4());old=server.session_id
    event=dict(type='command',payload=dict(id=str(uuid4()),action='spawn',shape='cube'))
    server._session_id=str(uuid4())
    assert not server.emit(event,expected_session=old) and not server._events
    for phase in ('SELECTED_READY','DRAGGING'):
        server.last_status={'phase':phase}
        for action in ('spawn','remove'):
            assert not server.emit(dict(event,payload=dict(event['payload'],action=action)))
            assert not server._events
    server.last_status={'phase':'IDLE'}
    assert server.emit(event,expected_session=server.session_id)


def test_transport_rejection_feedback_does_not_claim_command_accepted_or_replay():
    calls=[];feedback=[]
    handler=TranscriptHandler(lambda e:(calls.append(e),False)[1],threading.Event(),feedback.append)
    handler.handle(committed());handler.handle(committed())
    assert len(calls)==1
    assert any('discarded' in line for line in feedback)
    assert not any('Accepted speech' in line for line in feedback)


def test_microphone_reconnect_closes_old_stream_and_discards_old_sdk_callbacks():
    stop=threading.Event();current=['one'];connections=[];audios=[];emitted=[];states=[]
    class Audio:
        def check_input_settings(self,**kw):pass
        def RawInputStream(self,**kw):
            assert not audios or audios[-1].closed,'second microphone overlaps first'
            audio=FakeAudio(stop);audio.options=kw;audios.append(audio);return audio
    async def connect(options):
        conn=FakeConnection(stop);conn.strategy=options['commit_strategy'];connections.append(conn)
        index=len(connections)
        async def send(data):
            if index==1:
                current[0]='two'
                conn.handlers['committed_transcript_with_timestamps'](committed())
            else:
                connections[0].handlers['committed_transcript_with_timestamps'](committed(start=3))
                conn.handlers['committed_transcript_with_timestamps'](committed('remove cube'))
                stop.set()
        conn.send=send
        asyncio.get_running_loop().call_soon(lambda:conn.handlers['session_started']({}))
        return conn
    events=SimpleNamespace(**{n.upper():n for n in ('session_started','partial_transcript','committed_transcript','committed_transcript_with_timestamps','error','close')})
    sdk=SimpleNamespace(ElevenLabs=lambda **kw:SimpleNamespace(speech_to_text=SimpleNamespace(realtime=SimpleNamespace(connect=connect))),
        RealtimeAudioOptions=dict,AudioFormat=lambda x:x,CommitStrategy=SimpleNamespace(MANUAL='manual',VAD='vad'),RealtimeEvents=events)
    def emit_session(event,session):
        assert session==current[0]=='two'
        emitted.append(event);return True
    config=VoiceConfig(feedback=lambda _:None,state=states.append,session_id=lambda:current[0],emit_for_session=emit_session)
    with patch.dict('os.environ',{'ELEVENLABS_API_KEY':'test-placeholder'}),patch.object(microphone,'_dependencies',return_value=(Audio(),sdk,SimpleNamespace(Client=FakeClient))):
        run_voice(lambda _:pytest.fail('unbound callback'),stop,config)
    assert len(connections)==len(audios)==2
    assert all(a.closed for a in audios) and all(c.closed for c in connections)
    assert [e['payload']['action'] for e in emitted]==['remove']
    assert states.count('CONNECTING')==2
    assert 'LISTENING — CREATE/REMOVE ONLY' in states


def test_disconnect_between_ready_check_and_stream_open_waits_for_new_session():
    stop=threading.Event();sessions=iter(('old',None,'new','new'));opened=[]
    config=VoiceConfig(state=lambda _:None,session_id=lambda:next(sessions),
        emit_for_session=lambda event,session:opened.append(session))
    async def stream(emit,*args):
        emit({});stop.set()
    with patch.dict('os.environ',{'ELEVENLABS_API_KEY':'test-placeholder'}), \
         patch.object(microphone,'_dependencies',return_value=()),patch.object(microphone,'_stream',side_effect=stream):
        run_voice(lambda _:pytest.fail('unbound callback'),stop,config)
    assert opened==['new']


def test_default_voice_failure_leaves_hands_transport_and_typed_input_alive():
    import io
    from unittest.mock import MagicMock
    from companion.main import main
    from companion.voice.service import VoiceError
    hand_ready=threading.Event();voice_failed=threading.Event();hand_done=threading.Event()
    server=MagicMock(session_id='test',last_status=None,last_error=None);server.emit.return_value=True
    output=io.StringIO()
    def hands(emit,stop,config):
        assert config['preview'] is False
        hand_ready.set();stop.wait(3);hand_done.set()
    def voice(*args):
        voice_failed.set();raise VoiceError('Microphone unavailable; check permission')
    def lines(stream,stop):
        assert hand_ready.wait(2) and voice_failed.wait(2)
        assert not stop.is_set() and not hand_done.is_set()
        yield 'create cube';yield 'status';yield 'quit'
    with patch('companion.main.BridgeServer',return_value=server),patch('companion.main.typed_lines',side_effect=lines), \
         patch('companion.hands.tracker.run_hand_tracker',side_effect=hands),patch('companion.voice.service.run_voice',side_effect=voice), \
         patch('sys.stdout',output),patch('sys.stderr',output):
        assert main(['--camera','0','--two-hands'])==0
    assert hand_done.is_set() and server.close.call_count==1
    assert server.emit.call_args.args[0]['payload']['action']=='spawn'
    assert 'VOICE UNAVAILABLE' in output.getvalue() and 'Other inputs remain available' in output.getvalue()
