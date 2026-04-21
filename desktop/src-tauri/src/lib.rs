use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use tauri::Manager;

// ─── State ────────────────────────────────────────────────────────────────────

pub struct AgentState(pub Mutex<Option<Child>>);

// ─── Path helpers ─────────────────────────────────────────────────────────────

fn project_root() -> PathBuf {
    if let Ok(p) = std::env::var("UNLZ_PROJECT_ROOT") {
        return PathBuf::from(p);
    }
    let mut path = std::env::current_dir().unwrap_or_default();
    for _ in 0..8 {
        if path.join("agent_server.py").exists() {
            return path;
        }
        match path.parent() {
            Some(p) => path = p.to_path_buf(),
            None => break,
        }
    }
    std::env::current_dir()
        .unwrap_or_default()
        .parent()
        .map(|p| p.to_path_buf())
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_default())
}

fn resolve_python(root: &PathBuf) -> String {
    if let Ok(p) = std::env::var("UNLZ_PYTHON") {
        return p;
    }
    let candidates: Vec<PathBuf> = if cfg!(windows) {
        vec![
            root.join("venv").join("Scripts").join("python.exe"),
            root.join(".venv").join("Scripts").join("python.exe"),
        ]
    } else {
        vec![
            root.join("venv").join("bin").join("python"),
            root.join(".venv").join("bin").join("python"),
        ]
    };
    for c in &candidates {
        if c.exists() {
            return c.to_string_lossy().to_string();
        }
    }
    if cfg!(windows) { "python".to_string() } else { "python3".to_string() }
}

// ─── Spawn helpers ────────────────────────────────────────────────────────────

/// Dev mode: run agent_server.py with the venv Python
#[cfg(debug_assertions)]
fn do_spawn(root: &PathBuf, python: &str) -> Option<Child> {
    let script = root.join("agent_server.py");
    if !script.exists() {
        eprintln!("[unlz] agent_server.py not found at {:?}", script);
        return None;
    }

    let mut cmd = Command::new(python);
    cmd.arg("-u").arg(&script);
    cmd.env("PYTHONDONTWRITEBYTECODE", "1");
    cmd.env("UNLZ_FORCE_LOG_FILE", "1");
    cmd.current_dir(root);
    // Provide valid null handles so Python's isatty()/print() don't crash
    cmd.stdin(Stdio::null());
    cmd.stdout(Stdio::null());
    cmd.stderr(Stdio::null());

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }

    match cmd.spawn() {
        Ok(child) => { println!("[unlz] Dev agent PID {}", child.id()); Some(child) }
        Err(e)    => { eprintln!("[unlz] Failed to start dev agent: {}", e); None }
    }
}

/// Release mode: run the bundled agent_server sidecar exe (next to app exe)
#[cfg(not(debug_assertions))]
fn do_spawn(_root: &PathBuf, _python: &str) -> Option<Child> {
    let exe_dir = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|p| p.to_path_buf()))
        .unwrap_or_default();

    let sidecar = if cfg!(windows) {
        exe_dir.join("agent_server.exe")
    } else {
        exe_dir.join("agent_server")
    };

    if !sidecar.exists() {
        eprintln!("[unlz] sidecar not found at {:?}", sidecar);
        return None;
    }

    let mut cmd = Command::new(&sidecar);
    cmd.current_dir(&exe_dir);

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000); // CREATE_NO_WINDOW
    }

    match cmd.spawn() {
        Ok(child) => { println!("[unlz] Sidecar PID {}", child.id()); Some(child) }
        Err(e)    => { eprintln!("[unlz] Failed to start sidecar: {}", e); None }
    }
}

fn spawn_server(root: &PathBuf, python: &str) -> Option<Child> {
    do_spawn(root, python)
}

// ─── .env helpers ────────────────────────────────────────────────────────────

fn env_file_path() -> PathBuf {
    if let Ok(root) = std::env::var("UNLZ_PROJECT_ROOT") {
        return PathBuf::from(root).join(".env");
    }
    project_root().join(".env")
}

// ─── Tauri commands ───────────────────────────────────────────────────────────

#[tauri::command]
fn get_settings() -> Result<std::collections::HashMap<String, String>, String> {
    let path = env_file_path();
    let content = std::fs::read_to_string(&path)
        .unwrap_or_default();

    let mut map = std::collections::HashMap::new();
    for line in content.lines() {
        let line = line.trim();
        if line.starts_with('#') || line.is_empty() { continue; }
        if let Some(idx) = line.find('=') {
            let key = line[..idx].trim().to_string();
            let val = line[idx + 1..].to_string(); // preserve value as-is (paths with spaces, etc.)
            map.insert(key, val);
        }
    }
    Ok(map)
}

#[tauri::command]
fn save_settings(payload: std::collections::HashMap<String, String>) -> Result<(), String> {
    let path = env_file_path();
    let content = std::fs::read_to_string(&path).unwrap_or_default();

    let mut lines: Vec<String> = content.lines().map(|l| l.to_string()).collect();

    for (key, value) in &payload {
        // Only write SCREAMING_SNAKE_CASE keys
        if key != &key.to_uppercase() { continue; }
        let prefix = format!("{}=", key);
        let new_line = format!("{}={}", key, value);

        let pos = lines.iter().position(|l| {
            let t = l.trim_start();
            t.starts_with(&prefix)
        });

        match pos {
            Some(i) => lines[i] = new_line,
            None    => lines.push(new_line),
        }
    }

    let result = lines.join("\n");
    std::fs::write(&path, result.trim_end().to_string() + "\n")
        .map_err(|e| format!("Write error: {e}"))
}

#[tauri::command]
fn restart_agent(state: tauri::State<AgentState>) -> String {
    let root = project_root();
    let python = resolve_python(&root);
    let mut guard = state.0.lock().unwrap();

    if let Some(mut child) = guard.take() {
        let _ = child.kill();
        let _ = child.wait();
    }

    match spawn_server(&root, &python) {
        Some(child) => {
            let pid = child.id();
            *guard = Some(child);
            format!("started:{pid}")
        }
        None => "error:could not start agent".to_string(),
    }
}

#[tauri::command]
fn stop_agent(state: tauri::State<AgentState>) -> String {
    let mut guard = state.0.lock().unwrap();
    if let Some(mut child) = guard.take() {
        let _ = child.kill();
        let _ = child.wait();
        "stopped".to_string()
    } else {
        "not_running".to_string()
    }
}

// ─── App entry point ─────────────────────────────────────────────────────────

pub fn run() {
    let root = project_root();
    let python = resolve_python(&root);
    println!("[unlz] Project root : {:?}", root);
    println!("[unlz] Python       : {}", python);
    println!("[unlz] Mode         : {}", if cfg!(debug_assertions) { "dev" } else { "release" });

    tauri::Builder::default()
        .manage(AgentState(Mutex::new(None)))
        .setup(move |app| {
            let state = app.state::<AgentState>();
            let mut guard = state.0.lock().unwrap();
            if let Some(child) = spawn_server(&root, &python) {
                *guard = Some(child);
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![restart_agent, stop_agent, get_settings, save_settings])
        .build(tauri::generate_context!())
        .expect("error building UNLZ Agent")
        .run(|app_handle, event| {
            if let tauri::RunEvent::Exit = event {
                let state = app_handle.state::<AgentState>();
                let mut guard = state.0.lock().unwrap();
                if let Some(mut child) = guard.take() {
                    println!("[unlz] Killing agent server…");
                    let _ = child.kill();
                    let _ = child.wait();
                }
            }
        });
}
