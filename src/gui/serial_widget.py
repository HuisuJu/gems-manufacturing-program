import customtkinter as ctk
from serial_manager import serial_manager

class SerialFrame(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkFrame, title: str, **kwargs):
        super().__init__(parent, border_width=2, **kwargs)

        self.title = ctk.CTkLabel(
            parent, 
            text='  ' + title + '  ',
            font=ctk.CTkFont(size=14),
            fg_color=parent.cget('fg_color') if hasattr(parent, 'cget') else None
        )
        self.title.place(relx=0.5, y=10, anchor='center')

class SerialPortOptionMenu(ctk.CTkOptionMenu):
    def __init__(self, parent: ctk.CTkFrame, **kwargs):
        super().__init__(parent, values=['Select',], **kwargs)

class SerialConnectionButton(ctk.CTkButton):
    def __init__(self, parent: ctk.CTkFrame, menu: ctk.CTkOptionMenu,**kwargs):
        super().__init__(parent, command=self.on_click, **kwargs)

        self.menu = menu
        self.is_connected = serial_manager.is_connected()
        self.invalidate()

        serial_manager.event.connect(self.on_event)

    def on_click(self):
        if self.is_connected:
            serial_manager.close()
        else:
            serial_manager.open(port=self.menu.get())

    def on_event(self, sender, event: str):
        if event == 'connected':
            self.is_connected = True
        elif event == 'disconnected':
            self.is_connected = False
        self.invalidate()    

    def invalidate(self):
        if self.is_connected:
            self.configure(text='Disconnect', fg_color='#E74C3C', hover_color='#C0392B')
        else:
            self.configure(text='Connect', fg_color='#2ECC71', hover_color='#27AE60')    

class SerialRefreshButton(ctk.CTkButton):
    def __init__(self, parent: ctk.CTkFrame, menu: ctk.CTkOptionMenu, **kwargs):
        super().__init__(parent, text='Refresh', fg_color='#6495ED', 
                         hover_color='blue', command=self.on_lick, **kwargs)
        self.menu = menu
        
    def on_lick(self):
        ports = serial_manager.list_ports()
        if not ports:
            ports = ['Select',]

        self.menu.configure(values=ports)

class SerialIndicator(ctk.CTkLabel):
    def __init__(self, parent: ctk.CTkFrame, **kwargs):
        super().__init__(parent, **kwargs)

        self.is_connected = serial_manager.is_connected()
        self.invalidate()

        serial_manager.event.connect(self.on_event)

    def on_event(self, sender, event: str):
        if event == 'connected':
            self.is_connected = True
        elif event == 'disconnected':
            self.is_connected = False
        self.invalidate()    

    def invalidate(self):
        if self.is_connected:
            self.configure(text='● Connected', text_color='green')
        else:
            self.configure(text='● Disconnected', text_color='red')

class SerialWidget(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkFrame, **kwargs):
        super().__init__(parent, fg_color='transparent', **kwargs)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.frame = SerialFrame(self, 'Serial Connection')
        self.frame.grid(row=0, column=0, sticky='nsew', pady=(10, 0))

        self.frame.grid_columnconfigure(0, weight=0)
        self.frame.grid_columnconfigure(1, weight=0)
        self.frame.grid_columnconfigure(2, weight=0)

        self.port_menu = SerialPortOptionMenu(self.frame, width=140)
        self.port_menu.grid(row=0, column=0, padx=(15, 5), pady=(20, 5))

        self.refresh_btn = SerialRefreshButton(self.frame, self.port_menu, width=80)
        self.refresh_btn.grid(row=0, column=1, padx=(5, 10), pady=(20, 5))

        self.connect_btn = SerialConnectionButton(self.frame, self.port_menu, width=80)
        self.connect_btn.grid(row=0, column=2, padx=(0, 15), pady=(20, 5))

        self.status_indicator = SerialIndicator(self.frame)
        self.status_indicator.grid(row=1, column=0, columnspan=3,
                                   padx=15, pady=(0, 10), sticky='e')
