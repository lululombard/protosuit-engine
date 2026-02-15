"""
GStreamer WebRTC streaming for live display preview.
Captures X11 display via ximagesrc, encodes with VP8, and streams over WebRTC.
"""

import json
import threading

import gi

gi.require_version("Gst", "1.0")
gi.require_version("GstSdp", "1.0")
gi.require_version("GstWebRTC", "1.0")
from gi.repository import Gst, GstSdp, GstWebRTC, GLib

Gst.init(None)


class WebRTCStream:
    """Manages a GStreamer WebRTC pipeline for one client connection."""

    def __init__(self, display_config, system_config):
        self.pipeline = None
        self.webrtcbin = None
        self.mainloop = None
        self._loop_thread = None
        self._ws = None
        self._stopped = False

        # Build capture region from display config
        width = display_config.width
        height = display_config.height
        left_x = display_config.left_x
        y = display_config.y
        total_width = width * 2

        x_display = system_config.x_display

        # ximagesrc captures a region; endx/endy are exclusive
        # vp8enc: deadline=1 (realtime), cpu-used=8 (fastest), target-bitrate for quality
        pipeline_str = (
            f"ximagesrc display-name={x_display} "
            f"startx={left_x} starty={y} "
            f"endx={left_x + total_width} endy={y + height} "
            f"use-damage=false ! "
            f"videoconvert ! "
            f"videoscale ! "
            f"video/x-raw,framerate=30/1 ! "
            f"vp8enc deadline=1 cpu-used=8 target-bitrate=2000000 "
            f"keyframe-max-dist=30 buffer-size=1000 ! "
            f"rtpvp8pay pt=96 ! "
            f"webrtcbin name=webrtc bundle-policy=max-bundle "
            f"stun-server=stun://stun.l.google.com:19302"
        )

        self.pipeline = Gst.parse_launch(pipeline_str)
        self.webrtcbin = self.pipeline.get_by_name("webrtc")

        # Connect signals
        self.webrtcbin.connect("on-negotiation-needed", self._on_negotiation_needed)
        self.webrtcbin.connect("on-ice-candidate", self._on_ice_candidate)
        self.webrtcbin.connect("notify::ice-connection-state", self._on_ice_state)

        # Bus for errors
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message::error", self._on_bus_error)

    def start(self, ws):
        """Start the pipeline and GLib mainloop, sending signaling over ws."""
        self._ws = ws
        self.pipeline.set_state(Gst.State.PLAYING)

        # GLib mainloop drives GStreamer callbacks
        self.mainloop = GLib.MainLoop()
        self._loop_thread = threading.Thread(
            target=self.mainloop.run, daemon=True
        )
        self._loop_thread.start()

    def stop(self):
        """Tear down pipeline and mainloop."""
        if self._stopped:
            return
        self._stopped = True

        if self.pipeline:
            self.pipeline.set_state(Gst.State.NULL)
        if self.mainloop and self.mainloop.is_running():
            self.mainloop.quit()

    def handle_message(self, raw):
        """Handle an incoming JSON message from the browser WebSocket."""
        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return

        msg_type = msg.get("type")

        if msg_type == "answer":
            self._handle_sdp_answer(msg["sdp"])
        elif msg_type == "ice":
            self._handle_ice_candidate(
                msg["sdpMLineIndex"], msg["candidate"]
            )

    # -- GStreamer signal handlers (called from GLib thread) --

    def _on_negotiation_needed(self, webrtcbin):
        """webrtcbin wants to create an offer."""
        promise = Gst.Promise.new_with_change_func(self._on_offer_created)
        self.webrtcbin.emit("create-offer", None, promise)

    def _on_offer_created(self, promise):
        """SDP offer is ready — send to browser."""
        reply = promise.get_reply()
        offer = reply.get_value("offer")
        self.webrtcbin.emit("set-local-description", offer, None)

        sdp_text = offer.sdp.as_text()
        self._ws_send({"type": "offer", "sdp": sdp_text})

    def _on_ice_candidate(self, webrtcbin, sdp_mline_index, candidate):
        """Local ICE candidate ready — send to browser."""
        self._ws_send({
            "type": "ice",
            "sdpMLineIndex": sdp_mline_index,
            "candidate": candidate,
        })

    def _on_ice_state(self, webrtcbin, pspec):
        state = webrtcbin.get_property("ice-connection-state")
        print(f"[WebRTC] ICE state: {state}")

    def _on_bus_error(self, bus, msg):
        err, debug = msg.parse_error()
        print(f"[WebRTC] Pipeline error: {err.message}")
        if debug:
            print(f"[WebRTC] Debug: {debug}")

    # -- SDP / ICE from browser --

    def _handle_sdp_answer(self, sdp_text):
        """Set the remote SDP answer from the browser."""
        res, sdpmsg = GstSdp.SDPMessage.new_from_text(sdp_text)
        if res != GstSdp.SDPResult.OK:
            print("[WebRTC] Failed to parse SDP answer")
            return
        answer = GstWebRTC.WebRTCSessionDescription.new(
            GstWebRTC.WebRTCSDPType.ANSWER, sdpmsg
        )
        self.webrtcbin.emit("set-remote-description", answer, None)

    def _handle_ice_candidate(self, sdp_mline_index, candidate):
        """Add a remote ICE candidate from the browser."""
        self.webrtcbin.emit("add-ice-candidate", sdp_mline_index, candidate)

    # -- WebSocket helpers --

    def _ws_send(self, obj):
        """Send a JSON message to the browser (thread-safe via flask-sock)."""
        if self._ws and not self._stopped:
            try:
                self._ws.send(json.dumps(obj))
            except Exception:
                pass
