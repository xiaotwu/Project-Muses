// MIT. QuickJS requires input[input_len] == '\0'; NSData has no such promise.
// The pinned public quickjs.h documents this at its JS_Eval declaration.
static JSValue P0EvaluateData(JSContext *ctx, NSData *data, const char *filename, int flags) {
    if (!data) return JS_ThrowInternalError(ctx, "script_input_unavailable");
    size_t length = data.length;
    if (length > 4*1024*1024) return JS_ThrowRangeError(ctx, "script_input_limit");
    char *terminated = malloc(length+1);
    if (!terminated) return JS_ThrowOutOfMemory(ctx);
    if (length) memcpy(terminated, data.bytes, length);
    terminated[length] = '\0';
    JSValue result = JS_Eval(ctx, terminated, length, filename, flags);
    free(terminated);
    return result;
}
