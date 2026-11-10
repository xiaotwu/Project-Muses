// MIT. The inner solver's local 1 s timeout must not hide a shorter shared stop.
nativeEval('while (true) {}');
nativeFinish(1);
