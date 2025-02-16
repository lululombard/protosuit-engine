use anyhow::{Context, Result};
use x11rb::connection::Connection;
use x11rb::protocol::xproto::*;
use std::sync::Arc;

pub struct WindowManager {
    conn: Arc<x11rb::rust_connection::RustConnection>,
    root: Window,
    screen_num: usize,
}

impl WindowManager {
    pub fn new() -> Result<Self> {
        let (conn, screen_num) = x11rb::connect(None)
            .context("Failed to connect to X server")?;
        let conn = Arc::new(conn);
        let screen = &conn.setup().roots[screen_num];
        let root = screen.root;

        Ok(Self {
            conn,
            root,
            screen_num,
        })
    }

    pub fn focus_window(&self, window: u32) -> Result<()> {
        let atoms = self.get_ewmh_atoms()?;

        // Set _NET_ACTIVE_WINDOW
        self.conn.change_property(
            PropMode::REPLACE,
            self.root,
            atoms._NET_ACTIVE_WINDOW,
            AtomEnum::WINDOW,
            32,
            1,
            &window.to_ne_bytes(),
        )?;

        // Set input focus
        self.conn.set_input_focus(
            InputFocus::POINTER_ROOT,
            window,
            x11rb::CURRENT_TIME,
        )?;

        self.conn.flush()?;
        Ok(())
    }

    pub fn minimize_window(&self, window: u32) -> Result<()> {
        let atoms = self.get_ewmh_atoms()?;

        // Set _NET_WM_STATE_HIDDEN
        self.conn.change_property(
            PropMode::APPEND,
            window,
            atoms._NET_WM_STATE,
            AtomEnum::ATOM,
            32,
            1,
            &atoms._NET_WM_STATE_HIDDEN.to_ne_bytes(),
        )?;

        self.conn.flush()?;
        Ok(())
    }

    pub fn close_window(&self, window: Window) -> Result<()> {
        let atoms = self.get_ewmh_atoms()?;

        // Send WM_DELETE_WINDOW message
        let event = ClientMessageEvent::new(
            32,
            window,
            atoms.WM_PROTOCOLS,
            [atoms.WM_DELETE_WINDOW, 0, 0, 0, 0],
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

    fn get_ewmh_atoms(&self) -> Result<EWMHAtoms> {
        Ok(EWMHAtoms {
            _NET_ACTIVE_WINDOW: self.get_atom("_NET_ACTIVE_WINDOW")?,
            _NET_WM_STATE: self.get_atom("_NET_WM_STATE")?,
            _NET_WM_STATE_HIDDEN: self.get_atom("_NET_WM_STATE_HIDDEN")?,
            WM_PROTOCOLS: self.get_atom("WM_PROTOCOLS")?,
            WM_DELETE_WINDOW: self.get_atom("WM_DELETE_WINDOW")?,
        })
    }

    fn get_atom(&self, name: &str) -> Result<Atom> {
        Ok(self.conn.intern_atom(false, name.as_bytes())?
            .reply()
            .context("Failed to get atom")?
            .atom)
    }
}

struct EWMHAtoms {
    _NET_ACTIVE_WINDOW: Atom,
    _NET_WM_STATE: Atom,
    _NET_WM_STATE_HIDDEN: Atom,
    WM_PROTOCOLS: Atom,
    WM_DELETE_WINDOW: Atom,
}
