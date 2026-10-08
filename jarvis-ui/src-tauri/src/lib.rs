//! Casca nativa do Jarvis: barra de menus, atalho global (⌥Espaço) e janela HUD.
//! Não tem regra nem chave de API: só mostra a interface e entrega a sessão do cérebro.

use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, Manager, PhysicalPosition, WindowEvent,
};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

/// Porta e token do cérebro (arquivo de sessão gravado pelo `python -m jarvis`, permissão 600).
#[tauri::command]
fn jarvis_session() -> Result<serde_json::Value, String> {
    let path = dirs::home_dir()
        .ok_or("sem pasta pessoal")?
        .join("Library/Application Support/Jarvis/session.json");
    let text = std::fs::read_to_string(&path)
        .map_err(|_| "O cérebro do Jarvis não está rodando (uv run python -m jarvis).".to_string())?;
    serde_json::from_str(&text).map_err(|e| e.to_string())
}

#[tauri::command]
fn hide_hud(app: AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        let _ = w.hide();
    }
}

/// Mostra o HUD embaixo e no centro da tela atual, ou esconde se já estiver visível.
fn toggle_hud(app: &AppHandle) {
    let Some(w) = app.get_webview_window("main") else { return };
    if w.is_visible().unwrap_or(false) {
        let _ = w.hide();
        return;
    }
    if let (Ok(Some(monitor)), Ok(size)) = (w.current_monitor(), w.outer_size()) {
        let area = monitor.size();
        let pos = monitor.position();
        let x = pos.x + (area.width as i32 - size.width as i32) / 2;
        let y = pos.y + area.height as i32 - size.height as i32 - (area.height as i32 / 10);
        let _ = w.set_position(PhysicalPosition::new(x, y));
    }
    let _ = w.show();
    let _ = w.set_focus();
    let _ = w.emit("jarvis://shown", ());
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let hotkey = Shortcut::new(Some(Modifiers::ALT), Code::Space);
    tauri::Builder::default()
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(move |app, shortcut, event| {
                    if shortcut == &hotkey && event.state() == ShortcutState::Pressed {
                        toggle_hud(app);
                    }
                })
                .build(),
        )
        .plugin(tauri_plugin_opener::init())
        .setup(move |app| {
            #[cfg(target_os = "macos")]
            app.set_activation_policy(tauri::ActivationPolicy::Accessory); // sem ícone no Dock

            app.global_shortcut().register(hotkey)?;

            let open = MenuItem::with_id(app, "open", "Abrir Jarvis  ⌥Espaço", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Sair", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &quit])?;
            TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("Jarvis")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "open" => toggle_hud(app),
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = event {
                        toggle_hud(tray.app_handle());
                    }
                })
                .build(app)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            // Como o Spotlight: perdeu o foco, esconde.
            if let WindowEvent::Focused(false) = event {
                let _ = window.hide();
            }
        })
        .invoke_handler(tauri::generate_handler![jarvis_session, hide_hud])
        .run(tauri::generate_context!())
        .expect("erro ao iniciar o Jarvis");
}
