using System.Runtime.InteropServices;
using System.Text;

[StructLayout(LayoutKind.Sequential)]
struct Command {
    public uint Abi, Size, Kind, Reserved;
    public ulong Generation, Occurrence, Media;
}
[StructLayout(LayoutKind.Sequential)]
struct Snapshot {
    public uint Abi, Size, State, Reserved;
    public ulong Sequence, Generation, Occurrence, Media, Count;
    public static Snapshot Empty => new() { Abi = 1, Size = (uint)Marshal.SizeOf<Snapshot>() };
}
[StructLayout(LayoutKind.Sequential)]
struct Event {
    public uint Abi, Size, Kind, Reserved;
    public ulong Sequence, Generation, Occurrence, Media;
    public static Event Empty => new() { Abi = 1, Size = (uint)Marshal.SizeOf<Event>() };
}
[StructLayout(LayoutKind.Sequential)]
struct Entry { public ulong Occurrence, Media, Ordinal; }
static class Native {
    const string Library = "muses_p0_core";
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] public static extern uint muses_abi_version();
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] public static extern int muses_open(uint abi, byte[] path, nuint length, out ulong engine);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] public static extern int muses_release(ulong engine);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] public static extern int muses_command(ulong engine, ref Command command, out ulong generation);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] public static extern int muses_snapshot_acquire(ulong engine, out ulong snapshot);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] public static extern int muses_snapshot_read(ulong snapshot, ref Snapshot value);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] public static extern int muses_snapshot_entry(ulong snapshot, ulong index, out Entry entry);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] public static extern int muses_snapshot_release(ulong snapshot);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] public static extern int muses_subscribe(ulong engine, ulong after, out ulong subscription);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] public static extern int muses_poll(ulong subscription, ref Event value);
    [DllImport(Library, CallingConvention = CallingConvention.Cdecl)] public static extern int muses_unsubscribe(ulong subscription);
}
static class Program {
    static int checks;
    static void Check(bool condition, string name) { checks++; if (!condition) throw new InvalidOperationException("FAIL: " + name); }
    static void Status(int actual, string name, int expected = 0) => Check(actual == expected, $"{name}: expected {expected}, got {actual}");
    static ulong Open(string path, int expected = 0) {
        var bytes = Encoding.UTF8.GetBytes(path);
        Status(Native.muses_open(1, bytes, (nuint)bytes.Length, out var engine), "open", expected);
        if (expected != 0) Check(engine == 0, "failed open clears output");
        return engine;
    }
    static (ulong, Snapshot) Freeze(ulong engine) {
        Status(Native.muses_snapshot_acquire(engine, out var handle), "acquire");
        return (handle, Read(handle));
    }
    static Snapshot Read(ulong handle) {
        var value = Snapshot.Empty;
        Status(Native.muses_snapshot_read(handle, ref value), "read");
        return value;
    }
    static ulong Send(ulong engine, uint kind, ulong generation, ulong occurrence = 0, ulong media = 0, int expected = 0) {
        var value = new Command { Abi = 1, Size = (uint)Marshal.SizeOf<Command>(), Kind = kind, Generation = generation, Occurrence = occurrence, Media = media };
        Status(Native.muses_command(engine, ref value, out var next), "command " + kind, expected);
        if (expected != 0) Check(next == 0, "failed command output generation");
        return next;
    }
    static void Main(string[] args) {
        Check(args.Length == 2, "mode + isolated path required");
        string dylib = Environment.GetEnvironmentVariable("MUSES_P0_DYLIB") ?? throw new InvalidOperationException("explicit dylib required");
        NativeLibrary.SetDllImportResolver(typeof(Native).Assembly, (name, _, _) => name == "muses_p0_core" ? NativeLibrary.Load(dylib) : IntPtr.Zero);
        Check(Native.muses_abi_version() == 1, "ABI version");
        Check(Marshal.SizeOf<Command>() == 40, "command layout");
        Check(Marshal.SizeOf<Snapshot>() == 56 && Marshal.OffsetOf<Snapshot>(nameof(Snapshot.Generation)) == 24, "snapshot layout");
        Check(Marshal.SizeOf<Event>() == 48 && Marshal.OffsetOf<Event>(nameof(Event.Sequence)) == 16, "event layout");
        Check(Marshal.SizeOf<Entry>() == 24, "entry layout");
        if (args[0] is "busy" or "foreign" or "alias") {
            Open(args[1], args[0] == "busy" ? 9 : args[0] == "foreign" ? 5 : 2);
            Console.WriteLine($"PASS csharp {args[0]} checks={checks} open_refused=true");
            return;
        }
        var engine = Open(args[1]);
        if (args[0] == "resume") {
            var (initialHandle, initial) = Freeze(engine);
            Check(initial.Count == 2 && initial.Occurrence == 102 && initial.Generation == 5 && initial.State == 2 && initial.Sequence == 9, "Swift state persisted into C# process");
            Status(Native.muses_snapshot_entry(initialHandle, 0, out var entry), "entry read");
            Check(entry.Occurrence == 101 && entry.Media == 55 && entry.Ordinal == 0, "persistent occurrence identity");
            // A persisted sequence is not a durable UI event log. A client must
            // resnapshot after restart, not silently assume old events exist.
            Status(Native.muses_subscribe(engine, 0, out var oldEvents), "subscribe old sequence");
            var value = Event.Empty;
            Status(Native.muses_poll(oldEvents, ref value), "restart event gap", 6);
            Status(Native.muses_unsubscribe(oldEvents), "unsubscribe old");
            Status(Native.muses_subscribe(engine, initial.Sequence, out var subscription), "current subscription");
            // Two clients submit the same generation. Serialization permits one
            // selection; the other cannot replace it using an obsolete generation.
            var race = new (int Code, ulong Generation)[2];
            Parallel.For(0, 2, i => {
                var cmd = new Command { Abi = 1, Size = 40, Kind = 2, Generation = initial.Generation, Occurrence = (ulong)(101 + i) };
                race[i].Code = Native.muses_command(engine, ref cmd, out race[i].Generation);
            });
            Check(race.Count(x => x.Code == 0) == 1 && race.Count(x => x.Code == 4) == 1, "concurrent stale selection rejection");
            var (winnerHandle, winner) = Freeze(engine);
            Check(winner.Generation == initial.Generation + 1, "one generation increment");
            Send(engine, 3, initial.Generation, initial.Occurrence, expected: 4);
            Send(engine, 3, winner.Generation, winner.Occurrence);
            Status(Native.muses_poll(subscription, ref value), "selected event");
            Check(value.Sequence == initial.Sequence + 1 && value.Kind == 2, "selected event order");
            Status(Native.muses_poll(subscription, ref value), "resolved event");
            Check(value.Sequence == initial.Sequence + 2 && value.Kind == 3, "resolved event order");
            Status(Native.muses_poll(subscription, ref value), "caught up", 7);
            for (ulong i = 0; i < 70; i++) Send(engine, 1, winner.Generation, 1000 + i, 55);
            Status(Native.muses_poll(subscription, ref value), "bounded event gap", 6);
            Check(Read(initialHandle).Count == 2, "snapshot stable after queue mutations");
            Status(Native.muses_unsubscribe(subscription), "unsubscribe gap");
            Status(Native.muses_poll(subscription, ref value), "post unsubscribe", 1);
            Status(Native.muses_snapshot_release(initialHandle), "release initial");
            Status(Native.muses_snapshot_release(winnerHandle), "release winner");
            var (currentHandle, current) = Freeze(engine);
            Check(current.Count == 72, "all occurrences retained");
            Status(Native.muses_subscribe(engine, current.Sequence, out var caughtUp), "resubscribe from snapshot");
            Status(Native.muses_poll(caughtUp, ref value), "resnapshot gap recovery", 7);
            Status(Native.muses_unsubscribe(caughtUp), "release caught up");
            Status(Native.muses_snapshot_release(currentHandle), "release current");
            var snapshots = new List<ulong>();
            for (int i = 0; i < 64; i++) { Status(Native.muses_snapshot_acquire(engine, out var h), "bounded snapshot acquire"); snapshots.Add(h); }
            Status(Native.muses_snapshot_acquire(engine, out var denied), "snapshot budget", 8);
            Check(denied == 0, "limit output handle reset");
            foreach (var handle in snapshots) Status(Native.muses_snapshot_release(handle), "bounded snapshot release");
            var subscriptions = new List<ulong>();
            for (int i = 0; i < 16; i++) { Status(Native.muses_subscribe(engine, current.Sequence, out var h), "bounded subscription"); subscriptions.Add(h); }
            Status(Native.muses_subscribe(engine, current.Sequence, out _), "subscription budget", 8);
            foreach (var handle in subscriptions) Status(Native.muses_unsubscribe(handle), "subscription cleanup");
            var (retained, _) = Freeze(engine);
            Status(Native.muses_subscribe(engine, current.Sequence, out var dependent), "dependent subscription");
            Status(Native.muses_release(engine), "release engine");
            Status(Native.muses_poll(dependent, ref value), "released engine subscription", 1);
            Check(Read(retained).Count == 72, "snapshot outlives engine");
            Status(Native.muses_snapshot_release(retained), "release retained");
            Status(Native.muses_snapshot_release(retained), "double snapshot release", 1);
            Status(Native.muses_release(engine), "double engine release", 1);
            Console.WriteLine($"PASS csharp resume checks={checks} sequence={current.Sequence} generation={current.Generation} queue=72 library={dylib}");
        } else if (args[0] == "recover") {
            var (handle, current) = Freeze(engine);
            Check(current.Count == 72 && current.State == 0 && current.Generation == 8 && current.Sequence == 83, "crashed resolver invalidated on restart");
            Send(engine, 3, 7, 101, expected: 4);
            Status(Native.muses_subscribe(engine, current.Sequence - 1, out var sub), "recovery subscription");
            var value = Event.Empty;
            Status(Native.muses_poll(sub, ref value), "recovery event");
            Check(value.Kind == 5 && value.Generation == 8 && value.Sequence == 83, "durable recovery sequence");
            Status(Native.muses_release(engine), "release recovered engine");
            Status(Native.muses_poll(sub, ref value), "release subscription invalidated", 1);
            Check(Read(handle).State == 0, "recovered snapshot outlives engine");
            Status(Native.muses_snapshot_release(handle), "release recovered snapshot");
            Console.WriteLine($"PASS csharp recover checks={checks} generation={current.Generation} sequence={current.Sequence}");
        } else throw new InvalidOperationException("unknown mode");
    }
}
