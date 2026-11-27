use super::{Desktop, failure};
use crate::host::{RunControl, lock};
use reverie_platform::desktop::{Button, Gesture, Window};
use serde_json::{Value, json};
use std::time::{Duration, Instant};
use tokio_util::task::AbortOnDropHandle;

pub(super) fn watch_escape(control: &RunControl) -> AbortOnDropHandle<()> {
    let cancel = control.cancel.clone();
    let commit_gate = control.commit_gate.clone();
    AbortOnDropHandle::new(tokio::spawn(async move {
        let mut poll = tokio::time::interval(std::time::Duration::from_millis(20));
        poll.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Skip);
        loop {
            tokio::select! { biased;
                _=cancel.cancelled()=>break,
                _=poll.tick()=>if reverie_platform::desktop::escape_down() {
                    let _commit=commit_gate.lock().unwrap_or_else(|e|e.into_inner());
                    cancel.cancel();
                    break;
                }
            }
        }
    }))
}

pub(super) struct Target {
    pub(super) id: String,
    pub(super) presented: bool,
    captured_at: Instant,
    window: Value,
    displays: Value,
    geometry: Window,
    region: [u32; 4],
    size: [u32; 2],
}

pub(super) fn frame(window: &Value) -> Option<Window> {
    Window::observe(
        window["id"].as_str()?,
        window["pid"].as_u64()?.try_into().ok()?,
    )
}

impl Target {
    pub(super) fn from_image(
        id: &str,
        window: &Value,
        displays: &Value,
        geometry: Option<Window>,
        data: &mut Value,
        vision: bool,
        captured_at: Instant,
    ) -> Option<Self> {
        let geometry = geometry?;
        if data["original_width"] != geometry.frame.width
            || data["original_height"] != geometry.frame.height
        {
            return None;
        }
        let screens = displays.as_array()?;
        if screens.is_empty()
            || screens.iter().any(|s| {
                s["id"].is_null()
                    || !s["bounds"].is_object()
                    || s["scale"]
                        .as_f64()
                        .is_none_or(|n| !n.is_finite() || n <= 0.0)
            })
        {
            return None;
        }
        let number = |value: &Value| value.as_u64().and_then(|n| u32::try_from(n).ok());
        let size = [number(&data["width"])?, number(&data["height"])?];
        let crop = &data["region"];
        let region = [
            number(&crop["x"])?,
            number(&crop["y"])?,
            number(&crop["width"])?,
            number(&crop["height"])?,
        ];
        data["capture_bounds"] = json!(geometry.frame);
        data["scale_x"] = json!(f64::from(size[0]) / f64::from(region[2]));
        data["scale_y"] = json!(f64::from(size[1]) / f64::from(region[3]));
        data["coordinate_available"] = json!(vision);
        vision.then(|| Self {
            id: id.into(),
            presented: false,
            captured_at,
            window: window.clone(),
            displays: displays.clone(),
            geometry,
            region,
            size,
        })
    }

    fn point(&self, x: &Value, y: &Value) -> Option<(i32, i32)> {
        Some((
            pixel(
                x.as_f64()?,
                self.size[0],
                self.region[0],
                self.region[2],
                self.geometry.frame.x,
            )?,
            pixel(
                y.as_f64()?,
                self.size[1],
                self.region[1],
                self.region[3],
                self.geometry.frame.y,
            )?,
        ))
    }
}

fn pixel(value: f64, returned: u32, offset: u32, span: u32, origin: i32) -> Option<i32> {
    if !value.is_finite() || !(0.0..f64::from(returned)).contains(&value) || span == 0 {
        return None;
    }
    let physical = (value * f64::from(span) / f64::from(returned)).floor() as i64;
    (i64::from(origin) + i64::from(offset) + physical)
        .try_into()
        .ok()
}

fn image_is_fresh(captured_at: Instant, now: Instant) -> bool {
    now.duration_since(captured_at) <= Duration::from_secs(120)
}

impl Desktop {
    pub(super) async fn pointer_input(
        &mut self,
        name: &str,
        p: &Value,
        control: &RunControl,
    ) -> Result<Value, Value> {
        let dragging = name == "computer_drag";
        let command = if dragging { "drag" } else { "mouse-click" };
        let refused = |code, msg| failure(command, code, msg, false);
        let stale = || {
            refused(
                "STALE_IMAGE",
                "Capture a fresh window image with a vision model before sending coordinates.",
            )
        };
        let id = if dragging {
            &p["from_image_id"]
        } else {
            &p["image_id"]
        };
        let target = self
            .pointer
            .as_ref()
            .filter(|t| t.presented && *id == t.id && (!dragging || p["to_image_id"] == t.id))
            .ok_or_else(stale)?;
        let invalid = || {
            refused(
                "INVALID_ARGS",
                "Coordinates must fit inside the returned image.",
            )
        };
        let (from, gesture) = if dragging {
            (
                target
                    .point(&p["from_x"], &p["from_y"])
                    .ok_or_else(invalid)?,
                Gesture::Drag {
                    to: target.point(&p["to_x"], &p["to_y"]).ok_or_else(invalid)?,
                },
            )
        } else {
            let button = match p["button"].as_str().unwrap_or("left") {
                "left" => Button::Left,
                "right" => Button::Right,
                "middle" => Button::Middle,
                _ => return Err(invalid()),
            };
            (
                target.point(&p["x"], &p["y"]).ok_or_else(invalid)?,
                Gesture::Click {
                    button,
                    count: p["count"].as_u64().unwrap_or(1) as u8,
                },
            )
        };
        let target = self.pointer.take().unwrap();
        self.refs.clear();
        self.window = None;
        let current = self.live_window(&target.window, &control.cancel).await?;
        let displays = self
            .native
            .invoke("list-displays", &[], None, 5000, false, &control.cancel)
            .await;
        if displays["ok"] != true {
            return Err(displays);
        }
        if current["bounds"] != target.window["bounds"]
            || displays["data"] != target.displays
            || frame(&current).as_ref() != Some(&target.geometry)
        {
            return Err(stale());
        }
        let sent = {
            let _commit =
                lock(&control.commit_gate).map_err(|e| failure(command, "INPUT_BUSY", e, false))?;
            if control.cancel.is_cancelled() {
                return Err(refused(
                    "CANCELLED",
                    "Cancelled before dispatching the gesture.",
                ));
            }
            if !image_is_fresh(target.captured_at, Instant::now()) {
                return Err(stale());
            }
            target.geometry.dispatch(from, gesture)
        };
        if let Err(e) = sent {
            if e.code == "PHYSICAL_ESCAPE" {
                control
                    .request_cancel()
                    .map_err(|problem| failure(command, "CANCELLED", problem, false))?;
            }
            return Err(failure(command, e.code, e.message, e.uncertain));
        }
        Ok(
            json!({"version":"2.6","ok":true,"command":command,"data":{"window":current,"image_id":target.id,
            "verification_scope":"os_input_queue","disposition":{"delivery":"delivered_unverified","retry":"unsafe"}}}),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn approval_wait_counts_toward_the_image_lifetime() {
        let capture = Instant::now();
        let limit = capture + Duration::from_secs(120);
        assert!(image_is_fresh(capture, limit));
        assert!(!image_is_fresh(capture, limit + Duration::from_nanos(1)));
    }

    #[test]
    fn cropped_fractional_pixels_map_into_the_physical_frame_including_negative_origins() {
        assert_eq!(pixel(0.0, 400, 100, 800, -1920), Some(-1820));
        assert_eq!(pixel(399.9, 400, 100, 800, -1920), Some(-1021));
        for x in [400.0, -0.1, f64::NAN, f64::INFINITY] {
            assert_eq!(pixel(x, 400, 100, 800, -1920), None);
        }
        assert_eq!(pixel(1.0, 10, 16, 10, i32::MAX), None);
    }
}
