//! The tray menu model. The tray only notifies (lifecycle contract, LC-22): it never opens a Yes/No dialog and
//! never a modal window. A question goes to the one native question window. One notice per event per 24 hours.

pub const NOTICE_WINDOW_SECS: u64 = 24 * 60 * 60;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Event {
    UpdateReady,
    UpdateDone,
    UpdateFailed,
    NeedsYou,
}

/// A notice: text and an action that opens the app or the question window. It has no buttons of its own.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Notice {
    pub event: Event,
    pub text: String,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Item {
    /// Opens the console (web first).
    OpenApp,
    /// Opens the question window; the tray itself asks nothing.
    OpenUpdates,
    Quit,
}

#[derive(Default)]
pub struct TrayMenu {
    last: Vec<(Event, u64)>,
}

impl TrayMenu {
    pub fn items(&self) -> Vec<Item> {
        vec![Item::OpenApp, Item::OpenUpdates, Item::Quit]
    }

    /// Returns a notice unless the same event was already noticed in the last 24 hours. `now` is in seconds.
    pub fn notify(&mut self, event: Event, text: &str, now: u64) -> Option<Notice> {
        if let Some((_, at)) = self.last.iter_mut().find(|(e, _)| *e == event) {
            if now.saturating_sub(*at) < NOTICE_WINDOW_SECS {
                return None;
            }
            *at = now;
        } else {
            self.last.push((event, now));
        }
        Some(Notice { event, text: text.to_string() })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn one_notice_per_event_per_day() {
        let mut t = TrayMenu::default();
        assert!(t.notify(Event::UpdateReady, "Update ready", 1000).is_some());
        assert!(t.notify(Event::UpdateReady, "Update ready", 1000 + NOTICE_WINDOW_SECS - 1).is_none());
        assert!(t.notify(Event::UpdateReady, "Update ready", 1000 + NOTICE_WINDOW_SECS).is_some());
    }

    #[test]
    fn events_are_counted_apart() {
        let mut t = TrayMenu::default();
        assert!(t.notify(Event::UpdateReady, "a", 5).is_some());
        assert!(t.notify(Event::UpdateFailed, "b", 6).is_some());
    }

    #[test]
    fn menu_never_asks() {
        let t = TrayMenu::default();
        assert!(t.items().iter().all(|i| matches!(i, Item::OpenApp | Item::OpenUpdates | Item::Quit)));
    }
}
