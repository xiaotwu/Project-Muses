// SPDX-License-Identifier: MIT
// Measurement/reference only: JSC is not the proposed bounded production VM.
#import <Foundation/Foundation.h>
#import <JavaScriptCore/JavaScriptCore.h>
#import <CommonCrypto/CommonDigest.h>
#import <sys/resource.h>
static void record(NSDictionary *row){NSData *d=[NSJSONSerialization dataWithJSONObject:row options:0 error:nil];puts([[NSString alloc] initWithData:d encoding:NSUTF8StringEncoding].UTF8String);fflush(stdout);}
int main(int argc,char **argv){@autoreleasepool{
  if(argc!=4)return 64;
  NSString *bundle=[NSString stringWithContentsOfFile:@(argv[1]) encoding:NSUTF8StringEncoding error:nil];NSString *input=[NSString stringWithContentsOfFile:@(argv[2]) encoding:NSUTF8StringEncoding error:nil];if(!bundle||!input||bundle.length>4*1024*1024||input.length>4*1024*1024)return 65;
  JSContext *ctx=[[JSContext alloc] init];__block BOOL failed=NO;__weak JSContext *weak=ctx;
  ctx.exceptionHandler=^(JSContext *c,JSValue *e){(void)c;failed=YES;NSString *message=[e[@"message"] toString];BOOL safe=[message hasPrefix:@"Can't find variable: "]&&message.length<100;record(@{@"phase":@"jsc_exception",@"outcome":@"fail",@"name":[e[@"name"] toString]?:@"unknown",@"detail":safe?message:@"redacted"});};
  ctx[@"playerSource"]=input;ctx[@"PROBE_PHASE"]=@"extract";input=nil;
  ctx[@"nativeMark"]=^(NSString *name){struct rusage u;getrusage(RUSAGE_SELF,&u);record(@{@"phase":name,@"process_maxrss_bytes":@(u.ru_maxrss)});};
  ctx[@"nativeGC"]=^{JSGarbageCollect(weak.JSGlobalContextRef);};
  [ctx evaluateScript:bundle];if(failed)return 1;
  NSString *solver=[ctx[@"solverText"] toString];NSData *bytes=[solver dataUsingEncoding:NSUTF8StringEncoding];if(!bytes.length||bytes.length>256*1024)return 2;
  if(![bytes writeToFile:@(argv[3]) atomically:YES])return 3;
  unsigned char digest[CC_SHA256_DIGEST_LENGTH];CC_SHA256(bytes.bytes,(CC_LONG)bytes.length,digest);NSMutableString *sha=[NSMutableString string];for(int i=0;i<CC_SHA256_DIGEST_LENGTH;i++)[sha appendFormat:@"%02x",digest[i]];
  record(@{@"phase":@"full_source_reference",@"bytes":@(bytes.length),@"sha256":sha,@"signature_timestamp":[ctx[@"signatureTimestamp"] toNumber],@"runtime":@"system JavaScriptCore; diagnostic only"});
  ctx=nil;return 0;
}}
