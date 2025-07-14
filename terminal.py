import tkinter as tk
from tkinter import scrolledtext
import threading
import paramiko
import time
import queue
import re

ANSI_COLORS = {
    '30': 'gray',  # Black
    '31': 'red',
    '32': 'green',
    '33': 'yellow',
    '34': 'blue',
    '35': 'magenta',
    '36': 'cyan',
    '37': 'white',
    '0': 'white',  # Reset
}


class SSHTerminal(tk.Frame):
    def __init__(self, master=None, hostname="", username="", password="", port=22, autoconnect=False,frame=None):
        super().__init__(master)
        self.master = master
        self.pack(fill=tk.BOTH, expand=True)
        self.hostname = hostname
        self.username = username
        self.password = password
        self.port = port

        self.writing = 0
        self.lastSize = 0
        self.detect = False

        self.client = None
        self.shell = None
        self.queue = queue.Queue()

        self.create_widgets()
        self.bind_keys()

        if autoconnect:
            self.connect()


    def create_widgets(self):
        self.text = scrolledtext.ScrolledText(
            self,
            wrap=tk.WORD,
            bg='black',
            fg='white',
            insertbackground='white',
            font=("Courier New", 11)
        )
        self.text.pack(fill=tk.BOTH, expand=True)
        self.text.config(state='normal')

        # Define color tags
        self.define_tags()

        self.prompt_index = self.text.index("end-1c")
        self.text.focus_set()

    def define_tags(self):
        styles = {
            "black": "#000000",
            "red": "#ff4b4b",
            "green": "#00ff00",
            "yellow": "#ffff55",
            "blue": "#5555ff",
            "magenta": "#ff55ff",
            "cyan": "#55ffff",
            "white": "white",
            "gray": "#888888",
        }

        for name, color in styles.items():
            self.text.tag_config(f"ansi_{name}", foreground=name)
            self.text.tag_config(f"ansi_bold_{name}", foreground=name, font=("Courier New", 11, "bold"))
            self.text.tag_config(f"ansi_ul_{name}", foreground=name, underline=True)

    def bind_keys(self):
        self.text.bind("<Key>", self.on_keypress)
        self.text.bind("<Control-d>", self.ctrl_d)
        self.text.bind("<Return>", self.enter_key)
        self.text.bind("<BackSpace>", self.backspace_key)

        # Allow default clipboard copy/paste
        self.text.bind("<Control-c>", lambda e: "break" if self.has_selection() else self.ctrl_c())
        self.text.bind("<Control-v>", self.paste_clipboard)

        # Arrow keys

        self.text.bind("<Up>", self._send_up_and_break)
        self.text.bind("<Down>", self._send_down_and_break)
        self.text.bind("<Left>", self.left_arrow)
        self.text.bind("<Right>", self.right_arrow)
        self.text.bind('<Button-1>', self.on_mouseClick)

    def clearLine(self,min=1):
        current_index = float(self.text.index(tk.INSERT))
        if self.writing != 0:
            self.text.delete(str(current_index - (self.writing / 100)), str(current_index + min/100))
            self.writing = 0
        if self.lastSize != 0:
            self.text.delete(str(current_index - (self.lastSize/100)), str(current_index + min/100))
            self.lastSize = 0

    def _send_up_and_break(self, event):
        self.detect = True
        self.clearLine()
        self.shell.send('\x1b[A')  # Send ANSI Up arrow
        return "break" # Tell Tkinter to stop default action

    def _send_down_and_break(self, event):
        self.clearLine()
        self.shell.send('\x1b[B')  # Send ANSI Down arrow
        return "break" # Tell Tkinter to stop default action

    def left_arrow(self, event=None):
        insert_index = self.text.index(tk.INSERT)
        self.text.mark_set(tk.INSERT, f"{insert_index}-1c")
        self.shell.send('\x1b[D')
        return "break"

    def right_arrow(self, event=None):
        insert_index = self.text.index(tk.INSERT)
        self.text.mark_set(tk.INSERT, f"{insert_index}+1c")
        self.shell.send('\x1b[C')
        return "break"

    def has_selection(self):
        try:
            return bool(self.text.get(tk.SEL_FIRST, tk.SEL_LAST))
        except tk.TclError:
            return False

    def paste_clipboard(self, event=None):
        try:
            paste = self.text.clipboard_get()
            self.shell.send(paste)
        except:
            pass
        return "break"

    def connect(self, hostname="", username="", password="", port=22):
        try:
            self.hostname = hostname
            self.username = username
            self.password = password
            self.port = port
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            self.client.connect(self.hostname, port=self.port, username=self.username, password=self.password)
            self.shell = self.client.invoke_shell(term='xterm', width=200, height=24)
            self.shell.settimeout(0.0)
            threading.Thread(target=self.receive_data, daemon=True).start()
            self.write_text(f"Connected to {self.hostname}\n")
        except Exception as e:
            self.write_text(f"Connection error: {e}\n")

    def receive_data(self):
        firstDATA =0
        while True:
            if self.shell and self.shell.recv_ready():
                try:
                    data = self.shell.recv(4096)
                    print(data)
                    data = data.decode("utf-8", errors="ignore")
                    self.queue.put(data)
                    # noinspection PyTypeChecker
                    self.master.after(1, self.flush_queue)
                    if firstDATA == 0:
                        self.addSpace(1)
                        firstDATA = 1
                except:
                    break
            time.sleep(0.05)

    def flush_queue(self):
        while not self.queue.empty():
            data = self.queue.get()
            self.write_ansi(data)

    def write_text(self, text):
        self.text.insert(tk.END, text)
        self.text.see(tk.END)

    def GetEndLock(self):
        lastLoc = self.text.index(tk.INSERT + "")
        self.text.mark_set(tk.INSERT, tk.END)
        endLoc = self.text.index(tk.INSERT)
        self.text.mark_set(tk.INSERT, lastLoc)
        return endLoc != lastLoc

    def write_ansi(self, text=''):
        if text != re.sub(r'\x1b\[[0-9;]*[HfJK]', '',text):
            self.deleteCharacter()
        elif text != re.sub(r'\x1b\[1Pm', '',text):
            self.deleteCharacter()
        elif not self.GetEndLock() and len(re.sub(r'\x08', '', text)) > 1 and not '' == re.sub(r'\x08', '', text) and text == re.sub(r'\x07', '', text) and text == re.sub(r'\x1b\[C', '', text):
            print('delete')
            self.deleteCharacter()

        # Remove OSC sequences (set window title)
        text = re.sub(r'\x1b\].*?(\x07|\x1b\\)', 'n1n', text)

        text = re.sub(r'\x08', '', text) # left when not the end # \x1b\[C for the right not the end
        text = re.sub(r'\x07', '',text) # x07 mean the end of the cursor left and right !

        # Remove bracketed paste mode
        text = re.sub(r'\x1b\[\?2004[hl]', '', text)
        # Remove cursor movements, clears
        text = re.sub(r'\x1b\[[0-9;]*[HfJK]', '', text)
        # Remove cursor position requests
        text = re.sub(r'\x1b\[6n', '', text)

        # Remove unhandled control sequences (cursor move, bracketed paste, etc)
        text = re.sub(r'\x1b\[\?2004[hl]', '', text)  # bracketed paste
        text = re.sub(r'\x1b\[\d*[A-HJ]', '', text)  # cursor move, erase line
        text = re.sub(r'\x1b\[\d+;\d+[Hf]', '', text)  # move to row/col
        text = re.sub(r'\x1b\[6n', '', text)  # cursor position query
        text = re.sub(r'\x1b\[0?m', '', text)  # redundant reset

        # remove the cursor edit
        text = re.sub(r'\x1b\[1Pm', '', text)


        # store the up or down size for the clear line
        if self.detect:
            self.clearLine(len(text))
            self.lastSize = len(text)
            self.detect = False


        # ANSI color escape parser
        ansi_escape = re.compile(r'\x1b\[([0-9;]*)m')
        parts = ansi_escape.split(text)
        current_tag = ""

        while parts:
            chunk = parts.pop(0)
            if parts:
                code = parts.pop(0)
                tag = self.map_tag(code)
                if tag:
                    current_tag = tag
            if chunk:
                try:
                    an = re.findall(r'\"[^\"]*\"|\'[^\']*\'|\S+', chunk)
                    for index, item in enumerate(an):
                        # Modify the item (e.g., double it)
                        an[index] = re.sub(r'n1n','\n',an[index])
                    if current_tag == '':
                        forceStop = 10 / 0  # to force stop the loop idk what to do else
                    self.text.insert(tk.END, an[0] + ' ', current_tag)
                    self.text.insert(tk.END, " ".join(an[1:]))
                except:
                    self.text.insert(tk.END, re.sub(r'n1n','\n',chunk))

        self.prompt_index = self.text.index("end-1c")
        self.text.see(tk.END)

    def map_tag(self, code):
        codes = code.split(';')
        try:
            base = codes[1] if codes else '0'
            bold = '1' in codes[0]
            underline = '4' in codes[0]
        except:
            base = codes[0]
            bold = False
            underline = False

        color_map = {
            '30': 'black',
            '31': 'red',
            '32': 'green',
            '33': 'yellow',
            '34': 'blue',
            '35': 'magenta',
            '36': 'cyan',
            '37': 'white',
            '90': 'gray'
        }

        color = color_map.get(base, 'white')
        tag = f"ansi_{color}"
        if bold:
            tag = f"ansi_bold_{color}"
        elif underline:
            tag = f"ansi_ul_{color}"
        return tag

    def on_mouseClick(self,event):
        self.set_cursor_to_end()
        self.text.focus_force()
        return "break"

    def on_keypress(self, event):
        self.set_cursor_to_end()
        if event.keysym in ("BackSpace", "Left", "Right", "Up", "Down", "Return"):
            return  # handled separately

        if event.char and event.char.isprintable():
            try:
                self.writing =+ 1
                self.shell.send(event.char)
            except:
                pass
        return "break"

    def ctrl_c(self, event=None):
        try:
            self.shell.send('\x03')
        except:
            pass
        return "break"

    def ctrl_d(self, event=None):
        try:
            self.shell.send('\x04')
        except:
            pass
        return "break"

    def addSpace(self,count=2):
        self.text.insert(tk.END, " " * count)

    def enter_key(self, event=None):
        line = self.text.get(self.prompt_index, "end-1c")
        self.shell.send(line + "\n")
        self.after(100,self.addSpace)
        self.prompt_index = self.text.index("end+1c")
        return "break"

    def set_cursor_to_end(self):
        self.text.mark_set(tk.INSERT, tk.END)
        self.text.see(tk.END)

    def deleteCharacter(self):
        index = self.text.index(tk.INSERT)
        line, char = map(int, index.split('.'))

        if char == 0:
            if line <= 1:
                return
            delete_from = f"{line - 1}.end"
        else:
            delete_from = f"{line}.{char - 1}"

        self.text.delete(delete_from, index)


    def backspace_key(self, event=None):
        if self.shell:  # Only try to send if shell exists
            self.shell.send('\x7f')

        #self.deleteCharacter()
        return "break"

    def close(self):
        if self.shell:
            self.shell.close()
        if self.client:
            self.client.close()


def main():
    root = tk.Tk()
    root.title("SSH Terminal (PTY + ANSI)")
    root.geometry("900x550")

    # Fill with valid credentials before testing
    hostname = "158.69.59.238"
    username = "ubuntu"
    password = "dXfXfXMKxJnb3BnDc20ccmty1EZZQZ4iyQdERdJJpnTfB3UREA"

    term = SSHTerminal(root, hostname, username, password, autoconnect=True)

    root.protocol("WM_DELETE_WINDOW", lambda: (term.close(), root.destroy()))
    root.mainloop()


if __name__ == "__main__":
    main()
