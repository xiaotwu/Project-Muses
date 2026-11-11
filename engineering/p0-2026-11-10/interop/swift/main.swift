import Foundation
import MusesP0

var checks = 0
func check(_ condition: @autoclosure () -> Bool, _ label: String) {
    checks += 1
    guard condition() else { fatalError("FAIL: \(label)") }
}
func status(_ actual: Int32, _ expected: Int32, _ label: String) {
    check(actual == expected, "\(label): expected \(expected), got \(actual)")
}
func status(_ actual: Int32, _ label: String) { status(actual, 0, label) }
func openCore(_ path: String, expected: Int32 = 0) -> UInt64 {
    var handle: UInt64 = 0
    let bytes = Array(path.utf8)
    let result = bytes.withUnsafeBufferPointer { muses_open(1, $0.baseAddress, $0.count, &handle) }
    status(result, expected, "open")
    return handle
}
func snapshot(_ engine: UInt64) -> (UInt64, MusesSnapshot) {
    var token: UInt64 = 0
    status(muses_snapshot_acquire(engine, &token), "acquire snapshot")
    return (token, read(token))
}
func read(_ token: UInt64) -> MusesSnapshot {
    var value = MusesSnapshot()
    value.abi_version = 1
    value.struct_size = UInt32(MemoryLayout<MusesSnapshot>.size)
    status(muses_snapshot_read(token, &value), "read snapshot")
    return value
}
@discardableResult
func command(_ engine: UInt64, _ kind: UInt32, _ generation: UInt64,
             occurrence: UInt64 = 0, media: UInt64 = 0, expected: Int32 = 0) -> UInt64 {
    var value = MusesCommand()
    value.abi_version = 1
    value.struct_size = UInt32(MemoryLayout<MusesCommand>.size)
    value.kind = kind
    value.expected_generation = generation
    value.occurrence_id = occurrence
    value.media_id = media
    var result: UInt64 = 99
    status(muses_command(engine, &value, &result), expected, "command \(kind)")
    if expected != 0 { check(result == 0, "failed command clears output generation") }
    return result
}
func event() -> MusesEvent {
    var value = MusesEvent()
    value.abi_version = 1
    value.struct_size = UInt32(MemoryLayout<MusesEvent>.size)
    return value
}

check(CommandLine.arguments.count == 3, "mode + isolated database path required")
let mode = CommandLine.arguments[1]
let path = CommandLine.arguments[2]
check(muses_abi_version() == 1, "ABI version")
check(MemoryLayout<MusesCommand>.size == 40, "command C layout")
check(MemoryLayout<MusesSnapshot>.size == 56, "snapshot C layout")
check(MemoryLayout<MusesEvent>.size == 48, "event C layout")
check(MemoryLayout<MusesQueueEntry>.size == 24, "entry C layout")
if mode == "seed" {
    var bad: UInt64 = 99
    let bytes = Array(path.utf8)
    status(bytes.withUnsafeBufferPointer { muses_open(9, $0.baseAddress, $0.count, &bad) }, 3, "unsupported ABI")
    check(bad == 0, "invalid ABI output reset")
    let engine = openCore(path)
    check(openCore(path, expected: 9) == 0, "second engine refused")
    var subscription: UInt64 = 0
    status(muses_subscribe(engine, 0, &subscription), "subscribe")
    command(engine, 1, 0, occurrence: 101, media: 55)
    command(engine, 1, 0, occurrence: 102, media: 55)
    let initial = snapshot(engine)
    check(initial.1.queue_count == 2, "duplicate media has distinct occurrences")
    var entry = MusesQueueEntry()
    status(muses_snapshot_entry(initial.0, 1, &entry), "read second occurrence")
    check(entry.occurrence_id == 102 && entry.media_id == 55 && entry.ordinal == 1, "queue identity and order")
    command(engine, 1, 0, occurrence: 101, media: 99, expected: 5)
    let afterDuplicate = snapshot(engine)
    check(afterDuplicate.1.queue_count == 2 && afterDuplicate.1.sequence == initial.1.sequence, "failed transaction has no state/event side effect")
    status(muses_snapshot_release(afterDuplicate.0), "release duplicate check")
    let first = command(engine, 2, 0, occurrence: 101)
    let frozen = snapshot(engine)
    let second = command(engine, 2, first, occurrence: 102)
    command(engine, 3, first, occurrence: 101, expected: 4)
    command(engine, 3, second, occurrence: 102)
    check(read(frozen.0).occurrence_id == 101 && read(frozen.0).state == 1, "snapshot remains immutable")
    let cancelled = command(engine, 2, second, occurrence: 101)
    let afterCancel = command(engine, 4, cancelled)
    command(engine, 3, cancelled, occurrence: 101, expected: 4)
    let finalGeneration = command(engine, 2, afterCancel, occurrence: 102)
    command(engine, 3, finalGeneration, occurrence: 102)
    var value = event()
    var sequence: UInt64 = 0
    var kinds: [UInt32] = []
    while true {
        let result = muses_poll(subscription, &value)
        if result == 7 { break }
        status(result, "poll")
        check(value.sequence == sequence + 1, "strict event ordering")
        sequence = value.sequence
        kinds.append(value.kind)
    }
    check(kinds == [1, 1, 2, 2, 3, 2, 4, 2, 3], "successful commands only in event stream")
    var wrong = MusesSnapshot()
    wrong.abi_version = 1; wrong.struct_size = 8
    status(muses_snapshot_read(frozen.0, &wrong), 3, "short snapshot buffer version rejected")
    status(muses_snapshot_release(engine), 1, "handle kind checked")
    status(muses_unsubscribe(subscription), "unsubscribe")
    status(muses_poll(subscription, &value), 1, "poll after unsubscribe")
    status(muses_unsubscribe(subscription), 1, "double unsubscribe")
    var child: UInt64 = 0
    status(muses_subscribe(engine, sequence, &child), "dependent subscription")
    status(muses_release(engine), "engine release")
    status(muses_poll(child, &value), 1, "engine release invalidates subscription")
    check(read(initial.0).queue_count == 2 && read(frozen.0).generation == first, "snapshots outlive engine")
    status(muses_snapshot_release(initial.0), "release initial")
    status(muses_snapshot_release(frozen.0), "release frozen")
    status(muses_snapshot_release(frozen.0), 1, "double snapshot release")
    status(muses_release(engine), 1, "double engine release")
    print("PASS swift seed checks=\(checks) sequence=\(sequence) generation=\(finalGeneration) queue=2")
} else if mode == "verify" {
    let engine = openCore(path)
    let frozen = snapshot(engine)
    check(frozen.1.queue_count == 72 && frozen.1.state == 2, "C# changes persisted across process and language")
    var entry = MusesQueueEntry()
    status(muses_snapshot_entry(frozen.0, 71, &entry), "last persisted occurrence")
    check(entry.occurrence_id == 1069 && entry.ordinal == 71 && entry.media_id == 55, "full order persisted")
    status(muses_release(engine), "release")
    check(read(frozen.0).queue_count == 72, "post-release snapshot read")
    status(muses_snapshot_release(frozen.0), "release snapshot")
    print("PASS swift verify checks=\(checks) sequence=\(frozen.1.sequence) generation=\(frozen.1.generation)")
} else if mode == "pending" {
    let engine = openCore(path)
    let frozen = snapshot(engine)
    let generation = command(engine, 2, frozen.1.generation, occurrence: 101)
    status(muses_snapshot_release(frozen.0), "release snapshot")
    print("PENDING generation=\(generation) engine=\(engine)")
    fflush(stdout)
    // The orchestration process proves lock refusal, then SIGKILLs this exact
    // owned process. It never sends signals to a user application.
    while true { Thread.sleep(forTimeInterval: 0.1) }
} else { fatalError("unknown mode") }
