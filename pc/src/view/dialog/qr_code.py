from __future__ import annotations

from dataclasses import dataclass

from pathlib import Path

from tkinter import filedialog, messagebox

import customtkinter as ctk

from qrcode import QRCode

from qrcode.constants import ERROR_CORRECT_M

from PIL import Image

from logger import Logger, LogLevel


@dataclass(frozen=True, slots=True)
class QrCodeData:
    """One QR code result."""

    payload: str
    manual_code: str | None = None
    title: str = "Matter QR Code"


def _build_qr_image(payload: str) -> Image.Image:
    """Build a QR image from payload."""
    normalized = payload.strip()
    if not normalized:
        raise ValueError("QR payload must not be empty.")

    qr = QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=10,
        border=4,
    )
    qr.add_data(normalized)
    qr.make(fit=True)

    pil_image = qr.make_image(
        fill_color="black",
        back_color="white",
    )

    return pil_image.get_image().convert("RGB")


def _save_qr_image(payload: str, path: str | Path) -> Path:
    """Save QR image as PNG."""
    image = _build_qr_image(payload)

    output = Path(path).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)

    return output


class QrCodePopup(ctk.CTkToplevel):
    """Modal popup for one QR code result."""

    def __init__(self, parent, data: QrCodeData) -> None:
        super().__init__(parent)

        self._data = data
        self._image = _build_qr_image(data.payload)
        self._ctk_image = ctk.CTkImage(
            light_image=self._image,
            dark_image=self._image,
            size=(320, 320),
        )

        self.title(data.title)
        self.geometry("460x620")
        self.resizable(False, False)

        self.transient(parent)
        self.protocol("WM_DELETE_WINDOW", self._close)

        self.grid_columnconfigure(0, weight=1)

        self._build_widgets()

    def _build_widgets(self) -> None:
        title = ctk.CTkLabel(
            self,
            text=self._data.title,
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        title.grid(row=0, column=0, pady=(20, 10))

        image = ctk.CTkLabel(self, text="", image=self._ctk_image)
        image.grid(row=1, column=0, pady=(0, 20))

        payload_label = ctk.CTkLabel(
            self,
            text="QR Payload",
            anchor="w",
        )
        payload_label.grid(row=2, column=0, padx=20, sticky="ew")

        payload_box = ctk.CTkTextbox(self, width=400, height=100, wrap="word")
        payload_box.grid(row=3, column=0, padx=20, pady=(0, 15), sticky="ew")
        payload_box.insert("1.0", self._data.payload)
        payload_box.configure(state="disabled")

        row = 4

        if self._data.manual_code is not None:
            manual_label = ctk.CTkLabel(
                self,
                text="Manual Pairing Code",
                anchor="w",
            )
            manual_label.grid(row=row, column=0, padx=20, sticky="ew")

            manual_entry = ctk.CTkEntry(self, width=400)
            manual_entry.grid(row=row + 1, column=0, padx=20, pady=(0, 20))
            manual_entry.insert(0, self._data.manual_code)
            manual_entry.configure(state="readonly")

            row += 2

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=row, column=0, padx=20, pady=(0, 20), sticky="ew")
        buttons.grid_columnconfigure((0, 1), weight=1)

        save_btn = ctk.CTkButton(
            buttons,
            text="Save PNG",
            command=self._save_png,
        )
        save_btn.grid(row=0, column=0, padx=(0, 8), sticky="ew")

        close_btn = ctk.CTkButton(
            buttons,
            text="Close",
            command=self._close,
        )
        close_btn.grid(row=0, column=1, padx=(8, 0), sticky="ew")

    def show_modal(self) -> None:
        """Show popup as modal."""
        self.lift()
        self.focus_force()
        self.grab_set()
        self.wait_window(self)

    def _save_png(self) -> None:
        """Save QR image to selected file."""
        path = filedialog.asksaveasfilename(
            parent=self,
            title="Save QR Code",
            defaultextension=".png",
            filetypes=[("PNG", "*.png")],
        )
        if not path:
            return

        try:
            saved = _save_qr_image(self._data.payload, path)
        except Exception as exc:
            messagebox.showerror(
                "Save Failed",
                f"Failed to save QR image.\n\n{exc}",
                parent=self,
            )
            return

        messagebox.showinfo(
            "Saved",
            f"QR image saved:\n\n{saved}",
            parent=self,
        )

    def _close(self) -> None:
        """Close popup."""
        try:
            self.grab_release()
        except Exception:
            pass

        self.destroy()


class QrCodeView(ctk.CTkFrame):
    """State holder and popup launcher for QR codes."""

    def __init__(self, parent: ctk.CTkFrame, **kwargs) -> None:
        super().__init__(parent, **kwargs)

        self._last_qr_code_data: QrCodeData | None = None

        self._event_handlers = {
            "show_last": self._handle_show_last,
            "clear": self._handle_clear,
        }

    def set_qr_code(
        self,
        payload: str,
        manual_code: str | None = None,
        *,
        auto_show: bool = True,
        title: str = "Matter QR Code",
    ) -> None:
        """Store latest QR result and optionally show it."""
        normalized_payload = payload.strip()
        if not normalized_payload:
            Logger.write(LogLevel.WARNING, "QR payload is empty.")
            return

        self._last_qr_code_data = QrCodeData(
            payload=normalized_payload,
            manual_code=manual_code,
            title=title,
        )

        if auto_show:
            self.show_last_qr_code()

    def get_last_qr_code(self) -> QrCodeData | None:
        """Return latest QR result."""
        return self._last_qr_code_data

    def clear_qr_code(self) -> None:
        """Clear latest QR result."""
        self._last_qr_code_data = None

    def show_last_qr_code(self) -> bool:
        """Show latest QR popup."""
        if self._last_qr_code_data is None:
            Logger.write(LogLevel.WARNING, "No QR code is available.")
            return False

        try:
            popup = QrCodePopup(self.winfo_toplevel(), self._last_qr_code_data)
            popup.show_modal()
        except Exception as exc:
            Logger.write(
                LogLevel.WARNING,
                f"Failed to open QR popup ({type(exc).__name__}: {exc})",
            )
            return False

        return True

    def trigger(self, event_name: str) -> None:
        """Dispatch one named event."""
        handler = self._event_handlers.get(event_name)
        if handler is not None:
            handler()

    def _handle_show_last(self) -> None:
        self.show_last_qr_code()

    def _handle_clear(self) -> None:
        self.clear_qr_code()
