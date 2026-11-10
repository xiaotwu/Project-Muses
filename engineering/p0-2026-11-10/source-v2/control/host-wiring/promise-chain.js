// MIT. A replenishing queue must yield to native cancellation/deadline checks.
function again() { return Promise.resolve().then(again); }
again();
