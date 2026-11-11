// MIT. Adversarial lifetime/ordering checks for the P0 proof.
#define P0_LIBRARY_ONLY
#include "probe.cpp"

int main(int argc, char** argv) {
    try {
        check(argc == 2, "AAC fixture required");
        Ring ring;
        constexpr uint64_t total = 1000000;
        std::thread producer([&] {
            std::array<float, 137 * channels> block{};
            for (uint64_t cursor = 0; cursor < total;) {
                size_t count = std::min(uint64_t(137), total - cursor);
                for (size_t i = 0; i < count; ++i) {
                    block[i*channels] = float(cursor+i);
                    block[i*channels+1] = -float(cursor+i);
                }
                cursor += ring.push(block.data(), count);
                std::this_thread::yield();
            }
        });
        std::array<float, 251 * channels> output;
        bool ordered = true;
        for (uint64_t cursor = 0; cursor < total;) {
            auto count = ring.pop(output.data(), std::min(uint64_t(251), total-cursor));
            for (size_t i = 0; i < count; ++i)
                if (output[i*channels] != float(cursor+i) || output[i*channels+1] != -float(cursor+i)) ordered = false;
            cursor += count;
            std::this_thread::yield();
        }
        producer.join();
        check(ordered && ring.available() == 0 && ring.high <= capacity, "SPSC ordering or capacity");
        Decoder emptyA, emptyB;
        Mixer empty{&emptyA, &emptyB};
        std::array<float, 512 * channels> silence;
        silence.fill(1);
        empty.render(silence.data(), 512);
        for (float value : silence) check(value == 0, "starvation did not clear output");
        check(empty.underflows == 512 && empty.nonzeroOutput == 0, "starvation accounting");

        int error = 0;
        void* session = muses_p0_audio_start(argv[1], 2, 0, &error);
        check(session != nullptr, "watchdog session start");
        check(muses_p0_audio_prepare_next(session, "/nonexistent-p0-fixture", 100, 0) == -3, "failed next prepare accepted");
        std::this_thread::sleep_for(std::chrono::milliseconds(2300));
        MusesP0AudioSnapshot first{}, second{};
        muses_p0_audio_snapshot(session, &first);
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        muses_p0_audio_snapshot(session, &second);
        muses_p0_audio_stop(session);
        check(first.timed_stop == 1 && first.stops >= 1 && first.clock_frames == second.clock_frames, "watchdog clock did not stop");
        check(first.transitions == 0 && first.next_consumed_frames == 0 && first.nonzero_output_frames == 0, "failed next leaked samples or muted output");
        check(first.first_consumed_frames > 0 && first.first_error == 0, "first input failed while next unavailable");
        std::printf("{\"kind\":\"adversarial\",\"ordered_spsc_frames\":%llu,\"ring_high_frames\":%llu,\"starvation_silent_frames\":512,\"watchdog_stopped\":true,\"failed_next_isolated\":true,\"first_consumed_frames\":%llu,\"muted_nonzero_output_frames\":%llu}\n", (unsigned long long)total, ring.high.load(), first.first_consumed_frames, first.nonzero_output_frames);
        return 0;
    } catch (const std::exception& e) { std::fprintf(stderr, "FAIL: %s\n", e.what()); return 1; }
}
