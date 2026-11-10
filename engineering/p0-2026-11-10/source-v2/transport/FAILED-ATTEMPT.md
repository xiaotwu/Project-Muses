# Preserved decoder-input copy failure

The first guarded `restore_decoder_inputs.py` invocation copied all top-level
headers from four FFmpeg libraries, then failed its own assertion that selected
input bytes were below 8 MiB. No code was built or executed from that broad
header copy or from the prior-stage Trash. The failure was not a successful
dependency-preparation run.

The script was corrected to select upstream public `HEADERS` entries. The
already copied excess was handled separately by a frozen correction plan and
verified script, after an open-file check: 711 unnecessary private headers
were moved into this slice's recoverable `Trash/unused-private-headers`.
Existing copied libraries/fixtures were retained and their original immutable
audio-manifest hashes rechecked. Active selected inputs are 4,105,636 bytes.

The original nonzero guard receipt, successful correction receipt, complete
correction plan and journal are preserved under `evidence/`. The failed script
file was subsequently corrected; no claim is made that its original source
bytes were archived before the failure. This note records the observed failed
assertion and the subsequent bounded recovery without rewriting that receipt.
