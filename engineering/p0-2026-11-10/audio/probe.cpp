// MIT. P0 feasibility harness, not the production playback service.
// The real-time callback owns one output clock and reads two bounded SPSC rings.
#define MA_NO_RUNTIME_LINKING
#define MA_ENABLE_ONLY_SPECIFIC_BACKENDS
#define MA_ENABLE_COREAUDIO
#define MA_NO_DECODING
#define MA_NO_ENCODING
#define MA_NO_ENGINE
#define MA_NO_RESOURCE_MANAGER
#define MA_NO_NODE_GRAPH
#include "miniaudio.h"
#include "p0_audio.h"
extern "C" {
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libswresample/swresample.h>
}
#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

namespace {
constexpr size_t rate = 48000, channels = 2, capacity = 32768;
static_assert(std::atomic<uint64_t>::is_always_lock_free, "audio counters must be lock-free");
static_assert(std::atomic<bool>::is_always_lock_free, "audio cancellation must be lock-free");
using Clock = std::chrono::steady_clock;
void check(bool ok, const char* why) { if (!ok) throw std::runtime_error(why); }
void nap() { std::this_thread::sleep_for(std::chrono::milliseconds(1)); }

struct Ring {
    std::unique_ptr<std::array<float, capacity * channels>> samples =
        std::make_unique<std::array<float, capacity * channels>>();
    std::atomic<uint64_t> write{0}, read{0}, high{0};
    size_t available() const {
        const auto r = read.load(std::memory_order_acquire);
        const auto w = write.load(std::memory_order_acquire);
        return std::min(size_t(capacity), size_t(w - r));
    }
    size_t push(const float* data, size_t count) {
        auto w = write.load(std::memory_order_relaxed);
        auto r = read.load(std::memory_order_acquire);
        count = std::min(count, capacity - size_t(w - r));
        for (size_t i = 0; i < count; ++i)
            for (size_t c = 0; c < channels; ++c) (*samples)[((w + i) % capacity) * channels + c] = data[i * channels + c];
        write.store(w + count, std::memory_order_release);
        auto observed = high.load();
        while (w + count - r > observed && !high.compare_exchange_weak(observed, w + count - r)) {}
        return count;
    }
    size_t pop(float* data, size_t count) {
        auto r = read.load(std::memory_order_relaxed);
        auto w = write.load(std::memory_order_acquire);
        count = std::min(count, size_t(w - r));
        for (size_t i = 0; i < count; ++i)
            for (size_t c = 0; c < channels; ++c) data[i * channels + c] = (*samples)[((r + i) % capacity) * channels + c];
        read.store(r + count, std::memory_order_release);
        return count;
    }
};

struct Decoder {
    Ring ring;
    std::atomic<bool> cancel{false}, done{false};
    std::atomic<int> error{0};
    std::atomic<uint64_t> produced{0};
    double firstPTS = -1;
    std::thread thread;
    ~Decoder() { cancel = true; if (thread.joinable()) thread.join(); }
    void start(std::string url, double seek = 0) {
        thread = std::thread([this, url, seek] { decode(url, seek); done.store(true, std::memory_order_release); });
    }
    static int interrupt(void* pointer) { return static_cast<Decoder*>(pointer)->cancel.load() ? 1 : 0; }
    void decode(const std::string& url, double seek) {
        AVFormatContext* format = avformat_alloc_context();
        AVCodecContext* codec = nullptr;
        SwrContext* convert = nullptr;
        AVPacket* packet = av_packet_alloc();
        AVFrame* frame = av_frame_alloc();
        AVDictionary* options = nullptr;
        int stream = -1, result = 0;
        format->interrupt_callback = {interrupt, this};
        av_dict_set(&options, "rw_timeout", "2000000", 0);
        result = avformat_open_input(&format, url.c_str(), nullptr, &options);
        av_dict_free(&options);
        if (result >= 0) result = avformat_find_stream_info(format, nullptr);
        if (result >= 0) result = stream = av_find_best_stream(format, AVMEDIA_TYPE_AUDIO, -1, -1, nullptr, 0);
        if (result >= 0) {
            codec = avcodec_alloc_context3(avcodec_find_decoder(format->streams[stream]->codecpar->codec_id));
            result = avcodec_parameters_to_context(codec, format->streams[stream]->codecpar);
            codec->pkt_timebase = format->streams[stream]->time_base;
        }
        if (result >= 0) result = avcodec_open2(codec, codec->codec, nullptr);
        AVChannelLayout layout = AV_CHANNEL_LAYOUT_STEREO;
        if (result >= 0) result = swr_alloc_set_opts2(&convert, &layout, AV_SAMPLE_FMT_FLT, rate,
            &codec->ch_layout, codec->sample_fmt, codec->sample_rate, 0, nullptr);
        if (result >= 0) result = swr_init(convert);
        if (result >= 0 && seek > 0) {
            // Warm decoder history before the requested sample. SeekPreroll is
            // required for Opus; AAC's overlap window also needs earlier input.
            int64_t target = int64_t(std::max(0.0, seek - 0.12) / av_q2d(format->streams[stream]->time_base));
            result = avformat_seek_file(format, stream, INT64_MIN, target, target, AVSEEK_FLAG_BACKWARD);
            avcodec_flush_buffers(codec);
        }
        double duration = INFINITY;
        if (result >= 0 && format->streams[stream]->duration != AV_NOPTS_VALUE)
            duration = format->streams[stream]->duration * av_q2d(format->streams[stream]->time_base);
        std::array<float, 8192 * channels> buffer{};
        int frameIndex = 0;
        auto receive = [&]() {
            int got = AVERROR(EAGAIN);
            while (!cancel && (got = avcodec_receive_frame(codec, frame)) >= 0) {
                uint8_t* output = reinterpret_cast<uint8_t*>(buffer.data());
                if (swr_get_out_samples(convert, frame->nb_samples) > 8192) { error = AVERROR(ENOBUFS); return; }
                int count = swr_convert(convert, &output, 8192, const_cast<const uint8_t**>(frame->extended_data), frame->nb_samples);
                if (count < 0) { error = count; return; }
                // Decoder-adjusted PTS accounts for skip_samples; best_effort
                // may still name the pre-skip packet in this FFmpeg release.
                double pts = frame->pts == AV_NOPTS_VALUE
                    ? double(produced.load()) / rate : frame->pts * av_q2d(format->streams[stream]->time_base);
                if (std::getenv("P0_TRACE") && frameIndex++ < 3)
                    std::fprintf(stderr, "TRACE seek=%.3f pts=%.6f samples=%d duration=%.6f\n", seek, pts, count, duration);
                size_t begin = size_t(std::max(0.0, std::ceil((seek - pts) * rate - 0.01)));
                size_t end = size_t(std::max(0.0, std::min(double(count), std::ceil((duration - pts) * rate - 0.01))));
                if (begin < end && firstPTS < 0) firstPTS = pts + double(begin) / rate;
                while (begin < end && !cancel) {
                    auto written = ring.push(buffer.data() + begin * channels, end - begin);
                    begin += written;
                    produced += written;
                    if (written == 0) nap();
                }
                av_frame_unref(frame);
            }
            if (!cancel && got < 0 && got != AVERROR(EAGAIN) && got != AVERROR_EOF) error = got;
        };
        if (result >= 0) {
            while (!cancel && (result = av_read_frame(format, packet)) >= 0) {
                if (packet->stream_index == stream) {
                    result = avcodec_send_packet(codec, packet);
                    if (result < 0) break;
                    receive();
                }
                av_packet_unref(packet);
            }
            if (!cancel && result == AVERROR_EOF) { avcodec_send_packet(codec, nullptr); receive(); result = 0; }
        }
        if (result < 0 && !cancel) error = result;
        av_frame_free(&frame); av_packet_free(&packet);
        swr_free(&convert); avcodec_free_context(&codec); avformat_close_input(&format);
    }
};

std::vector<float> drain(Decoder& decoder) {
    std::vector<float> samples;
    samples.reserve(rate * 5 * channels);
    std::array<float, 1024 * channels> block{};
    auto deadline = Clock::now() + std::chrono::seconds(12);
    while (!decoder.done || decoder.ring.available()) {
        check(Clock::now() < deadline, "decode timeout");
        size_t count = decoder.ring.pop(block.data(), 1024);
        check(samples.size() + count * channels <= rate * 8 * channels, "test output hard limit");
        samples.insert(samples.end(), block.begin(), block.begin() + count * channels);
        if (!count) nap();
    }
    if (decoder.thread.joinable()) decoder.thread.join();
    check(decoder.error == 0, "decoder error");
    return samples;
}

double power(const std::vector<float>& data) {
    double sum = 0; for (float value : data) { check(std::isfinite(value), "nonfinite PCM"); sum += value * value; }
    return std::sqrt(sum / std::max(size_t(1), data.size()));
}

struct Mixer {
    Decoder* a; Decoder* b;
    uint64_t clock = 0;
    std::atomic<uint64_t> crossStart{rate * 3}, crossLength{rate};
    std::atomic<uint64_t> publishedClock{0}, transitions{0};
    std::atomic<uint64_t> aConsumed{0}, bConsumed{0}, nonzeroOutput{0};
    std::atomic<uint64_t> callbacks{0}, underflows{0}, clipped{0}, notifications{0};
    std::atomic<uint64_t> starts{0}, stops{0}, reroutes{0}, interruptions{0};
    bool muted = false;
    float gain = 1;
    // Fixed stack buffers bound even if a backend requests more frames than one period.
    void render(float* output, size_t frames) {
        for (size_t offset = 0; offset < frames;) {
            size_t count = std::min(size_t(256), frames - offset);
            const uint64_t start = crossStart.load(std::memory_order_acquire);
            const uint64_t length = crossLength.load(std::memory_order_relaxed);
            uint64_t consumedA = 0, consumedB = 0, nonzeroFrames = 0;
            std::array<float, 256 * channels> left{}, right{};
            for (size_t i = 0; i < count; ++i) {
                auto t = clock + i;
                bool needA = t < start + length;
                bool needB = t >= start;
                size_t na = needA ? a->ring.pop(left.data() + i * channels, 1) : 0;
                size_t nb = needB ? b->ring.pop(right.data() + i * channels, 1) : 0;
                consumedA += na; consumedB += nb;
                if ((needA && !na && !a->done) || (needB && !nb && !b->done)) ++underflows;
                double phase = length ? std::clamp(double(t) - double(start), 0.0, double(length)) / length : double(needB);
                float ga = float(std::cos(phase * 1.5707963267948966));
                float gb = float(std::sin(phase * 1.5707963267948966));
                bool nonzero = false;
                for (size_t c = 0; c < channels; ++c) {
                    float value = left[i * channels + c] * ga + right[i * channels + c] * gb;
                    if (std::abs(value) > 1) ++clipped;
                    output[(offset + i) * channels + c] = muted ? 0 : value * gain;
                    if (!muted && std::abs(value * gain) > 1e-8f) nonzero = true;
                }
                nonzeroFrames += nonzero ? 1 : 0;
                if (t == start + length) transitions.fetch_add(1, std::memory_order_relaxed);
            }
            clock += count; offset += count;
            aConsumed.fetch_add(consumedA, std::memory_order_relaxed);
            bConsumed.fetch_add(consumedB, std::memory_order_relaxed);
            nonzeroOutput.fetch_add(nonzeroFrames, std::memory_order_relaxed);
        }
        publishedClock.store(clock, std::memory_order_release);
    }
};

void prepare(Decoder& decoder) {
    auto deadline = Clock::now() + std::chrono::seconds(5);
    while (decoder.ring.available() < 8192 && !decoder.done) { check(Clock::now() < deadline, "prepare timeout"); nap(); }
    check(decoder.error == 0 && decoder.ring.available() >= 8192, "prepare failed");
}
void callback(ma_device* device, void* output, const void*, ma_uint32 frames) {
    auto* mixer = static_cast<Mixer*>(device->pUserData);
    mixer->render(static_cast<float*>(output), frames);
    ++mixer->callbacks;
}
void notification(const ma_device_notification* note) {
    auto* mixer = static_cast<Mixer*>(note->pDevice->pUserData);
    ++mixer->notifications;
    if (note->type == ma_device_notification_type_started) ++mixer->starts;
    if (note->type == ma_device_notification_type_stopped) ++mixer->stops;
    if (note->type == ma_device_notification_type_rerouted) ++mixer->reroutes;
    if (note->type == ma_device_notification_type_interruption_began) ++mixer->interruptions;
}

void deviceTest(const char* urlA, const char* urlB, bool audible) {
    Decoder a, b; a.start(urlA); b.start(urlB); prepare(a); prepare(b);
    Mixer mixer{&a, &b}; mixer.muted = !audible;
    ma_context context;
    auto cc = ma_context_config_init();
    cc.coreaudio.sessionCategory = ma_ios_session_category_none;
    // AVAudioSession belongs to the iOS native host. No session activation here.
    cc.coreaudio.noAudioSessionActivate = MA_TRUE;
    cc.coreaudio.noAudioSessionDeactivate = MA_TRUE;
    ma_backend backend = ma_backend_coreaudio;
    check(ma_context_init(&backend, 1, &cc, &context) == MA_SUCCESS, "CoreAudio context init");
    ma_device_config config = ma_device_config_init(ma_device_type_playback);
    config.playback.format = ma_format_f32; config.playback.channels = channels;
    config.playback.shareMode = ma_share_mode_shared; config.sampleRate = rate;
    config.periodSizeInFrames = 256; config.dataCallback = callback;
    config.notificationCallback = notification; config.pUserData = &mixer;
    ma_device device;
    check(ma_device_init(&context, &config, &device) == MA_SUCCESS, "shared device init");
    check(ma_device_start(&device) == MA_SUCCESS, "device start");
    std::this_thread::sleep_for(std::chrono::milliseconds(250));
    check(ma_device_stop(&device) == MA_SUCCESS, "device stop");
    auto paused = mixer.clock;
    std::this_thread::sleep_for(std::chrono::milliseconds(80));
    check(mixer.clock == paused, "clock moved while stopped");
    check(ma_device_start(&device) == MA_SUCCESS, "device restart");
    std::this_thread::sleep_for(std::chrono::milliseconds(250));
    ma_device_stop(&device);
    ma_device_uninit(&device); ma_context_uninit(&context);
    check(mixer.callbacks > 1 && mixer.clock > paused && mixer.underflows == 0, "native callback invariant");
    std::printf("{\"kind\":\"native_device\",\"backend\":\"CoreAudio\",\"shared\":true,\"muted\":%s,\"callbacks\":%llu,\"clock_frames\":%llu,\"underflows\":%llu,\"starts\":%llu,\"stops\":%llu,\"reroutes\":%llu,\"interruptions\":%llu,\"human_audibility_verified\":false}\n",
        audible ? "false" : "true", mixer.callbacks.load(), (unsigned long long)mixer.clock,
        mixer.underflows.load(), mixer.starts.load(), mixer.stops.load(), mixer.reroutes.load(), mixer.interruptions.load());
}

void decodeTest(const char* url, const char* kind) {
    Decoder decoder; decoder.start(url); auto decoded = drain(decoder);
    size_t frames = decoded.size() / channels;
    check(frames >= rate * 399 / 100 && frames <= rate * 401 / 100, "duration trimming outside 10 ms");
    double rms = power(decoded); check(rms > 0.04 && rms < 0.1, "signal amplitude");
    Decoder sought; sought.start(url, 1.5); auto tail = drain(sought);
    size_t offset = size_t(std::llround(sought.firstPTS * rate)) * channels;
    if (std::getenv("P0_TRACE")) std::fprintf(stderr,"TRACE %s decoded=%zu sought=%zu offset=%zu first=%.6f\n",kind,decoded.size()/channels,tail.size()/channels,offset/channels,sought.firstPTS);
    check(offset + tail.size() <= decoded.size() + 96, "seek duration");
    size_t count = std::min(tail.size(), decoded.size() - std::min(offset, decoded.size()));
    double err = 0; for (size_t i = 0; i < count; ++i) err += std::pow(tail[i] - decoded[offset + i], 2);
    err = std::sqrt(err / std::max(size_t(1), count));
    // WebM timestamps use a millisecond time base. Quantization can shift the
    // decoded seek origin by up to one tick; measure and report it, not hide it.
    int bestShift = 0;
    for (int shift = -48; shift <= 48; ++shift) {
        auto candidate = int64_t(offset) + shift * int(channels);
        if (candidate < 0) continue;
        size_t length = std::min(tail.size(), decoded.size() - size_t(candidate));
        double squared = 0;
        for (size_t i = 0; i < length; ++i) squared += std::pow(tail[i] - decoded[size_t(candidate) + i], 2);
        double rmsError = std::sqrt(squared / std::max(size_t(1), length));
        if (rmsError < err) { err = rmsError; bestShift = shift; }
    }
    std::printf("{\"kind\":\"decode_seek\",\"codec\":\"%s\",\"frames\":%zu,\"rms\":%.7f,\"seek_first_pts\":%.7f,\"seek_frames\":%zu,\"seek_alignment_frames\":%d,\"seek_rms_error\":%.7f,\"ring_high_frames\":%llu}\n", kind, frames, rms, sought.firstPTS, tail.size()/channels, bestShift, err, decoder.ring.high.load());
    check(count > rate * 2 * channels && err < 0.01, "seek signal differs from reference");
}

void mixTest(const char* urlA, const char* urlB, bool gapless) {
    Decoder a, b; a.start(urlA); b.start(urlB); prepare(a); prepare(b);
    Mixer mixer{&a, &b}; if (gapless) { mixer.crossStart = rate * 4; mixer.crossLength = 0; }
    std::vector<float> result; result.reserve(rate * 8 * channels);
    std::array<float, 256 * channels> block;
    uint64_t total = gapless ? rate * 8 : rate * 7;
    auto deadline = Clock::now() + std::chrono::seconds(10);
    while (mixer.clock < total) {
        check(Clock::now() < deadline, "mix timeout");
        bool needA = mixer.clock < mixer.crossStart.load() + mixer.crossLength.load();
        bool needB = mixer.clock + 256 >= mixer.crossStart.load();
        if ((needA && a.ring.available() < 256 && !a.done) || (needB && b.ring.available() < 256 && !b.done)) { nap(); continue; }
        size_t count = std::min(uint64_t(256), total - mixer.clock);
        mixer.render(block.data(), count);
        result.insert(result.end(), block.begin(), block.begin() + count * channels);
    }
    check(mixer.underflows == 0 && mixer.clipped == 0, "mixer underflow or clipping");
    check(power(result) > 0.04, "empty mix");
    // Every 10 ms window, including the transition, must contain nonzero signal.
    double minRms = 1;
    for (size_t i = 0; i + 960 <= result.size(); i += 960) {
        double sum = 0; for (size_t j = 0; j < 960; ++j) sum += result[i+j] * result[i+j];
        minRms = std::min(minRms, std::sqrt(sum / 960));
    }
    check(minRms > 0.01, "silent transition window");
    std::printf("{\"kind\":\"%s\",\"clock_frames\":%llu,\"underflows\":%llu,\"clipped\":%llu,\"minimum_10ms_rms\":%.7f,\"pcm_pool_bytes\":%zu}\n", gapless ? "gapless" : "equal_power_crossfade", (unsigned long long)mixer.clock, mixer.underflows.load(), mixer.clipped.load(), minRms, 2 * capacity * channels * sizeof(float));
}

void cancellationTest(const char* slowURL, const char* url) {
    Decoder pending; auto started = Clock::now(); pending.start(slowURL);
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    auto requested = Clock::now(); pending.cancel = true; pending.thread.join();
    double ms = std::chrono::duration<double, std::milli>(Clock::now() - requested).count();
    check(ms < 750 && pending.produced == 0, "blocked input cancellation or stale PCM");
    Decoder full; full.start(url); prepare(full);
    while (full.ring.available() < capacity && !full.done) nap();
    auto before = full.produced.load(); full.cancel = true; full.thread.join();
    check(full.produced == before && full.ring.high <= capacity, "producer cancellation bound");
    // Replacement has its own ring; discarded generation cannot enter the new stream.
    Decoder replacement; replacement.start(url); auto clean = drain(replacement);
    check(!clean.empty(), "replacement failed after cancellation");
    std::printf("{\"kind\":\"cancellation\",\"blocked_io_cancel_ms\":%.3f,\"cancelled_generation_frames\":%llu,\"full_ring_frames\":%llu,\"replacement_frames\":%zu}\n", ms, pending.produced.load(), full.ring.high.load(), clean.size()/channels);
}

struct Session {
    Decoder first, next;
    Mixer mixer{&first, &next};
    ma_context context{};
    ma_device device{};
    bool contextReady = false, deviceReady = false;
    std::atomic<bool> watchCancelled{false}, timedStop{false};
    std::atomic<int> nextState{0}; // 0 empty, 1 preparing, 2 ready, -1 failed.
    std::thread watchdog;
    ~Session() {
        watchCancelled = true;
        if (watchdog.joinable()) watchdog.join();
        if (deviceReady) { ma_device_stop(&device); ma_device_uninit(&device); }
        if (contextReady) ma_context_uninit(&context);
        // Decoder destructors cancel and join only after output has stopped.
    }
    void start(const char* path, int seconds, bool audible) {
        mixer.crossStart = UINT64_MAX - rate * 10;
        mixer.crossLength = 0;
        mixer.muted = !audible;
        mixer.gain = 0.12f;
        first.start(path); prepare(first);
        auto cc = ma_context_config_init();
        cc.coreaudio.sessionCategory = ma_ios_session_category_none;
        cc.coreaudio.noAudioSessionActivate = MA_TRUE;
        cc.coreaudio.noAudioSessionDeactivate = MA_TRUE;
        ma_backend backend = ma_backend_coreaudio;
        check(ma_context_init(&backend, 1, &cc, &context) == MA_SUCCESS, "session context");
        contextReady = true;
        auto dc = ma_device_config_init(ma_device_type_playback);
        dc.playback.format = ma_format_f32; dc.playback.channels = channels;
        dc.playback.shareMode = ma_share_mode_shared; dc.sampleRate = rate;
        dc.periodSizeInFrames = 256; dc.dataCallback = callback;
        dc.notificationCallback = notification; dc.pUserData = &mixer;
        check(ma_device_init(&context, &dc, &device) == MA_SUCCESS, "session device");
        deviceReady = true;
        check(ma_device_start(&device) == MA_SUCCESS, "session start");
        watchdog = std::thread([this, seconds] {
            const auto deadline = Clock::now() + std::chrono::seconds(seconds);
            while (!watchCancelled && Clock::now() < deadline)
                std::this_thread::sleep_for(std::chrono::milliseconds(20));
            if (!watchCancelled) { ma_device_stop(&device); timedStop = true; first.cancel = true; next.cancel = true; }
        });
    }
};
}

extern "C" void* muses_p0_audio_start(const char* path, int seconds, int audible, int* error) {
    if (error) *error = 0;
    if (!path || seconds < 2 || seconds > 180 || (audible != 0 && audible != 1)) {
        if (error) *error = -1; return nullptr;
    }
    try {
        av_log_set_level(AV_LOG_ERROR);
        auto session = std::make_unique<Session>();
        session->start(path, seconds, audible != 0);
        return session.release();
    } catch (...) { if (error) *error = -2; return nullptr; }
}

extern "C" int muses_p0_audio_prepare_next(void* pointer, const char* path, int lead, int fade) {
    if (!pointer || !path || lead < 100 || lead > 10000 || fade < 0 || fade > 5000) return -1;
    auto* session = static_cast<Session*>(pointer);
    int expected = 0;
    if (session->timedStop || !session->nextState.compare_exchange_strong(expected, 1)) return -2;
    try {
        session->next.start(path); prepare(session->next);
        if (session->timedStop) { session->nextState = -1; return -3; }
        session->mixer.crossLength.store(uint64_t(fade) * rate / 1000, std::memory_order_relaxed);
        session->mixer.crossStart.store(session->mixer.publishedClock.load(std::memory_order_acquire) + uint64_t(lead) * rate / 1000, std::memory_order_release);
        session->nextState = 2;
        return 0;
    } catch (...) { session->next.cancel = true; session->nextState = -1; return -3; }
}

extern "C" int muses_p0_audio_snapshot(void* pointer, MusesP0AudioSnapshot* out) {
    if (!pointer || !out) return -1;
    auto* s = static_cast<Session*>(pointer);
    *out = {};
    out->clock_frames = s->mixer.publishedClock.load(); out->callbacks = s->mixer.callbacks.load();
    out->underflow_frames = s->mixer.underflows.load(); out->clipped_samples = s->mixer.clipped.load();
    out->transition_start_frame = s->mixer.crossStart.load();
    out->transition_end_frame = out->transition_start_frame + s->mixer.crossLength.load();
    out->transitions = s->mixer.transitions.load();
    out->first_decoded_frames = s->first.produced.load(); out->next_decoded_frames = s->next.produced.load();
    out->first_buffered_frames = s->first.ring.available(); out->next_buffered_frames = s->next.ring.available();
    out->starts = s->mixer.starts.load(); out->stops = s->mixer.stops.load();
    out->reroutes = s->mixer.reroutes.load(); out->interruptions = s->mixer.interruptions.load();
    out->first_error = s->first.error.load(); out->next_error = s->next.error.load();
    out->next_ready = s->nextState.load() == 2; out->timed_stop = s->timedStop.load();
    out->first_consumed_frames = s->mixer.aConsumed.load();
    out->next_consumed_frames = s->mixer.bConsumed.load();
    out->nonzero_output_frames = s->mixer.nonzeroOutput.load();
    return 0;
}

extern "C" void muses_p0_audio_stop(void* pointer) { delete static_cast<Session*>(pointer); }

extern "C" int muses_p0_audio_test(const char* a, const char* b, int device) {
    try { av_log_set_level(AV_LOG_ERROR); decodeTest(a, "aac"); decodeTest(b, "opus"); mixTest(a,b,false); mixTest(a,b,true); if (device) deviceTest(a,b,false); return 0; }
    catch (const std::exception& e) { std::fprintf(stderr, "FAIL: %s\n", e.what()); return 1; }
}

#ifndef P0_LIBRARY_ONLY
int main(int argc, char** argv) {
    try {
        check(argc >= 4, "usage: audio-probe tests|device|audible AAC OPUS [SLOW_URL]");
        av_log_set_level(AV_LOG_ERROR);
        std::printf("{\"kind\":\"dependency\",\"ffmpeg\":\"%s\",\"license\":\"%s\",\"miniaudio\":\"%s\",\"runtime_linking\":false}\n", av_version_info(), avcodec_license(), MA_VERSION_STRING);
        if (std::string(argv[1]) == "session") {
            int error = 0;
            void* session = muses_p0_audio_start(argv[2], 6, 0, &error);
            check(session != nullptr && error == 0, "persistent session start");
            std::this_thread::sleep_for(std::chrono::milliseconds(300));
            MusesP0AudioSnapshot before{}, after{};
            muses_p0_audio_snapshot(session, &before);
            check(before.next_ready == 0 && before.next_decoded_frames == 0, "next was prepared early");
            check(muses_p0_audio_prepare_next(session, argv[3], 500, 500) == 0, "late next prepare");
            check(muses_p0_audio_prepare_next(session, argv[3], 500, 500) == -2, "duplicate next accepted");
            std::this_thread::sleep_for(std::chrono::milliseconds(1400));
            muses_p0_audio_snapshot(session, &after);
            muses_p0_audio_stop(session);
            check(after.transitions == 1 && after.underflow_frames == 0 && after.first_error == 0 && after.next_error == 0, "persistent transition failed");
            check(after.clock_frames > before.clock_frames && after.next_ready == 1, "persistent clock or readiness");
            std::printf("{\"kind\":\"late_next_native_session\",\"muted\":true,\"initial_next_decoded_frames\":%llu,\"clock_frames\":%llu,\"transition_start_frame\":%llu,\"transition_end_frame\":%llu,\"transitions\":%llu,\"underflows\":%llu,\"callbacks\":%llu}\n", before.next_decoded_frames, after.clock_frames, after.transition_start_frame, after.transition_end_frame, after.transitions, after.underflow_frames, after.callbacks);
        }
        else if (std::string(argv[1]) == "device" || std::string(argv[1]) == "audible") deviceTest(argv[2],argv[3],std::string(argv[1]) == "audible");
        else { check(muses_p0_audio_test(argv[2],argv[3],0) == 0, "audio tests"); if (argc > 4) cancellationTest(argv[4],argv[2]); }
        return 0;
    } catch (const std::exception& e) { std::fprintf(stderr, "FAIL: %s\n", e.what()); return 1; }
}
#endif
