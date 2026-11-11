// MIT. Exactly 128 pending native timers; the 129th must reject.
let completed = 0;
let rejected = false;
try { for (let id=1; id<=129; id++) { nativeTimer(id,60000); completed++; } }
catch (_) { rejected = true; }
nativeFinish(rejected && completed===128 ? 0 : 1);
