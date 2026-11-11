#!/usr/bin/env python3
"""Recover exact earlier source bytes by inverse edits; reject nonmatching hashes.

This generates text evidence only, not an alternative executable or new test.
Every expected digest was recorded by the original attempt before reconstruction.
"""
from pathlib import Path
import difflib,hashlib,json
HERE=Path(__file__).resolve().parent
def digest(text):return hashlib.sha256(text.encode()).hexdigest()
def change(s,after,before):
 assert s.count(after)==1,after[:100]
 return s.replace(after,before,1)
def remove_line(s,needle):
 lines=s.splitlines(keepends=True);found=[line for line in lines if needle in line];assert len(found)==1,needle
 return s.replace(found[0],'',1)
current=(HERE/'Streaming.cpp').read_text()
assert digest(current)=='b1adba3d2375676d270a144dcd8b3e92463173ea0d671c951e7e7a58b2b19b28'
versions={}
s=current
s=change(s,'#include <libavutil/intreadwrite.h>\n#include <libavutil/mathematics.h>\n','')
s=remove_line(s,'std::atomic<bool> mappedAACPadding')
s=remove_line(s,'\\"gate\\":\\"timeline_policy\\"')
start=s.index('        const double timebase=av_q2d(track->time_base);\n')
end=s.index('        require(std::isfinite(origin)',start)
s=s[:start]+'''        // Positive presentation origins are relative to the first advertised
        // presentation timestamp. Negative codec preroll remains before zero.
        const double origin=track->start_time!=AV_NOPTS_VALUE?std::max(0.0,track->start_time*av_q2d(track->time_base)):0;
'''+s[end:]
s=change(s,'        double target=initialSeek,nextPTS=0;','        const double timebase=av_q2d(track->time_base);double target=initialSeek,nextPTS=0;')
s=change(s,'auto at=originTicks+int64_t(std::max(0.0,seconds-.12)/timebase);','auto at=(origin>0?track->start_time:0)+int64_t(std::max(0.0,seconds-.12)/timebase);')
start=s.index('            if(packet->stream_index==stream){if(mappedAACPadding)')
end=s.index('                code=avcodec_send_packet(codec,packet);',start)
s=s[:start]+'''            if(packet->stream_index==stream){if(currentSeek&&seekFirstPacketPTS<0&&packet->pts!=AV_NOPTS_VALUE)seekFirstPacketPTS=packet->pts*timebase-origin;
'''+s[end:]
assert digest(s)=='19355d1df02198a01e06cb7bca2d541c25a9acda9bf9a3e4fed1e5a054ae5ad7',digest(s)
versions['Streaming-19355d1d.cpp']=s
for needle in ('std::atomic<int> firstNonCancelTransportFailure','std::atomic<bool> holdFailureReturn','std::atomic<uint64_t> seekCodecResets'):
 s=remove_line(s,needle)
start=s.index('        size_t got=0;d.readEpoch.fetch_add')
end=s.index('        d.network=s.network_bytes;',start)
s=s[:start]+'''        size_t got=0;d.readEpoch.fetch_add(1,std::memory_order_release);d.inflight=true;MTStatus status=mt_read_at(d.handle,d.position,buffer,size,&got);MTStats s{};mt_snapshot(d.handle,&s);
'''+s[end:]
s=change(s,'d->ring.releasePublish=true;d->releaseFailureReturn=true;mt_cancel(d->handle);','d->ring.releasePublish=true;mt_cancel(d->handle);')
s=change(s,'''        for(auto *d:{&first,&next})if(d->worker.joinable()){d->worker.join();joinedWorkers++;}
        if(first.error||next.error||first.firstNonCancelTransportFailure||next.firstNonCancelTransportFailure)reason=4;joined=true;}''',
'''        for(auto *d:{&first,&next})if(d->worker.joinable()){d->worker.join();joinedWorkers++;}joined=true;}''')
s=remove_line(s,'\\"gate\\":\\"failure_latch\\"')
s=remove_line(s,'\\"gate\\":\\"seek_work\\"')
s=remove_line(s,'require(std::isfinite(origin)&&origin<=1000000')
start=s.index('        auto performSeek=')
end=s.index('        if(target>0)performSeek(target);',start)
s=s[:start]+'''        auto performSeek=[&](double seconds){auto at=int64_t((origin+std::max(0.0,seconds-.12))/timebase);ok(avformat_seek_file(format,stream,INT64_MIN,at,at,AVSEEK_FLAG_BACKWARD));
            avcodec_flush_buffers(codec);swr_close(swr);ok(swr_init(swr));nextPTS=seconds;target=seconds;seekFirstPTS=-1;};
'''+s[end:]
s=remove_line(s,'if(currentSeek)seekTrimmedFrames+=begin;')
start=s.index('            if(packet->stream_index==stream){if(currentSeek&&seekFirstPacketPTS')
end=s.index('            av_packet_unref(packet);',start)
s=s[:start]+'''            if(packet->stream_index==stream){code=avcodec_send_packet(codec,packet);if(code==AVERROR(EAGAIN)){receive(Decoding);code=avcodec_send_packet(codec,packet);}ok(code);receive(Decoding);}
'''+s[end:]
s=change(s,'''        if(stopping()&&phase!=Ended){if(firstNonCancelTransportFailure){error=AVERROR(EIO);phase=Failed;}else phase=Cancelled;}
    }catch(int code){if(stopping()&&!firstNonCancelTransportFailure)phase=Cancelled;else{error=code;phase=Failed;}}
     catch(...){if(stopping()&&!firstNonCancelTransportFailure)phase=Cancelled;else{error=AVERROR_UNKNOWN;phase=Failed;}}''',
'''        if(stopping()&&phase!=Ended)phase=Cancelled;
    }catch(int code){if(stopping())phase=Cancelled;else{error=code;phase=Failed;}}
     catch(...){if(stopping())phase=Cancelled;else{error=AVERROR_UNKNOWN;phase=Failed;}}''')
start=s.index('        session.attach(session.first,source);')
end=s.index('            session.prepare(session.first);pause_ms(80);require(session.first.ring.size()==capacity',start)
s=s[:start]+'''        session.attach(session.first,source);session.first.launch(0);
        if(!strcmp(mode,"full-ring-cancel")){
'''+s[end:]
s=change(s,'bool expectedFailure=!strcmp(mode,"disconnect")||!strcmp(mode,"late-failure")||!strcmp(mode,"failure-cancel-race");','bool expectedFailure=!strcmp(mode,"disconnect")||!strcmp(mode,"late-failure");')
s=change(s,'require(!session.first.error&&!session.next.error&&!session.first.firstNonCancelTransportFailure&&!session.next.firstNonCancelTransportFailure,"input error cannot pass");','require(!session.first.error&&!session.next.error,"input error cannot pass");')
s=remove_line(s,'int expectedReason=expectedFailure?4:')
s=remove_line(s,'require(session.reason==expectedReason,')
assert digest(s)=='6211062ab620c0513a966468cfa66938d934486dbf8aa17be439300fb174ddb3',digest(s)
versions['Streaming-6211062a.cpp']=s
# The exact old inspection script was saved before the formatting fix.
initial=(HERE/'build.initial.py').read_text();assert digest(initial)=='b80073ae2f4a1d499786be8d416e02698b589995a6f60ca0994fc4c9f55e97fc'
versions['build-b80073ae.py']=initial
runner=(HERE/'run_local.py').read_text();assert digest(runner)=='26d994beeeaaab7114f452d15df48c1f80db8b99c677f3005e510c24d07bc1ef'
runner=change(runner,",('failure-cancel-race','failure-cancel-race','aac',None)",'')
runner=change(runner,"else '?mode=disconnect' if mode in ('disconnect','failure-cancel-race') else ''","else '?mode=disconnect' if mode=='disconnect' else ''")
assert digest(runner)=='f36912b1486aff762d109e7b29b7457598250ae8d1bfc29cab86ec0e469b8bbe',digest(runner)
versions['run_local-f36912b1.py']=runner
OUT=HERE/'history';assert not OUT.exists();OUT.mkdir()
for name,text in versions.items():(OUT/name).write_text(text)
for name,text in versions.items():
 if name.startswith('Streaming-'):
  (OUT/(name+'.to-final.patch')).write_text(''.join(difflib.unified_diff(text.splitlines(keepends=True),current.splitlines(keepends=True),fromfile=name,tofile='Streaming.cpp')))
(OUT/'manifest.json').write_text(json.dumps({'method':'inverse exact recorded edits; every recovered source SHA must match its original receipt','files':{name:{'sha256':digest(text),'bytes':len(text.encode())} for name,text in versions.items()},'final_source_sha256':digest(current)},indent=2)+'\n')
print(json.dumps({name:digest(text) for name,text in versions.items()}))
