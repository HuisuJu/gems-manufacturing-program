from __future__ import annotations

import threading
from typing import Callable

import customtkinter as ctk

from stream import Stream

from .base import View


class SerialFrame(ctk.CTkFrame):
    """
    Container frame for stream connection controls.
    """

    def __init__(self, parent: ctk.CTkFrame, title: str, **kwargs) -> None:
        super().__init__(parent, border_width=2, **kwargs)


class SerialPortOptionMenu(ctk.CTkOptionMenu):
    """
    Option menu showing available stream endpoints.
    """

    def __init__(self, parent: ctk.CTkFrame, **kwargs) -> None:
        super().__init__(parent, values=["Select"], **kwargs)


class SerialRefreshButton(ctk.CTkButton):
    """
    Refresh button that reloads the available endpoint list.
    """

    def __init__(
        self,
        parent: ctk.CTkFrame,
        menu: ctk.CTkOptionMenu,
        get_ports: Callable[[], list[str]],
        **kwargs,
    ) -> None:
        super().__init__(parent, text="Refresh", command=self._on_click, **kwargs)
        self._menu = menu
        self._get_ports = get_ports

    def _on_click(self) -> None:
        ports = self._get_ports()
        if not ports:
            ports = ["Select"]

        current = self._menu.get().strip()
        self._menu.configure(values=ports)

        if current in ports:
            self._menu.set(current)
        else:
            self._menu.set(ports[0])


class SerialIndicator(ctk.CTkLabel):
    """
    Connection state indicator for the stream transport.
    """

    def __init__(
        self,
        parent: ctk.CTkFrame,
        stream: Stream,
        get_connected: Callable[[], bool],
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)

        self._stream = stream
        self._get_connected = get_connected
        self._state: str = "connected" if self._get_connected() else "disconnected"
        self._invalidate()

        self._stream.subscribe_event(self._on_event)

    def set_transitioning(self, is_transitioning: bool) -> None:
        """
        Update the indicator to show a transitional state.
        """
        if is_transitioning:
            self._state = "connecting"
        else:
            self._state = "connected" if self._get_connected() else "disconnected"
        self._invalidate()

    def refresh(self) -> None:
        """
        Refresh the indicator from the stream connection state.
        """
        self._state = "connected" if self._get_connected() else "disconnected"
        self._invalidate()

    def _on_event(self, _: str) -> None:
        self.after(0, self.refresh)

    def _invalidate(self) -> None:
        """
        Apply the current visual state.
        """
        if self._state == "connecting":
            self.configure(text="● Connecting...", text_color="orange")
        elif self._state == "connected":
            self.configure(text="● Connected", text_color="green")
        else:
            self.configure(text="● Disconnected", text_color="red")

    def destroy(self) -> None:
        """
        Release stream subscriptions.
        """
        self._stream.unsubscribe_event(self._on_event)
        super().destroy()


class SerialConnectionButton(ctk.CTkButton):
    """
    Connect/disconnect button for a generic stream endpoint.
    """

    def __init__(
        self,
        parent: ctk.CTkFrame,
        stream: Stream,
        menu: ctk.CTkOptionMenu,
        indicator: SerialIndicator,
        get_connected: Callable[[], bool],
        **kwargs,
    ) -> None:
        super().__init__(parent, command=self._on_click, **kwargs)

        self._stream = stream
        self._menu = menu
        self._indicator = indicator
        self._get_connected = get_connected

        self._is_connected = self._get_connected()
        self._is_transitioning = False
        self._invalidate()

        self._stream.subscribe_event(self._on_event)

    def _on_click(self) -> None:
        """
        Handle button click.
        """
        if self._is_transitioning:
            return

        self._is_transitioning = True
        self._indicator.set_transitioning(True)
        self.configure(state="disabled")

        if self._is_connected:
            threading.Thread(target=self._do_disconnect, daemon=True).start()
            return

        threading.Thread(target=self._do_connect, daemon=True).start()

    def _do_connect(self) -> None:
        """
        Connect to the currently selected endpoint.
        """
        try:
            port = self._menu.get().strip()
            if not port or port == "Select":
                return

            self._stream.open(port=port)
        finally:
            self.after(0, self._finish_transition)

    def _do_disconnect(self) -> None:
        """
        Disconnect the stream transport.
        """
        try:
            self._stream.close()
        finally:
            self.after(0, self._finish_transition)

    def _finish_transition(self) -> None:
        """
        Finalize one connect or disconnect transition.
        """
        self._is_connected = self._get_connected()
        self._is_transitioning = False
        self.configure(state="normal")
        self._indicator.set_transitioning(False)
        self._invalidate()

    def refresh(self) -> None:
        """
        Refresh the button state.
        """
        self._is_connected = self._get_connected()
        if not self._is_transitioning:
            self._indicator.refresh()
            self._invalidate()

    def _on_event(self, _: str) -> None:
        self.after(0, self.refresh)

    def _invalidate(self) -> None:
        """
        Apply the current button label.
        """
        if self._is_connected:
            self.configure(text="Disconnect")
        else:
            self.configure(text="Connect")

    def destroy(self) -> None:
        """
        Release stream subscriptions.
        """
        self._stream.unsubscribe_event(self._on_event)
        super().destroy()


class SerialView(View):
    """
    Stream connection view.

    This view depends only on the Stream interface and does not distinguish
    between real serial transports and emulator transports.
    """

    def __init__(self, parent: ctk.CTkFrame, stream: Stream, **kwargs) -> None:
        super().__init__(parent, **kwargs)

        self._stream = stream

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.frame = SerialFrame(self, "Serial Connection", corner_radius=10)
        self.frame.grid(row=0, column=0, sticky="nsew", pady=(10, 0))

        self.title_label = ctk.CTkLabel(
            self,
            text="  Serial Connection  ",
            font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=self.master.cget("fg_color"),
        )
        self.title_label.place(relx=0.5, y=10, anchor="center")
        self.title_label.lift()

        self.frame.grid_columnconfigure(0, weight=1)
        self.frame.grid_columnconfigure(1, weight=0)
        self.frame.grid_columnconfigure(2, weight=0)

        self.port_menu = SerialPortOptionMenu(self.frame, width=130)
        self.port_menu.grid(row=0, column=0, padx=(15, 6), pady=(20, 6), sticky="ew")

        self.refresh_btn = SerialRefreshButton(
            self.frame,
            self.port_menu,
            self._get_available_ports,
            width=64,
            height=28,
        )
        self.refresh_btn.grid(row=0, column=1, padx=(6, 6), pady=(20, 6), sticky="ew")

        self.status_indicator = SerialIndicator(
            self.frame,
            self._stream,
            self.is_connected,
        )
        self.status_indicator.grid(
            row=1,
            column=0,
            columnspan=3,
            padx=15,
            pady=(2, 14),
            sticky="w",
        )

        self.connect_btn = SerialConnectionButton(
            self.frame,
            self._stream,
            self.port_menu,
            self.status_indicator,
            self.is_connected,
            width=76,
            height=28,
        )
        self.connect_btn.grid(row=0, column=2, padx=(6, 15), pady=(20, 6), sticky="ew")

        self._event_handlers = {
            "refresh": self.refresh,
            "refresh_ports": self.refresh_ports,
            "connect": self.connect,
            "disconnect": self.disconnect,
        }

        self.refresh_ports()

    def is_connected(self) -> bool:
        """
        Return whether the stream is currently connected.
        """
        return self._stream.is_connected()

    def refresh_ports(self) -> None:
        """
        Refresh the visible endpoint list.
        """
        self.refresh_btn._on_click()

    def refresh(self) -> None:
        """
        Refresh the full stream connection UI state.
        """
        self.refresh_ports()
        self.status_indicator.refresh()
        self.connect_btn.refresh()

    def connect(self) -> None:
        """
        Request a connection using the currently selected endpoint.
        """
        if not self.is_connected():
            self.connect_btn._on_click()

    def disconnect(self) -> None:
        """
        Request disconnection from the current endpoint.
        """
        if self.is_connected():
            self.connect_btn._on_click()

    def _get_available_ports(self) -> list[str]:
        """
        Return the current endpoint list to be shown in the option menu.
        """
        ports = self._stream.list_ports()
        if not ports:
            return ["Select"]
        return ports