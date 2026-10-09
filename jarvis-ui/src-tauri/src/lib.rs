//! Casca nativa do Jarvis: barra de menus, atalhos globais e janela HUD.
//! Não tem regra nem chave de API: só mostra a interface e entrega a sessão do cérebro.
//!
//! Dois atalhos, uma função cada:
//! - ⌥Espaço: abre/fecha o HUD em modo texto, com foco no campo (Esc fecha).
//! - ⌘⇧Espaço segurado (push-to-talk): `Pressed` abre o HUD *sem roubar o foco* e avisa a
//!   interface (`jarvis://ptt`, state=down); `Released` avisa de novo (state=up).

use std::sync::atomic::{AtomicBool, Ordering};

use serde::Serialize;
use tauri::{
    menu::{Menu, MenuItem},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    AppHandle, Emitter, Manager, PhysicalPosition, WindowEvent,
};
use tauri_plugin_global_shortcut::{Code, GlobalShortcutExt, Modifiers, Shortcut, ShortcutState};

/// Tecla segurada: evita o auto-repeat do macOS gerar vários `Pressed`.
static HELD: AtomicBool = AtomicBool::new(false);

#[derive(Clone, Serialize)]
struct Ptt {
    state: &'static str,
    /// O HUD já estava visível antes de apertar (sem fala, ele continua como estava).
    visible: bool,
}

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

/// Mostra o HUD. `focus=true` (modo texto) ativa a janela e o campo; `false` (voz) só
/// a põe por cima, deixando o app em uso ativo.
#[tauri::command]
fn show_hud(app: AppHandle, focus: bool) {
    place_and_show(&app, focus);
}

fn is_visible(app: &AppHandle) -> bool {
    app.get_webview_window("main")
        .and_then(|w| w.is_visible().ok())
        .unwrap_or(false)
}

fn place_and_show(app: &AppHandle, focus: bool) {
    let Some(w) = app.get_webview_window("main") else { return };
    if !w.is_visible().unwrap_or(false) {
        if let (Ok(Some(monitor)), Ok(size)) = (w.current_monitor(), w.outer_size()) {
            let area = monitor.size();
            let pos = monitor.position();
            let x = pos.x + (area.width as i32 - size.width as i32) / 2;
            let y = pos.y + area.height as i32 - size.height as i32 - (area.height as i32 / 10);
            let _ = w.set_position(PhysicalPosition::new(x, y));
        }
    }
    let _ = w.set_focusable(focus);
    let _ = w.show();
    if focus {
        let _ = w.set_focus();
        let _ = w.emit("jarvis://shown", ());
    }
}

fn toggle_text_mode(app: &AppHandle) {
    if is_visible(app) {
        hide_hud(app.clone());
    } else {
        place_and_show(app, true);
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let text_key = Shortcut::new(Some(Modifiers::ALT), Code::Space);
    let voice_key = Shortcut::new(Some(Modifiers::SUPER | Modifiers::SHIFT), Code::Space);
    tauri::Builder::default()
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(move |app, shortcut, event| {
                    if shortcut == &text_key {
                        if event.state() == ShortcutState::Pressed {
                            toggle_text_mode(app);
                        }
                        return;
                    }
                    if shortcut != &voice_key {
                        return;
                    }
                    match event.state() {
                        ShortcutState::Pressed => {
                            if HELD.swap(true, Ordering::SeqCst) {
                                return; // auto-repeat com a tecla segurada
                            }
                            let visible = is_visible(app);
                            place_and_show(app, false);
                            let _ = app.emit("jarvis://ptt", Ptt { state: "down", visible });
                        }
                        ShortcutState::Released => {
                            if !HELD.swap(false, Ordering::SeqCst) {
                                return;
                            }
                            let _ = app.emit("jarvis://ptt", Ptt { state: "up", visible: true });
                        }
                    }
                })
                .build(),
        )
        .plugin(tauri_plugin_opener::init())
        .setup(move |app| {
            #[cfg(target_os = "macos")]
            app.set_activation_policy(tauri::ActivationPolicy::Accessory); // sem ícone no Dock

            app.global_shortcut().register(text_key)?;
            app.global_shortcut().register(voice_key)?;

            let open = MenuItem::with_id(app, "open", "Abrir Jarvis  ⌥Espaço   ·   Falar: segure ⌘⇧Espaço", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Sair", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &quit])?;
            TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("Jarvis")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "open" => toggle_text_mode(app),
                    "quit" => app.exit(0),
                    _ => {}
                })
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click { button: MouseButton::Left, button_state: MouseButtonState::Up, .. } = event {
                        toggle_text_mode(tray.app_handle());
                    }
                })
                .build(app)?;
            Ok(())
        })
        .on_window_event(|window, event| {
            // Modo texto, como o Spotlight: perdeu o foco, esconde. (Em voz a janela nunca tem foco.)
            if let WindowEvent::Focused(false) = event {
                let _ = window.hide();
            }
        })
        .invoke_handler(tauri::generate_handler![jarvis_session, hide_hud, show_hud])
        .run(tauri::generate_context!())
        .expect("erro ao iniciar o Jarvis");
}
