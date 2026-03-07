import customtkinter as ctk
from logger.logger import Logger, LogRecord, LogLevel

class LogWidget(ctk.CTkFrame):
    def __init__(self, parent: ctk.CTkFrame, **kwargs):
        super().__init__(parent, **kwargs)

        # Layout: this frame has 1 row, 2 columns (textbox + scrollbar)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.textbox = ctk.CTkTextbox(
            self,
            wrap='word',
            height=140,
        )
        self.textbox.grid(row=0, column=0, sticky='nsew', padx=(8, 0), pady=8)

        self.scrollbar = ctk.CTkScrollbar(self, command=self.textbox.yview)
        self.scrollbar.grid(row=0, column=1, sticky='ns', padx=(0, 8), pady=8)

        self.textbox.configure(yscrollcommand=self.scrollbar.set)
        self.textbox.configure(state='disabled')

        self.autoscroll = True

        Logger.subscribe(self.print)

    def print(self, record: LogRecord):
        timestamp = record.timestamp.strftime('%H:%M:%S')

        line = f'[{timestamp}] [{record.level.name}] {record.message}\n'

        self.textbox.configure(state='normal')
        self.textbox.insert('end', line)
        self.textbox.configure(state='disabled')

        self.textbox.see('end')
    