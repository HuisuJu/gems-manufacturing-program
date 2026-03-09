import customtkinter as ctk
import threading
from typing import Callable, Optional

from stream import SerialManager


class SerialFrame(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkFrame, title: str, **kwargs):
        super().__init__(parent, border_width=2, **kwargs)


class SerialPortOptionMenu(ctk.CTkOptionMenu):
    def __init__(self, parent: ctk.CTkFrame, **kwargs):
        super().__init__(parent, values=["Select"], **kwargs)


class SerialRefreshButton(ctk.CTkButton):
    def __init__(
        self,
        parent: ctk.CTkFrame,
        menu: ctk.CTkOptionMenu,
        get_ports: Callable[[], list[str]],
        **kwargs,
    ):
        super().__init__(parent, text="Refresh", command=self._on_click, **kwargs)
        self._menu = menu
        self._get_ports = get_ports

    def _on_click(self) -> None:
        ports = self._get_ports()
        if not ports:
            ports = ["Select"]

        self._menu.configure(values=ports)
        if self._menu.get() not in ports:
            self._menu.set(ports[0])


class SerialIndicator(ctk.CTkLabel):
    def __init__(
        self,
        parent: ctk.CTkFrame,
        serial_manager: SerialManager,
        get_effective_connected: Callable[[], bool],
        **kwargs,
    ):
        super().__init__(parent, **kwargs)

        self._sm = serial_manager
        self._get_effective_connected = get_effective_connected
        self._state: str = "connected" if self._get_effective_connected() else "disconnected"
        self._invalidate()

        self._sm.subscribe_event(self._on_event)

    def set_transitioning(self, is_transitioning: bool) -> None:
        if is_transitioning:
            self._state = "connecting"
        else:
            self._state = "connected" if self._get_effective_connected() else "disconnected"
        self._invalidate()

    def refresh(self) -> None:
        self._state = "connected" if self._get_effective_connected() else "disconnected"
        self._invalidate()

    def _on_event(self, name: str) -> None:
        self.after(0, self._apply_event, name)

    def _apply_event(self, _: str) -> None:
        self._state = "connected" if self._get_effective_connected() else "disconnected"
        self._invalidate()

    def _invalidate(self) -> None:
        if self._state == "connecting":
            self.configure(text="● Connecting...", text_color="orange")
        elif self._state == "connected":
            self.configure(text="● Connected", text_color="green")
        else:
            self.configure(text="● Disconnected", text_color="red")


class SerialConnectionButton(ctk.CTkButton):
    def __init__(
        self,
        parent: ctk.CTkFrame,
        serial_manager: SerialManager,
        menu: ctk.CTkOptionMenu,
        indicator: SerialIndicator,
        get_effective_connected: Callable[[], bool],
        is_virtual_port: Callable[[str], bool],
        connect_virtual: Callable[[str], None],
        disconnect_virtual: Callable[[], None],
        **kwargs,
    ):
        super().__init__(parent, command=self._on_click, **kwargs)

        self._sm = serial_manager
        self._menu = menu
        self._indicator = indicator
        self._get_effective_connected = get_effective_connected
        self._is_virtual_port = is_virtual_port
        self._connect_virtual = connect_virtual
        self._disconnect_virtual = disconnect_virtual

        self._is_connected = self._get_effective_connected()
        self._is_transitioning = False
        self._active_virtual = False
        self._invalidate()

        self._sm.subscribe_event(self._on_event)

    def _on_click(self) -> None:
        if self._is_transitioning:
            return

        self._is_transitioning = True
        self._indicator.set_transitioning(True)
        self.configure(state="disabled")

        if self._is_connected:
            if self._active_virtual:
                threading.Thread(target=self._do_disconnect_virtual, daemon=True).start()
            else:
                threading.Thread(target=self._do_disconnect_real, daemon=True).start()
            return

        threading.Thread(target=self._do_connect, daemon=True).start()

    def _do_connect(self) -> None:
        try:
            port = self._menu.get().strip()
            if not port or port == "Select":
                return

            if self._is_virtual_port(port):
                self._connect_virtual(port)
                self._active_virtual = True
                return

            self._sm.open(port=port)
            self._active_virtual = False
        finally:
            self.after(0, self._finish_transition)

    def _do_disconnect_real(self) -> None:
        try:
            self._sm.close()
            self._active_virtual = False
        finally:
            self.after(0, self._finish_transition)

    def _do_disconnect_virtual(self) -> None:
        try:
            self._disconnect_virtual()
            self._active_virtual = False
        finally:
            self.after(0, self._finish_transition)

    def _finish_transition(self) -> None:
        self._is_connected = self._get_effective_connected()
        self._is_transitioning = False
        self.configure(state="normal")
        self._indicator.set_transitioning(False)
        self._invalidate()

    def refresh(self) -> None:
        self._is_connected = self._get_effective_connected()
        self._active_virtual = self._is_connected and self._menu.get().strip().endswith("_emulator")
        if not self._is_transitioning:
            self._indicator.refresh()
            self._invalidate()

    def _on_event(self, _: str) -> None:
        self.after(0, self.refresh)

    def _invalidate(self) -> None:
        if self._is_connected:
            self.configure(text="Disconnect")
        else:
            self.configure(text="Connect")


class SerialWidget(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkFrame, serial_manager: SerialManager, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        self._sm = serial_manager
        self._virtual_ports: list[str] = []
        self._virtual_connected_port: Optional[str] = None

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

        self.port_menu = SerialPortOptionMenu(self.frame, width=220)
        self.port_menu.grid(row=0, column=0, padx=(15, 6), pady=(20, 6), sticky="ew")

        self.refresh_btn = SerialRefreshButton(
            self.frame,
            self.port_menu,
            self._get_available_ports,
            width=86,
            height=28,
        )
        self.refresh_btn.grid(row=0, column=1, padx=(6, 6), pady=(20, 6), sticky="ew")

        self.status_indicator = SerialIndicator(
            self.frame,
            self._sm,
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
            self._sm,
            self.port_menu,
            self.status_indicator,
            self.is_connected,
            self._is_virtual_port,
            self._connect_virtual,
            self._disconnect_virtual,
            width=100,
            height=28,
        )
        self.connect_btn.grid(row=0, column=2, padx=(6, 15), pady=(20, 6), sticky="ew")

        self.refresh_btn._on_click()

    def is_connected(self) -> bool:
        """
        Return whether the widget is effectively connected.

        In emulator mode this reflects the virtual connection state.
        Otherwise it reflects the real SerialManager state.
        """
        return self._virtual_connected_port is not None or self._sm.is_connected()

    def set_virtual_ports(self, ports: list[str]) -> None:
        """
        Replace the current virtual serial port list.

        When virtual ports are configured, the refresh list shows those ports
        instead of probing real serial ports.
        """
        normalized = [str(port).strip() for port in ports if str(port).strip()]
        self._virtual_ports = normalized

        if self._virtual_connected_port is not None:
            if self._virtual_connected_port not in self._virtual_ports:
                self._virtual_connected_port = None

        self.refresh_btn._on_click()
        self.status_indicator.refresh()
        self.connect_btn.refresh()

    def clear_virtual_ports(self) -> None:
        """
        Disable virtual port mode and return to real serial port listing.
        """
        self._virtual_ports = []
        self._virtual_connected_port = None
        self.refresh_btn._on_click()
        self.status_indicator.refresh()
        self.connect_btn.refresh()

    def _get_available_ports(self) -> list[str]:
        """
        Return the current port list to be shown in the option menu.
        """
        if self._virtual_ports:
            return list(self._virtual_ports)

        ports = SerialManager.list_ports()
        if not ports:
            return ["Select"]
        return ports

    def _is_virtual_port(self, port: str) -> bool:
        """
        Return whether the given port is a configured virtual emulator port.
        """
        return port in self._virtual_ports or port.strip().endswith("_emulator")

    def _connect_virtual(self, port: str) -> None:
        """
        Connect to a virtual emulator port.

        This operation always succeeds.
        """
        self._virtual_connected_port = port

    def _disconnect_virtual(self) -> None:
        """
        Disconnect from the current virtual emulator port.
        """
        self._virtual_connected_port = None