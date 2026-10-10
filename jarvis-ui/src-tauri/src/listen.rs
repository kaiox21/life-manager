//! Escuta da palavra "Jarvis" (change jarvis-wake-word): enquanto ligada, captura o microfone
//! com o `cpal` (a permissão de Microfone é do Jarvis.app) e manda blocos PCM de 16 kHz mono ao
//! cérebro pelo WebSocket local. Desligada, o stream é fechado e o ponto laranja do macOS some.
//! Quando o cérebro detecta a palavra, manda `wake`, e aqui o HUD aparece como no atalho de voz.
//! Nada de áudio é guardado aqui: o que não cabe no envio é descartado.

use std::net::TcpStream;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc;
use std::time::Duration;

use cpal::traits::{DeviceTrait, HostTrait, StreamTrait};
use serde::Serialize;
use tauri::{AppHandle, Emitter};
use tungstenite::{stream::MaybeTlsStream, Message, WebSocket};

/// Escuta ligada (item "Ouvir 'Jarvis'" no menu da barra).
pub static LISTEN: AtomicBool = AtomicBool::new(false);

const RATE: f64 = 16_000.0;
const BLOCK: usize = 1_600; // 100 ms
const FRAME_PCM: u8 = 0x10;

#[derive(Clone, Serialize)]
struct Wake {
    target: &'static str,
    visible: bool,
}

fn config_path() -> Option<std::path::PathBuf> {
    dirs::home_dir().map(|h| h.join("Library/Application Support/Jarvis/config.json"))
}

/// Escolha guardada em config.json (`"escuta"`); sem a chave, ligada (padrão da instalação).
pub fn load_choice() -> bool {
    config_path()
        .and_then(|p| std::fs::read_to_string(p).ok())
        .and_then(|t| serde_json::from_str::<serde_json::Value>(&t).ok())
        .and_then(|v| v.get("escuta").and_then(|e| e.as_bool()))
        .unwrap_or(true)
}

/// Guarda a escolha sem mexer nas outras chaves do config.json (usadas pelo cérebro).
pub fn save_choice(on: bool) {
    let Some(path) = config_path() else { return };
    let mut value = std::fs::read_to_string(&path)
        .ok()
        .and_then(|t| serde_json::from_str::<serde_json::Value>(&t).ok())
        .filter(|v| v.is_object())
        .unwrap_or_else(|| serde_json::json!({}));
    value["escuta"] = serde_json::Value::Bool(on);
    if let Some(dir) = path.parent() {
        let _ = std::fs::create_dir_all(dir);
    }
    let tmp = path.with_extension("json.tmp");
    if std::fs::write(&tmp, serde_json::to_string_pretty(&value).unwrap_or_default()).is_ok() {
        let _ = std::fs::rename(&tmp, &path);
    }
}

pub fn start(app: AppHandle) {
    std::thread::spawn(move || loop {
        if LISTEN.load(Ordering::SeqCst) {
            if let Err(e) = session(&app) {
                super::ui_log(format!("escuta: {e}"));
            }
        }
        std::thread::sleep(Duration::from_millis(if LISTEN.load(Ordering::SeqCst) { 5_000 } else { 300 }));
    });
}

fn brain_address() -> Result<(u64, String), String> {
    let path = dirs::home_dir().ok_or("sem pasta pessoal")?.join("Library/Application Support/Jarvis/session.json");
    let text = std::fs::read_to_string(path).map_err(|_| "cérebro fora".to_string())?;
    let v: serde_json::Value = serde_json::from_str(&text).map_err(|e| e.to_string())?;
    let port = v["port"].as_u64().ok_or("sem porta")?;
    let token = v["token"].as_str().ok_or("sem token")?.to_string();
    Ok((port, token))
}

/// Uma conexão com o cérebro e um stream do microfone; volta quando a escuta é desligada ou a
/// conexão cai (o laço de `start` reconecta em 5 s).
fn session(app: &AppHandle) -> Result<(), String> {
    // Microfone primeiro: na primeira vez (ou depois de um build novo) o macOS segura a
    // abertura até o Kaio responder à pergunta de permissão; com a conexão já aberta, o
    // keepalive do cérebro estourava nesse meio-tempo (visto em 10/10/2026).
    let (port, token) = brain_address()?;
    let (tx, rx) = mpsc::sync_channel::<Vec<f32>>(64);
    let (stream, rate) = open_mic(tx)?;
    stream.play().map_err(|e| e.to_string())?;
    if !LISTEN.load(Ordering::SeqCst) {
        return Ok(()); // desligada enquanto esperava a permissão
    }
    let (port, token) = brain_address().unwrap_or((port, token));
    let (mut ws, _) = tungstenite::connect(format!("ws://127.0.0.1:{port}/?token={token}")).map_err(|e| e.to_string())?;
    if let MaybeTlsStream::Plain(s) = ws.get_mut() {
        let _ = s.set_read_timeout(Some(Duration::from_millis(20)));
    }
    send_text(&mut ws, r#"{"type":"wake_listen","on":true}"#)?;
    while rx.try_recv().is_ok() {} // o que chegou antes de conectar fica para trás
    let mut resampler = Resampler::new(rate as f64);
    let mut pending: Vec<i16> = Vec::with_capacity(BLOCK * 2);
    let mut last_audio = std::time::Instant::now();
    let mut warned = false;

    let result = loop {
        if !LISTEN.load(Ordering::SeqCst) {
            break Ok(());
        }
        while let Ok(chunk) = rx.try_recv() {
            resampler.push(&chunk, &mut pending);
            last_audio = std::time::Instant::now();
            warned = false;
        }
        if !warned && last_audio.elapsed() > Duration::from_secs(5) {
            // microfone aberto mas sem áudio: permissão de Microfone pendente ou negada
            super::ui_log("escuta: o microfone não entrega áudio (permissão de Microfone do Jarvis?)".into());
            warned = true;
        }
        if pending.len() > BLOCK * 50 {
            pending.clear(); // atrasado demais (cérebro lento): descarta
        }
        while pending.len() >= BLOCK {
            let mut frame = Vec::with_capacity(1 + BLOCK * 2);
            frame.push(FRAME_PCM);
            for s in pending.drain(..BLOCK) {
                frame.extend_from_slice(&s.to_le_bytes());
            }
            if let Err(e) = ws.send(Message::Binary(frame.into())) {
                return Err(e.to_string());
            }
        }
        match ws.read() {
            Ok(Message::Text(text)) => {
                if text.contains(r#""type": "wake""#) || text.contains(r#""type":"wake""#) {
                    on_wake(app);
                }
            }
            Ok(Message::Close(_)) => break Err("cérebro fechou a conexão".into()),
            Ok(_) => {}
            Err(tungstenite::Error::Io(e))
                if e.kind() == std::io::ErrorKind::WouldBlock || e.kind() == std::io::ErrorKind::TimedOut => {}
            Err(e) => break Err(e.to_string()),
        }
        // manda o que estiver na fila (o pong do keepalive do servidor), com ou sem áudio
        match ws.flush() {
            Ok(()) => {}
            Err(tungstenite::Error::Io(e))
                if e.kind() == std::io::ErrorKind::WouldBlock || e.kind() == std::io::ErrorKind::TimedOut => {}
            Err(e) => break Err(e.to_string()),
        }
    };
    drop(stream); // fecha o microfone: o ponto laranja some
    let _ = send_text(&mut ws, r#"{"type":"wake_listen","on":false}"#);
    let _ = ws.close(None);
    result
}

fn send_text(ws: &mut WebSocket<MaybeTlsStream<TcpStream>>, text: &str) -> Result<(), String> {
    ws.send(Message::Text(text.to_string().into())).map_err(|e| e.to_string())
}

/// Microfone padrão; manda blocos mono f32 pelo canal (descarta se o canal encher).
fn open_mic(tx: mpsc::SyncSender<Vec<f32>>) -> Result<(cpal::Stream, u32), String> {
    let host = cpal::default_host();
    let device = host.default_input_device().ok_or("sem microfone")?;
    let config = device.default_input_config().map_err(|e| e.to_string())?;
    let channels = config.channels() as usize;
    let rate = config.sample_rate();
    let err = |e| eprintln!("microfone: {e}");
    let stream = match config.sample_format() {
        cpal::SampleFormat::F32 => device.build_input_stream(
            config.clone().into(),
            move |data: &[f32], _: &cpal::InputCallbackInfo| {
                let _ = tx.try_send(mono(data, channels, |s| s));
            },
            err,
            None,
        ),
        cpal::SampleFormat::I16 => device.build_input_stream(
            config.clone().into(),
            move |data: &[i16], _: &cpal::InputCallbackInfo| {
                let _ = tx.try_send(mono(data, channels, |s| s as f32 / 32768.0));
            },
            err,
            None,
        ),
        other => return Err(format!("formato de áudio não suportado: {other:?}")),
    }
    .map_err(|e| e.to_string())?;
    Ok((stream, rate))
}

fn mono<T: Copy>(data: &[T], channels: usize, to_f32: impl Fn(T) -> f32) -> Vec<f32> {
    let channels = channels.max(1);
    data.chunks(channels).map(|frame| frame.iter().map(|&s| to_f32(s)).sum::<f32>() / channels as f32).collect()
}

/// Reamostragem linear para 16 kHz (voz; o detector e o VAD não precisam de mais que isso).
struct Resampler {
    step: f64,
    pos: f64,
    last: f32,
}

impl Resampler {
    fn new(rate: f64) -> Self {
        Self { step: rate / RATE, pos: 0.0, last: 0.0 }
    }

    fn push(&mut self, input: &[f32], out: &mut Vec<i16>) {
        // `pos` é a posição (em amostras da entrada) da próxima saída, relativa ao início de
        // `input`; -1 indica a última amostra do bloco anterior.
        while self.pos < input.len() as f64 - 1.0 {
            let i = self.pos.floor();
            let frac = (self.pos - i) as f32;
            let a = if i < 0.0 { self.last } else { input[i as usize] };
            let b = input[(i + 1.0) as usize];
            let s = a + (b - a) * frac;
            out.push((s.clamp(-1.0, 1.0) * 32767.0) as i16);
            self.pos += self.step;
        }
        if let Some(&l) = input.last() {
            self.last = l;
        }
        self.pos -= input.len() as f64;
    }
}

/// "Jarvis": só voz, nenhuma janela abre (pedido do Kaio, 10/10). O painel, se aberto, mostra a
/// conversa pelos eventos do cérebro; o evento fica para quem quiser saber da ativação.
fn on_wake(app: &AppHandle) {
    let panel_open = super::window_visible(app, "painel");
    let visible = super::is_visible(app);
    let target = if panel_open { "painel" } else { "hud" };
    let _ = app.emit("jarvis://wake", Wake { target, visible });
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn reamostra_48k_para_16k() {
        let mut r = Resampler::new(48_000.0);
        let mut out = Vec::new();
        let input: Vec<f32> = (0..4_800).map(|i| (i as f32 / 4_800.0)).collect();
        r.push(&input, &mut out);
        r.push(&input, &mut out);
        assert!((3_195..=3_201).contains(&out.len()), "{}", out.len()); // 2 × 100 ms
    }

    #[test]
    fn mistura_canais() {
        assert_eq!(mono(&[1.0f32, 0.0, 0.5, 0.5], 2, |s| s), vec![0.5, 0.5]);
    }
}
