// MIT. Isolated physical-device P0 harness, not part of the shipped app.
#import <UIKit/UIKit.h>
#import <AVFAudio/AVFAudio.h>
#import <MediaPlayer/MediaPlayer.h>
#include "p0_audio.h"
extern int RunProof(NSString *,NSString *);
extern void P0SetMediaDirectory(NSString *);
extern void P0SetMediaHandler(void (^)(NSString *,BOOL));
extern void P0SetLogHandler(void (^)(NSString *));

@interface P0Controller : UIViewController
@property UITextView *text;
@property NSMutableArray<NSString *> *lines;
@property NSString *tracePath;
@property dispatch_queue_t worker;
@property dispatch_source_t timer;
@property void *audio;
@property BOOL running;
@property BOOL nextRequested;
@property NSString *state;
@property(atomic,copy) NSDictionary *lifecycleSnapshot;
@property double started;
@property BOOL calibration;
@property uint64_t generation;
@property uint64_t executingGeneration;
@property uint64_t audioGeneration;
- (void)record:(NSDictionary *)event;
- (void)startBackground;
- (void)startCalibration;
- (void)requestNext;
- (void)stop;
- (NSDictionary *)captureLifecycleSnapshot;
@end
@implementation P0Controller
- (void)viewDidLoad {
    [super viewDidLoad];self.view.backgroundColor=UIColor.systemBackgroundColor;
    self.worker=dispatch_queue_create("org.muses.p0.sourceprobe.control",DISPATCH_QUEUE_SERIAL);
    self.lines=[NSMutableArray array];self.state=@"unknown";
    NSString *documents=NSSearchPathForDirectoriesInDomains(NSDocumentDirectory,NSUserDomainMask,YES).firstObject;
    self.tracePath=[documents stringByAppendingPathComponent:@"p0-source-trace.jsonl"];
    NSString *cache=[NSSearchPathForDirectoriesInDomains(NSCachesDirectory,NSUserDomainMask,YES).firstObject stringByAppendingPathComponent:@"MusesP0Source"];
    P0SetMediaDirectory(cache);
    self.text=[[UITextView alloc] init];self.text.editable=NO;self.text.font=[UIFont monospacedSystemFontOfSize:11 weight:UIFontWeightRegular];
    UILabel *title=[[UILabel alloc] init];title.text=@"Muses P0 · Native Source";title.font=[UIFont preferredFontForTextStyle:UIFontTextStyleTitle2];
    UILabel *hint=[[UILabel alloc] init];hint.numberOfLines=0;hint.text=@"Start → wait for audio_started → lock iPhone.\nNext is resolved after 30 s, then decoded and crossfaded.\nAudio stops after 90 s. Task files stay inside this app.";
    UIButton *catalog=[UIButton buttonWithType:UIButtonTypeSystem];[catalog setTitle:@"Run catalog" forState:UIControlStateNormal];[catalog addTarget:self action:@selector(catalog) forControlEvents:UIControlEventTouchUpInside];
    UIButton *start=[UIButton buttonWithType:UIButtonTypeSystem];[start setTitle:@"Start background proof" forState:UIControlStateNormal];[start addTarget:self action:@selector(startBackground) forControlEvents:UIControlEventTouchUpInside];
    UIButton *calibration=[UIButton buttonWithType:UIButtonTypeSystem];[calibration setTitle:@"Calibration: synthetic audio + live catalog" forState:UIControlStateNormal];[calibration addTarget:self action:@selector(startCalibration) forControlEvents:UIControlEventTouchUpInside];
    UIButton *stop=[UIButton buttonWithType:UIButtonTypeSystem];[stop setTitle:@"Stop audio" forState:UIControlStateNormal];[stop addTarget:self action:@selector(stop) forControlEvents:UIControlEventTouchUpInside];
    UIStackView *stack=[[UIStackView alloc] initWithArrangedSubviews:@[title,hint,catalog,start,calibration,stop,self.text]];stack.axis=UILayoutConstraintAxisVertical;stack.spacing=10;stack.translatesAutoresizingMaskIntoConstraints=NO;[self.view addSubview:stack];
    [NSLayoutConstraint activateConstraints:@[[stack.topAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.topAnchor constant:20],[stack.bottomAnchor constraintEqualToAnchor:self.view.safeAreaLayoutGuide.bottomAnchor constant:-20],[stack.leadingAnchor constraintEqualToAnchor:self.view.leadingAnchor constant:20],[stack.trailingAnchor constraintEqualToAnchor:self.view.trailingAnchor constant:-20]]];
    __weak typeof(self) weak=self;
    P0SetLogHandler(^(NSString *line){uint64_t origin=weak.executingGeneration;if(origin!=weak.generation)return;NSData *data=[line dataUsingEncoding:NSUTF8StringEncoding];NSMutableDictionary *event=[[NSJSONSerialization JSONObjectWithData:data options:0 error:nil] mutableCopy];if(event){event[@"run_generation"]=@(origin);[weak record:event];}});
    P0SetMediaHandler(^(NSString *path,BOOL next){[weak acceptMedia:path next:next];});
    [NSNotificationCenter.defaultCenter addObserverForName:UIApplicationProtectedDataWillBecomeUnavailable object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n){[weak record:@{@"gate":@"protected_data",@"outcome":@"will_become_unavailable"}];}];
    [NSNotificationCenter.defaultCenter addObserverForName:UIApplicationProtectedDataDidBecomeAvailable object:nil queue:NSOperationQueue.mainQueue usingBlock:^(NSNotification *n){[weak record:@{@"gate":@"protected_data",@"outcome":@"available"}];}];
    [self record:@{@"gate":@"app_ready",@"outcome":@"pass",@"bundle":@"org.muses.p0.sourceprobe",@"runtime":@"QuickJS 2026-06-04",@"heap_limit_bytes":@(64*1024*1024)}];
    if([NSProcessInfo.processInfo.arguments containsObject:@"--run-background"])dispatch_after(dispatch_time(DISPATCH_TIME_NOW,5*NSEC_PER_SEC),dispatch_get_main_queue(),^{[weak startBackground];});
    if([NSProcessInfo.processInfo.arguments containsObject:@"--run-catalog"])dispatch_after(dispatch_time(DISPATCH_TIME_NOW,2*NSEC_PER_SEC),dispatch_get_main_queue(),^{[weak catalog];});
    if([NSProcessInfo.processInfo.arguments containsObject:@"--calibration"])dispatch_after(dispatch_time(DISPATCH_TIME_NOW,5*NSEC_PER_SEC),dispatch_get_main_queue(),^{[weak startCalibration];});
}
- (NSDictionary *)captureLifecycleSnapshot {
    __block NSDictionary *captured;
    void (^readOnMain)(void)=^{
        UIApplication *application=UIApplication.sharedApplication;
        UIApplicationState app=application.applicationState;
        UIWindowScene *scene=self.viewIfLoaded.window.windowScene;
        UISceneActivationState activation=scene?scene.activationState:UISceneActivationStateUnattached;
        NSString *appName=app==UIApplicationStateActive?@"active":app==UIApplicationStateInactive?@"inactive":@"background";
        NSString *sceneName=activation==UISceneActivationStateForegroundActive?@"foreground_active":activation==UISceneActivationStateForegroundInactive?@"foreground_inactive":activation==UISceneActivationStateBackground?@"background":@"unattached";
        captured=@{@"app_state":appName,@"native_application_state":@(app),@"scene_activation_state":sceneName,@"native_scene_activation_state":@(activation),@"protected_data_available":@(application.protectedDataAvailable),@"last_scene_callback_state":self.state?:@"unknown",@"state_sample_uptime_seconds":@(NSProcessInfo.processInfo.systemUptime),@"state_sample_on_main_thread":@YES};
        self.lifecycleSnapshot=captured;
    };
    if(NSThread.isMainThread)readOnMain();else dispatch_sync(dispatch_get_main_queue(),readOnMain);
    return captured;
}
- (void)record:(NSDictionary *)event {
    NSDictionary *lifecycle=[self captureLifecycleSnapshot];
    NSMutableDictionary *row=[event mutableCopy];[row addEntriesFromDictionary:lifecycle];row[@"uptime_seconds"]=@(NSProcessInfo.processInfo.systemUptime);row[@"test_mode"]=self.calibration?@"calibration_synthetic_audio_live_catalog":@"source";if(!row[@"run_generation"])row[@"run_generation"]=@(self.generation);
    NSData *data=[NSJSONSerialization dataWithJSONObject:row options:NSJSONWritingSortedKeys error:nil];NSString *line=[[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding];
    @synchronized(self){if(self.lines.count>=512)return;[self.lines addObject:line];NSString *all=[[self.lines componentsJoinedByString:@"\n"] stringByAppendingString:@"\n"];[all writeToFile:self.tracePath atomically:YES encoding:NSUTF8StringEncoding error:nil];[[NSFileManager defaultManager] setAttributes:@{NSFileProtectionKey:NSFileProtectionCompleteUntilFirstUserAuthentication} ofItemAtPath:self.tracePath error:nil];}
    NSLog(@"P0 %@",line);dispatch_async(dispatch_get_main_queue(),^{if(self.viewIfLoaded.window.windowScene.activationState!=UISceneActivationStateForegroundActive)return;@synchronized(self){self.text.text=[self.lines componentsJoinedByString:@"\n"];NSRange end=NSMakeRange(self.text.text.length,0);[self.text scrollRangeToVisible:end];}});
}
- (NSString *)bundle {return [NSBundle.mainBundle pathForResource:@"probe.bundle" ofType:@"js"];}
- (void)catalog {if(self.running)return;self.running=YES;uint64_t generation=++self.generation;dispatch_async(self.worker,^{if(generation!=self.generation)return;self.executingGeneration=generation;int result=RunProof(self.bundle,@"catalog");if(generation==self.generation){[self record:@{@"gate":@"catalog_finished",@"outcome":result?@"fail":@"pass",@"code":@(result),@"run_generation":@(generation)}];self.running=NO;}});}
- (void)startBackground {
    if(self.running)return;self.running=YES;self.calibration=NO;self.nextRequested=NO;self.started=NSProcessInfo.processInfo.systemUptime;uint64_t generation=++self.generation;
    [self record:@{@"gate":@"background_test_started",@"outcome":@"started",@"next_delay_seconds":@30,@"audio_watchdog_seconds":@90}];
    dispatch_async(self.worker,^{if(generation!=self.generation)return;self.executingGeneration=generation;int result=RunProof(self.bundle,@"background_first");if(generation==self.generation&&(result||!self.audio)){[self record:@{@"gate":@"background_test",@"outcome":@"failed_before_audio",@"source_code":@(result)}];self.running=NO;}});
}
- (void)startCalibration {
    if(self.running)return;self.running=YES;self.calibration=YES;self.nextRequested=NO;self.started=NSProcessInfo.processInfo.systemUptime;uint64_t generation=++self.generation;
    [self record:@{@"gate":@"calibration_started",@"outcome":@"started",@"source_playback_gate":@"not_tested",@"next_delay_seconds":@30,@"audio_watchdog_seconds":@90}];
    dispatch_async(self.worker,^{if(generation!=self.generation)return;self.executingGeneration=generation;NSString *path=[NSBundle.mainBundle pathForResource:@"calibration-first" ofType:@"m4a"];if(!path){[self record:@{@"gate":@"calibration_fixture",@"outcome":@"missing"}];self.running=NO;return;}[self acceptMedia:path next:NO];if(!self.audio)self.running=NO;});
}
- (void)acceptMedia:(NSString *)path next:(BOOL)next {
    uint64_t generation=self.executingGeneration;if(generation!=self.generation)return;
    if(next){int code=self.audio?muses_p0_audio_prepare_next(self.audio,path.fileSystemRepresentation,1000,1000):-1;if(generation==self.generation)[self record:@{@"gate":@"next_decoder_prepared",@"outcome":code?@"fail":@"pass",@"code":@(code),@"run_generation":@(generation)}];return;}
    NSError *error=nil;AVAudioSession *session=AVAudioSession.sharedInstance;BOOL category=[session setCategory:AVAudioSessionCategoryPlayback mode:AVAudioSessionModeDefault options:AVAudioSessionCategoryOptionMixWithOthers error:&error];BOOL active=category&&[session setActive:YES error:&error];
    if(!active){[self record:@{@"gate":@"audio_session",@"outcome":@"fail",@"error_code":@(error.code)}];return;}
    int code=0;void *candidate=muses_p0_audio_start(path.fileSystemRepresentation,90,1,&code);
    if(generation!=self.generation){if(candidate)muses_p0_audio_stop(candidate);[AVAudioSession.sharedInstance setActive:NO withOptions:AVAudioSessionSetActiveOptionNotifyOthersOnDeactivation error:nil];return;}
    self.audio=candidate;self.audioGeneration=generation;
    [self record:@{@"gate":@"audio_started",@"outcome":self.audio?@"pass":@"fail",@"code":@(code),@"app_gain":@0.12,@"run_generation":@(generation)}];if(!self.audio)return;
    dispatch_async(dispatch_get_main_queue(),^{if(generation!=self.generation)return;MPNowPlayingInfoCenter.defaultCenter.nowPlayingInfo=@{MPMediaItemPropertyTitle:self.calibration?@"Muses P0 calibration":@"Muses P0 source proof",MPMediaItemPropertyArtist:@"Native audio validation",MPNowPlayingInfoPropertyPlaybackRate:@1};MPRemoteCommandCenter.sharedCommandCenter.nextTrackCommand.enabled=YES;[MPRemoteCommandCenter.sharedCommandCenter.nextTrackCommand removeTarget:nil];[MPRemoteCommandCenter.sharedCommandCenter.nextTrackCommand addTargetWithHandler:^MPRemoteCommandHandlerStatus(MPRemoteCommandEvent *e){[self requestNextForGeneration:generation];return MPRemoteCommandHandlerStatusSuccess;}];});
    self.timer=dispatch_source_create(DISPATCH_SOURCE_TYPE_TIMER,0,0,self.worker);dispatch_source_set_timer(self.timer,dispatch_time(DISPATCH_TIME_NOW,5*NSEC_PER_SEC),5*NSEC_PER_SEC,NSEC_PER_SEC/10);__weak typeof(self) weak=self;dispatch_source_set_event_handler(self.timer,^{if(generation==weak.generation)[weak snapshot];});dispatch_resume(self.timer);
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW,30*NSEC_PER_SEC),self.worker,^{if(generation==weak.generation)[weak requestNextForGeneration:generation];});
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW,90*NSEC_PER_SEC),self.worker,^{if(generation==weak.generation)[weak stopOnWorker];});
}
- (void)requestNext {[self requestNextForGeneration:self.generation];}
- (void)requestNextForGeneration:(uint64_t)generation {
    dispatch_async(self.worker,^{if(generation!=self.generation||!self.audio||self.nextRequested)return;self.nextRequested=YES;self.executingGeneration=generation;
      if(self.calibration){[self record:@{@"gate":@"calibration_fresh_catalog_started",@"outcome":@"started",@"source_playback_gate":@"not_tested",@"run_generation":@(generation)}];int result=RunProof(self.bundle,@"catalog");if(generation!=self.generation)return;[self record:@{@"gate":@"calibration_fresh_catalog_finished",@"outcome":result?@"fail":@"pass",@"code":@(result),@"run_generation":@(generation)}];NSString *path=[NSBundle.mainBundle pathForResource:@"calibration-next" ofType:@"m4a"];if(path)[self acceptMedia:path next:YES];else[self record:@{@"gate":@"calibration_fixture",@"outcome":@"missing"}];return;}
      [self record:@{@"gate":@"fresh_next_resolution_started",@"outcome":@"started",@"run_generation":@(generation)}];int result=RunProof(self.bundle,@"background_next");if(generation==self.generation)[self record:@{@"gate":@"fresh_next_resolution_finished",@"outcome":result?@"fail":@"pass",@"code":@(result),@"run_generation":@(generation)}];});
}
- (void)snapshot {
    if(!self.audio)return;MusesP0AudioSnapshot s={0};int code=muses_p0_audio_snapshot(self.audio,&s);
    [self record:@{@"gate":@"audio_snapshot",@"outcome":code?@"fail":@"pass",@"clock_frames":@(s.clock_frames),@"callbacks":@(s.callbacks),@"underflow_frames":@(s.underflow_frames),@"transitions":@(s.transitions),@"transition_start_frame":@(s.transition_start_frame),@"transition_end_frame":@(s.transition_end_frame),@"first_decoded_frames":@(s.first_decoded_frames),@"next_decoded_frames":@(s.next_decoded_frames),@"next_ready":@(s.next_ready),@"first_error":@(s.first_error),@"next_error":@(s.next_error),@"timed_stop":@(s.timed_stop),@"first_consumed_frames":@(s.first_consumed_frames),@"next_consumed_frames":@(s.next_consumed_frames),@"nonzero_output_frames":@(s.nonzero_output_frames),@"run_generation":@(self.audioGeneration)}];
}
- (void)stop {++self.generation;dispatch_async(self.worker,^{[self stopOnWorker];});}
- (void)stopOnWorker {uint64_t origin=self.audio?self.audioGeneration:self.executingGeneration,cleanupGeneration=self.generation;if(self.timer){dispatch_source_cancel(self.timer);self.timer=nil;}if(self.audio){[self snapshot];muses_p0_audio_stop(self.audio);self.audio=NULL;}[AVAudioSession.sharedInstance setActive:NO withOptions:AVAudioSessionSetActiveOptionNotifyOthersOnDeactivation error:nil];self.running=NO;[self record:@{@"gate":@"audio_stopped",@"outcome":@"pass",@"run_generation":@(origin)}];dispatch_async(dispatch_get_main_queue(),^{if(cleanupGeneration!=self.generation)return;MPNowPlayingInfoCenter.defaultCenter.nowPlayingInfo=nil;[MPRemoteCommandCenter.sharedCommandCenter.nextTrackCommand removeTarget:nil];});}
@end
@interface P0SceneDelegate : UIResponder <UIWindowSceneDelegate>
@property(nonatomic,strong) UIWindow *window;
@end
@implementation P0SceneDelegate
- (void)scene:(UIScene *)scene willConnectToSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {if(![scene isKindOfClass:UIWindowScene.class])return;self.window=[[UIWindow alloc] initWithWindowScene:(UIWindowScene *)scene];self.window.rootViewController=[[P0Controller alloc] init];[self.window makeKeyAndVisible];}
- (void)sceneDidBecomeActive:(UIScene *)scene {P0Controller *controller=(P0Controller *)self.window.rootViewController;controller.state=@"active";[controller record:@{@"gate":@"app_state",@"outcome":@"active",@"lifecycle":@"UIScene"}];}
- (void)sceneWillResignActive:(UIScene *)scene {P0Controller *controller=(P0Controller *)self.window.rootViewController;controller.state=@"inactive";[controller record:@{@"gate":@"scene_will_resign_active",@"outcome":@"observed",@"lifecycle":@"UIScene"}];}
- (void)sceneWillEnterForeground:(UIScene *)scene {P0Controller *controller=(P0Controller *)self.window.rootViewController;controller.state=@"inactive";[controller record:@{@"gate":@"scene_will_enter_foreground",@"outcome":@"observed",@"lifecycle":@"UIScene"}];}
- (void)sceneDidEnterBackground:(UIScene *)scene {P0Controller *controller=(P0Controller *)self.window.rootViewController;controller.state=@"background";[controller record:@{@"gate":@"app_state",@"outcome":@"background",@"lifecycle":@"UIScene"}];}
@end
@interface P0AppDelegate : UIResponder <UIApplicationDelegate>
@end
@implementation P0AppDelegate
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)options {return YES;}
- (UISceneConfiguration *)application:(UIApplication *)application configurationForConnectingSceneSession:(UISceneSession *)session options:(UISceneConnectionOptions *)options {UISceneConfiguration *configuration=[[UISceneConfiguration alloc] initWithName:@"Default Configuration" sessionRole:session.role];configuration.delegateClass=P0SceneDelegate.class;return configuration;}
@end
int main(int argc,char **argv){@autoreleasepool{return UIApplicationMain(argc,argv,nil,NSStringFromClass(P0AppDelegate.class));}}
