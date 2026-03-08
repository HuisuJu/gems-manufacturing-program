import customtkinter as ctk
import threading

from connection import SerialManager


class SerialFrame(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkFrame, title: str, **kwargs):
        super().__init__(parent, border_width=2, **kwargs)

        self.title_label = ctk.CTkLabel(
            self,
            text=f"  {title}  ",
            font=ctk.CTkFont(size=14),
            fg_color=self.cget("fg_color"),
        )
        self.title_label.place(relx=0.5, y=10, anchor="center")


class SerialPortOptionMenu(ctk.CTkOptionMenu):
    def __init__(self, parent: ctk.CTkFrame, **kwargs):
        super().__init__(parent, values=["Select"], **kwargs)


class SerialRefreshButton(ctk.CTkButton):
    def __init__(self, parent: ctk.CTkFrame, menu: ctk.CTkOptionMenu, **kwargs):
        super().__init__(parent, text="Refresh", command=self._on_click, **kwargs)
        self._menu = menu

    def _on_click(self) -> None:
        ports = SerialManager.list_ports()
        if not ports:
            ports = ["Select"]

        self._menu.configure(values=ports)
        if self._menu.get() not in ports:
            self._menu.set(ports[0])


class SerialIndicator(ctk.CTkLabel):
    def __init__(self, parent: ctk.CTkFrame, serial_manager: SerialManager, **kwargs):
        super().__init__(parent, **kwargs)

        self._sm = serial_manager
        self._state: str = "connected" if self._sm.is_connected() else "disconnected"
        self._invalidate()

        self._sm.subscribe_event(self._on_event)

    def set_transitioning(self, is_transitioning: bool) -> None:
        if is_transitioning:
            self._state = "connecting"
        else:
            self._state = "connected" if self._sm.is_connected() else "disconnected"
        self._invalidate()

    def _on_event(self, name: str) -> None:
        if name == "connected":
            self._state = "connected"
        elif name == "disconnected":
            self._state = "disconnected"
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
        **kwargs,
    ):
        super().__init__(parent, command=self._on_click, **kwargs)

        self._sm = serial_manager
        self._menu = menu
        self._indicator = indicator

        self._is_connected = self._sm.is_connected()
        self._is_transitioning = False
        self._invalidate()

        self._sm.subscribe_event(self._on_event)

    def _on_click(self) -> None:
        if self._is_transitioning:
            return

        self._is_transitioning = True
        self._indicator.set_transitioning(True)
        self.configure(state="disabled")

        if self._is_connected:
            threading.Thread(target=self._do_disconnect, daemon=True).start()
        else:
            threading.Thread(target=self._do_connect, daemon=True).start()

    def _do_connect(self) -> None:
        try:
            port = self._menu.get().strip()
            if not port or port == "Select":
                self._finish_transition()
                return

            self._sm.open(port=port)
        finally:
            self.after(0, self._finish_transition)

    def _do_disconnect(self) -> None:
        try:
            self._sm.close()
        finally:
            self.after(0, self._finish_transition)

    def _finish_transition(self) -> None:
        self._is_connected = self._sm.is_connected()
        self._is_transitioning = False
        self.configure(state="normal")
        self._indicator.set_transitioning(False)
        self._invalidate()

    def _on_event(self, name: str) -> None:
        self._is_connected = self._sm.is_connected()
        if not self._is_transitioning:
            self._indicator.set_transitioning(False)
            self._invalidate()

    def _invalidate(self) -> None:
        if self._is_connected:
            self.configure(text="Disconnect")
        else:
            self.configure(text="Connect")


class SerialWidget(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkFrame, serial_manager: SerialManager, **kwargs):
        super().__init__(parent, fg_color="transparent", **kwargs)

        self._sm = serial_manager

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.frame = SerialFrame(self, "Serial Connection")
        self.frame.grid(row=0, column=0, sticky="nsew", pady=(10, 0))

        for c in range(3):
            self.frame.grid_columnconfigure(c, weight=0)

        self.port_menu = SerialPortOptionMenu(self.frame, width=140)
        self.port_menu.grid(row=0, column=0, padx=(15, 5), pady=(20, 5))

        self.refresh_btn = SerialRefreshButton(self.frame, self.port_menu, width=80)
        self.refresh_btn.grid(row=0, column=1, padx=(5, 10), pady=(20, 5))

        self.status_indicator = SerialIndicator(self.frame, self._sm)
        self.status_indicator.grid(
            row=1,
            column=0,
            columnspan=3,
            padx=15,
            pady=(0, 10),
            sticky="e",
        )

        self.connect_btn = SerialConnectionButton(
            self.frame,
            self._sm,
            self.port_menu,
            self.status_indicator,
            width=80,
        )
        self.connect_btn.grid(row=0, column=2, padx=(0, 15), pady=(20, 5))

        self.refresh_btn._on_click()