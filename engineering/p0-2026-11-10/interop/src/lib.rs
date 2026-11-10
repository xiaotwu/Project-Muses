//! An original, dependency-free interop experiment; not a production backend.
//! SQLite is supplied by the host OS. All calls serialize under one mutex.
use std::{
    collections::{HashMap, VecDeque},
    ffi::{c_char, c_int, c_void, CString},
    fs::{File, OpenOptions},
    mem::size_of,
    panic::{catch_unwind, AssertUnwindSafe},
    path::Path,
    ptr,
    sync::{Mutex, OnceLock},
};
#[cfg(unix)]
use std::os::unix::fs::MetadataExt;

const ABI: u32 = 1;
const INVALID_HANDLE: i32 = 1;
const ARGUMENT: i32 = 2;
const VERSION: i32 = 3;
const STALE: i32 = 4;
const STORAGE: i32 = 5;
const GAP: i32 = 6;
const EMPTY: i32 = 7;
const LIMIT: i32 = 8;
const BUSY: i32 = 9;
const INTERNAL: i32 = 10;
const MAX_EVENTS: usize = 64;
const MAX_SNAPSHOTS: usize = 64;
const MAX_SUBSCRIPTIONS: usize = 16;
const MAX_QUEUE: usize = 10_000;
type Result<T> = std::result::Result<T, i32>;

#[repr(C)]
#[derive(Clone, Copy, Default)]
pub struct Command {
    pub abi_version: u32, pub struct_size: u32, pub kind: u32, pub reserved: u32,
    pub expected_generation: u64, pub occurrence_id: u64, pub media_id: u64,
}
#[repr(C)]
#[derive(Clone, Copy, Default, Debug, PartialEq)]
pub struct Snapshot {
    pub abi_version: u32, pub struct_size: u32, pub state: u32, pub reserved: u32,
    pub sequence: u64, pub generation: u64, pub occurrence_id: u64,
    pub media_id: u64, pub queue_count: u64,
}
#[repr(C)]
#[derive(Clone, Copy, Default, Debug)]
pub struct Event {
    pub abi_version: u32, pub struct_size: u32, pub kind: u32, pub reserved: u32,
    pub sequence: u64, pub generation: u64, pub occurrence_id: u64, pub media_id: u64,
}
#[repr(C)]
#[derive(Clone, Copy, Default, Debug, PartialEq)]
pub struct QueueEntry { pub occurrence_id: u64, pub media_id: u64, pub ordinal: u64 }

#[link(name = "sqlite3")]
extern "C" {
    fn sqlite3_open_v2(path: *const c_char, db: *mut *mut c_void, flags: c_int, vfs: *const c_char) -> c_int;
    fn sqlite3_close(db: *mut c_void) -> c_int;
    fn sqlite3_exec(db: *mut c_void, sql: *const c_char, callback: Option<unsafe extern "C" fn(*mut c_void, c_int, *mut *mut c_char, *mut *mut c_char) -> c_int>, arg: *mut c_void, error: *mut *mut c_char) -> c_int;
    fn sqlite3_prepare_v2(db: *mut c_void, sql: *const c_char, bytes: c_int, stmt: *mut *mut c_void, tail: *mut *const c_char) -> c_int;
    fn sqlite3_step(stmt: *mut c_void) -> c_int;
    fn sqlite3_column_int64(stmt: *mut c_void, column: c_int) -> i64;
    fn sqlite3_finalize(stmt: *mut c_void) -> c_int;
    fn sqlite3_busy_timeout(db: *mut c_void, milliseconds: c_int) -> c_int;
}
struct Database { raw: *mut c_void, _owner: File }
// SQLite is opened FULLMUTEX and every access/drop is behind REGISTRY's mutex.
unsafe impl Send for Database {}
impl Drop for Database { fn drop(&mut self) { unsafe { sqlite3_close(self.raw); } } }
struct Statement(*mut c_void);
impl Drop for Statement { fn drop(&mut self) { unsafe { sqlite3_finalize(self.0); } } }
impl Database {
    fn open(path: &str) -> Result<Self> {
        let path = Path::new(path);
        if !path.is_absolute() || path.file_name().is_none() { return Err(ARGUMENT); }
        let parent = path.parent().ok_or(ARGUMENT)?.canonicalize().map_err(|_| STORAGE)?;
        let canonical = parent.join(path.file_name().ok_or(ARGUMENT)?);
        // A separate lease avoids interfering with SQLite's own database lock.
        // Refuse aliases in the macOS proof instead of treating a second path
        // to the same store as an independent engine. Private directory access
        // is still required; this prototype does not defend path-replacement races.
        if let Ok(meta) = canonical.symlink_metadata() {
            if meta.file_type().is_symlink() { return Err(ARGUMENT); }
            #[cfg(unix)]
            if meta.nlink() != 1 { return Err(ARGUMENT); }
        }
        let lease = format!("{}.p0-owner", canonical.to_str().ok_or(ARGUMENT)?);
        let owner = OpenOptions::new().read(true).write(true).create(true).truncate(false).open(lease).map_err(|_| STORAGE)?;
        owner.try_lock().map_err(|_| BUSY)?;
        let path = CString::new(canonical.to_str().ok_or(ARGUMENT)?).map_err(|_| ARGUMENT)?;
        let mut raw = ptr::null_mut();
        let status = unsafe { sqlite3_open_v2(path.as_ptr(), &mut raw, 0x2 | 0x4 | 0x10000, ptr::null()) };
        if status != 0 { if !raw.is_null() { unsafe { sqlite3_close(raw); } } return Err(STORAGE); }
        let db = Self { raw, _owner: owner };
        if unsafe { sqlite3_busy_timeout(raw, 1000) } != 0 { return Err(STORAGE); }
        let application = db.rows("PRAGMA application_id;", 1)?[0][0];
        let schema = db.rows("PRAGMA user_version;", 1)?[0][0];
        let tables = db.rows("SELECT count(*) FROM sqlite_master WHERE type='table';", 1)?[0][0];
        let empty = application == 0 && schema == 0 && tables == 0;
        if !empty && !(application == 0x4d505030 && schema == 1) { return Err(STORAGE); }
        db.exec("PRAGMA foreign_keys=ON; PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA temp_store=MEMORY; PRAGMA cache_size=-1024;")?;
        // This is a disposable P0 namespace, not a generation-7 migration.
        db.exec("BEGIN IMMEDIATE;
            CREATE TABLE IF NOT EXISTS p0_queue(occurrence INTEGER PRIMARY KEY CHECK(occurrence>0), media INTEGER NOT NULL CHECK(media>0), ordinal INTEGER NOT NULL UNIQUE);
            CREATE TABLE IF NOT EXISTS p0_state(id INTEGER PRIMARY KEY CHECK(id=1), generation INTEGER NOT NULL, sequence INTEGER NOT NULL, occurrence INTEGER REFERENCES p0_queue(occurrence), state INTEGER NOT NULL CHECK(state BETWEEN 0 AND 2));
            INSERT OR IGNORE INTO p0_state VALUES(1,0,0,NULL,0);
            PRAGMA application_id=1297109040; PRAGMA user_version=1; COMMIT;")?;
        Ok(db)
    }
    fn exec(&self, sql: &str) -> Result<()> {
        let sql = CString::new(sql).map_err(|_| INTERNAL)?;
        let status = unsafe { sqlite3_exec(self.raw, sql.as_ptr(), None, ptr::null_mut(), ptr::null_mut()) };
        if status == 0 { Ok(()) } else { Err(STORAGE) }
    }
    fn rows(&self, sql: &str, width: usize) -> Result<Vec<Vec<i64>>> {
        let sql = CString::new(sql).map_err(|_| INTERNAL)?;
        let mut stmt = ptr::null_mut();
        if unsafe { sqlite3_prepare_v2(self.raw, sql.as_ptr(), -1, &mut stmt, ptr::null_mut()) } != 0 { return Err(STORAGE); }
        let stmt = Statement(stmt);
        let mut rows = Vec::new();
        loop {
            match unsafe { sqlite3_step(stmt.0) } {
                100 => rows.push((0..width).map(|i| unsafe { sqlite3_column_int64(stmt.0, i as c_int) }).collect()),
                101 => return Ok(rows),
                _ => return Err(STORAGE),
            }
        }
    }
    fn commit_state(&self, snapshot: Snapshot, insert: Option<QueueEntry>) -> Result<()> {
        self.exec("BEGIN IMMEDIATE;")?;
        let result = (|| {
            // Only validated integer values enter SQL. No caller strings are SQL.
            if let Some(item) = insert { self.exec(&format!("INSERT INTO p0_queue VALUES({},{},{});", item.occurrence_id, item.media_id, item.ordinal))?; }
            let occurrence = if snapshot.occurrence_id == 0 { "NULL".to_owned() } else { snapshot.occurrence_id.to_string() };
            self.exec(&format!("UPDATE p0_state SET generation={}, sequence={}, occurrence={}, state={} WHERE id=1;", snapshot.generation, snapshot.sequence, occurrence, snapshot.state))?;
            self.exec("COMMIT;")
        })();
        if result.is_err() { let _ = self.exec("ROLLBACK;"); }
        result
    }
}

struct Engine { db: Database, value: Snapshot, queue: Vec<QueueEntry>, events: VecDeque<Event> }
impl Engine {
    fn open(path: &str) -> Result<Self> {
        let db = Database::open(path)?;
        let rows = db.rows("SELECT occurrence,media,ordinal FROM p0_queue ORDER BY ordinal;", 3)?;
        if rows.len() > MAX_QUEUE { return Err(LIMIT); }
        let queue: Vec<_> = rows.into_iter().map(|r| QueueEntry { occurrence_id: r[0] as u64, media_id: r[1] as u64, ordinal: r[2] as u64 }).collect();
        let rows = db.rows("SELECT generation,sequence,coalesce(occurrence,0),state FROM p0_state WHERE id=1;", 4)?;
        let row = rows.first().ok_or(STORAGE)?;
        if row.iter().any(|v| *v < 0) { return Err(STORAGE); }
        let occurrence_id = row[2] as u64;
        let media_id = queue.iter().find(|entry| entry.occurrence_id == occurrence_id).map_or(0, |entry| entry.media_id);
        if occurrence_id != 0 && media_id == 0 { return Err(STORAGE); }
        let value = Snapshot { abi_version: ABI, struct_size: size_of::<Snapshot>() as u32, state: row[3] as u32, sequence: row[1] as u64, generation: row[0] as u64, occurrence_id, media_id, queue_count: queue.len() as u64, reserved: 0 };
        let mut engine = Self { db, value, queue, events: VecDeque::with_capacity(MAX_EVENTS) };
        if engine.value.state == 1 {
            // No resolver job survives a process. Invalidate pending generations.
            let mut next = engine.value;
            next.generation = increment(next.generation)?;
            next.sequence = increment(next.sequence)?;
            next.state = 0;
            engine.db.commit_state(next, None)?;
            engine.value = next;
            engine.emit(5, next.occurrence_id, next.media_id);
        }
        Ok(engine)
    }
    fn emit(&mut self, kind: u32, occurrence_id: u64, media_id: u64) {
        if self.events.len() == MAX_EVENTS { self.events.pop_front(); }
        self.events.push_back(Event { abi_version: ABI, struct_size: size_of::<Event>() as u32, kind, reserved: 0, sequence: self.value.sequence, generation: self.value.generation, occurrence_id, media_id });
    }
    fn command(&mut self, c: Command) -> Result<u64> {
        if c.reserved != 0 { return Err(ARGUMENT); }
        if c.expected_generation != self.value.generation { return Err(STALE); }
        let mut next = self.value;
        let mut insertion = None;
        let (event_occurrence, event_media) = match c.kind {
            1 => {
                if c.occurrence_id == 0 || c.media_id == 0 || c.occurrence_id > i64::MAX as u64 || c.media_id > i64::MAX as u64 { return Err(ARGUMENT); }
                if self.queue.len() == MAX_QUEUE { return Err(LIMIT); }
                insertion = Some(QueueEntry { occurrence_id: c.occurrence_id, media_id: c.media_id, ordinal: self.queue.len() as u64 });
                next.queue_count += 1;
                (c.occurrence_id, c.media_id)
            }
            2 => {
                let item = self.queue.iter().find(|item| item.occurrence_id == c.occurrence_id).ok_or(ARGUMENT)?;
                next.generation = increment(next.generation)?;
                next.occurrence_id = item.occurrence_id;
                next.media_id = item.media_id;
                next.state = 1;
                (next.occurrence_id, next.media_id)
            }
            3 => {
                if self.value.state != 1 { return Err(STALE); }
                if c.occurrence_id != self.value.occurrence_id { return Err(STALE); }
                next.state = 2;
                (next.occurrence_id, next.media_id)
            }
            4 => {
                if self.value.state != 1 { return Err(STALE); }
                next.generation = increment(next.generation)?;
                next.state = 0;
                (next.occurrence_id, next.media_id)
            }
            _ => return Err(ARGUMENT),
        };
        next.sequence = increment(next.sequence)?;
        self.db.commit_state(next, insertion)?;
        // Only a successful COMMIT changes the published state/event sequence.
        if let Some(item) = insertion { self.queue.push(item); }
        self.value = next;
        self.emit(c.kind, event_occurrence, event_media);
        Ok(next.generation)
    }
}
fn increment(value: u64) -> Result<u64> { value.checked_add(1).filter(|n| *n <= i64::MAX as u64).ok_or(LIMIT) }
struct Frozen { value: Snapshot, queue: Vec<QueueEntry> }
struct Subscription { engine: u64, cursor: u64 }
#[derive(Default)]
struct Registry {
    next: u64, engines: HashMap<u64, Engine>, snapshots: HashMap<u64, Frozen>, subscriptions: HashMap<u64, Subscription>,
}
impl Registry { fn handle(&mut self) -> Result<u64> { self.next = increment(self.next)?; Ok(self.next) } }
static REGISTRY: OnceLock<Mutex<Registry>> = OnceLock::new();
fn boundary(action: impl FnOnce(&mut Registry) -> Result<()>) -> i32 {
    catch_unwind(AssertUnwindSafe(|| {
        let mut registry = REGISTRY.get_or_init(|| Mutex::new(Registry::default())).lock().map_err(|_| INTERNAL)?;
        action(&mut registry)
    })).map_or(INTERNAL, |result| result.err().unwrap_or(0))
}
fn version(abi: u32, bytes: u32, expected: usize) -> Result<()> { if abi == ABI && bytes as usize == expected { Ok(()) } else { Err(VERSION) } }

#[no_mangle] pub extern "C" fn muses_abi_version() -> u32 { ABI }

/// # Safety
/// Non-null caller pointers must reference readable/writable buffers of stated size.
#[no_mangle]
pub unsafe extern "C" fn muses_open(abi: u32, path: *const u8, length: usize, out: *mut u64) -> i32 {
    boundary(|r| {
        if out.is_null() { return Err(ARGUMENT); } *out = 0;
        if abi != ABI { return Err(VERSION); }
        if path.is_null() || length == 0 || length > 4096 { return Err(ARGUMENT); }
        if !r.engines.is_empty() { return Err(BUSY); }
        let path = std::str::from_utf8(std::slice::from_raw_parts(path, length)).map_err(|_| ARGUMENT)?;
        let engine = Engine::open(path)?;
        let handle = r.handle()?;
        r.engines.insert(handle, engine); *out = handle; Ok(())
    })
}
#[no_mangle]
pub extern "C" fn muses_release(handle: u64) -> i32 {
    boundary(|r| { r.engines.remove(&handle).ok_or(INVALID_HANDLE)?; r.subscriptions.retain(|_, s| s.engine != handle); Ok(()) })
}
/// # Safety
/// command and generation must point to their corresponding C struct/scalar.
#[no_mangle]
pub unsafe extern "C" fn muses_command(handle: u64, command: *const Command, generation: *mut u64) -> i32 {
    boundary(|r| {
        if command.is_null() || generation.is_null() { return Err(ARGUMENT); } *generation = 0;
        // Read only the fixed prefix until version/size validation succeeds.
        version((*command).abi_version, (*command).struct_size, size_of::<Command>())?;
        let engine = r.engines.get_mut(&handle).ok_or(INVALID_HANDLE)?;
        *generation = engine.command(*command)?; Ok(())
    })
}
/// # Safety
/// out must reference one writable uint64_t.
#[no_mangle]
pub unsafe extern "C" fn muses_snapshot_acquire(handle: u64, out: *mut u64) -> i32 {
    boundary(|r| {
        if out.is_null() { return Err(ARGUMENT); } *out = 0;
        let engine = r.engines.get(&handle).ok_or(INVALID_HANDLE)?;
        if r.snapshots.len() == MAX_SNAPSHOTS { return Err(LIMIT); }
        let frozen = Frozen { value: engine.value, queue: engine.queue.clone() };
        let token = r.handle()?; r.snapshots.insert(token, frozen); *out = token; Ok(())
    })
}
/// # Safety
/// out must reference a MusesSnapshot with its ABI/size prefix initialized.
#[no_mangle]
pub unsafe extern "C" fn muses_snapshot_read(handle: u64, out: *mut Snapshot) -> i32 {
    boundary(|r| {
        if out.is_null() { return Err(ARGUMENT); }
        version((*out).abi_version, (*out).struct_size, size_of::<Snapshot>())?;
        *out = r.snapshots.get(&handle).ok_or(INVALID_HANDLE)?.value; Ok(())
    })
}
/// # Safety
/// out must reference one writable MusesQueueEntry.
#[no_mangle]
pub unsafe extern "C" fn muses_snapshot_entry(handle: u64, index: u64, out: *mut QueueEntry) -> i32 {
    boundary(|r| {
        if out.is_null() { return Err(ARGUMENT); }
        let frozen = r.snapshots.get(&handle).ok_or(INVALID_HANDLE)?;
        *out = *frozen.queue.get(usize::try_from(index).map_err(|_| ARGUMENT)?).ok_or(ARGUMENT)?; Ok(())
    })
}
#[no_mangle]
pub extern "C" fn muses_snapshot_release(handle: u64) -> i32 { boundary(|r| { r.snapshots.remove(&handle).ok_or(INVALID_HANDLE)?; Ok(()) }) }
/// # Safety
/// out must reference one writable uint64_t.
#[no_mangle]
pub unsafe extern "C" fn muses_subscribe(handle: u64, cursor: u64, out: *mut u64) -> i32 {
    boundary(|r| {
        if out.is_null() { return Err(ARGUMENT); } *out = 0;
        let engine = r.engines.get(&handle).ok_or(INVALID_HANDLE)?;
        if cursor > engine.value.sequence { return Err(ARGUMENT); }
        if r.subscriptions.len() == MAX_SUBSCRIPTIONS { return Err(LIMIT); }
        let token = r.handle()?; r.subscriptions.insert(token, Subscription { engine: handle, cursor }); *out = token; Ok(())
    })
}
/// # Safety
/// out must reference a MusesEvent with its ABI/size prefix initialized.
#[no_mangle]
pub unsafe extern "C" fn muses_poll(handle: u64, out: *mut Event) -> i32 {
    boundary(|r| {
        if out.is_null() { return Err(ARGUMENT); }
        version((*out).abi_version, (*out).struct_size, size_of::<Event>())?;
        let sub = r.subscriptions.get_mut(&handle).ok_or(INVALID_HANDLE)?;
        let engine = r.engines.get(&sub.engine).ok_or(INVALID_HANDLE)?;
        if sub.cursor == engine.value.sequence { return Err(EMPTY); }
        let first = engine.events.front().ok_or(GAP)?;
        if sub.cursor < first.sequence - 1 { return Err(GAP); }
        let event = engine.events.iter().find(|e| e.sequence > sub.cursor).ok_or(GAP)?;
        *out = *event; sub.cursor = event.sequence; Ok(())
    })
}
#[no_mangle]
pub extern "C" fn muses_unsubscribe(handle: u64) -> i32 { boundary(|r| { r.subscriptions.remove(&handle).ok_or(INVALID_HANDLE)?; Ok(()) }) }

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn layout_contract() {
        assert_eq!(size_of::<Command>(), 40);
        assert_eq!(size_of::<Snapshot>(), 56);
        assert_eq!(size_of::<Event>(), 48);
        assert_eq!(size_of::<QueueEntry>(), 24);
        assert_eq!(std::mem::offset_of!(Snapshot, generation), 24);
        assert_eq!(std::mem::offset_of!(Event, sequence), 16);
        assert_eq!(increment(i64::MAX as u64), Err(LIMIT));
    }
}
