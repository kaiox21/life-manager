//! Casca nativa do Jarvis: barra de menus, atalhos globais e janela HUD.
//! Não tem regra nem chave de API: só mostra a interface e entrega a sessão do cérebro.
//!
//! Três atalhos, uma função cada:
//! - ⌥Espaço: abre/fecha o HUD em modo texto, com foco no campo (Esc fecha). Com o painel
//!   aberto, só foca o campo do painel.
//! - ⌘⇧Espaço segurado (push-to-talk): `Pressed` avisa a interface (`jarvis://ptt`,
//!   state=down) e, sem o painel aberto, mostra o HUD *sem roubar o foco*; `Released` avisa
//!   de novo (state=up). `target` diz qual janela cuida da fala.
//! - ⌥⇧Espaço: abre/fecha o painel em tela cheia (também pelo menu da barra; Esc fecha).

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
    /// Janela que cuida da fala: "painel" se ele estiver aberto, senão "hud".
    target: &'static str,
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
    window_visible(app, "main")
}

fn window_visible(app: &AppHandle, label: &str) -> bool {
    app.get_webview_window(label)
        .and_then(|w| w.is_visible().ok())
        .unwrap_or(false)
}

#[tauri::command]
fn hide_panel(app: AppHandle) {
    if let Some(w) = app.get_webview_window("painel") {
        let _ = w.set_simple_fullscreen(false);
        let _ = w.hide();
        let _ = w.emit("jarvis://panel", false);
    }
}

/// Painel em tela cheia no monitor onde está o cursor, sem criar um Space novo.
fn show_panel(app: &AppHandle) {
    let Some(w) = app.get_webview_window("painel") else { return };
    hide_hud(app.clone());
    if let Ok(cursor) = app.cursor_position() {
        if let Ok(Some(monitor)) = app.monitor_from_point(cursor.x, cursor.y) {
            let _ = w.set_position(*monitor.position());
            let _ = w.set_size(*monitor.size());
        }
    }
    let _ = w.show();
    let _ = w.set_simple_fullscreen(true);
    let _ = w.set_focus();
    let _ = w.emit("jarvis://panel", true);
}

fn toggle_panel(app: &AppHandle) {
    if window_visible(app, "painel") {
        hide_panel(app.clone());
    } else {
        show_panel(app);
    }
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
    let panel_key = Shortcut::new(Some(Modifiers::ALT | Modifiers::SHIFT), Code::Space);
    tauri::Builder::default()
        .plugin(
            tauri_plugin_global_shortcut::Builder::new()
                .with_handler(move |app, shortcut, event| {
                    let pressed = event.state() == ShortcutState::Pressed;
                    let panel_open = window_visible(app, "painel");
                    if shortcut == &panel_key {
                        if pressed {
                            toggle_panel(app);
                        }
                        return;
                    }
                    if shortcut == &text_key {
                        if !pressed {
                            return;
                        }
                        if panel_open {
                            if let Some(w) = app.get_webview_window("painel") {
                                let _ = w.set_focus();
                                let _ = w.emit("jarvis://shown", ());
                            }
                        } else {
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
                            let target = if panel_open { "painel" } else { "hud" };
                            let visible = is_visible(app);
                            if !panel_open {
                                place_and_show(app, false);
                            }
                            let _ = app.emit("jarvis://ptt", Ptt { state: "down", target, visible });
                        }
                        ShortcutState::Released => {
                            if !HELD.swap(false, Ordering::SeqCst) {
                                return;
                            }
                            let target = if panel_open { "painel" } else { "hud" };
                            let _ = app.emit("jarvis://ptt", Ptt { state: "up", target, visible: true });
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
            if let Err(e) = app.global_shortcut().register(panel_key) {
                // atalho ocupado por outro app: o painel continua no menu da barra
                eprintln!("atalho do painel indisponível: {e}");
            }

            let open = MenuItem::with_id(app, "open", "Abrir Jarvis  ⌥Espaço   ·   Falar: segure ⌘⇧Espaço", true, None::<&str>)?;
            let panel = MenuItem::with_id(app, "panel", "Painel  ⌥⇧Espaço", true, None::<&str>)?;
            let quit = MenuItem::with_id(app, "quit", "Sair", true, None::<&str>)?;
            let menu = Menu::with_items(app, &[&open, &panel, &quit])?;
            TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("Jarvis")
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_menu_event(|app, event| match event.id.as_ref() {
                    "open" => toggle_text_mode(app),
                    "panel" => toggle_panel(app),
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
            // O painel não fecha ao perder o foco: o Kaio pode trocar de app e voltar.
            if let WindowEvent::Focused(false) = event {
                if window.label() == "main" {
                    let _ = window.hide();
                }
            }
        })
        .invoke_handler(tauri::generate_handler![jarvis_session, hide_hud, show_hud, hide_panel])
        .run(tauri::generate_context!())
        .expect("erro ao iniciar o Jarvis");
}
