// SPDX-License-Identifier: MIT
#import <AppKit/AppKit.h>
#import <AVFoundation/AVFoundation.h>
#import <CoreAudio/CoreAudio.h>
#include <mach/mach_time.h>
#include <os/lock.h>
#include "calibration.h"

static CalGate Gate;
static mach_timebase_info_data_t Timebase;
static uint64_t HostNS(void){return (uint64_t)((__uint128_t)mach_absolute_time()*Timebase.numer/Timebase.denom);}
static uint64_t TicksToNS(uint64_t ticks){return (uint64_t)((__uint128_t)ticks*Timebase.numer/Timebase.denom);}
static NSString *const ReceiptDirectory=@"/Users/xiaotwu/.muses/tmp/p0-20261110-01/interop/macos-calibration/receipts";

static BOOL ReadProperty(AudioObjectID object,AudioObjectPropertySelector selector,AudioObjectPropertyScope scope,void *out,UInt32 bytes){AudioObjectPropertyAddress p={selector,scope,kAudioObjectPropertyElementMain};return AudioObjectGetPropertyData(object,&p,0,NULL,&bytes,out)==noErr;}
static NSDictionary *DeviceFacts(BOOL input){
    AudioDeviceID device=0;AudioObjectPropertyScope scope=input?kAudioObjectPropertyScopeInput:kAudioObjectPropertyScopeOutput;
    if(!ReadProperty(kAudioObjectSystemObject,input?kAudioHardwarePropertyDefaultInputDevice:kAudioHardwarePropertyDefaultOutputDevice,kAudioObjectPropertyScopeGlobal,&device,sizeof(device))||!device)return @{@"available":@NO};
    UInt32 transport=0,latency=0,safety=0,frames=0,mute=0;Float64 rate=0;Float32 volume=0;CFStringRef name=NULL;
    BOOL transportKnown=ReadProperty(device,kAudioDevicePropertyTransportType,kAudioObjectPropertyScopeGlobal,&transport,sizeof(transport));
    BOOL latencyKnown=ReadProperty(device,kAudioDevicePropertyLatency,scope,&latency,sizeof(latency));
    BOOL safetyKnown=ReadProperty(device,kAudioDevicePropertySafetyOffset,scope,&safety,sizeof(safety));
    BOOL framesKnown=ReadProperty(device,kAudioDevicePropertyBufferFrameSize,kAudioObjectPropertyScopeGlobal,&frames,sizeof(frames));
    BOOL rateKnown=ReadProperty(device,kAudioDevicePropertyNominalSampleRate,kAudioObjectPropertyScopeGlobal,&rate,sizeof(rate));
    BOOL volumeKnown=ReadProperty(device,kAudioDevicePropertyVolumeScalar,scope,&volume,sizeof(volume));
    BOOL muteKnown=ReadProperty(device,kAudioDevicePropertyMute,scope,&mute,sizeof(mute));
    ReadProperty(device,kAudioObjectPropertyName,kAudioObjectPropertyScopeGlobal,&name,sizeof(name));
    NSString *label=CFBridgingRelease(name)?:@"unknown";BOOL builtin=transportKnown&&transport==kAudioDeviceTransportTypeBuiltIn;
    if(!builtin)label=@"non_builtin_device";
    // Device names are retained for route review; stable device UIDs are not read.
    return @{@"available":@YES,@"name":label,@"built_in":@(builtin),@"nominal_rate":rateKnown?@(rate):(id)NSNull.null,@"device_latency_frames":latencyKnown?@(latency):(id)NSNull.null,@"safety_offset_frames":safetyKnown?@(safety):(id)NSNull.null,@"buffer_frames":framesKnown?@(frames):(id)NSNull.null,@"volume_scalar":volumeKnown?@(volume):(id)NSNull.null,@"muted":muteKnown?@(mute!=0):(id)NSNull.null};
}

@interface CalRun:NSObject {
@public
    uint64_t generation,startNS,hardStopNS,clickHandlerNS;
    double clickEventSeconds,inputRate,outputRate;
    float *samples,*markers[2];size_t capacity,written,markerFrames,outputFrame,ownedAudioBytes;
    CalAnchor anchors[CAL_MAX_ANCHORS];size_t anchorCount;
    os_unfair_lock captureLock;
    _Atomic unsigned fault;
    _Atomic uint64_t renderMarkerNS[2],submitMarkerNS[2];
}
@property AVAudioEngine *engine;
@property AVAudioSourceNode *source;
@property dispatch_source_t timer;
@property id configurationObserver;
@property NSDictionary *inputDevice,*outputDevice;
@property double reportedOutputPresentationLatency;
@property BOOL tapInstalled,started;
@end
@implementation CalRun
- (instancetype)init{if((self=[super init])){captureLock=OS_UNFAIR_LOCK_INIT;atomic_init(&fault,0);for(int i=0;i<2;i++){atomic_init(&renderMarkerNS[i],0);atomic_init(&submitMarkerNS[i],0);}}return self;}
- (void)dealloc{if(samples){cal_wipe(samples,capacity*sizeof(float));free(samples);}for(int i=0;i<2;i++)free(markers[i]);}
@end
static bool AnalysisCancelled(void *opaque){CalRun *run=(__bridge CalRun *)opaque;return !cal_gate_finishing(&Gate,run->generation);}

@interface CalibrationApp:NSObject<NSApplicationDelegate,NSWindowDelegate>
@property NSWindow *window;
@property NSTextField *status;
@property NSButton *start,*cancel,*consent;
@property NSTextView *summary;
@property dispatch_queue_t control;
@property CalRun *run; // control queue only
@property id sleepObserver;
@end

@implementation CalibrationApp
- (void)applicationDidFinishLaunching:(NSNotification *)note{
    (void)note;cal_gate_init(&Gate);mach_timebase_info(&Timebase);self.control=dispatch_queue_create("org.muses.p0.calibration.control",DISPATCH_QUEUE_SERIAL);
    self.window=[[NSWindow alloc] initWithContentRect:NSMakeRect(0,0,720,590) styleMask:NSWindowStyleMaskTitled|NSWindowStyleMaskClosable backing:NSBackingStoreBuffered defer:NO];
    self.window.title=@"Muses 声学校准（P0）";self.window.delegate=self;self.window.releasedWhenClosed=NO;
    NSView *view=self.window.contentView;
    NSTextField *title=[NSTextField labelWithString:@"短时扬声器 → 麦克风校准"];title.font=[NSFont systemFontOfSize:22 weight:NSFontWeightSemibold];title.frame=NSMakeRect(28,535,665,30);[view addSubview:title];
    NSTextField *explanation=[NSTextField wrappingLabelWithString:@"仅校准测量链。开始后播放两段短校准声，并采集内建麦克风中的环境音，最长 8 秒。录音只在内存中使用，不保存；仅保存测量摘要。请停止其他声音并保持安静。尚未进行真实声学验证。"];
    explanation.frame=NSMakeRect(28,437,665,84);[view addSubview:explanation];
    self.consent=[NSButton checkboxWithTitle:@"我已知晓并同意这次短时环境音采集" target:nil action:nil];self.consent.frame=NSMakeRect(28,402,650,28);[view addSubview:self.consent];
    self.start=[NSButton buttonWithTitle:@"开始短时校准" target:self action:@selector(startClicked:)];self.start.bezelStyle=NSBezelStyleRounded;self.start.frame=NSMakeRect(28,357,180,34);[view addSubview:self.start];
    self.cancel=[NSButton buttonWithTitle:@"取消并停止" target:self action:@selector(cancelClicked:)];self.cancel.frame=NSMakeRect(220,357,140,34);self.cancel.enabled=NO;self.cancel.keyEquivalent=@"\e";[view addSubview:self.cancel];
    self.status=[NSTextField wrappingLabelWithString:@"空闲：未申请麦克风权限，未采集，未播放。"];self.status.frame=NSMakeRect(28,298,665,48);[view addSubview:self.status];
    NSScrollView *scroll=[[NSScrollView alloc] initWithFrame:NSMakeRect(28,28,665,255)];scroll.hasVerticalScroller=YES;scroll.borderType=NSBezelBorder;
    self.summary=[[NSTextView alloc] initWithFrame:scroll.bounds];self.summary.editable=NO;self.summary.font=[NSFont monospacedSystemFontOfSize:11 weight:NSFontWeightRegular];self.summary.string=@"尚无测量结果。这个工具不能代替 30 个来源、100 次真实播放基线。";scroll.documentView=self.summary;[view addSubview:scroll];
    __weak CalibrationApp *weakSelf=self;
    self.sleepObserver=[NSWorkspace.sharedWorkspace.notificationCenter addObserverForName:NSWorkspaceWillSleepNotification object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n){(void)n;[weakSelf cancelClicked:nil];}];
    [self.window center];[self.window makeKeyAndOrderFront:nil];[NSApp activateIgnoringOtherApps:YES];
    // No AVAudioEngine, input node, permission request, or timer is created here.
}
- (BOOL)applicationShouldTerminateAfterLastWindowClosed:(NSApplication *)sender{(void)sender;return YES;}
- (NSApplicationTerminateReply)applicationShouldTerminate:(NSApplication *)sender{
    (void)sender;[self cancelClicked:nil];dispatch_async(self.control,^{[self stopRun:@"application_terminated" analyze:NO];dispatch_async(dispatch_get_main_queue(),^{[NSApp replyToApplicationShouldTerminate:YES];});});return NSTerminateLater;
}
- (void)windowWillClose:(NSNotification *)notification{(void)notification;[self cancelClicked:nil];}
- (void)windowDidMiniaturize:(NSNotification *)notification{(void)notification;[self cancelClicked:nil];}
- (void)cancelClicked:(id)sender{
    (void)sender;if(!cal_gate_cancel(&Gate))return;self.cancel.enabled=NO;self.status.stringValue=@"正在停止；音频回调已禁止提交新声音和录音样本。";
    dispatch_async(self.control,^{if(self.run)[self stopRun:@"cancelled" analyze:NO];});
}
- (void)permissionFinished:(uint64_t)generation reason:(NSString *)reason{
    cal_gate_finish(&Gate,generation);cal_gate_reset(&Gate,generation);
    dispatch_async(dispatch_get_main_queue(),^{self.start.enabled=YES;self.consent.enabled=YES;self.cancel.enabled=NO;self.status.stringValue=reason;});
}
- (void)startClicked:(id)sender{
    (void)sender;if(self.consent.state!=NSControlStateValueOn){self.status.stringValue=@"请先确认本次环境音采集说明。";return;}
    uint64_t generation=cal_gate_begin(&Gate);if(!generation)return;
    uint64_t clickHost=HostNS();double clickEvent=NSApp.currentEvent.timestamp;
    self.start.enabled=NO;self.consent.enabled=NO;self.cancel.enabled=YES;self.status.stringValue=@"等待麦克风权限；尚未播放或采集。";
    void (^authorized)(BOOL)=^(BOOL granted){dispatch_async(self.control,^{
        if(!granted){[self permissionFinished:generation reason:@"未获得麦克风权限；未播放或采集。请在系统设置中自行确认权限。"] ;return;}
        if(!cal_gate_start(&Gate,generation)){[self permissionFinished:generation reason:@"已取消；未开始采集。"] ;return;}
        [self startGranted:generation clickHost:clickHost clickEvent:clickEvent];
    });};
    AVAuthorizationStatus status=[AVCaptureDevice authorizationStatusForMediaType:AVMediaTypeAudio];
    if(status==AVAuthorizationStatusNotDetermined)[AVCaptureDevice requestAccessForMediaType:AVMediaTypeAudio completionHandler:authorized];
    else authorized(status==AVAuthorizationStatusAuthorized);
}
- (void)startGranted:(uint64_t)generation clickHost:(uint64_t)clickHost clickEvent:(double)clickEvent{
    CalRun *r=[CalRun new];r->generation=generation;r->clickHandlerNS=clickHost;r->clickEventSeconds=clickEvent;self.run=r;
    r.inputDevice=DeviceFacts(YES);r.outputDevice=DeviceFacts(NO);
    if(![r.inputDevice[@"built_in"] boolValue]||![r.outputDevice[@"built_in"] boolValue]){[self stopRun:@"built_in_input_and_output_required" analyze:NO];return;}
    if([r.outputDevice[@"muted"] isEqual:@YES]){[self stopRun:@"output_muted" analyze:NO];return;}
    NSDictionary *disk=[NSFileManager.defaultManager attributesOfFileSystemForPath:ReceiptDirectory.stringByDeletingLastPathComponent error:nil];
    if([disk[NSFileSystemFreeSize] unsignedLongLongValue]<40ull*1024*1024*1024){[self stopRun:@"free_space_floor" analyze:NO];return;}
    NSArray *existing=[[NSFileManager defaultManager] contentsOfDirectoryAtPath:ReceiptDirectory error:nil];if(existing.count>=32){[self stopRun:@"receipt_limit_32" analyze:NO];return;}
    if(!cal_gate_running(&Gate,generation)){[self stopRun:@"cancelled" analyze:NO];return;}
    r.engine=[AVAudioEngine new];AVAudioInputNode *input=r.engine.inputNode;
    AVAudioFormat *inFormat=[input outputFormatForBus:0],*outFormat=[r.engine.outputNode inputFormatForBus:0];
    r->inputRate=inFormat.sampleRate;r->outputRate=outFormat.sampleRate;
    if(r->inputRate<16000||r->inputRate>192000||r->outputRate<16000||r->outputRate>192000||inFormat.commonFormat!=AVAudioPCMFormatFloat32||inFormat.interleaved||inFormat.channelCount<1||inFormat.channelCount>2){[self stopRun:@"unsupported_device_format" analyze:NO];return;}
    r->capacity=(size_t)ceil(r->inputRate*CAL_MAX_SECONDS);r->markerFrames=(size_t)llround(r->outputRate*CAL_MARKER_SECONDS);
    size_t ownedAudio=r->capacity*sizeof(float)+2*r->markerFrames*sizeof(float)+(size_t)(CAL_ANALYSIS_RATE*CAL_MAX_SECONDS+2*CAL_ANALYSIS_RATE*CAL_MARKER_SECONDS)*sizeof(float)+128*1024;
    r->ownedAudioBytes=ownedAudio;
    if(ownedAudio>CAL_AUDIO_BYTES){[self stopRun:@"audio_memory_limit" analyze:NO];return;}
    r->samples=calloc(r->capacity,sizeof(float));for(int i=0;i<2;i++)r->markers[i]=calloc(r->markerFrames,sizeof(float));
    if(!r->samples||!r->markers[0]||!r->markers[1]){[self stopRun:@"allocation_failed" analyze:NO];return;}
    for(int i=0;i<2;i++)cal_make_marker(i,r->outputRate,r->markers[i],r->markerFrames);
    AVAudioFormat *sourceFormat=[[AVAudioFormat alloc] initStandardFormatWithSampleRate:r->outputRate channels:1];
    r.source=[[AVAudioSourceNode alloc] initWithFormat:sourceFormat renderBlock:^OSStatus(BOOL *silence,const AudioTimeStamp *timestamp,AVAudioFrameCount count,AudioBufferList *buffers){
        bool active=cal_gate_running(&Gate,r->generation)&&HostNS()<r->hardStopNS;*silence=YES;
        for(UInt32 b=0;b<buffers->mNumberBuffers;b++)memset(buffers->mBuffers[b].mData,0,buffers->mBuffers[b].mDataByteSize);
        if(count>8192){atomic_store(&r->fault,4);return noErr;}
        if(!active)return noErr;
        for(unsigned marker=0;marker<2;marker++){
            size_t start=(size_t)llround((.5+marker*CAL_MARKER_GAP_SECONDS)*r->outputRate),end=start+r->markerFrames;
            if(r->outputFrame+count<=start||r->outputFrame>=end)continue;
            size_t offset=start>r->outputFrame?start-r->outputFrame:0;
            if(!atomic_load(&r->renderMarkerNS[marker])){
                if(!(timestamp->mFlags&kAudioTimeStampHostTimeValid)){atomic_store(&r->fault,1);continue;}
                atomic_store(&r->renderMarkerNS[marker],TicksToNS(timestamp->mHostTime)+(uint64_t)llround(offset/r->outputRate*1e9));
            }
            for(size_t i=offset;i<count&&r->outputFrame+i<end;i++){
                if((i&31)==0&&(!cal_gate_running(&Gate,r->generation)||HostNS()>=r->hardStopNS))break;
                float value=r->markers[marker][r->outputFrame+i-start];
                for(UInt32 b=0;b<buffers->mNumberBuffers;b++){AudioBuffer *buffer=&buffers->mBuffers[b];size_t available=buffer->mDataByteSize/sizeof(float);float *dst=buffer->mData;for(UInt32 ch=0;ch<buffer->mNumberChannels;ch++)if(i*buffer->mNumberChannels+ch<available)dst[i*buffer->mNumberChannels+ch]=value;}
                if(value!=0&&!atomic_load(&r->submitMarkerNS[marker]))atomic_store(&r->submitMarkerNS[marker],HostNS());
                *silence=NO;
            }
        }r->outputFrame+=count;return noErr;
    }];
    [r.engine attachNode:r.source];[r.engine connect:r.source to:r.engine.mainMixerNode format:sourceFormat];
    [input installTapOnBus:0 bufferSize:512 format:inFormat block:^(AVAudioPCMBuffer *buffer,AVAudioTime *when){
        if(!cal_gate_running(&Gate,r->generation)||HostNS()>=r->hardStopNS)return;
        if(!when.hostTimeValid||!buffer.floatChannelData||buffer.frameLength>8192||buffer.format.sampleRate!=r->inputRate){atomic_store(&r->fault,1);return;}
        if(!os_unfair_lock_trylock(&r->captureLock)){atomic_store(&r->fault,2);return;}
        if(cal_gate_running(&Gate,r->generation)){
            size_t frames=buffer.frameLength;
            if(r->written+frames>r->capacity||r->anchorCount>=CAL_MAX_ANCHORS)atomic_store(&r->fault,3);
            else{r->anchors[r->anchorCount++]=(CalAnchor){r->written,TicksToNS(when.hostTime)};memcpy(r->samples+r->written,buffer.floatChannelData[0],frames*sizeof(float));r->written+=frames;}
        }os_unfair_lock_unlock(&r->captureLock);
    }];r.tapInstalled=YES;
    if(!cal_gate_running(&Gate,generation)){[self stopRun:@"cancelled" analyze:NO];return;}
    r->startNS=HostNS();r->hardStopNS=r->startNS+8000000000ull;
    NSError *error=nil;if(![r.engine startAndReturnError:&error]){[self stopRun:@"engine_start_failed" analyze:NO];return;}r.started=YES;
    r.reportedOutputPresentationLatency=r.source.outputPresentationLatency;
    __weak CalibrationApp *weakSelf=self;
    r.configurationObserver=[NSNotificationCenter.defaultCenter addObserverForName:AVAudioEngineConfigurationChangeNotification object:r.engine queue:nil usingBlock:^(NSNotification *n){(void)n;cal_gate_cancel_generation(&Gate,r->generation);CalibrationApp *owner=weakSelf;if(owner)dispatch_async(owner.control,^{if(owner.run==r)[owner stopRun:@"audio_configuration_changed" analyze:NO];});}];
    r.timer=dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER,0,0,self.control);dispatch_source_set_timer(r.timer,dispatch_time(DISPATCH_TIME_NOW,100000000),100000000,1000000);
    dispatch_source_set_event_handler(r.timer,^{CalibrationApp *owner=weakSelf;if(!owner||owner.run!=r)return;uint64_t elapsed=HostNS()-r->startNS;if(!cal_gate_running(&Gate,r->generation))[owner stopRun:@"cancelled" analyze:NO];else if(atomic_load(&r->fault))[owner stopRun:@"capture_timestamp_or_buffer_invalid" analyze:NO];else if(elapsed>=6000000000ull)[owner stopRun:@"capture_complete" analyze:YES];});dispatch_resume(r.timer);
    dispatch_async(dispatch_get_main_queue(),^{self.status.stringValue=@"正在短时校准：将播放两段声音并采集环境音。6 秒后自动停止，硬上限 8 秒。";});
}
- (void)stopRun:(NSString *)reason analyze:(BOOL)analyze{
    CalRun *r=self.run;if(!r)return;self.run=nil;BOOL mayAnalyze=cal_gate_finish(&Gate,r->generation);
    if(analyze&&!mayAnalyze){analyze=NO;reason=@"cancelled";}
    if(r.timer){dispatch_source_cancel(r.timer);r.timer=nil;}
    if(r.configurationObserver){[NSNotificationCenter.defaultCenter removeObserver:r.configurationObserver];r.configurationObserver=nil;}
    [r.engine stop];if(r.tapInstalled)[r.engine.inputNode removeTapOnBus:0];r.tapInstalled=NO;r.source=nil;r.engine=nil;
    uint64_t stoppedNS=HostNS();os_unfair_lock_lock(&r->captureLock);
    CalResult result={0};result.reason=reason.UTF8String;result.confidence="invalid";
    BOOL sameRoute=[r.inputDevice isEqual:DeviceFacts(YES)]&&[r.outputDevice isEqual:DeviceFacts(NO)];
    if(analyze&&sameRoute&&!atomic_load(&r->fault)&&atomic_load(&r->renderMarkerNS[0])&&atomic_load(&r->renderMarkerNS[1])){
        CalCapture capture={r->samples,r->written,r->inputRate,r->anchors,r->anchorCount,AnalysisCancelled,(__bridge void *)r};result=cal_analyze(&capture);
    }else if(analyze)result.reason=sameRoute?"missing_output_or_capture_clock":"route_or_gain_changed";
    NSMutableArray *matches=[NSMutableArray array];
    if(result.valid)for(int i=0;i<2;i++){
        CalMatch m=result.markers[i];uint64_t rendered=atomic_load(&r->renderMarkerNS[i]);
        [matches addObject:@{@"marker":@(i),@"source_render_host_ns":@(rendered),@"source_callback_submission_host_ns":@(atomic_load(&r->submitMarkerNS[i])),@"microphone_reference_host_ns":@(m.reference_host_ns),@"microphone_sustained_onset_host_ns":@(m.onset_host_ns),@"observed_render_to_microphone_reference_ms":@(((int64_t)m.reference_host_ns-(int64_t)rendered)/1e6),@"correlation":@(m.correlation),@"runner_up":@(m.runner_up_correlation),@"signal_rms":@(m.signal_rms)}];
    }
    if(r->samples)cal_wipe(r->samples,r->capacity*sizeof(float));os_unfair_lock_unlock(&r->captureLock);
    // Cancellation before this CAS wins even after the detector's final poll.
    // After it succeeds the operation is complete; a later Cancel is a no-op.
    if(!cal_gate_commit_result(&Gate,r->generation)){
        result.valid=NO;result.reason="cancelled";result.confidence="invalid";
        [matches removeAllObjects];cal_gate_reset(&Gate,r->generation);
    }
    NSDictionary *summary=@{@"schema":@1,
        @"detector_version":@CAL_VERSION,
        @"source_set_sha256":[NSBundle.mainBundle objectForInfoDictionaryKey:@"P0CalibrationSourceSetSHA256"]?:@"unknown",
        @"owned_audio_reservation_bytes":@(r->ownedAudioBytes),
        @"application_signal_gain":@1.0,
        @"kind":@"measurement_chain_calibration_only",
        @"outcome":result.valid?@"acoustic_markers_matched":@"measurement_invalid",
        @"reason":@(result.reason),
        @"confidence_class":@(result.confidence),
        @"confidence_is_probability":@NO,
        @"baseline_attempt":@NO,
        @"raw_audio_saved":@NO,
        @"input_rate":@(r->inputRate),
        @"output_rate":@(r->outputRate),
        @"input_device":r.inputDevice?:@{},
        @"output_device":r.outputDevice?:@{},
        @"input_channel":@0,
        @"input_frames":@(r->written),
        @"input_anchors":@(r->anchorCount),
        @"capture_start_host_ns":@(r->startNS),
        @"capture_stopped_host_ns":@(stoppedNS),
        @"click_event_timestamp_seconds":@(r->clickEventSeconds),
        @"click_handler_host_ns":@(r->clickHandlerNS),
        @"noise_rms":@(result.noise_rms),
        @"clipped_fraction":@(result.clipped_fraction),
        @"input_clock_drift_ppm":@(result.clock_drift_ppm),
        @"input_clock_max_fit_residual_ms":@(result.clock_max_residual_ms),
        @"detector_resolution_and_clock_residual_ms":result.valid?@(result.detector_error_bound_ms):(id)NSNull.null,
        @"total_physical_error_bound_ms":NSNull.null,
        @"reported_output_presentation_latency_s":@(r.reportedOutputPresentationLatency),
        @"markers":matches,
        @"submission_point":@"AVAudioSourceNode render callback before mixer and hardware",
        @"limits":@{@"capture_seconds":@8,
        @"owned_audio_bytes":@(CAL_AUDIO_BYTES),
        @"receipt_count":@32},
        @"interpretation":@"Acoustic capture observation only. Device timestamp bias and DAC/speaker/propagation/ADC components are not separately calibrated. No L_sound or p95 is computed; hardware-reported latency is not silently subtracted."};
    NSData *json=[NSJSONSerialization dataWithJSONObject:summary options:NSJSONWritingPrettyPrinted|NSJSONWritingSortedKeys error:nil];
    BOOL saved=NO;NSDictionary *disk=[NSFileManager.defaultManager attributesOfFileSystemForPath:ReceiptDirectory.stringByDeletingLastPathComponent error:nil];if(json.length<=65536&&[disk[NSFileSystemFreeSize] unsignedLongLongValue]>=40ull*1024*1024*1024){NSFileManager *fm=NSFileManager.defaultManager;[fm createDirectoryAtPath:ReceiptDirectory withIntermediateDirectories:YES attributes:@{NSFilePosixPermissions:@0700} error:nil];NSArray *files=[fm contentsOfDirectoryAtPath:ReceiptDirectory error:nil];if(files.count<32){NSString *path=[ReceiptDirectory stringByAppendingPathComponent:[NSString stringWithFormat:@"calibration-%llu-%llu.json",r->generation,stoppedNS]];saved=[json writeToFile:path options:NSDataWritingAtomic error:nil];}}
    dispatch_async(dispatch_get_main_queue(),^{self.start.enabled=YES;self.consent.enabled=YES;self.cancel.enabled=NO;self.status.stringValue=[NSString stringWithFormat:@"%@。%@；本工具持有的录音缓冲已清除。",result.valid?@"检测到两段匹配标记":@"本次测量无效或已取消",saved?@"摘要已保存":@"摘要未保存，请查看下方"];self.summary.string=[[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding]?:@"summary_serialization_failed";});
}
@end

int main(void){@autoreleasepool{NSApplication *app=NSApplication.sharedApplication;[app setActivationPolicy:NSApplicationActivationPolicyRegular];CalibrationApp *delegate=[CalibrationApp new];app.delegate=delegate;[app run];}return 0;}
