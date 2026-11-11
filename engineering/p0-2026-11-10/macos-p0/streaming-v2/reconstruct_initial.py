#!/usr/bin/env python3
"""Restore the first compiling/failed-compile candidates with exact hash checks."""
from pathlib import Path
import hashlib,json,difflib
HERE=Path(__file__).resolve().parent;OUT=HERE/'history'
def digest(s):return hashlib.sha256(s.encode()).hexdigest()
def change(s,a,b):assert s.count(a)==1,a[:100];return s.replace(a,b,1)
s=(OUT/'Streaming-6211062a.cpp').read_text();assert digest(s)=='6211062ab620c0513a966468cfa66938d934486dbf8aa17be439300fb174ddb3'
s=change(s,'std::atomic<double> presentationOrigin{0};','std::atomic<bool> unsupportedTimeline{false};')
s=change(s,'    std::atomic<uint64_t> sealedWrite{UINT64_MAX};\n','')
start=s.index('        bool available=ring.pop(out);');end=s.index('consumed++;uint64_t zero=0;',start)
s=s[:start]+'        if(ring.pop(out)){'+s[end:]
s=change(s,'''            consumedDigest.add(out,1);if(seekAck>0)seekConsumedDigest.add(out,1);if(std::abs(out[0])>1e-8f||std::abs(out[1])>1e-8f)contentFrames++;
        }
''','''            consumedDigest.add(out,1);if(seekAck>0)seekConsumedDigest.add(out,1);if(std::abs(out[0])>1e-8f||std::abs(out[1])>1e-8f)contentFrames++;
        }else if(phase.load(std::memory_order_acquire)==Ended){uint64_t zero=0;ringDrainNS.compare_exchange_strong(zero,now);}
''')
s=change(s,r'\"presentation_origin_seconds\":%.8f,\"sealed_write_frames\":%llu,\"ring_read_frames\":%llu,\"ring_remaining_frames\":%llu,',r'\"unsupported_positive_timeline\":%s,')
s=change(s,'d->presentationOrigin.load(),d->sealedWrite.load(),d->ring.read.load(),d->ring.size(),','d->unsupportedTimeline?"true":"false",')
s=change(s,'''        // Positive presentation origins are relative to the first advertised
        // presentation timestamp. Negative codec preroll remains before zero.
        const double origin=track->start_time!=AV_NOPTS_VALUE?std::max(0.0,track->start_time*av_q2d(track->time_base)):0;
        presentationOrigin=origin;
''','''        // This P0 supports presentation origin zero and codec preroll before it.
        // Positive origins require a separately validated timeline mapping.
        if(track->start_time!=AV_NOPTS_VALUE&&track->start_time>0){unsupportedTimeline=true;throw AVERROR_PATCHWELCOME;}
''')
s=change(s,'track->start_time!=AV_NOPTS_VALUE&&track->start_time>=0&&track->duration','track->start_time==0&&track->duration')
s=change(s,'int64_t((origin+std::max(0.0,seconds-.12))/timebase)','int64_t(std::max(0.0,seconds-.12)/timebase)')
s=change(s,'frame->pts*timebase-origin-double','frame->pts*timebase-double')
s=change(s,'sealedWrite=ring.write.load();producerEndNS=','producerEndNS=')
s=change(s,'''        require(session.reason==5&&session.first.codecDrainNS&&session.first.swrDrainNS&&session.first.producerEndNS,"drain sequence");
        require(session.first.ring.read==session.first.sealedWrite&&session.first.ring.size()==0,"sealed ring not drained");};''','''        require(session.reason==5&&session.first.codecDrainNS&&session.first.swrDrainNS&&session.first.producerEndNS,"drain sequence");};''')
s=change(s,'}else if(!strcmp(mode,"disconnect")){','}else if(!strcmp(mode,"disconnect")||!strcmp(mode,"offset-reject")){')
s=change(s,'require(failed&&session.first.error!=0,"expected input rejection");session.finish(4);','require(failed&&session.first.error!=0,"expected input rejection");if(!strcmp(mode,"offset-reject"))require(session.first.unsupportedTimeline,"typed timeline rejection");session.finish(4);')
s=change(s,'||!strcmp(mode,"publish-seek")||!strcmp(mode,"timeline-seek")){','||!strcmp(mode,"publish-seek")){')
s=change(s,'''                pause_ms(400);if(!strcmp(mode,"timeline-seek")){require(session.first.firstCallback>0,"timeline input not consumed");std::puts("{\\"gate\\":\\"small_timeline_fixture\\",\\"partial_fetch_proved\\":false}");}else verifyEarly(session.first);
                double target=live?std::strtod(argv[3],nullptr):std::strtod(argv[5],nullptr);''','''                pause_ms(400);verifyEarly(session.first);double target=live?std::strtod(argv[3],nullptr):std::strtod(argv[5],nullptr);''')
s=change(s,'bool expectedFailure=!strcmp(mode,"disconnect")||!strcmp(mode,"late-failure");','bool expectedFailure=!strcmp(mode,"disconnect")||!strcmp(mode,"offset-reject")||!strcmp(mode,"late-failure");')
assert digest(s)=='3c3e4dcc6a036e6569bdac551f63757066014996db76bdc8287408f667505fa8',digest(s)
versions={'Streaming-3c3e4dcc.cpp':s}
s=change(s,'format->duration_estimation_method!=AVFMT_DURATION_FROM_BITRATE','av_fmt_ctx_get_duration_estimation_method(format)!=AVFMT_DURATION_FROM_BITRATE')
assert digest(s)=='2539398d91a482de404a06ddea1c61616a046481392d9337c768bbc1558a9afb',digest(s)
versions['Streaming-2539398d.cpp']=s
current=(HERE/'Streaming.cpp').read_text();manifest=json.loads((OUT/'manifest.json').read_text())
for name,text in versions.items():
 assert not (OUT/name).exists();(OUT/name).write_text(text)
 (OUT/(name+'.to-final.patch')).write_text(''.join(difflib.unified_diff(text.splitlines(keepends=True),current.splitlines(keepends=True),fromfile=name,tofile='Streaming.cpp')))
 manifest['files'][name]={'sha256':digest(text),'bytes':len(text.encode())}
(OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({name:digest(text) for name,text in versions.items()}))
