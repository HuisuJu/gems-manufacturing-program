from __future__ import annotations

import threading

import customtkinter as ctk

from provision import ProvisionManager
from stream import Stream


class SerialSettingWidget(ctk.CTkFrame):
    """
    Stream connection widget.

    This widget manages endpoint discovery, connection state, and the
    connect/disconnect workflow for the current ProvisionManager stream.
    """

    _PLACEHOLDER_PORT = "Select"

    def __init__(self, parent: ctk.CTkFrame, **kwargs) -> None:
        super().__init__(parent, fg_color="transparent", **kwargs)

        self._is_transitioning = False
        self._event_handlers = {
            "refresh": self.refresh,
            "refresh_ports": self.refresh_ports,
            "connect": self.connect,
            "disconnect": self.disconnect,
        }

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._card = ctk.CTkFrame(self, corner_radius=10, border_width=2)
        self._card.grid(row=0, column=0, sticky="nsew", pady=(10, 0))

        self._title_label = ctk.CTkLabel(
            self,
            text="  Serial Connection  ",
            font=ctk.CTkFont(size=16, weight="bold"),
            fg_color=self._card.cget("fg_color"),
        )
        self._title_label.place(relx=0.5, y=10, anchor="center")
        self._title_label.lift()

        self._build_layout()
        self._build_widgets()

        self.refresh_ports()

    def _build_layout(self) -> None:
        """Configure the card layout."""
        self._card.grid_columnconfigure(0, weight=0)
        self._card.grid_columnconfigure(1, weight=1)
        self._card.grid_rowconfigure(0, weight=0)
        self._card.grid_rowconfigure(1, weight=0)
        self._card.grid_rowconfigure(2, weight=0)
        self._card.grid_rowconfigure(3, weight=0)

    def _build_widgets(self) -> None:
        """Create the widget UI."""
        self._description_label = ctk.CTkLabel(
            self._card,
            text=(
                "Choose the target serial port and connect the station "
                "before starting provisioning."
            ),
            anchor="w",
            justify="left",
            wraplength=680,
            text_color=("gray30", "gray70"),
            font=ctk.CTkFont(size=13),
        )
        self._description_label.grid(
            row=0,
            column=0,
            columnspan=2,
            padx=28,
            pady=(28, 14),
            sticky="ew",
        )

        self._port_label = ctk.CTkLabel(
            self._card,
            text="Select Port",
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self._port_label.grid(
            row=1,
            column=0,
            padx=(28, 14),
            pady=(0, 14),
            sticky="w",
        )

        self._port_menu = ctk.CTkOptionMenu(
            self._card,
            values=[self._PLACEHOLDER_PORT],
            height=30,
            command=lambda _value: self._update_controls(),
        )
        self._port_menu.grid(
            row=1,
            column=1,
            padx=(0, 28),
            pady=(0, 14),
            sticky="ew",
        )

        self._button_row = ctk.CTkFrame(self._card, fg_color="transparent")
        self._button_row.grid(
            row=2,
            column=0,
            columnspan=2,
            padx=28,
            pady=(0, 12),
            sticky="e",
        )

        self._refresh_button = ctk.CTkButton(
            self._button_row,
            text="Refresh",
            command=self.refresh_ports,
            width=130,
            height=38,
        )
        self._refresh_button.pack(side="left", padx=(0, 10))

        self._connect_button = ctk.CTkButton(
            self._button_row,
            text="Connect",
            command=self._on_connect_button_clicked,
            width=130,
            height=38,
        )
        self._connect_button.pack(side="left")

        self._status_indicator = ctk.CTkLabel(
            self._card,
            anchor="e",
            justify="right",
            font=ctk.CTkFont(size=14),
        )
        self._status_indicator.grid(
            row=3,
            column=0,
            columnspan=2,
            padx=28,
            pady=(0, 16),
            sticky="e",
        )

        self._update_indicator()
        self._update_controls()

    def is_connected(self) -> bool:
        """
        Return whether the stream is currently connected.
        """
        stream = self._get_stream()
        if stream is None:
            return False
        return stream.is_connected()

    def refresh_ports(self) -> None:
        """
        Refresh the visible endpoint list.
        """
        ports = self._get_available_ports()
        current = self._port_menu.get().strip()

        self._port_menu.configure(values=ports)

        if current in ports:
            self._port_menu.set(current)
        else:
            self._port_menu.set(ports[0])

        self._update_controls()

    def refresh(self) -> None:
        """
        Refresh the full stream connection UI state.
        """
        self.refresh_ports()
        self._update_indicator()
        self._update_controls()

    def connect(self) -> None:
        """
        Request a connection using the currently selected endpoint.
        """
        if not self.is_connected() and not self._is_transitioning:
            self._on_connect_button_clicked()

    def disconnect(self) -> None:
        """
        Request disconnection from the current endpoint.
        """
        if self.is_connected() and not self._is_transitioning:
            self._on_connect_button_clicked()

    def trigger(self, event_name: str) -> None:
        """Dispatch one named event."""
        handler = self._event_handlers.get(event_name)
        if handler is not None:
            handler()

    def _on_connect_button_clicked(self) -> None:
        """Handle connect/disconnect button click."""
        if self._is_transitioning:
            return

        if not self.is_connected():
            port = self._port_menu.get().strip()
            if not port or port == self._PLACEHOLDER_PORT:
                return

        self._start_transition()

        if self.is_connected():
            threading.Thread(target=self._do_disconnect, daemon=True).start()
        else:
            threading.Thread(target=self._do_connect, daemon=True).start()

    def _start_transition(self) -> None:
        """Enter transitional UI state."""
        self._is_transitioning = True
        self._update_indicator(is_transitioning=True)
        self._update_controls()

    def _do_connect(self) -> None:
        """Connect to the selected endpoint."""
        try:
            port = self._port_menu.get().strip()
            if not port or port == self._PLACEHOLDER_PORT:
                return

            stream = self._get_stream()
            if stream is None:
                return

            stream.open(port=port)
        finally:
            self.after(0, self._finish_transition)

    def _do_disconnect(self) -> None:
        """Disconnect the current endpoint."""
        try:
            stream = self._get_stream()
            if stream is None:
                return

            stream.close()
        finally:
            self.after(0, self._finish_transition)

    def _finish_transition(self) -> None:
        """Leave transitional UI state."""
        self._is_transitioning = False
        self._update_indicator()
        self._update_controls()

    def _update_indicator(self, is_transitioning: bool = False) -> None:
        """Update the connection status indicator."""
        if is_transitioning:
            self._status_indicator.configure(
                text="● Connecting...",
                text_color="orange",
            )
            return

        if self.is_connected():
            self._status_indicator.configure(
                text="● Connected",
                text_color="green",
            )
        else:
            self._status_indicator.configure(
                text="● Disconnected",
                text_color="red",
            )

    def _update_controls(self) -> None:
        """
        Update enabled/disabled state and button label.
        """
        is_connected = self.is_connected()
        selected = self._port_menu.get().strip()

        if self._is_transitioning:
            self._port_menu.configure(state="disabled")
            self._refresh_button.configure(state="disabled")
            self._connect_button.configure(
                state="disabled",
                text="Disconnect..." if is_connected else "Connect...",
            )
            return

        if is_connected:
            self._port_menu.configure(state="disabled")
            self._refresh_button.configure(state="disabled")
            self._connect_button.configure(
                state="normal",
                text="Disconnect",
            )
            return

        self._port_menu.configure(state="normal")
        self._refresh_button.configure(state="normal")

        if not selected or selected == self._PLACEHOLDER_PORT:
            self._connect_button.configure(
                state="disabled",
                text="Connect",
            )
        else:
            self._connect_button.configure(
                state="normal",
                text="Connect",
            )

    def _get_available_ports(self) -> list[str]:
        """
        Return the current endpoint list to be shown in the option menu.
        """
        stream = self._get_stream()
        if stream is None:
            return [self._PLACEHOLDER_PORT]

        ports = stream.list_ports()
        if not ports:
            return [self._PLACEHOLDER_PORT]

        return ports

    @staticmethod
    def _get_stream() -> Stream | None:
        """Return stream from ProvisionManager if available."""
        stream = ProvisionManager.get_stream()
        if stream is None:
            return None

        if isinstance(stream, Stream):
            return stream

        return None
