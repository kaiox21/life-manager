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

/// Registro da interface (erros que antes sumiam): ~/Library/Logs/Jarvis/ui.log
#[tauri::command]
fn ui_log(message: String) {
    use std::io::Write;
    let Some(home) = dirs::home_dir() else { return };
    let path = home.join("Library/Logs/Jarvis/ui.log");
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(path) {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs())
            .unwrap_or(0);
        let _ = writeln!(f, "{now} {message}");
    }
}

#[tauri::command]
fn hide_hud(app: AppHandle) {
    if let Some(w) = app.get_webview_window("main") {
        if let Err(e) = w.hide() {
            ui_log(format!("hide_hud falhou: {e}"));
        }
    }
    grab_esc(&app, false);
}

/// Esc é do Jarvis só enquanto o HUD está na tela *sem foco* (voz, aviso de terminal): sem
/// isso o Esc ia para o app em uso e nunca fechava o HUD. Ao esconder, devolve o Esc.
static ESC_GRABBED: AtomicBool = AtomicBool::new(false);

fn esc_key() -> Shortcut {
    Shortcut::new(None, Code::Escape)
}

/// Agenda para depois: registrar ou soltar um atalho de dentro do tratamento de outro atalho
/// trava o app inteiro (a trava do gerenciador de atalhos já está tomada). Aconteceu em
/// 09/10/2026 com o Esc registrado dentro do ⌘⇧Espaço.
fn grab_esc(app: &AppHandle, on: bool) {
    // `run_on_main_thread` chamado da própria thread principal roda na hora (e trava de novo);
    // de outra thread, ele entra na fila e só roda depois que o atalho atual termina.
    let handle = app.clone();
    std::thread::spawn(move || {
        let inner = handle.clone();
        let _ = handle.run_on_main_thread(move || grab_esc_now(&inner, on));
    });
}

fn grab_esc_now(app: &AppHandle, on: bool) {
    if on {
        if !ESC_GRABBED.swap(true, Ordering::SeqCst) {
            if let Err(e) = app.global_shortcut().register(esc_key()) {
                ESC_GRABBED.store(false, Ordering::SeqCst);
                ui_log(format!("não deu para pegar o Esc: {e}"));
            }
        }
    } else if ESC_GRABBED.swap(false, Ordering::SeqCst) {
        let _ = app.global_shortcut().unregister(esc_key());
    }
}

/// Mostra o HUD. `focus=true` (modo texto) ativa a janela e o campo; `false` (voz) só
/// a põe por cima, deixando o app em uso ativo.
#[tauri::command]
fn show_hud(app: AppHandle, focus: bool) {
    place_and_show(&app, focus, !focus);
}

fn is_visible(app: &AppHandle) -> bool {
    window_visible(app, "main")
}

fn window_visible(app: &AppHandle, label: &str) -> bool {
    app.get_webview_window(label)
        .and_then(|w| w.is_visible().ok())
        .unwrap_or(false)
}

/// Aviso de um terminal do Claude Code: mostra o HUD sem roubar o foco, a não ser que o painel
/// esteja aberto (ele mostra o aviso). Devolve "painel", "ja_aberto" ou "mostrado".
/// Não pega o Esc: o Kaio pode estar no Terminal.app, onde o Esc interrompe o Claude Code
/// (change jarvis-terminais-controle). O aviso some quando o pedido se resolve, ou pelo ×.
#[tauri::command]
fn show_alert(app: AppHandle) -> &'static str {
    if window_visible(&app, "painel") {
        return "painel";
    }
    if is_visible(&app) {
        return "ja_aberto";
    }
    place_and_show(&app, false, false);
    "mostrado"
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

/// `esc`: pegar o Esc global enquanto o HUD está sem foco (só o HUD aberto pela voz).
fn place_and_show(app: &AppHandle, focus: bool, esc: bool) {
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
    grab_esc(app, esc && !focus);
    if focus {
        let _ = w.set_focus();
        let _ = w.emit("jarvis://shown", ());
    }
}

fn toggle_text_mode(app: &AppHandle) {
    if is_visible(app) {
        hide_hud(app.clone());
    } else {
        place_and_show(app, true, false);
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
                    if shortcut == &esc_key() {
                        if pressed {
                            let _ = app.emit_to("main", "jarvis://esc", ());
                            hide_hud(app.clone());
                        }
                        return;
                    }
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
                                place_and_show(app, false, true);
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
            if let WindowEvent::Focused(focused) = event {
                if window.label() == "main" {
                    if !focused {
                        let _ = window.hide();
                        grab_esc(window.app_handle(), false);
                    }
                }
            }
        })
        .invoke_handler(tauri::generate_handler![jarvis_session, hide_hud, show_hud, hide_panel, ui_log, show_alert])
        .run(tauri::generate_context!())
        .expect("erro ao iniciar o Jarvis");
}
