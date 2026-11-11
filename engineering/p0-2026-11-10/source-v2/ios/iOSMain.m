// MIT. Isolated source-v2 physical-device proof; no production UI or synthetic audio.
#import <UIKit/UIKit.h>
#import <AVFAudio/AVFAudio.h>
#import <MediaPlayer/MediaPlayer.h>
#import <mach/mach.h>
#import <sys/resource.h>
#include <math.h>
#include "../../audio/p0_audio.h"
#include "RunPolicy.h"

extern int P0V2RunSource(NSString *bundle, BOOL next);
extern void P0V2Cancel(void);
extern void P0SetMediaDirectory(NSString *directory);
extern void P0SetMediaHandler(void (^handler)(NSString *, BOOL));
extern void P0SetLogHandler(void (^handler)(NSString *));

static const uint64_t MiB = 1024*1024;
static double Uptime(void) { return NSProcessInfo.processInfo.systemUptime; }
static uint64_t Resident(void) {
    mach_task_basic_info_data_t info; mach_msg_type_number_t count = MACH_TASK_BASIC_INFO_COUNT;
    return task_info(mach_task_self(), MACH_TASK_BASIC_INFO, (task_info_t)&info, &count) == KERN_SUCCESS ? info.resident_size : UINT64_MAX;
}
// Fail closed on links, unreadable files, unexpected node types, or unbounded inventories.
static BOOL TreeBytes(NSString *path, uint64_t *logical, uint64_t *allocated) {
    NSFileManager *fm = NSFileManager.defaultManager;
    NSDictionary *root = [fm attributesOfItemAtPath:path error:nil];
    if (!root || ![root[NSFileType] isEqual:NSFileTypeDirectory]) return NO;
    __block BOOL failed=NO;
    NSDirectoryEnumerator *scan = [fm enumeratorAtURL:[NSURL fileURLWithPath:path]
        includingPropertiesForKeys:@[NSURLFileSizeKey, NSURLFileAllocatedSizeKey]
        options:0 errorHandler:^BOOL(NSURL *url, NSError *error) { failed=YES;return NO; }];
    if (!scan) return NO;
    uint64_t bytes = 0, blocks = 0; NSUInteger items = 0;
    for (NSURL *url in scan) {
        if (++items > 4096) return NO;
        NSDictionary *attrs = [fm attributesOfItemAtPath:url.path error:nil];
        NSString *type = attrs[NSFileType];
        if ([type isEqual:NSFileTypeDirectory]) continue;
        if (![type isEqual:NSFileTypeRegular]) return NO;
        NSNumber *size, *disk;
        if (![url getResourceValue:&size forKey:NSURLFileSizeKey error:nil] ||
            ![url getResourceValue:&disk forKey:NSURLFileAllocatedSizeKey error:nil]) return NO;
        if (size.unsignedLongLongValue > UINT64_MAX-bytes || disk.unsignedLongLongValue > UINT64_MAX-blocks) return NO;
        bytes += size.unsignedLongLongValue; blocks += disk.unsignedLongLongValue;
    }
    *logical = bytes; *allocated = blocks; return !failed;
}
static BOOL ProtectedDirectory(NSString *path) {
    NSFileManager *fm = NSFileManager.defaultManager;
    NSDictionary *existing=[fm attributesOfItemAtPath:path error:nil];
    if(existing && ![existing[NSFileType] isEqual:NSFileTypeDirectory])return NO;
    NSDictionary *attrs = @{NSFileProtectionKey:NSFileProtectionCompleteUntilFirstUserAuthentication};
    return [fm createDirectoryAtPath:path withIntermediateDirectories:YES attributes:attrs error:nil] &&
        [fm setAttributes:attrs ofItemAtPath:path error:nil] &&
        [[fm attributesOfItemAtPath:path error:nil][NSFileType] isEqual:NSFileTypeDirectory] &&
        [[fm attributesOfItemAtPath:path error:nil][NSFileProtectionKey] isEqual:NSFileProtectionCompleteUntilFirstUserAuthentication];
}
static NSString *StopName(int reason) {
    switch(reason) {
        case P0_STOP_USER:return @"user_stop"; case P0_STOP_RESOURCE:return @"resource_limit";
        case P0_STOP_DEADLINE:return @"90_second_deadline"; case P0_STOP_NOT_BACKGROUND:return @"not_background";
        case P0_STOP_SOURCE:return @"source_failure"; case P0_STOP_AUDIO:return @"audio_failure";
        case P0_STOP_STORAGE:return @"storage_limit"; case P0_STOP_TRACE:return @"trace_limit";
        default:return @"none";
    }
}

@interface P0Run : NSObject {
@public P0RunPolicy policy;
    atomic_uint sourceJobs;
    atomic_bool stopEnqueued, audioFinished, finishEnqueued;
}
@property uint64_t generation;
@property NSString *directory;
@property NSString *mediaDirectory;
@property NSString *tracePath;
@property dispatch_source_t monitor;
@property void *audio; // audioQueue only, including snapshots and destruction.
@property BOOL sessionActive; // audioQueue only.
@property NSUInteger traceRows, traceBytes; // evidenceQueue only.
@property BOOL traceLimitRecorded; // evidenceQueue only.
@property uint64_t residentHigh, cacheBytes, cacheAllocated, mediaBytes; // monitorQueue writer.
@property double lastResourceLog, lastAudioLog;
@end
@implementation P0Run
- (instancetype)init { if ((self=[super init])) { p0_policy_init(&policy); atomic_init(&sourceJobs,1); atomic_init(&stopEnqueued,false); atomic_init(&audioFinished,false); atomic_init(&finishEnqueued,false); } return self; }
@end

@interface P0Controller : UIViewController
@property UILabel *status;
@property UIButton *startButton;
@property dispatch_queue_t sourceQueue, audioQueue, monitorQueue, evidenceQueue;
@property P0Run *currentRun;
@property P0Run *sourceRun;
@property uint64_t nextGeneration;
@property NSString *cacheRoot;
@property NSString *lastSceneCallback; // main thread only.
@property id remoteStopTarget;
@property BOOL autoStartConsumed; // main thread only; Stop also cancels the five-second launch.
- (void)stopRun:(P0Run *)run reason:(int)reason;
- (void)finishIfReady:(P0Run *)run;
@end

@implementation P0Controller
- (void)viewDidLoad {
    [super viewDidLoad]; self.view.backgroundColor=UIColor.systemBackgroundColor;
    self.sourceQueue=dispatch_queue_create("org.muses.p0.v2.source",DISPATCH_QUEUE_SERIAL);
    self.audioQueue=dispatch_queue_create("org.muses.p0.v2.audio",DISPATCH_QUEUE_SERIAL);
    self.monitorQueue=dispatch_queue_create("org.muses.p0.v2.monitor",DISPATCH_QUEUE_SERIAL);
    self.evidenceQueue=dispatch_queue_create("org.muses.p0.v2.evidence",DISPATCH_QUEUE_SERIAL);
    self.cacheRoot=[NSSearchPathForDirectoriesInDomains(NSCachesDirectory,NSUserDomainMask,YES).firstObject stringByAppendingPathComponent:@"MusesP0SourceV2"];
    self.lastSceneCallback=@"unknown";
    UILabel *title=[UILabel new];title.text=@"Muses P0 · Source v2";title.font=[UIFont preferredFontForTextStyle:UIFontTextStyleTitle2];
    UILabel *hint=[UILabel new];hint.numberOfLines=0;hint.text=@"Start, wait for audio_started, then lock iPhone.\nAt audio +30 s, both native states must be background before the next source is freshly resolved.\nAudio stops at +90 s. No synthetic fallback.";
    self.status=[UILabel new];self.status.numberOfLines=0;self.status.text=@"Ready. Previous runs are retained; a full cache refuses a new run.";
    self.startButton=[UIButton buttonWithType:UIButtonTypeSystem];[self.startButton setTitle:@"Start real source proof" forState:UIControlStateNormal];[self.startButton addTarget:self action:@selector(start) forControlEvents:UIControlEventTouchUpInside];
    UIButton *stop=[UIButton buttonWithType:UIButtonTypeSystem];[stop setTitle:@"Stop" forState:UIControlStateNormal];[stop addTarget:self action:@selector(stop) forControlEvents:UIControlEventTouchUpInside];
    UIStackView *stack=[[UIStackView alloc]initWithArrangedSubviews:@[title,hint,self.startButton,stop,self.status]];stack.axis=UILayoutConstraintAxisVertical;stack.spacing=18;stack.translatesAutoresizingMaskIntoConstraints=NO;[self.view addSubview:stack];
    [NSLayoutConstraint activateConstraints:@[[stack.topAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.topAnchor constant:24],[stack.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor constant:24],[stack.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor constant:-24]]];
    __weak typeof(self) weak=self;
    P0SetLogHandler(^(NSString *line) {
        P0Run *run=weak.sourceRun; if(!run || line.length>32768)return;
        id event=[NSJSONSerialization JSONObjectWithData:[line dataUsingEncoding:NSUTF8StringEncoding] options:0 error:nil];
        if([event isKindOfClass:NSDictionary.class])[weak record:event run:run terminal:NO lifecycle:nil];
    });
    P0SetMediaHandler(^(NSString *path,BOOL next) { P0Run *run=weak.sourceRun; if(run)[weak acceptMedia:path next:next run:run]; });
    [NSNotificationCenter.defaultCenter addObserverForName:UIApplicationProtectedDataWillBecomeUnavailable object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n){P0Run *run=weak.currentRun;if(run)[weak record:@{@"gate":@"protected_data",@"outcome":@"will_become_unavailable"} run:run terminal:NO lifecycle:nil];}];
    [NSNotificationCenter.defaultCenter addObserverForName:UIApplicationProtectedDataDidBecomeAvailable object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n){P0Run *run=weak.currentRun;if(run)[weak record:@{@"gate":@"protected_data",@"outcome":@"available"} run:run terminal:NO lifecycle:nil];}];
    // Only a coordinator-requested launch flag opts in; normal opening is idle.
    if([NSProcessInfo.processInfo.arguments containsObject:@"--run-background-v2"])
        dispatch_after(dispatch_time(DISPATCH_TIME_NOW,5*NSEC_PER_SEC),dispatch_get_main_queue(),^{if(!weak.autoStartConsumed)[weak start];});
    // No remote early-next path.
}
- (BOOL)isCurrent:(P0Run *)run { @synchronized(self){return self.currentRun==run;} }
- (NSDictionary *)lifecycle {
    __block NSDictionary *value;
    void (^read)(void)=^{
        UIApplication *app=UIApplication.sharedApplication;UIWindowScene *scene=self.viewIfLoaded.window.windowScene;
        UIApplicationState a=app.applicationState;UISceneActivationState s=scene?scene.activationState:UISceneActivationStateUnattached;
        value=@{@"native_application_state":@(a),@"native_scene_activation_state":@(s),
            @"app_state":a==UIApplicationStateBackground?@"background":a==UIApplicationStateActive?@"active":@"inactive",
            @"scene_state":s==UISceneActivationStateBackground?@"background":s==UISceneActivationStateForegroundActive?@"foreground_active":s==UISceneActivationStateForegroundInactive?@"foreground_inactive":@"unattached",
            @"protected_data_available":@(app.protectedDataAvailable),@"state_sample_uptime_seconds":@(Uptime()),
            @"state_sample_on_main_thread":@(NSThread.isMainThread),@"last_scene_callback":self.lastSceneCallback?:@"unknown"};
    };
    if(NSThread.isMainThread)read();else dispatch_sync(dispatch_get_main_queue(),read);
    return value;
}
// Native logs are allowlisted again at the UI boundary. No raw error/string/URL dump.
- (NSDictionary *)safeEvent:(NSDictionary *)event {
    NSSet *strings=[NSSet setWithArray:@[@"gate",@"outcome",@"category",@"reason",@"status",@"phase",@"client",@"client_version",@"codec",@"video_id",@"sha256",@"pcm_sha256",@"transport_category",@"stop_reason"]];
    NSCharacterSet *allowed=[NSCharacterSet characterSetWithCharactersInString:@"abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_. -"];
    NSMutableDictionary *safe=[NSMutableDictionary dictionary];
    for(id key in event) {
        if(![key isKindOfClass:NSString.class] || [key length]>64)continue;
        NSString *lower=[key lowercaseString];BOOL private=NO;
        for(NSString *part in @[@"url",@"visitor",@"profile",@"token",@"cookie",@"authorization",@"header",@"path",@"filename"])if([lower containsString:part])private=YES;
        if(private)continue;id v=event[key];
        if([v isKindOfClass:NSNumber.class] && isfinite([v doubleValue]))safe[key]=v;
        else if([strings containsObject:key] && [v isKindOfClass:NSString.class] && [v length]<=128 && [v rangeOfCharacterFromSet:allowed.invertedSet].location==NSNotFound)safe[key]=v;
    }
    if(!safe[@"gate"])safe[@"gate"]=@"native_event";
    if(!safe[@"outcome"])safe[@"outcome"]=@"observed";
    return safe;
}
- (void)record:(NSDictionary *)event run:(P0Run *)run terminal:(BOOL)terminal lifecycle:(NSDictionary *)snapshot {
    double eventTime=Uptime();NSDictionary *safe=[self safeEvent:event];
    dispatch_async(self.evidenceQueue,^{
        NSMutableDictionary *row=[safe mutableCopy];[row addEntriesFromDictionary:snapshot?:[self lifecycle]];
        row[@"event_uptime_seconds"]=@(eventTime);row[@"run_generation"]=@(run.generation);row[@"test_mode"]=@"real_source_v2";
        NSData *json=[NSJSONSerialization dataWithJSONObject:row options:NSJSONWritingSortedKeys error:nil];
        NSMutableData *line=[json mutableCopy];[line appendBytes:"\n" length:1];
        BOOL room=json && p0_trace_admit(run.traceRows,run.traceBytes,line.length,terminal);
        if(!room){if(!run.traceLimitRecorded){run.traceLimitRecorded=YES;[self stopRun:run reason:P0_STOP_TRACE];}return;}
        if(run.tracePath) {
            NSFileHandle *file=[NSFileHandle fileHandleForWritingAtPath:run.tracePath];
            NSError *error=nil;BOOL wrote=file && [file seekToEndReturningOffset:NULL error:&error] && [file writeData:line error:&error];
            [file closeAndReturnError:nil];
            if(!wrote){[self stopRun:run reason:P0_STOP_STORAGE];return;}
        }
        run.traceRows++;run.traceBytes+=line.length;
        NSLog(@"P0V2 %@",[[NSString alloc]initWithData:json encoding:NSUTF8StringEncoding]);
        dispatch_async(dispatch_get_main_queue(),^{if([self isCurrent:run] && self.viewIfLoaded.window.windowScene.activationState==UISceneActivationStateForegroundActive)self.status.text=[NSString stringWithFormat:@"%@ · %@",safe[@"gate"],safe[@"outcome"]];});
    });
}
- (void)start {
    NSAssert(NSThread.isMainThread,@"UI owner");
    self.autoStartConsumed=YES;
    P0Run *run=[P0Run new];
    @synchronized(self){if(self.currentRun)return;run.generation=++self.nextGeneration;self.currentRun=run;}
    self.startButton.enabled=NO;self.status.text=@"Preparing a complete first source…";
    dispatch_async(self.sourceQueue,^{
        if(p0_cancelled(&run->policy)){atomic_fetch_sub(&run->sourceJobs,1);[self finishIfReady:run];return;}
        uint64_t existing=0,allocated=0;
        BOOL ready=ProtectedDirectory(self.cacheRoot) && TreeBytes(self.cacheRoot,&existing,&allocated) && p0_storage_admit(existing,34*MiB,64*MiB);
        if(ready){run.directory=[self.cacheRoot stringByAppendingPathComponent:[@"run-" stringByAppendingString:NSUUID.UUID.UUIDString]];run.mediaDirectory=[run.directory stringByAppendingPathComponent:@"media"];ready=ProtectedDirectory(run.directory) && ProtectedDirectory(run.mediaDirectory);}
        if(ready){run.tracePath=[run.directory stringByAppendingPathComponent:@"trace.jsonl"];ready=[NSFileManager.defaultManager createFileAtPath:run.tracePath contents:[NSData data] attributes:@{NSFileProtectionKey:NSFileProtectionCompleteUntilFirstUserAuthentication}];}
        if(!ready){[self record:@{@"gate":@"cache_admission",@"outcome":@"refused",@"existing_bytes":@(existing),@"reserve_bytes":@(34*MiB)} run:run terminal:YES lifecycle:nil];[self stopRun:run reason:P0_STOP_STORAGE];atomic_fetch_sub(&run->sourceJobs,1);[self finishIfReady:run];return;}
        [self startMonitor:run];
        [self record:@{@"gate":@"run_started",@"outcome":@"pass",@"rss_observation_limit_bytes":@(256*MiB),@"media_total_limit_bytes":@(32*MiB),@"cache_total_limit_bytes":@(64*MiB),@"operation_limit_seconds":@45} run:run terminal:NO lifecycle:nil];
        P0SetMediaDirectory(run.mediaDirectory);[self runSource:run next:NO];
    });
}
- (void)runSource:(P0Run *)run next:(BOOL)next {
    if(p0_cancelled(&run->policy) || ![self isCurrent:run]){atomic_fetch_sub(&run->sourceJobs,1);[self finishIfReady:run];return;}
    NSDictionary *state=[self lifecycle];
    if(next && ([state[@"native_application_state"] integerValue]!=UIApplicationStateBackground || [state[@"native_scene_activation_state"] integerValue]!=UISceneActivationStateBackground)) {
        [self record:@{@"gate":@"fresh_next_resolution",@"outcome":@"not_background"} run:run terminal:YES lifecycle:state];[self stopRun:run reason:P0_STOP_NOT_BACKGROUND];atomic_fetch_sub(&run->sourceJobs,1);[self finishIfReady:run];return;
    }
    self.sourceRun=run;
    [self record:@{@"gate":next?@"fresh_next_resolution_started":@"first_resolution_started",@"outcome":@"started",@"audio_elapsed_seconds":@(atomic_load(&run->policy.audio_started)>0?Uptime()-atomic_load(&run->policy.audio_started):0)} run:run terminal:NO lifecycle:state];
    int code=P0V2RunSource([NSBundle.mainBundle pathForResource:@"probe.bundle" ofType:@"js"],next);
    self.sourceRun=nil;
    [self record:@{@"gate":next?@"fresh_next_resolution_finished":@"first_resolution_finished",@"outcome":code?@"fail":@"pass",@"code":@(code)} run:run terminal:NO lifecycle:nil];
    if(code && !p0_cancelled(&run->policy))[self stopRun:run reason:P0_STOP_SOURCE];
    atomic_fetch_sub(&run->sourceJobs,1);[self finishIfReady:run];
}
- (void)acceptMedia:(NSString *)path next:(BOOL)next run:(P0Run *)run {
    NSDictionary *attrs=[NSFileManager.defaultManager attributesOfItemAtPath:path error:nil];
    BOOL file=[path.stringByDeletingLastPathComponent isEqual:run.mediaDirectory] && ![path.pathExtension isEqual:@"partial"] && [attrs[NSFileType] isEqual:NSFileTypeRegular] && [attrs[NSFileSize] unsignedLongLongValue]>0 && [attrs[NSFileSize] unsignedLongLongValue]<=16*MiB;
    if(!file){[self stopRun:run reason:P0_STOP_STORAGE];return;}
    @synchronized(self){
        if(self.currentRun!=run || p0_cancelled(&run->policy))return;
        dispatch_async(self.audioQueue,^{
            if(p0_cancelled(&run->policy))return;
            if(next){
                int code=run.audio?muses_p0_audio_prepare_next(run.audio,path.fileSystemRepresentation,1000,1000):-1;
                [self record:@{@"gate":@"next_decoder_prepared",@"outcome":code?@"fail":@"pass",@"code":@(code)} run:run terminal:NO lifecycle:nil];
                if(code)[self stopRun:run reason:P0_STOP_AUDIO];return;
            }
            if(run.audio){[self stopRun:run reason:P0_STOP_AUDIO];return;}
            AVAudioSession *session=AVAudioSession.sharedInstance;NSError *error=nil;
            BOOL active=[session setCategory:AVAudioSessionCategoryPlayback mode:AVAudioSessionModeDefault options:AVAudioSessionCategoryOptionMixWithOthers error:&error] && [session setActive:YES error:&error];
            run.sessionActive=active;
            if(!active){[self record:@{@"gate":@"audio_session",@"outcome":@"fail",@"error_code":@(error.code)} run:run terminal:NO lifecycle:nil];[self stopRun:run reason:P0_STOP_AUDIO];return;}
            int code=0;void *candidate=muses_p0_audio_start(path.fileSystemRepresentation,90,1,&code);
            if(p0_cancelled(&run->policy)){if(candidate)muses_p0_audio_stop(candidate);return;}
            run.audio=candidate;
            if(!candidate){[self record:@{@"gate":@"audio_started",@"outcome":@"fail",@"code":@(code)} run:run terminal:NO lifecycle:nil];[self stopRun:run reason:P0_STOP_AUDIO];return;}
            atomic_store(&run->policy.audio_started,Uptime());
            [self record:@{@"gate":@"audio_started",@"outcome":@"pass",@"app_gain":@0.12,@"native_audio_watchdog_seconds":@90,@"next_delay_seconds":@30} run:run terminal:NO lifecycle:nil];
            dispatch_async(dispatch_get_main_queue(),^{
                if(![self isCurrent:run] || p0_cancelled(&run->policy))return;
                MPNowPlayingInfoCenter.defaultCenter.nowPlayingInfo=@{MPMediaItemPropertyTitle:@"Muses P0 real source proof",MPNowPlayingInfoPropertyPlaybackRate:@1};
                MPRemoteCommandCenter *remote=MPRemoteCommandCenter.sharedCommandCenter;remote.nextTrackCommand.enabled=NO;remote.previousTrackCommand.enabled=NO;remote.stopCommand.enabled=YES;
                self.remoteStopTarget=[remote.stopCommand addTargetWithHandler:^MPRemoteCommandHandlerStatus(MPRemoteCommandEvent *event){[self stopRun:run reason:P0_STOP_USER];return MPRemoteCommandHandlerStatusSuccess;}];
            });
        });
    }
}
- (void)startMonitor:(P0Run *)run {
    run.monitor=dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER,0,0,self.monitorQueue);
    dispatch_source_set_timer(run.monitor,dispatch_time(DISPATCH_TIME_NOW,0),100*NSEC_PER_MSEC,10*NSEC_PER_MSEC);
    __weak typeof(self) weak=self;
    dispatch_source_set_event_handler(run.monitor,^{[weak observe:run];});dispatch_resume(run.monitor);
}
- (void)observe:(P0Run *)run {
    if(![self isCurrent:run])return;
    double now=Uptime();uint64_t rss=Resident();run.residentHigh=MAX(run.residentHigh,rss);
    uint64_t cache=0,allocated=0,media=0,mediaAllocated=0;
    BOOL files=TreeBytes(self.cacheRoot,&cache,&allocated) && TreeBytes(run.mediaDirectory,&media,&mediaAllocated);
    // A .partial -> complete atomic rename can race one inventory; retry once.
    if(!files)files=TreeBytes(self.cacheRoot,&cache,&allocated) && TreeBytes(run.mediaDirectory,&media,&mediaAllocated);
    run.cacheBytes=cache;run.cacheAllocated=allocated;run.mediaBytes=media;
    if(rss>256*MiB)[self stopRun:run reason:P0_STOP_RESOURCE];
    if(!files || cache>64*MiB || media>32*MiB)[self stopRun:run reason:P0_STOP_STORAGE];
    double audioStart=atomic_load(&run->policy.audio_started);
    if(audioStart>0 && now>=audioStart+90)[self stopRun:run reason:P0_STOP_DEADLINE];
    if(p0_cancelled(&run->policy)) {
        // Reassert cancellation while an entry raced with Stop. Never reset it here.
        @synchronized(self){if(self.currentRun==run)P0V2Cancel();}
        [self finishIfReady:run];return;
    }
    if(now-run.lastResourceLog>=1){run.lastResourceLog=now;[self record:@{@"gate":@"resource_sample",@"outcome":@"observed",@"resident_bytes":@(rss),@"resident_high_bytes":@(run.residentHigh),@"cache_logical_bytes":@(cache),@"cache_allocated_bytes":@(allocated),@"media_logical_bytes":@(media)} run:run terminal:NO lifecycle:nil];}
    if(audioStart>0 && now-audioStart>=30 && !atomic_load(&run->policy.next_claimed)) {
        NSDictionary *state=[self lifecycle];int decision;
        @synchronized(self){
            decision=self.currentRun==run?p0_next(&run->policy,Uptime(),[state[@"native_application_state"] integerValue]==UIApplicationStateBackground,[state[@"native_scene_activation_state"] integerValue]==UISceneActivationStateBackground):P0_NEXT_CANCELLED;
            if(decision==P0_NEXT_CLAIMED){atomic_fetch_add(&run->sourceJobs,1);dispatch_async(self.sourceQueue,^{[self runSource:run next:YES];});}
        }
        if(decision==P0_NEXT_NOT_BACKGROUND){[self record:@{@"gate":@"fresh_next_resolution",@"outcome":@"not_background"} run:run terminal:YES lifecycle:state];[self stopRun:run reason:P0_STOP_NOT_BACKGROUND];}
    }
    if(audioStart>0 && now-run.lastAudioLog>=5){run.lastAudioLog=now;dispatch_async(self.audioQueue,^{if(!atomic_load(&run->audioFinished))[self snapshot:run];});}
}
- (void)snapshot:(P0Run *)run {
    if(!run.audio)return;MusesP0AudioSnapshot s={0};int code=muses_p0_audio_snapshot(run.audio,&s);
    [self record:@{@"gate":@"audio_snapshot",@"outcome":code?@"fail":@"observed",@"clock_frames":@(s.clock_frames),@"callbacks":@(s.callbacks),@"underflow_frames":@(s.underflow_frames),@"clipped_samples":@(s.clipped_samples),@"transitions":@(s.transitions),@"transition_start_frame":@(s.transition_start_frame),@"transition_end_frame":@(s.transition_end_frame),@"first_consumed_frames":@(s.first_consumed_frames),@"next_consumed_frames":@(s.next_consumed_frames),@"nonzero_output_frames":@(s.nonzero_output_frames),@"first_error":@(s.first_error),@"next_error":@(s.next_error),@"next_ready":@(s.next_ready),@"timed_stop":@(s.timed_stop),@"starts":@(s.starts),@"stops":@(s.stops),@"reroutes":@(s.reroutes),@"interruptions":@(s.interruptions)} run:run terminal:p0_cancelled(&run->policy) lifecycle:nil];
}
- (void)stop {self.autoStartConsumed=YES;P0Run *run=self.currentRun;if(run)[self stopRun:run reason:P0_STOP_USER];}
- (void)stopRun:(P0Run *)run reason:(int)reason {
    BOOL first;
    @synchronized(self){if(self.currentRun!=run)return;first=p0_cancel(&run->policy,reason);P0V2Cancel();}
    if(first)[self record:@{@"gate":@"cancel_requested",@"outcome":@"observed",@"stop_reason":StopName(atomic_load(&run->policy.stop_reason))} run:run terminal:YES lifecycle:nil];
    if(atomic_exchange(&run->stopEnqueued,true))return;
    dispatch_async(self.audioQueue,^{
        [self snapshot:run];if(run.audio){muses_p0_audio_stop(run.audio);run.audio=NULL;}
        if(run.sessionActive){[AVAudioSession.sharedInstance setActive:NO withOptions:AVAudioSessionSetActiveOptionNotifyOthersOnDeactivation error:nil];run.sessionActive=NO;}
        atomic_store(&run->audioFinished,true);
        [self record:@{@"gate":@"audio_stopped",@"outcome":@"observed",@"stop_reason":StopName(atomic_load(&run->policy.stop_reason))} run:run terminal:YES lifecycle:nil];
        [self finishIfReady:run];
    });
}
- (void)finishIfReady:(P0Run *)run {
    if(!p0_cancelled(&run->policy) || atomic_load(&run->sourceJobs) || !atomic_load(&run->audioFinished) || atomic_exchange(&run->finishEnqueued,true))return;
    if(run.monitor){dispatch_source_cancel(run.monitor);run.monitor=nil;}
    struct rusage usage;getrusage(RUSAGE_SELF,&usage);
    [self record:@{@"gate":@"run_finished",@"outcome":atomic_load(&run->policy.stop_reason)==P0_STOP_DEADLINE?@"observation_complete":@"stopped",@"stop_reason":StopName(atomic_load(&run->policy.stop_reason)),@"process_maxrss_bytes":@(usage.ru_maxrss),@"sampled_peak_rss_bytes":@(run.residentHigh),@"source_idle":@YES,@"audio_closed":@YES} run:run terminal:YES lifecycle:nil];
    dispatch_async(self.evidenceQueue,^{dispatch_async(dispatch_get_main_queue(),^{
        @synchronized(self){if(self.currentRun!=run)return;self.currentRun=nil;}
        if(self.remoteStopTarget){[MPRemoteCommandCenter.sharedCommandCenter.stopCommand removeTarget:self.remoteStopTarget];self.remoteStopTarget=nil;}
        MPNowPlayingInfoCenter.defaultCenter.nowPlayingInfo=nil;self.startButton.enabled=YES;
        self.status.text=[NSString stringWithFormat:@"Finished: %@. Evidence retained; audibility requires human confirmation.",StopName(atomic_load(&run->policy.stop_reason))];
    });});
}
- (void)sceneChanged:(NSString *)state {self.lastSceneCallback=state;P0Run *run=self.currentRun;if(run)[self record:@{@"gate":@"scene_callback",@"outcome":state} run:run terminal:NO lifecycle:[self lifecycle]];}
@end

@interface P0V2SceneDelegate : UIResponder <UIWindowSceneDelegate>
@property(nonatomic,strong) UIWindow *window;
@end
@implementation P0V2SceneDelegate
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {if(![scene isKindOfClass:UIWindowScene.class])return;self.window=[[UIWindow alloc]initWithWindowScene:(UIWindowScene *)scene];self.window.rootViewController=[P0Controller new];[self.window makeKeyAndVisible];}
- (void)sceneDidBecomeActive:(UIScene *)scene {[(P0Controller *)self.window.rootViewController sceneChanged:@"active"];}
- (void)sceneWillResignActive:(UIScene *)scene {[(P0Controller *)self.window.rootViewController sceneChanged:@"inactive"];}
- (void)sceneWillEnterForeground:(UIScene *)scene {[(P0Controller *)self.window.rootViewController sceneChanged:@"will_enter_foreground"];}
- (void)sceneDidEnterBackground:(UIScene *)scene {[(P0Controller *)self.window.rootViewController sceneChanged:@"background"];}
@end
@interface P0V2AppDelegate : UIResponder <UIApplicationDelegate>
@end
@implementation P0V2AppDelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {return YES;}
- (UISceneConfiguration *)application:(UIApplication *)app configurationForConnectingSceneSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {UISceneConfiguration *c=[[UISceneConfiguration alloc]initWithName:@"Default Configuration" sessionRole:session.role];c.delegateClass=P0V2SceneDelegate.class;return c;}
@end
int main(int argc,char **argv){@autoreleasepool{return UIApplicationMain(argc,argv,nil,NSStringFromClass(P0V2AppDelegate.class));}}
