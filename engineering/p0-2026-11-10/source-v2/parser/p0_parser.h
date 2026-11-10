// SPDX-License-Identifier: MIT
#ifndef MUSES_P0_PARSER_H
#define MUSES_P0_PARSER_H
#include <stddef.h>
#include <stdint.h>
#include <signal.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef enum {
  P0_PARSE_OK=0, P0_PARSE_INPUT_LIMIT, P0_PARSE_MEMORY_LIMIT,
  P0_PARSE_OUTPUT_LIMIT, P0_PARSE_CANCELLED, P0_PARSE_DEADLINE,
  P0_PARSE_SYNTAX, P0_PARSE_UNSUPPORTED, P0_PARSE_BUSY
} p0_parser_status;
typedef struct {
  size_t max_input_bytes;       // default 4 MiB
  size_t max_working_bytes;     // default 64 MiB, includes allocation headers
  size_t max_output_bytes;      // default 256 KiB
  uint32_t max_depth;           // default 256
  uint64_t deadline_ns;         // absolute CLOCK_MONOTONIC; zero means 5 s
  const volatile sig_atomic_t *cancelled; // optional signal-handler flag
  int (*should_cancel)(void *); // optional trusted host callback; may read atomics
  void *cancel_context;
} p0_parser_limits;
typedef struct {
  p0_parser_status status;
  size_t input_bytes, output_bytes, peak_working_bytes, live_working_bytes;
  uint32_t declarations, selected_declarations, solver_matches, timestamp_matches;
  uint64_t parse_ns, reduce_ns;
  uint32_t failure_offset, parse_window_bytes;
} p0_parser_result;
// No network, JS execution, or retained parser/context. Caller owns both buffers.
// Output is a conservative reduced IIFE for the pinned upstream analyzer, NOT a
// safe-to-execute player. Only upstream side-effect-filtered output may execute.
// Calls serialize by rejection (BUSY). This P0 owns its linked Tree-sitter copy;
// do not share that library instance with unrelated concurrent Tree-sitter users.
p0_parser_status p0_player_reduce(const char *input,size_t length,
  const p0_parser_limits *limits,char *output,size_t capacity,p0_parser_result *result);
const char *p0_parser_status_name(p0_parser_status status);
#ifdef __cplusplus
}
#endif
#endif
