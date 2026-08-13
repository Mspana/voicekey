#!/usr/bin/env python3
"""Check the icon pipeline end to end and say which step failed."""
import sys, tkinter as tk
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import icons, textfx

print("=" * 58)
print("  VoiceKey icon test")
print("=" * 58)
print("platform      :", sys.platform)
print("bundled Lora  :", textfx.BUNDLED.exists(), textfx.BUNDLED)
print("app id set    :", icons.set_app_id())

path = icons.ico_path("#1F9D5B")
print("ico generated :", path)
if path:
    print("ico size      :", Path(path).stat().st_size, "bytes")

root = tk.Tk()
root.title("VoiceKey icon test")
root.geometry("320x140")
root.overrideredirect(True)
tk.Label(root, text="icon test\n\nlook at the taskbar button", pady=30).pack()
root.update_idletasks()

import app as A
A.claim_taskbar(root)
root.update()
h = A._hwnd(root)
print("hwnd          :", h)
print("WM_SETICON    :", icons.apply_to_window(h, path))
print("console icon  :", icons.apply_to_console(path))
print()
print("A 'vk' tile with a green dot should now be on the taskbar.")
print("Close the little window to finish.")
root.after(20000, root.destroy)
root.bind("<Button-1>", lambda e: root.destroy())
root.mainloop()
