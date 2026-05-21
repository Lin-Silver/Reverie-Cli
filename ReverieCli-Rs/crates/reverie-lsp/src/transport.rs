//! LSP 传输层
//!
//! 提供与语言服务器的通信传输

use std::io::{BufRead, BufReader, Write};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc::{self, Receiver, Sender};
use std::thread;
use std::time::Duration;

use crate::types::{Notification, Request, Response};

/// LSP 传输错误
#[derive(Debug)]
pub enum LspTransportError {
    ProcessFailed(String),
    IoError(std::io::Error),
    Timeout,
    ConnectionClosed,
    ParseError(String),
}

impl std::fmt::Display for LspTransportError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            LspTransportError::ProcessFailed(msg) => write!(f, "Process failed: {}", msg),
            LspTransportError::IoError(e) => write!(f, "IO error: {}", e),
            LspTransportError::Timeout => write!(f, "Timeout"),
            LspTransportError::ConnectionClosed => write!(f, "Connection closed"),
            LspTransportError::ParseError(msg) => write!(f, "Parse error: {}", msg),
        }
    }
}

impl std::error::Error for LspTransportError {}

/// LSP 传输层
pub struct LspTransport {
    /// 语言服务器进程
    process: Option<Child>,
    /// 输入通道发送器
    tx: Sender<String>,
    output_tx: Sender<String>,
    /// 输出通道接收器
    rx: Receiver<String>,
    outbound_rx: Option<Receiver<String>>,
    /// 是否已停止
    stopped: bool,
}

impl LspTransport {
    /// 创建新的 LSP 传输
    pub fn new() -> Result<Self, LspTransportError> {
        let (tx_in, rx_in) = mpsc::channel();
        let (tx_out, rx_out) = mpsc::channel();

        Ok(Self {
            process: None,
            tx: tx_in,
            output_tx: tx_out,
            rx: rx_out,
            outbound_rx: Some(rx_in),
            stopped: false,
        })
    }

    /// 启动语言服务器
    pub fn start(&mut self, command: &str, args: &[&str]) -> Result<(), LspTransportError> {
        let mut child = Command::new(command)
            .args(args)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| LspTransportError::ProcessFailed(e.to_string()))?;

        // 获取 stdin 和 stdout
        let stdin = child.stdin.take().ok_or(LspTransportError::ProcessFailed(
            "Failed to get stdin".to_string(),
        ))?;
        let stdout = child.stdout.take().ok_or(LspTransportError::ProcessFailed(
            "Failed to get stdout".to_string(),
        ))?;

        self.process = Some(child);

        // 启动读取线程
        let tx_out = self.output_tx.clone();
        thread::spawn(move || {
            let reader = BufReader::new(stdout);
            for line in reader.lines() {
                match line {
                    Ok(line) => {
                        if tx_out.send(line).is_err() {
                            break;
                        }
                    }
                    Err(_) => break,
                }
            }
        });

        // 启动写入线程
        let mut stdin = stdin;
        let rx_in = self.outbound_rx.take().ok_or_else(|| {
            LspTransportError::ProcessFailed("transport already started".to_string())
        })?;
        thread::spawn(move || {
            for message in rx_in {
                if writeln!(
                    stdin,
                    "Content-Length: {}\r\n\r\n{}",
                    message.len(),
                    message
                )
                .is_err()
                {
                    break;
                }
                let _ = stdin.flush();
            }
        });

        Ok(())
    }

    /// 发送请求
    pub fn send_request(&self, request: Request) -> Result<Response, LspTransportError> {
        let json = serde_json::to_string(&request)
            .map_err(|e| LspTransportError::ParseError(e.to_string()))?;
        self.tx
            .send(json)
            .map_err(|_| LspTransportError::ConnectionClosed)?;

        // 等待响应（简化处理，实际应该使用异步）
        return self.receive_response_timeout(Duration::from_secs(10));

        // 这里应该实现真正的请求-响应匹配
    }

    /// 发送通知
    pub fn send_notification(&self, notification: Notification) -> Result<(), LspTransportError> {
        let json = serde_json::to_string(&notification)
            .map_err(|e| LspTransportError::ParseError(e.to_string()))?;
        self.tx
            .send(json)
            .map_err(|_| LspTransportError::ConnectionClosed)?;
        Ok(())
    }

    /// 接收响应
    pub fn receive_response(&self) -> Result<Response, LspTransportError> {
        let line = self
            .rx
            .recv()
            .map_err(|_| LspTransportError::ConnectionClosed)?;
        serde_json::from_str(&line).map_err(|e| LspTransportError::ParseError(e.to_string()))
    }

    pub fn receive_response_timeout(
        &self,
        timeout: Duration,
    ) -> Result<Response, LspTransportError> {
        let line = self.rx.recv_timeout(timeout).map_err(|err| match err {
            mpsc::RecvTimeoutError::Timeout => LspTransportError::Timeout,
            mpsc::RecvTimeoutError::Disconnected => LspTransportError::ConnectionClosed,
        })?;
        serde_json::from_str(&line).map_err(|e| LspTransportError::ParseError(e.to_string()))
    }

    /// 停止传输
    pub fn stop(&mut self) -> Result<(), LspTransportError> {
        self.stopped = true;

        if let Some(mut process) = self.process.take() {
            process.kill().map_err(LspTransportError::IoError)?;
            let _ = process.wait();
        }

        Ok(())
    }

    /// 检查是否已停止
    pub fn is_stopped(&self) -> bool {
        self.stopped
    }
}

impl Drop for LspTransport {
    fn drop(&mut self) {
        let _ = self.stop();
    }
}
