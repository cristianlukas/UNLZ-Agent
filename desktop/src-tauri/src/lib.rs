use std::path::PathBuf;
use std::process::{Child, Command};
#[cfg(debug_assertions)]
use std::process::Stdio;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use tauri::Manager;
use tauri::menu::MenuBuilder;
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};

// ─── State ────────────────────────────────────────────────────────────────────

pub struct AgentState(pub Mutex<Option<Child>>);
static ALLOW_EXIT: AtomicBool = AtomicBool::new(false);

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

    let candidates: Vec<PathBuf> = if cfg!(windows) {
        vec![
            exe_dir.join("agent_server.exe"),
            exe_dir.join("resources").join("agent_server.exe"),
            exe_dir.join("..").join("Resources").join("agent_server.exe"),
        ]
    } else {
        vec![
            exe_dir.join("agent_server"),
            exe_dir.join("resources").join("agent_server"),
            exe_dir.join("..").join("Resources").join("agent_server"),
        ]
    };
    let sidecar = candidates.into_iter().find(|p| p.exists());
    let Some(sidecar) = sidecar else {
        eprintln!("[unlz] sidecar not found in expected locations near {:?}", exe_dir);
        return None;
    };

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

#[cfg(windows)]
fn refresh_windows_shortcut_and_icon_cache() {
    let exe = std::env::current_exe().unwrap_or_default();
    if exe.as_os_str().is_empty() {
        return;
    }
    let exe_str = exe.to_string_lossy().replace('\'', "''");
    let exe_dir = exe.parent().map(|p| p.to_path_buf()).unwrap_or_default();
    let icon_candidate = exe_dir.join("resources").join("icon.ico");
    let icon_path = if icon_candidate.exists() { icon_candidate } else { exe.clone() };
    let icon_str = icon_path.to_string_lossy().replace('\'', "''");
    let ps = format!(
        r#"$ErrorActionPreference='SilentlyContinue';
$targets = @();
$targets += Get-ChildItem (Join-Path $env:USERPROFILE 'Desktop') -Filter '*UNLZ*Agent*.lnk' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName;
$targets += Get-ChildItem (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs') -Filter '*UNLZ*Agent*.lnk' -ErrorAction SilentlyContinue | Select-Object -ExpandProperty FullName;
$targets += 'C:\Users\Public\Desktop\UNLZ Agent.lnk';
$targets = $targets | Select-Object -Unique;
$ws = New-Object -ComObject WScript.Shell;
foreach($p in $targets) {{
  if(Test-Path $p) {{
    $s = $ws.CreateShortcut($p);
    $s.TargetPath = '{0}';
    $s.IconLocation = '{1},0';
    $s.WorkingDirectory = Split-Path '{0}';
    $s.Save();
  }}
}}
Start-Process ie4uinit.exe -ArgumentList '-show' -WindowStyle Hidden;"#,
        exe_str,
        icon_str
    );
    let _ = Command::new("powershell")
        .arg("-NoProfile")
        .arg("-ExecutionPolicy")
        .arg("Bypass")
        .arg("-Command")
        .arg(ps)
        .spawn();
}

// ─── .env helpers ────────────────────────────────────────────────────────────

fn env_file_path() -> PathBuf {
    if let Ok(root) = std::env::var("UNLZ_PROJECT_ROOT") {
        return PathBuf::from(root).join(".env");
    }
    project_root().join(".env")
}

fn read_bool_setting(key: &str, default_value: bool) -> bool {
    let path = env_file_path();
    let content = std::fs::read_to_string(path).unwrap_or_default();
    for line in content.lines() {
        let line = line.trim();
        if line.starts_with('#') || line.is_empty() {
            continue;
        }
        if let Some((k, v)) = line.split_once('=') {
            if k.trim().eq_ignore_ascii_case(key) {
                let value = v.trim().to_ascii_lowercase();
                return matches!(value.as_str(), "1" | "true" | "yes" | "on");
            }
        }
    }
    default_value
}

fn minimize_to_tray_on_close_enabled() -> bool {
    read_bool_setting("MINIMIZE_TO_TRAY_ON_CLOSE", false)
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
fn pick_directory() -> Option<String> {
    rfd::FileDialog::new()
        .pick_folder()
        .map(|p| p.to_string_lossy().to_string())
}

#[tauri::command]
fn pick_file(filter_name: Option<String>, extensions: Option<Vec<String>>) -> Option<String> {
    let mut dialog = rfd::FileDialog::new();
    if let (Some(name), Some(exts)) = (filter_name.as_deref(), extensions.as_deref()) {
        if !exts.is_empty() {
            let ext_refs: Vec<&str> = exts.iter().map(String::as_str).collect();
            dialog = dialog.add_filter(name, &ext_refs);
        }
    }
    dialog.pick_file().map(|p| p.to_string_lossy().to_string())
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

            let mut tray_builder = TrayIconBuilder::with_id("main-tray");
            if let Some(icon) = app.default_window_icon() {
                tray_builder = tray_builder.icon(icon.clone());
                if let Some(w) = app.get_webview_window("main") {
                    let _ = w.set_icon(icon.clone());
                }
            }
            #[cfg(windows)]
            refresh_windows_shortcut_and_icon_cache();
            let tray_menu = MenuBuilder::new(app)
                .text("show", "Mostrar")
                .text("quit", "Salir")
                .build()?;
            tray_builder
                .menu(&tray_menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| {
                    match event.id.as_ref() {
                        "show" => {
                            if let Some(w) = app.get_webview_window("main") {
                                let _ = w.show();
                                let _ = w.unminimize();
                                let _ = w.set_focus();
                            }
                        }
                        "quit" => {
                            ALLOW_EXIT.store(true, Ordering::SeqCst);
                            app.exit(0);
                        }
                        _ => {}
                    }
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click { button, button_state, .. } = event {
                        if button == MouseButton::Left && button_state == MouseButtonState::Up {
                            if let Some(w) = tray.app_handle().get_webview_window("main") {
                                let _ = w.show();
                                let _ = w.unminimize();
                                let _ = w.set_focus();
                            }
                        }
                    }
                })
                .build(app)?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            restart_agent,
            stop_agent,
            get_settings,
            save_settings,
            pick_directory,
            pick_file
        ])
        .build(tauri::generate_context!())
        .expect("error building UNLZ Agent")
        .run(|app_handle, event| {
            match event {
                tauri::RunEvent::WindowEvent { label, event, .. } => {
                    if label == "main" {
                        if let tauri::WindowEvent::CloseRequested { api, .. } = event {
                            if !ALLOW_EXIT.load(Ordering::SeqCst) && minimize_to_tray_on_close_enabled() {
                                api.prevent_close();
                                if let Some(w) = app_handle.get_webview_window("main") {
                                    let _ = w.hide();
                                }
                            }
                        }
                    }
                }
                tauri::RunEvent::Exit => {
                    let state = app_handle.state::<AgentState>();
                    let mut guard = state.0.lock().unwrap();
                    if let Some(mut child) = guard.take() {
                        println!("[unlz] Killing agent server…");
                        let _ = child.kill();
                        let _ = child.wait();
                    }
                }
                _ => {}
            }
        });
}
