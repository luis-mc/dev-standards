//! The one native question window model (lifecycle contract: web first, one native window for progress and
//! questions). It serves update progress and remove. The window is sized from its content, never a fixed size (LC-30).
//! The toolkit (a native window library) measures text with `Measure` and applies the returned `Size`.

/// Text measurement supplied by the toolkit: the pixel size of `text` wrapped to `max_width`, at the current text scale.
pub trait Measure {
    fn text(&self, text: &str, max_width: u32) -> Size;
    fn button(&self, label: &str) -> Size;
    /// Space between items and the window padding, from the design-system tokens.
    fn gap(&self) -> u32;
    fn padding(&self) -> u32;
    fn bar_height(&self) -> u32;
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub struct Size {
    pub width: u32,
    pub height: u32,
}

/// The display the window opens on, so it never grows past the screen.
#[derive(Clone, Copy, Debug)]
pub struct Screen {
    pub width: u32,
    pub height: u32,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DataChoice {
    Keep,
    Purge,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Kind {
    /// Update progress: Review, Downloading, Waiting, Installing, Restarting, Done.
    Progress { step: String, percent: Option<u8> },
    /// Remove: asks every time, no default; the Remove button stays disabled until a choice is made.
    Remove { size: String, path: String, choice: Option<DataChoice> },
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct QuestionWindow {
    pub title: String,
    pub detail: String,
    pub buttons: Vec<String>,
    pub kind: Kind,
}

impl QuestionWindow {
    /// Whether the primary button can be pressed. Remove needs a choice first.
    pub fn primary_enabled(&self) -> bool {
        match &self.kind {
            Kind::Remove { choice, .. } => choice.is_some(),
            Kind::Progress { .. } => true,
        }
    }

    /// Every line the window shows, top to bottom.
    pub fn lines(&self) -> Vec<String> {
        let mut v = vec![self.title.clone(), self.detail.clone()];
        match &self.kind {
            Kind::Progress { step, .. } => v.push(step.clone()),
            Kind::Remove { size, path, .. } => {
                v.push(format!("{size}, {path}"));
            }
        }
        v
    }

    /// The size that fits the content: the lines wrapped to the widest the screen allows, the bar, one row of buttons.
    /// The result grows with the text scale because `Measure` does. It is clamped to the screen, and nothing else.
    pub fn size_for(&self, m: &dyn Measure, screen: Screen) -> Size {
        let pad = m.padding();
        let gap = m.gap();
        let avail = screen.width.saturating_sub(2 * pad);
        let mut width = 0;
        let mut height = 0;
        for line in self.lines() {
            let s = m.text(&line, avail);
            width = width.max(s.width);
            height += s.height + gap;
        }
        if matches!(&self.kind, Kind::Progress { percent: Some(_), .. }) {
            height += m.bar_height() + gap;
        }
        let (mut row_w, mut row_h) = (0, 0);
        for b in &self.buttons {
            let s = m.button(b);
            row_w += s.width + gap;
            row_h = row_h.max(s.height);
        }
        width = width.max(row_w.saturating_sub(gap));
        height += row_h;
        Size {
            width: (width + 2 * pad).min(screen.width),
            height: (height + 2 * pad).min(screen.height),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A fake toolkit: a character is `scale` pixels wide.
    struct Fake { scale: u32 }
    impl Measure for Fake {
        fn text(&self, text: &str, max_width: u32) -> Size {
            let w = text.chars().count() as u32 * self.scale;
            let lines = w.div_ceil(max_width.max(1)).max(1);
            Size { width: w.min(max_width), height: lines * self.scale * 2 }
        }
        fn button(&self, label: &str) -> Size { Size { width: label.len() as u32 * self.scale + 16, height: self.scale * 4 } }
        fn gap(&self) -> u32 { 8 }
        fn padding(&self) -> u32 { 16 }
        fn bar_height(&self) -> u32 { 8 }
    }
    const SCREEN: Screen = Screen { width: 1920, height: 1080 };

    fn remove(choice: Option<DataChoice>) -> QuestionWindow {
        QuestionWindow {
            title: "Remove".into(), detail: "Choose what happens to your data".into(),
            buttons: vec!["Cancel".into(), "Remove".into()],
            kind: Kind::Remove { size: "1.4 GB".into(), path: "/data/app".into(), choice },
        }
    }

    #[test]
    fn remove_is_disabled_until_a_choice() {
        assert!(!remove(None).primary_enabled());
        assert!(remove(Some(DataChoice::Keep)).primary_enabled());
        assert!(remove(Some(DataChoice::Purge)).primary_enabled());
    }

    #[test]
    fn remove_names_size_and_path() {
        let l = remove(None).lines().join("\n");
        assert!(l.contains("1.4 GB") && l.contains("/data/app"));
    }

    #[test]
    fn size_follows_content() {
        let short = remove(None);
        let mut long = remove(None);
        long.detail = "x".repeat(400);
        let m = Fake { scale: 8 };
        assert!(long.size_for(&m, SCREEN).height > short.size_for(&m, SCREEN).height);
    }

    #[test]
    fn size_follows_text_scale() {
        let w = remove(None);
        let a = w.size_for(&Fake { scale: 8 }, SCREEN);
        let b = w.size_for(&Fake { scale: 16 }, SCREEN);
        assert!(b.width > a.width && b.height > a.height);
    }

    #[test]
    fn never_past_the_screen() {
        let mut w = remove(None);
        w.detail = "word ".repeat(5000);
        let s = Screen { width: 360, height: 640 };
        let z = w.size_for(&Fake { scale: 8 }, s);
        assert!(z.width <= 360 && z.height <= 640);
    }

    #[test]
    fn progress_bar_adds_height() {
        let base = QuestionWindow { title: "Updating".into(), detail: "".into(), buttons: vec!["Cancel".into()],
            kind: Kind::Progress { step: "Downloading".into(), percent: None } };
        let mut bar = base.clone();
        bar.kind = Kind::Progress { step: "Downloading".into(), percent: Some(40) };
        let m = Fake { scale: 8 };
        assert!(bar.size_for(&m, SCREEN).height > base.size_for(&m, SCREEN).height);
    }
}
