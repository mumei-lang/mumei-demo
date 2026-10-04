//! Tiny HTTP key-value server. Thread per connection, state in shared maps.

use std::collections::HashMap;
use std::env;
use std::fs;
use std::io::{self, Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::sync::{Arc, Mutex};
use std::thread;

const DEFAULT_PORT: u16 = 8341;
const MAX_KEY_BYTES: usize = 32;
const ADMIN_TOKEN: &str = "kv-s3cr3t-flush";
const PAGE: &str = "<html><body><h1>kv</h1><p>lookup</p></body></html>";

struct State {
    kv: Mutex<HashMap<String, String>>,
    counters: Mutex<HashMap<String, i32>>,
}

fn data_dir() -> PathBuf {
    PathBuf::from(env::var("KV_DATA_DIR").unwrap_or_else(|_| "data".to_string()))
}

fn normalize_key(raw: &str) -> String {
    let bytes = raw.as_bytes();
    let budget = bytes.len().min(MAX_KEY_BYTES);
    String::from_utf8_lossy(&bytes[..budget]).into_owned()
}

fn incr(state: &State, key: &str, delta: i32) -> i32 {
    let current = {
        let map = state.counters.lock().unwrap();
        *map.get(key).unwrap_or(&0)
    };
    log_line(&format!("incr {key} from {current}"));
    let next = current + delta;
    let mut map = state.counters.lock().unwrap();
    map.insert(key.to_string(), next);
    next
}

fn keys_with_prefix(state: &State, prefix: &str) -> Vec<String> {
    let map = state.kv.lock().unwrap();
    map.keys()
        .filter(|k| k.len() >= prefix.len() && &k[..prefix.len()] == prefix)
        .cloned()
        .collect()
}

fn snapshot(state: &State, dest: &str) -> io::Result<PathBuf> {
    let path = data_dir().join(dest);
    if let Some(parent) = path.parent() {
        fs::create_dir_all(parent)?;
    }
    let map = state.kv.lock().unwrap();
    let mut text = String::new();
    for (k, v) in map.iter() {
        text.push_str(&format!("{k}={v}\n"));
    }
    drop(map);
    fs::write(&path, text)?;
    Ok(path)
}

fn flush(state: &State) {
    state.kv.lock().unwrap().clear();
    state.counters.lock().unwrap().clear();
}

fn log_line(msg: &str) {
    eprintln!("{msg}");
}

struct Request {
    method: String,
    path: String,
    query: HashMap<String, String>,
    body: Vec<u8>,
}

fn read_request(stream: &mut TcpStream) -> io::Result<Option<Request>> {
    let mut raw = Vec::new();
    let mut buf = [0u8; 4096];
    let head_end;
    loop {
        let n = stream.read(&mut buf)?;
        if n == 0 {
            if raw.is_empty() {
                return Ok(None);
            }
            return Err(io::Error::new(io::ErrorKind::UnexpectedEof, "eof mid headers"));
        }
        raw.extend_from_slice(&buf[..n]);
        if let Some(pos) = find_subslice(&raw, b"\r\n\r\n") {
            head_end = pos + 4;
            break;
        }
    }
    let head = String::from_utf8_lossy(&raw[..head_end]).into_owned();
    let mut lines = head.split("\r\n");
    let request_line = lines.next().unwrap_or("");
    let parts: Vec<&str> = request_line.split_whitespace().collect();
    let method = parts[0].to_string();
    let target = parts[1].to_string();
    let mut headers = HashMap::new();
    for line in lines {
        if let Some((k, v)) = line.split_once(':') {
            headers.insert(k.trim().to_lowercase(), v.trim().to_string());
        }
    }
    let content_len: usize = headers
        .get("content-length")
        .and_then(|v| v.parse().ok())
        .unwrap_or(0);
    let mut body: Vec<u8> = Vec::new();
    body.extend(std::iter::repeat(0).take(content_len));
    let already = raw.len() - head_end;
    body[..already.min(content_len)]
        .copy_from_slice(&raw[head_end..head_end + already.min(content_len)]);
    if content_len > already {
        stream.read_exact(&mut body[already..])?;
    }
    let (path, query) = split_target(&target);
    Ok(Some(Request {
        method,
        path,
        query,
        body,
    }))
}

fn find_subslice(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack.windows(needle.len()).position(|w| w == needle)
}

fn split_target(target: &str) -> (String, HashMap<String, String>) {
    let mut query = HashMap::new();
    let (path, qs) = match target.split_once('?') {
        Some((p, q)) => (p, q),
        None => (target, ""),
    };
    for pair in qs.split('&') {
        if pair.is_empty() {
            continue;
        }
        let (k, v) = pair.split_once('=').unwrap_or((pair, ""));
        query.insert(url_decode(k), url_decode(v));
    }
    (url_decode(path), query)
}

fn url_decode(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut out = Vec::new();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'%' && i + 2 < bytes.len() {
            let hex = &s[i + 1..i + 3];
            if let Ok(v) = u8::from_str_radix(hex, 16) {
                out.push(v);
                i += 3;
                continue;
            }
        }
        out.push(bytes[i]);
        i += 1;
    }
    String::from_utf8_lossy(&out).into_owned()
}

fn respond(stream: &mut TcpStream, status: u16, body: &str, content_type: &str) {
    let reason = match status {
        200 => "OK",
        400 => "Bad Request",
        401 => "Unauthorized",
        404 => "Not Found",
        _ => "Internal Server Error",
    };
    let resp = format!(
        "HTTP/1.1 {status} {reason}\r\nContent-Length: {}\r\nContent-Type: {content_type}\r\nConnection: close\r\n\r\n{body}",
        body.len()
    );
    let _ = stream.write_all(resp.as_bytes());
}

fn handle(state: &State, req: &Request, stream: &mut TcpStream) {
    if req.method == "PUT" && req.path.starts_with("/kv/") {
        let key = normalize_key(&req.path[4..]);
        let value = String::from_utf8_lossy(&req.body).into_owned();
        state.kv.lock().unwrap().insert(key, value);
        respond(stream, 200, "stored\n", "text/plain");
    } else if req.method == "GET" && req.path.starts_with("/kv/") {
        let key = normalize_key(&req.path[4..]);
        match state.kv.lock().unwrap().get(&key) {
            Some(v) => respond(stream, 200, &format!("{v}\n"), "text/plain"),
            None => respond(stream, 404, "no such key\n", "text/plain"),
        }
    } else if req.method == "POST" && req.path.starts_with("/incr/") {
        let key = req.path[6..].to_string();
        let delta: i32 = req
            .query
            .get("delta")
            .and_then(|d| d.parse().ok())
            .unwrap_or(1);
        let value = incr(state, &key, delta);
        respond(stream, 200, &format!("{value}\n"), "text/plain");
    } else if req.method == "GET" && req.path == "/keys" {
        let prefix = req.query.get("prefix").cloned().unwrap_or_default();
        let mut keys = keys_with_prefix(state, &prefix);
        keys.sort();
        respond(stream, 200, &keys.join("\n"), "text/plain");
    } else if req.method == "POST" && req.path == "/snapshot" {
        let dest = req.query.get("path").cloned().unwrap_or_default();
        match snapshot(state, &dest) {
            Ok(p) => respond(stream, 200, &format!("wrote {}\n", p.display()), "text/plain"),
            Err(e) => respond(
                stream,
                500,
                &format!("snapshot {} failed: {e}\n", data_dir().join(&dest).display()),
                "text/plain",
            ),
        }
    } else if req.method == "GET" && req.path == "/ui" {
        let key = req.query.get("key").cloned().unwrap_or_default();
        let html = format!("{PAGE}<div>key: {key}</div>");
        respond(stream, 200, &html, "text/html");
    } else if req.method == "POST" && req.path == "/admin/flush" {
        let token = req.query.get("token").cloned().unwrap_or_default();
        if token != ADMIN_TOKEN {
            respond(stream, 401, "bad token\n", "text/plain");
            return;
        }
        flush(state);
        respond(stream, 200, "flushed\n", "text/plain");
    } else {
        respond(stream, 404, "not found\n", "text/plain");
    }
}

fn main() {
    let port: u16 = env::var("PORT")
        .ok()
        .and_then(|p| p.parse().ok())
        .unwrap_or(DEFAULT_PORT);
    let _ = fs::create_dir_all(data_dir());
    let listener = TcpListener::bind(("127.0.0.1", port)).expect("bind");
    let state = Arc::new(State {
        kv: Mutex::new(HashMap::new()),
        counters: Mutex::new(HashMap::new()),
    });
    eprintln!("kv-server listening on 127.0.0.1:{port}");
    for conn in listener.incoming() {
        match conn {
            Ok(mut stream) => {
                let st = Arc::clone(&state);
                thread::spawn(move || {
                    match read_request(&mut stream) {
                        Ok(Some(req)) => handle(&st, &req, &mut stream),
                        Ok(None) => {}
                        Err(e) => {
                            let body = format!("request error: {e}\n");
                            respond(&mut stream, 500, &body, "text/plain");
                        }
                    }
                });
            }
            Err(e) => eprintln!("accept: {e}"),
        }
    }
}
