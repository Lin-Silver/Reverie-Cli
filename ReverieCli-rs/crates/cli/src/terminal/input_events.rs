#[cfg(windows)]
mod windows;
#[cfg(windows)]
pub use windows::InputEvents;

#[cfg(not(windows))]
pub struct InputEvents;

#[cfg(not(windows))]
impl InputEvents {
    pub fn new() -> std::io::Result<Self> {
        Ok(Self)
    }

    pub fn poll(
        &mut self,
        timeout: std::time::Duration,
    ) -> std::io::Result<Option<crossterm::event::Event>> {
        if crossterm::event::poll(timeout)? {
            crossterm::event::read().map(Some)
        } else {
            Ok(None)
        }
    }
}
