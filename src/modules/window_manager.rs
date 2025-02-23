use anyhow::Result;

#[cfg(all(unix, not(target_os = "macos")))]
use {
    anyhow::Context,
    x11rb::connection::Connection,
    x11rb::protocol::xproto::*,
    std::sync::Arc,
};

#[cfg(all(unix, not(target_os = "macos")))]
mod unix {
    use super::*;

    struct EWMHAtoms {
        _NET_ACTIVE_WINDOW: Atom,
        _NET_WM_STATE: Atom,
        _NET_WM_STATE_HIDDEN: Atom,
        WM_PROTOCOLS: Atom,
        WM_DELETE_WINDOW: Atom,
    }

    pub struct WindowManager {
        conn: Arc<x11rb::xcb_ffi::XCBConnection>,
        root: Window,
    }

    impl WindowManager {
        pub fn new() -> Result<Self> {
            let (conn, screen_num) = x11rb::connect(None)?;
            let conn = Arc::new(conn);
            let setup = conn.setup();
            let root = setup.roots[screen_num].root;

            Ok(Self { conn, root })
        }

        fn get_atom(&self, name: &str) -> Result<Atom> {
            Ok(self.conn.intern_atom(false, name.as_bytes())?
                .reply()
                .context("Failed to get atom")?
                .atom)
        }

        fn get_ewmh_atoms(&self) -> Result<EWMHAtoms> {
            Ok(EWMHAtoms {
                _NET_ACTIVE_WINDOW: self.get_atom("_NET_ACTIVE_WINDOW")?,
                _NET_WM_STATE: self.get_atom("_NET_WM_STATE")?,
                _NET_WM_STATE_HIDDEN: self.get_atom("_NET_WM_STATE_HIDDEN")?,
                WM_PROTOCOLS: self.get_atom("WM_PROTOCOLS")?,
                WM_DELETE_WINDOW: self.get_atom("WM_DELETE_WINDOW")?,
            })
        }

        pub fn focus_window(&self, window_id: u32) -> Result<()> {
            let window = window_id as Window;
            self.conn.set_input_focus(InputFocus::PARENT, window, x11rb::CURRENT_TIME)?;
            self.conn.flush()?;
            Ok(())
        }

        pub fn minimize_window(&self, window_id: u32) -> Result<()> {
            let window = window_id as Window;
            let atom = self.conn.intern_atom(false, b"_NET_WM_STATE")?;
            let atom_minimize = self.conn.intern_atom(false, b"_NET_WM_STATE_HIDDEN")?;

            if let (Ok(atom_reply), Ok(atom_minimize_reply)) = (atom.reply(), atom_minimize.reply()) {
                self.conn.change_property(
                    PropMode::REPLACE,
                    window,
                    atom_reply.atom,
                    AtomEnum::ATOM,
                    32,
                    1,
                    &[atom_minimize_reply.atom],
                )?;
                self.conn.flush()?;
            }
            Ok(())
        }

        pub fn close_window(&self, window_id: u32) -> Result<()> {
            let window = window_id as Window;
            let wm_protocols = self.conn.intern_atom(false, b"WM_PROTOCOLS")?.reply()?;
            let wm_delete_window = self.conn.intern_atom(false, b"WM_DELETE_WINDOW")?.reply()?;

            let event = ClientMessageEvent::new(
                32,
                window,
                wm_protocols.atom,
                [wm_delete_window.atom, 0, 0, 0, 0],
            );

            self.conn.send_event(
                false,
                window,
                EventMask::NO_EVENT,
                event,
            )?;

            self.conn.flush()?;
            Ok(())
        }
    }
}

#[cfg(target_os = "macos")]
mod macos {
    use super::*;

    pub struct WindowManager {}

    impl WindowManager {
        pub fn new() -> Result<Self> {
            log::debug!("Creating macOS WindowManager");
            Ok(Self {})
        }

        pub fn focus_window(&self, _window_id: u32) -> Result<()> {
            log::debug!("macOS focus_window called");
            Ok(())
        }

        pub fn minimize_window(&self, _window_id: u32) -> Result<()> {
            log::debug!("macOS minimize_window called");
            Ok(())
        }

        pub fn close_window(&self, _window_id: u32) -> Result<()> {
            log::debug!("macOS close_window called");
            Ok(())
        }
    }
}

#[cfg(all(unix, not(target_os = "macos")))]
pub use unix::WindowManager;

#[cfg(target_os = "macos")]
pub use macos::WindowManager;
