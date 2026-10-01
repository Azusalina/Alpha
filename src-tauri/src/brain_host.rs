//! Bounded, serialized JSON-lines transport. No executable/path comes from IPC.

use serde_json::{json, Value};
use std::{
    ffi::OsString,
    io::{self, Write},
    path::PathBuf,
    process::Stdio,
    sync::atomic::{AtomicBool, Ordering},
    time::Duration,
};
use tokio::{
    io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader},
    process::{Child, ChildStdin, ChildStdout, Command},
    sync::{mpsc, oneshot, watch, Mutex},
    time::{timeout, timeout_at, Instant},
};

const MAX_REQUEST_BYTES: usize = 6_004_096;
const MAX_RESPONSE_BYTES: usize = 16_000_000;
const QUEUE_SIZE: usize = 32;
const TRACE_PREFIX: &str = "[alpha.model] ";
const MAX_TRACE_LINE: usize = 4096;
const UNAVAILABLE: &str =
    "local backend unavailable; check the host Python and backend installation";
const UNCERTAIN: &str = "backend exchange failed or timed out; a write may have committed; inspect state before retrying";

#[derive(Clone)]
pub(crate) struct HostConfig {
    pub python: OsString,
    pub root: PathBuf,
    pub db: PathBuf,
    pub request_timeout: Duration,
}

struct Work {
    id: Value,
    wire: Vec<u8>,
    deadline: Instant,
    reply: oneshot::Sender<Value>,
}

pub(crate) struct BrainHost {
    requests: mpsc::Sender<Work>,
    stop: watch::Sender<bool>,
    closed: AtomicBool,
    done: Mutex<Option<oneshot::Receiver<()>>>,
    request_timeout: Duration,
}

pub(crate) fn error(id: Value, code: &str, message: &str) -> Value {
    json!({"schema_version": 1, "id": id, "ok": false, "error": {"code": code, "message": message}})
}

pub(crate) fn request_id(request: &Value) -> Value {
    match request.get("id").and_then(Value::as_str) {
        Some(id) if (1..=128).contains(&id.chars().count()) => json!(id),
        _ => Value::Null,
    }
}

struct RequestBuffer(Vec<u8>);

impl Write for RequestBuffer {
    fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
        if self.0.len().saturating_add(bytes.len()) > MAX_REQUEST_BYTES {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "request exceeds host size limit",
            ));
        }
        self.0.extend_from_slice(bytes);
        Ok(bytes.len())
    }
    fn flush(&mut self) -> io::Result<()> {
        Ok(())
    }
}

fn encode_request(request: &Value) -> Result<Vec<u8>, Value> {
    let id = request_id(request);
    let Some(object) = request.as_object() else {
        return Err(error(id, "INVALID_REQUEST", "request must be an object"));
    };
    if object.len() != 4
        || id.is_null()
        || !object.contains_key("schema_version")
        || !object.contains_key("method")
        || !object.contains_key("params")
    {
        return Err(error(id, "INVALID_REQUEST", "invalid request envelope"));
    }
    if request["schema_version"].as_u64() != Some(1) {
        return Err(error(id, "UNSUPPORTED_VERSION", "schema_version must be 1"));
    }
    if !request["method"].is_string() || !request["params"].is_object() {
        return Err(error(
            id,
            "INVALID_REQUEST",
            "method must be text and params an object",
        ));
    }
    let mut buffer = RequestBuffer(Vec::new());
    serde_json::to_writer(&mut buffer, request).map_err(|_| {
        error(
            id.clone(),
            "INVALID_REQUEST",
            "request cannot be serialized within the host size limit",
        )
    })?;
    let mut wire = buffer.0;
    wire.push(b'\n');
    Ok(wire)
}

fn validate_response(response: &Value, id: &Value) -> bool {
    let Some(object) = response.as_object() else {
        return false;
    };
    if object.len() != 4
        || response["schema_version"].as_u64() != Some(1)
        || response.get("id") != Some(id)
    {
        return false;
    }
    match response["ok"].as_bool() {
        Some(true) => object.contains_key("result"),
        Some(false) => response
            .get("error")
            .and_then(Value::as_object)
            .is_some_and(|e| {
                e.len() == 2
                    && e.get("code").is_some_and(Value::is_string)
                    && e.get("message").is_some_and(Value::is_string)
            }),
        None => false,
    }
}

struct Session {
    child: Child,
    stdin: Option<ChildStdin>,
    stdout: BufReader<ChildStdout>,
    stderr: tokio::task::JoinHandle<()>,
}

// Only bounded, known telemetry can reach the host terminal. Ordinary Python
// stderr, private diagnostics and trace-shaped text payloads are discarded.
fn terminal_trace(line: &[u8], db: &std::path::Path) -> Option<String> {
    if line.len() > MAX_TRACE_LINE {
        return None;
    }
    let text = std::str::from_utf8(line).ok()?.strip_prefix(TRACE_PREFIX)?;
    let record: Value = serde_json::from_str(text).ok()?;
    let object = record.as_object()?;
    let event = object.get("event")?.as_str()?;
    if !matches!(
        event,
        "ready"
            | "operation_received"
            | "operation_committed"
            | "operation_failed"
            | "data_saved"
            | "judgement"
            | "param_update"
            | "fit_committed"
            | "fit_skipped"
            | "source_deleted"
            | "model_reset"
    ) {
        return None;
    }
    object.get("time_ms")?.as_u64()?;
    if event != "ready" && !object.contains_key("operation") {
        return None;
    }
    for (key, value) in object {
        let valid = match key.as_str() {
            "event" => true,
            "time_ms" | "char_count" | "support_before" | "support_after" | "revision"
            | "model_epoch" | "previous_epoch" | "parameter_count" | "observed_terms" => {
                value.as_u64().is_some()
            }
            "operation" => value.as_str().is_some_and(|s| {
                matches!(
                    s,
                    "submit"
                        | "review"
                        | "review_version"
                        | "correction_reopen"
                        | "replay_reopen"
                        | "revoke"
                        | "input_edit"
                        | "input_delete"
                        | "correction_set"
                        | "reset_model"
                )
            }),
            "source_id" => value.as_str().is_some_and(|s| {
                s.len() == 32
                    && s.bytes()
                        .all(|c| c.is_ascii_digit() || (b'a'..=b'f').contains(&c))
            }),
            "partition" => value
                .as_str()
                .is_some_and(|s| matches!(s, "rational" | "emotional" | "crazy")),
            "status" => value
                .as_str()
                .is_some_and(|s| matches!(s, "pending" | "agreed" | "disagreed" | "revoked")),
            "immediate" | "exclamation" | "restored_fit" | "translator_preserved" => {
                value.is_boolean()
            }
            "confirm" => value.is_boolean() || value.is_null(),
            "reason" => value
                .as_str()
                .is_some_and(|s| matches!(s, "unchanged" | "not_dual_true")),
            "error_type" => value.as_str().is_some_and(|s| {
                matches!(
                    s,
                    "ValueError"
                        | "KeyError"
                        | "RuntimeError"
                        | "OSError"
                        | "OperationalError"
                        | "IntegrityError"
                        | "DatabaseError"
                        | "Exception"
                )
            }),
            "parameter" => value.as_str().is_some_and(|s| {
                matches!(
                    s,
                    "value.autonomy"
                        | "value.fairness"
                        | "value.care"
                        | "value.truth"
                        | "value.security"
                        | "value.growth"
                        | "value.achievement"
                        | "value.connection"
                        | "affect.disappointment"
                        | "affect.sadness"
                        | "affect.happiness"
                        | "affect.anger"
                        | "expression.less_initiative"
                )
            }),
            "before" | "after" | "delta" => value
                .as_f64()
                .is_some_and(|n| n.is_finite() && (-2.0..=2.0).contains(&n)),
            "db_path" => matches!(event, "ready" | "data_saved") && value.as_str() == db.to_str(),
            _ => false,
        };
        if !valid {
            return None;
        }
    }
    Some(format!(
        "{TRACE_PREFIX}{}",
        serde_json::to_string(&record).ok()?
    ))
}

#[derive(Default)]
struct TraceLines {
    line: Vec<u8>,
    oversized: bool,
}

impl TraceLines {
    fn feed(&mut self, bytes: &[u8], db: &std::path::Path, mut emit: impl FnMut(String)) {
        for &byte in bytes {
            if byte == b'\n' {
                if !self.oversized {
                    if let Some(line) = terminal_trace(&self.line, db) {
                        emit(line);
                    }
                }
                self.line.clear();
                self.oversized = false;
            } else if !self.oversized {
                if self.line.len() < MAX_TRACE_LINE {
                    self.line.push(byte);
                } else {
                    self.line.clear();
                    self.oversized = true;
                }
            }
        }
    }
}

impl Session {
    fn start(config: &HostConfig) -> Result<Self, &'static str> {
        if !config.root.is_absolute()
            || !config.db.is_absolute()
            || !config.root.join("core/api.py").is_file()
        {
            return Err(UNAVAILABLE);
        }
        let mut child = Command::new(&config.python)
            .args(["-E", "-s", "-u", "-m", "core.api", "--db"])
            .arg(&config.db)
            .current_dir(&config.root)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true)
            .spawn()
            .map_err(|_| UNAVAILABLE)?;
        let stdin = child.stdin.take().ok_or(UNAVAILABLE)?;
        let stdout = child.stdout.take().ok_or(UNAVAILABLE)?;
        let mut stderr = child.stderr.take().ok_or(UNAVAILABLE)?;
        // Drain bounded chunks. Forward only validated telemetry to the host
        // terminal, never ordinary stderr or any content to the webview.
        let trace_db = config.db.clone();
        let stderr = tokio::spawn(async move {
            let mut buffer = [0u8; 4096];
            let mut lines = TraceLines::default();
            while let Ok(n) = stderr.read(&mut buffer).await {
                if n == 0 {
                    break;
                }
                lines.feed(&buffer[..n], &trace_db, |line| {
                    // Ignore terminal failures: logging cannot panic this drain.
                    let _ = writeln!(io::stderr().lock(), "{line}");
                });
            }
        });
        Ok(Self {
            child,
            stdin: Some(stdin),
            stdout: BufReader::new(stdout),
            stderr,
        })
    }

    async fn exchange(&mut self, work: &Work) -> Result<Value, &'static str> {
        let stdin = self.stdin.as_mut().ok_or(UNCERTAIN)?;
        stdin.write_all(&work.wire).await.map_err(|_| UNCERTAIN)?;
        stdin.flush().await.map_err(|_| UNCERTAIN)?;
        let mut line = Vec::new();
        (&mut self.stdout)
            .take((MAX_RESPONSE_BYTES + 1) as u64)
            .read_until(b'\n', &mut line)
            .await
            .map_err(|_| UNCERTAIN)?;
        if line.len() > MAX_RESPONSE_BYTES || line.last() != Some(&b'\n') {
            return Err(UNCERTAIN);
        }
        let response: Value = serde_json::from_slice(&line).map_err(|_| UNCERTAIN)?;
        if !validate_response(&response, &work.id) {
            return Err(UNCERTAIN);
        }
        Ok(response)
    }

    async fn stop(&mut self, graceful: bool) {
        self.stdin.take(); // EOF lets an idle Python process exit normally.
        if !graceful {
            let _ = self.child.start_kill();
        }
        if timeout(Duration::from_secs(1), self.child.wait())
            .await
            .is_err()
        {
            let _ = self.child.start_kill();
            let _ = timeout(Duration::from_secs(1), self.child.wait()).await;
        }
        self.stderr.abort();
    }
}

impl Drop for Session {
    fn drop(&mut self) {
        self.stderr.abort();
    } // Child also has kill_on_drop.
}

async fn worker(
    config: HostConfig,
    mut requests: mpsc::Receiver<Work>,
    mut stop: watch::Receiver<bool>,
    done: oneshot::Sender<()>,
) {
    let mut session: Option<Session> = None;
    loop {
        let work = tokio::select! {
            biased;
            _ = stop.changed() => break,
            work = requests.recv() => match work { Some(work) => work, None => break },
        };
        if work.reply.is_closed() {
            continue;
        }
        if Instant::now() >= work.deadline {
            let _ = work.reply.send(error(
                work.id,
                "MODEL_UNAVAILABLE",
                "request expired in host queue; it was not sent",
            ));
            continue;
        }
        if let Some(active) = &mut session {
            if !matches!(active.child.try_wait(), Ok(None)) {
                active.stop(false).await;
                session = None;
            }
        }
        if session.is_none() {
            match Session::start(&config) {
                Ok(started) => session = Some(started),
                Err(message) => {
                    let _ = work
                        .reply
                        .send(error(work.id, "MODEL_UNAVAILABLE", message));
                    continue;
                }
            }
        }
        let active = session.as_mut().expect("session started");
        let result = tokio::select! {
            biased;
            _ = stop.changed() => Err(UNCERTAIN),
            result = timeout_at(work.deadline, active.exchange(&work)) => result.unwrap_or(Err(UNCERTAIN)),
        };
        let response = match result {
            Ok(response) => response,
            Err(message) => {
                active.stop(false).await;
                session = None;
                error(work.id.clone(), "MODEL_UNAVAILABLE", message)
            }
        };
        let _ = work.reply.send(response);
        if *stop.borrow() {
            break;
        }
    }
    requests.close();
    while let Ok(work) = requests.try_recv() {
        let _ = work.reply.send(error(
            work.id,
            "MODEL_UNAVAILABLE",
            "backend host is shutting down",
        ));
    }
    if let Some(mut active) = session {
        active.stop(true).await;
    }
    let _ = done.send(());
}

impl BrainHost {
    pub fn new(config: HostConfig) -> Self {
        let (requests, receiver) = mpsc::channel(QUEUE_SIZE);
        let (stop, stopping) = watch::channel(false);
        let (done_tx, done_rx) = oneshot::channel();
        let request_timeout = config.request_timeout;
        tauri::async_runtime::spawn(worker(config, receiver, stopping, done_tx));
        Self {
            requests,
            stop,
            closed: AtomicBool::new(false),
            done: Mutex::new(Some(done_rx)),
            request_timeout,
        }
    }

    pub async fn call(&self, request: Value) -> Value {
        let id = request_id(&request);
        let wire = match encode_request(&request) {
            Ok(wire) => wire,
            Err(response) => return response,
        };
        if self.closed.load(Ordering::Acquire) {
            return error(id, "MODEL_UNAVAILABLE", "backend host is closed");
        }
        let deadline = Instant::now() + self.request_timeout;
        let (reply, receive) = oneshot::channel();
        let work = Work {
            id: id.clone(),
            wire,
            deadline,
            reply,
        };
        if self.requests.try_send(work).is_err() {
            return error(
                id,
                "MODEL_UNAVAILABLE",
                "host queue full or unavailable; request was not sent",
            );
        }
        match timeout_at(deadline, receive).await {
            Ok(Ok(response)) => response,
            _ => error(id, "MODEL_UNAVAILABLE", UNCERTAIN),
        }
    }

    pub async fn shutdown(&self) {
        self.closed.store(true, Ordering::Release);
        let _ = self.stop.send(true);
        if let Some(done) = self.done.lock().await.take() {
            let _ = timeout(Duration::from_secs(3), done).await;
        }
    }
}

impl Drop for BrainHost {
    fn drop(&mut self) {
        let _ = self.stop.send(true);
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;
    use tempfile::TempDir;

    #[test]
    fn trace_filter_is_bounded_and_never_relays_private_stderr() {
        let db = PathBuf::from("/tmp/model.sqlite3");
        let line = format!(
            "{TRACE_PREFIX}{}",
            json!({"event":"judgement", "time_ms":1,
            "operation":"review", "immediate":true, "confirm":true, "status":"agreed"})
        );
        assert!(terminal_trace(line.as_bytes(), &db).is_some());
        for operation in ["review_version", "correction_reopen", "replay_reopen"] {
            let mut record = json!({"event":"operation_committed", "time_ms":1,
                "operation":operation});
            let allowed = format!("{TRACE_PREFIX}{record}");
            assert!(terminal_trace(allowed.as_bytes(), &db).is_some());
            for field in ["password", "payload", "corrections", "text"] {
                record[field] = json!("private fixture");
                let denied = format!("{TRACE_PREFIX}{record}");
                assert!(terminal_trace(denied.as_bytes(), &db).is_none());
                record.as_object_mut().unwrap().remove(field);
            }
        }
        let baseline: Value =
            serde_json::from_str(include_str!("../../back-end-core/model/baseline.json")).unwrap();
        for parameter in baseline["parameters"].as_object().unwrap().keys() {
            let parameter_line = format!(
                "{TRACE_PREFIX}{}",
                json!({
                    "event":"param_update", "time_ms":1, "operation":"review",
                    "parameter":parameter, "before":0.0, "after":0.2, "delta":0.2,
                    "support_before":0, "support_after":1, "model_epoch":0, "revision":1
                })
            );
            assert!(
                terminal_trace(parameter_line.as_bytes(), &db).is_some(),
                "{parameter}"
            );
        }
        let saved = format!(
            "{TRACE_PREFIX}{}",
            json!({"event":"data_saved",
            "time_ms":1, "operation":"submit", "db_path":db.to_str().unwrap()})
        );
        assert!(terminal_trace(saved.as_bytes(), &db).is_some());
        for bad in [
            "private diary text".to_owned(),
            format!(
                "{TRACE_PREFIX}{}",
                json!({"event":"param_update", "time_ms":1,
                "operation":"review", "parameter":"private diary text"})
            ),
            format!(
                "{TRACE_PREFIX}{}",
                json!({"event":"operation_failed", "time_ms":1,
                "operation":"review", "error_type":"RuntimeError", "message":"private diary text"})
            ),
            format!(
                "{TRACE_PREFIX}{}",
                json!({"event":"ready", "time_ms":1, "db_path":"private diary text"})
            ),
        ] {
            assert!(terminal_trace(bad.as_bytes(), &db).is_none());
        }
        let mut framing = TraceLines::default();
        let mut accepted = vec![];
        framing.feed(&vec![b'x'; MAX_TRACE_LINE + 100], &db, |s| accepted.push(s));
        framing.feed(line.as_bytes(), &db, |s| accepted.push(s));
        framing.feed(b"\n", &db, |s| accepted.push(s));
        assert!(accepted.is_empty());
        for chunk in format!("{line}\n").as_bytes().chunks(3) {
            framing.feed(chunk, &db, |s| accepted.push(s));
        }
        assert_eq!(accepted.len(), 1);
        assert!(framing.line.len() <= MAX_TRACE_LINE);
    }

    fn request(id: &str, method: &str, params: Value) -> Value {
        json!({"schema_version":1,"id":id,"method":method,"params":params})
    }

    fn real_config(temp: &TempDir) -> HostConfig {
        HostConfig {
            python: "python3".into(),
            root: PathBuf::from(env!("CARGO_MANIFEST_DIR"))
                .parent()
                .unwrap()
                .join("back-end-core"),
            db: temp.path().join("brain.sqlite3"),
            request_timeout: Duration::from_secs(10),
        }
    }

    fn fake_config(temp: &TempDir, body: &str) -> HostConfig {
        let root = temp.path().join("backend");
        std::fs::create_dir_all(root.join("core")).unwrap();
        std::fs::write(root.join("core/__init__.py"), "").unwrap();
        std::fs::write(root.join("core/api.py"), body).unwrap();
        HostConfig {
            root,
            ..real_config(temp)
        }
    }

    const ECHO: &str = r#"
import json, sys, os, time
for line in sys.stdin:
    req = json.loads(line)
    if req['method'] == 'slow': time.sleep(1)
    if req['method'] == 'stderr':
        sys.stderr.write('private diary text' * 100000)
        sys.stderr.flush()
    print(json.dumps({'schema_version':1,'id':req['id'],'ok':True,'result':{'pid':os.getpid()}}), flush=True)
"#;

    #[test]
    fn envelope_checks_and_bounded_json_lines() {
        let good = request("emoji-😀", "health", json!({}));
        let wire = encode_request(&good).unwrap();
        assert_eq!(wire.last(), Some(&b'\n'));
        assert_eq!(serde_json::from_slice::<Value>(&wire).unwrap(), good);
        for bad in [
            json!({}),
            request("", "health", json!({})),
            request("id", "health", json!([])),
        ] {
            assert!(encode_request(&bad).is_err());
        }
        let mut oversized = request(
            "large",
            "submit",
            json!({"text":"x".repeat(MAX_REQUEST_BYTES)}),
        );
        assert!(encode_request(&oversized).is_err());
        oversized["schema_version"] = json!(2);
        assert_eq!(
            encode_request(&oversized).unwrap_err()["error"]["code"],
            "UNSUPPORTED_VERSION"
        );
    }

    #[test]
    fn response_id_version_and_shape_must_match() {
        let good = json!({"schema_version":1,"id":"id","ok":true,"result":{}});
        assert!(validate_response(&good, &json!("id")));
        assert!(!validate_response(&good, &json!("other")));
        for bad in [
            json!({"schema_version":2,"id":"id","ok":true,"result":{}}),
            json!({"schema_version":1,"id":"id","ok":true,"error":{}}),
            json!({"schema_version":1,"id":"id","ok":false,"error":{"code":1,"message":"bad"}}),
        ] {
            assert!(!validate_response(&bad, &json!("id")));
        }
    }

    #[tokio::test]
    async fn real_python_workflow_persists_across_host_restart() {
        let temp = TempDir::new().unwrap();
        let config = real_config(&temp);
        let host = BrainHost::new(config.clone());
        let health = host.call(request("health", "health", json!({}))).await;
        assert_eq!(health["ok"], true, "{health}");
        assert_eq!(health["result"]["features"]["two_judgements"], true);
        let submitted = host
            .call(request(
                "submit",
                "submit",
                json!({"text":"😀我重视公平。\r\n", "partition":"rational"}),
            ))
            .await;
        assert_eq!(submitted["ok"], true, "{submitted}");
        let source = submitted["result"]["source_id"].as_str().unwrap();
        let preview = host
            .call(request("preview", "preview", json!({"source_id":source})))
            .await;
        assert_eq!(preview["result"]["hypothetical"], true, "{preview}");
        let rejected = host
            .call(request(
                "bad-review",
                "review",
                json!({"source_id":source,"agree":"true"}),
            ))
            .await;
        assert_eq!(rejected["error"]["code"], "INVALID_ARGUMENT");
        let review = host
            .call(request(
                "review",
                "review",
                json!({"source_id":source,"agree":true}),
            ))
            .await;
        assert_eq!(review["result"]["status"], "agreed", "{review}");
        assert_eq!(review["result"]["confirm"], true);
        let automatic = host
            .call(request("automatic", "submit", json!({
                "text":"我重视自由。", "partition":"emotional", "immediate":false, "exclamation":true
            })))
            .await;
        assert_eq!(automatic["result"]["immediate"], true, "{automatic}");
        assert_eq!(automatic["result"]["confirm"], true);
        assert_eq!(automatic["result"]["confirmed_by"], "exclamation");
        assert!(!automatic["result"]["effects"]
            .as_array()
            .unwrap()
            .is_empty());
        let denied = host
            .call(request(
                "deny",
                "review",
                json!({"source_id":source,"agree":false}),
            ))
            .await;
        assert_eq!(denied["result"]["reason"], "confirm_false", "{denied}");
        let restored = host
            .call(request(
                "restore",
                "review",
                json!({"source_id":source,"agree":true}),
            ))
            .await;
        assert_eq!(restored["result"]["restored_fit"], true, "{restored}");
        let page = host
            .call(request("page", "input_page", json!({"limit":1})))
            .await;
        assert_eq!(page["result"]["total"], 2, "{page}");
        assert_eq!(page["result"]["items"].as_array().unwrap().len(), 1);
        assert!(page["result"]["items"][0]["excerpt"].is_string());
        assert!(page["result"]["items"][0].get("text").is_none());
        let cursor = page["result"]["next_cursor"].as_str().unwrap();
        let second = host
            .call(request(
                "page-2",
                "input_page",
                json!({"limit":1,"cursor":cursor}),
            ))
            .await;
        assert_eq!(second["result"]["total"], 2, "{second}");
        assert_eq!(second["result"]["next_cursor"], Value::Null);
        let changed = host
            .call(request(
                "new-source",
                "submit",
                json!({"text":"一条新记录。","partition":"crazy"}),
            ))
            .await;
        assert_eq!(changed["ok"], true, "{changed}");
        let stale = host
            .call(request(
                "stale-page",
                "input_page",
                json!({"cursor":cursor}),
            ))
            .await;
        assert_eq!(stale["error"]["code"], "STALE_CURSOR", "{stale}");
        host.shutdown().await;
        assert_eq!(
            host.call(request("closed", "health", json!({}))).await["error"]["code"],
            "MODEL_UNAVAILABLE"
        );
        let restarted = BrainHost::new(config);
        let fetched = restarted
            .call(request("fetch", "input_get", json!({"source_id":source})))
            .await;
        assert_eq!(fetched["result"]["text"], "😀我重视公平。\r\n", "{fetched}");
        assert_eq!(fetched["result"]["status"], "agreed");
        restarted.shutdown().await;
    }

    #[tokio::test]
    async fn parallel_requests_are_serialized_and_stderr_is_drained() {
        let temp = TempDir::new().unwrap();
        let host = BrainHost::new(fake_config(&temp, ECHO));
        let (a, b, c) = tokio::join!(
            host.call(request("a", "stderr", json!({}))),
            host.call(request("b", "echo", json!({}))),
            host.call(request("c", "echo", json!({})))
        );
        for (response, id) in [(&a, "a"), (&b, "b"), (&c, "c")] {
            assert_eq!(response["ok"], true, "{response}");
            assert_eq!(response["id"], id);
            assert!(!response.to_string().contains("private diary text"));
        }
        assert_eq!(a["result"]["pid"], b["result"]["pid"]);
        assert_eq!(b["result"]["pid"], c["result"]["pid"]);
        host.shutdown().await;
    }

    #[tokio::test]
    async fn timeout_does_not_retry_and_next_explicit_call_uses_a_new_process() {
        let temp = TempDir::new().unwrap();
        let mut config = fake_config(&temp, &ECHO.replace("time.sleep(1)", "time.sleep(3)"));
        config.request_timeout = Duration::from_secs(1);
        let host = BrainHost::new(config);
        let first = host.call(request("first", "echo", json!({}))).await;
        assert_eq!(first["ok"], true, "{first}");
        let timed = host.call(request("timeout", "slow", json!({}))).await;
        assert_eq!(timed["error"]["code"], "MODEL_UNAVAILABLE");
        assert!(timed["error"]["message"]
            .as_str()
            .unwrap()
            .contains("may have committed"));
        let next = host.call(request("next", "echo", json!({}))).await;
        assert_eq!(next["ok"], true, "{next}");
        assert_ne!(first["result"]["pid"], next["result"]["pid"]);
        host.shutdown().await;
    }

    #[tokio::test]
    async fn malformed_or_exited_backend_returns_masked_unavailable() {
        for script in ["print('not JSON', flush=True)",
            "raise SystemExit(1)",
            "print('{\"schema_version\":1,\"id\":\"wrong\",\"ok\":true,\"result\":{}}', flush=True)"] {
            let temp = TempDir::new().unwrap();
            let host = BrainHost::new(fake_config(&temp, script));
            let response = host.call(request("test", "echo", json!({}))).await;
            assert_eq!(response["error"]["code"], "MODEL_UNAVAILABLE", "{response}");
            assert_eq!(response["id"], "test");
            host.shutdown().await;
        }
    }

    #[tokio::test]
    async fn oversized_response_is_rejected_and_child_is_reset() {
        let temp = TempDir::new().unwrap();
        let script = format!("print('x'*{}, flush=True)", MAX_RESPONSE_BYTES + 100);
        let host = BrainHost::new(fake_config(&temp, &script));
        let response = host.call(request("huge", "health", json!({}))).await;
        assert_eq!(response["error"]["code"], "MODEL_UNAVAILABLE");
        assert!(response.to_string().len() < 1000);
        host.shutdown().await;
    }

    #[tokio::test]
    async fn expired_queue_entry_is_never_sent() {
        let temp = TempDir::new().unwrap();
        let config = fake_config(&temp, &ECHO.replace("time.sleep(1)", "time.sleep(0.2)"));
        let (send, receive) = mpsc::channel(2);
        let (stop, stopping) = watch::channel(false);
        let (done, completed) = oneshot::channel();
        tauri::async_runtime::spawn(worker(config, receive, stopping, done));
        let (a, a_response) = oneshot::channel();
        let (b, b_response) = oneshot::channel();
        let make_work = |id: &str, method: &str, millis, reply| Work {
            id: json!(id),
            wire: encode_request(&request(id, method, json!({}))).unwrap(),
            deadline: Instant::now() + Duration::from_millis(millis),
            reply,
        };
        send.send(make_work("active", "slow", 5000, a))
            .await
            .unwrap();
        send.send(make_work("expired", "echo", 10, b))
            .await
            .unwrap();
        assert_eq!(a_response.await.unwrap()["ok"], true);
        let expired = b_response.await.unwrap();
        assert!(expired["error"]["message"]
            .as_str()
            .unwrap()
            .contains("was not sent"));
        stop.send(true).unwrap();
        completed.await.unwrap();
    }

    #[tokio::test]
    async fn full_queue_rejects_immediately_without_retaining_an_extra_work_item() {
        let (requests, _receiver) = mpsc::channel(1);
        let (stop, _stopping) = watch::channel(false);
        let host = BrainHost {
            requests,
            stop,
            closed: AtomicBool::new(false),
            done: Mutex::new(None),
            request_timeout: Duration::from_secs(2),
        };
        let first = host.call(request("queued", "health", json!({})));
        tokio::pin!(first);
        tokio::select! {
            _ = &mut first => panic!("first request unexpectedly completed without a worker"),
            _ = tokio::time::sleep(Duration::from_millis(10)) => {},
        }
        let rejected = host.call(request("full", "health", json!({}))).await;
        assert!(rejected["error"]["message"]
            .as_str()
            .unwrap()
            .contains("was not sent"));
        assert_eq!(host.requests.capacity(), 0);
        host.shutdown().await;
    }

    #[tokio::test]
    async fn shutdown_interrupts_an_active_exchange_and_rejects_new_calls() {
        let temp = TempDir::new().unwrap();
        let host = Arc::new(BrainHost::new(fake_config(&temp, ECHO)));
        assert_eq!(
            host.call(request("warmup", "echo", json!({}))).await["ok"],
            true
        );
        let h = host.clone();
        let pending =
            tokio::spawn(async move { h.call(request("active", "slow", json!({}))).await });
        tokio::time::sleep(Duration::from_millis(50)).await;
        timeout(Duration::from_secs(2), host.shutdown())
            .await
            .unwrap();
        assert_eq!(pending.await.unwrap()["error"]["code"], "MODEL_UNAVAILABLE");
        assert_eq!(
            host.call(request("closed", "echo", json!({}))).await["error"]["code"],
            "MODEL_UNAVAILABLE"
        );
    }

    #[tokio::test]
    async fn caller_cancellation_cannot_misalign_the_next_response() {
        let temp = TempDir::new().unwrap();
        let host = Arc::new(BrainHost::new(fake_config(&temp, ECHO)));
        let h = host.clone();
        let task =
            tokio::spawn(async move { h.call(request("cancelled", "slow", json!({}))).await });
        tokio::time::sleep(Duration::from_millis(100)).await;
        task.abort();
        let next = host.call(request("next", "echo", json!({}))).await;
        assert_eq!(next["ok"], true, "{next}");
        assert_eq!(next["id"], "next");
        host.shutdown().await;
    }

    #[tokio::test]
    async fn shutdown_reaps_the_owned_process_and_missing_python_does_not_create_db() {
        let temp = TempDir::new().unwrap();
        let config = fake_config(&temp, ECHO);
        let mut session = Session::start(&config).unwrap();
        session.stop(true).await;
        assert!(session.child.try_wait().unwrap().is_some());
        let bad = HostConfig {
            python: temp.path().join("nonexistent-python").into_os_string(),
            ..config
        };
        let host = BrainHost::new(bad.clone());
        let response = host.call(request("test", "health", json!({}))).await;
        assert_eq!(response["error"]["code"], "MODEL_UNAVAILABLE");
        assert!(!bad.db.exists());
        host.shutdown().await;
    }
}
