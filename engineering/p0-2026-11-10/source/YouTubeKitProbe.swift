// MIT. One local-only alternate adapter probe, isolated from the iOS candidate.
import Foundation
import YouTubeKit
import Darwin
import CryptoKit

final class ProofProtocol: URLProtocol, URLSessionDataDelegate, @unchecked Sendable {
    private static let countsLock=NSLock()
    private static var requestCount=0
    static var count:Int {countsLock.lock();defer{countsLock.unlock()};return requestCount}
    private var session: URLSession?
    private var networkTask: URLSessionDataTask?
    private var bytes=0
    private static func allowed(_ url:URL?) -> Bool {guard let url, url.scheme=="https", let host=url.host?.lowercased() else{return false};return host=="youtube.com"||host.hasSuffix(".youtube.com")||host.hasSuffix(".googlevideo.com")}
    override class func canInit(with request:URLRequest)->Bool {URLProtocol.property(forKey:"MusesP0Handled",in:request)==nil&&(request.url?.scheme=="https"||request.url?.scheme=="http")}
    override class func canonicalRequest(for request:URLRequest)->URLRequest{request}
    override func startLoading(){
        guard Self.allowed(request.url) else{client?.urlProtocol(self,didFailWithError:URLError(.unsupportedURL));return}
        Self.countsLock.lock();Self.requestCount+=1;Self.countsLock.unlock()
        let config=URLSessionConfiguration.ephemeral;config.protocolClasses=[];config.httpCookieStorage=nil;config.httpShouldSetCookies=false;config.urlCache=nil;config.timeoutIntervalForRequest=15;config.timeoutIntervalForResource=20
        session=URLSession(configuration:config,delegate:self,delegateQueue:nil)
        var clean=request;clean.httpShouldHandleCookies=false;for name in ["Cookie","Authorization","Proxy-Authorization"]{clean.setValue(nil,forHTTPHeaderField:name)}
        let marked=(clean as NSURLRequest).mutableCopy() as! NSMutableURLRequest;URLProtocol.setProperty(true,forKey:"MusesP0Handled",in:marked)
        networkTask=session!.dataTask(with:marked as URLRequest);networkTask!.resume()
    }
    override func stopLoading(){networkTask?.cancel();session?.invalidateAndCancel()}
    func urlSession(_ session:URLSession,dataTask:URLSessionDataTask,didReceive response:URLResponse,completionHandler:@escaping(URLSession.ResponseDisposition)->Void){if response.expectedContentLength>16*1024*1024{completionHandler(.cancel);return};client?.urlProtocol(self,didReceive:response,cacheStoragePolicy:.notAllowed);completionHandler(.allow)}
    func urlSession(_ session:URLSession,dataTask:URLSessionDataTask,didReceive data:Data){bytes+=data.count;if bytes>16*1024*1024{dataTask.cancel();return};client?.urlProtocol(self,didLoad:data)}
    func urlSession(_ session:URLSession,task:URLSessionTask,didCompleteWithError error:Error?){if let error{client?.urlProtocol(self,didFailWithError:error)}else{client?.urlProtocolDidFinishLoading(self)};session.finishTasksAndInvalidate()}
    func urlSession(_ session:URLSession,task:URLSessionTask,willPerformHTTPRedirection response:HTTPURLResponse,newRequest request:URLRequest,completionHandler:@escaping(URLRequest?)->Void){completionHandler(Self.allowed(request.url) ? request:nil)}
}
func emit(_ gate:String,_ outcome:String,_ values:[String:Any]=[:]){var row=values;row["gate"]=gate;row["outcome"]=outcome;let data=try! JSONSerialization.data(withJSONObject:row,options:.sortedKeys);print(String(decoding:data,as:UTF8.self));fflush(stdout)}
@main struct Probe {
    static func main() async {
        URLProtocol.registerClass(ProofProtocol.self)
        emit("alternate_runtime","started",["library":"YouTubeKit","commit":"7f75a2299dc329c0b7855afb25d47663a02855cb","method":"local_only","native_network":"URLSession","runtime":"Swift + JavaScriptCore","oauth":false,"browser_cookies":false,"remote_fallback":false])
        let start=Date()
        do{
            let streams=try await YouTube(videoID:"aqz-KE-bpKQ",useOAuth:false,allowOAuthCache:false,methods:[.local]).streams
            let candidates=streams.filterAudioOnly().filter{$0.fileExtension == .m4a}
            emit("alternate_extract","pass",["elapsed_ms":Int(Date().timeIntervalSince(start)*1000),"stream_count":streams.count,"aac_count":candidates.count,"native_requests":ProofProtocol.count])
            guard ProofProtocol.count>0 else{emit("alternate_native_policy","fail");exit(1)}
            func declaredLength(_ stream:YouTubeKit.Stream)->Int?{URLComponents(url:stream.url,resolvingAgainstBaseURL:false)?.queryItems?.first{$0.name=="clen"}?.value.flatMap(Int.init)}
            let bounded=candidates.filter{guard let n=declaredLength($0) else{return false};return n>0&&n<=16*1048576}
            emit("alternate_bounded_candidates","observed",["count":bounded.count,"declared_lengths":candidates.compactMap(declaredLength)])
            guard let selected=bounded.highestAudioBitrateStream() else{emit("alternate_format","bounded_stop",["limit_bytes":16*1048576]);exit(1)}
            let wait=max(0,selected.availableAt.timeIntervalSinceNow)
            emit("alternate_availability","pending",["required_wait_ms":Int(wait*1000)])
            guard wait<=20 else{emit("alternate_availability","bounded_stop",["limit_seconds":20]);exit(1)}
            try await selected.waitUntilAvailable()
            let configuration=URLSessionConfiguration.ephemeral;configuration.protocolClasses=[ProofProtocol.self];configuration.httpCookieStorage=nil;configuration.httpShouldSetCookies=false;configuration.urlCache=nil
            let session=URLSession(configuration:configuration)
            let length=declaredLength(selected)
            guard let length,length>0,length<=16*1048576 else{emit("alternate_length","bounded_stop",["limit_bytes":16*1048576]);exit(1)}
            emit("alternate_length","pass",["bytes":length])
            let path="/Users/xiaotwu/.muses/tmp/p0-20261110-01/source/media/youtubekit-512.partial"
            FileManager.default.createFile(atPath:path,contents:nil);let file=try FileHandle(forWritingTo:URL(fileURLWithPath:path));defer{try? file.close()}
            var allOK=true,total=0,index=0,hash=SHA256()
            for offset in stride(from:0,to:length,by:1048576){
                let end=min(length-1,offset+1048575)
                let before=Date();var request=URLRequest(url:selected.url);request.httpShouldHandleCookies=false;request.setValue("bytes=\(offset)-\(end)",forHTTPHeaderField:"Range")
                let (data,response)=try await session.data(for:request);let status=(response as? HTTPURLResponse)?.statusCode ?? 0
                let ok=status==206&&data.count==end-offset+1;allOK = allOK&&ok
                emit("alternate_continuity",ok ? "pass":"fail",["chunk":index,"http_status":status,"bytes":data.count,"elapsed_ms":Int(Date().timeIntervalSince(before)*1000)])
                if !ok{break}
                try file.write(contentsOf:data);hash.update(data:data);total+=data.count;index+=1
            }
            session.invalidateAndCancel();let complete=allOK&&total==length
            emit("alternate_result",complete ? "pass":"fail",["full_download":complete,"tested_bytes":total,"chunks":index,"content_sha256":hash.finalize().map{String(format:"%02x",$0)}.joined()]);exit(complete ? 0:1)
        }catch{let ns=error as NSError;emit("alternate_error","fail",["error_type":String(reflecting:type(of:error)),"error_code":ns.code]);exit(1)}
    }
}
