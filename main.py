import customtkinter as ctk
import tkinter as tk
import multiprocessing
import os
import json
import stat
import socket
import time
import queue
import terminal # Assuming terminal.py exists and contains SSHTerminal class
from multiprocessing.connection import Listener, Client
from pygments.styles import get_style_by_name # Needed for pygments_style
from editor import CodeEditor # Import the new CodeEditor class

# Set customtkinter appearance mode and default color theme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# Configuration file for saving host information
CONFIG_FILE = "saved_hosts.json"


# Background process SSH handler
def ssh_worker(address):
    """
    A separate process to handle SSH/SFTP connections and operations.
    It listens for commands from the main process and executes them.
    """
    # Import paramiko here to avoid issues with multiprocessing on Windows
    # (paramiko is not picklable)
    from paramiko import SSHClient, AutoAddPolicy
    import paramiko

    listener = Listener(address, authkey=b'ssh')
    ssh = None
    sftp = None
    shell = None

    while True:
        conn = listener.accept() # Accept a connection from the main process
        try:
            msg = conn.recv() # Receive the command message
            cmd = msg["cmd"]

            if cmd == "connect":
                # Establish SSH connection
                host = msg["host"]
                ssh = SSHClient()
                ssh.set_missing_host_key_policy(AutoAddPolicy()) # Automatically add host keys
                ssh.connect(hostname=host["ip"], username=host["username"], password=host["password"])
                sftp = ssh.open_sftp() # Open SFTP client
                shell = ssh.invoke_shell() # Invoke an interactive shell
                shell.settimeout(0.1) # Set a timeout for shell operations
                conn.send({"status": "connected"})
            elif cmd == "listdir":
                # List directory contents via SFTP
                path = msg["path"]
                items = sftp.listdir_attr(path)
                result = []
                if path not in (".", "/", ""):
                    result.append(("📁", "..")) # Add ".." for navigating up
                for item in items:
                    icon = "📁" if stat.S_ISDIR(item.st_mode) else "📄" # Determine icon based on file type
                    result.append((icon, item.filename))
                conn.send(result)
            elif cmd == "read_file":
                # Read file content via SFTP
                path = msg["path"]
                with sftp.open(path, "r") as f:
                    content = f.read().decode("utf-8", errors="ignore") # Read and decode content
                conn.send(content)
            elif cmd == "write_file":
                # Write data to a file via SFTP
                path = msg["path"]
                data = msg["data"]
                with sftp.open(path, "w") as f:
                    f.write(data)
                conn.send("ok")
            elif cmd == "send_command":
                # Send a command to the SSH shell
                shell.send(msg["data"] + "\n")
                time.sleep(0.1) # Give time for command to execute
                output = b""
                while shell.recv_ready(): # Read all available output
                    output += shell.recv(4096)
                conn.send(output.strip()) # Send stripped output back
        except Exception as e:
            # Send error message back to the main process
            conn.send({"error": str(e)})
        finally:
            conn.close() # Close the connection after handling the command


class SSHClientApp(ctk.CTk):
    """
    Main application class for the SSH/SFTP client.
    Manages the UI, host connections, file browsing, editing, and terminal.
    """
    def __init__(self):
        super().__init__()
        self.title("SSH/SFTP Client")
        self.geometry("1200x650")
        self.protocol("WM_DELETE_WINDOW", self.on_close) # Handle window close event

        self.current_path = "." # Current remote directory path
        self.current_file = None # Currently opened remote file

        self.ui_queue = queue.Queue() # Queue for inter-process communication (not used in this version but kept)
        self.hosts = self.load_hosts() # Load saved SSH hosts
        self.create_widgets() # Initialize UI widgets
        self.after(10, self.process_ui_queue) # Start processing UI queue (if used)

        # Setup multiprocessing for SSH worker
        self.process_address = ("localhost", 6000)
        self.worker = multiprocessing.Process(target=ssh_worker, args=(self.process_address,))
        self.worker.start() # Start the SSH worker process

    def load_hosts(self):
        """Loads saved host configurations from a JSON file."""
        if not os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "w") as f:
                json.dump([], f) # Create an empty file if it doesn't exist
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)

    def save_hosts(self):
        """Saves current host configurations to the JSON file."""
        with open(CONFIG_FILE, "w") as f:
            json.dump(self.hosts, f, indent=4) # Save with indentation for readability

    def create_widgets(self):
        """Creates and arranges all UI widgets."""
        # Configure main window grid layout
        self.grid_rowconfigure(0, weight=1) # Main content row expands vertically
        self.grid_columnconfigure(0, weight=0) # Left frame (host list) fixed width
        self.grid_columnconfigure(1, weight=3) # Middle tabview (explorer/editor) takes more space
        self.grid_columnconfigure(2, weight=2) # Right frame (terminal) takes less space

        # Left Frame: Host View
        self.left_frame = ctk.CTkFrame(self, width=250)
        self.left_frame.grid(row=0, column=0, sticky="nswe", padx=5, pady=5)
        self.left_frame.grid_rowconfigure(1, weight=1) # Host listbox expands vertically
        self.left_frame.grid_columnconfigure(0, weight=1) # Content expands horizontally

        ctk.CTkLabel(self.left_frame, text="Saved Hosts", font=("Arial", 16)).grid(row=0, column=0, pady=10)
        self.host_listbox = tk.Listbox(self.left_frame)
        self.host_listbox.grid(row=1, column=0, sticky="nsew", padx=10)
        self.host_listbox.bind("<<ListboxSelect>>", self.connect_selected_host) # Bind selection event
        self.host_listbox.config(bg="black", fg="white", selectbackground="#303030", selectforeground="white")

        self.refresh_host_list() # Populate the host listbox
        ctk.CTkButton(self.left_frame, text="Add Host", command=self.add_host_popup).grid(row=2, column=0, pady=10)

        # Middle Section: Tabview (Explorer and Editor)
        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        self.tabview.add("Explorer")
        self.tabview.add("Editor")

        # Explorer Tab Content
        explorerTab = self.tabview.tab("Explorer")
        explorerTab.grid_rowconfigure(1, weight=1) # File listbox expands vertically
        explorerTab.grid_columnconfigure(0, weight=1) # Content expands horizontally

        self.path_label = ctk.CTkLabel(explorerTab, text="Path: .")
        self.path_label.grid(row=0, column=0, sticky="w", padx=10, pady=(5, 0))

        self.file_listbox = tk.Listbox(explorerTab)
        self.file_listbox.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        self.file_listbox.bind("<<ListboxSelect>>", self.file_list_click) # Bind file selection event
        self.file_listbox.config(bg="black", fg="white", selectbackground="#303030", selectforeground="white")

        # Editor Tab Content
        editorTab = self.tabview.tab("Editor")
        editorTab.grid_rowconfigure(0, weight=1) # Editor widget expands vertically
        editorTab.grid_columnconfigure(0, weight=1) # Editor widget expands horizontally

        # Instantiate the CodeEditor widget from editor.py
        self.editor_widget = CodeEditor(editorTab, pygments_style=get_style_by_name('lightbulb'))
        self.editor_widget.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        self.saveButton = ctk.CTkButton(editorTab, text="Save to Server", command=self.save_file_to_server)
        self.saveButton.grid(row=1, column=0, pady=(0, 10))

        # Right Frame: SSH Terminal
        self.right_frame = ctk.CTkFrame(self, width=600)
        self.right_frame.grid(row=0, column=2, sticky="nsew", padx=5, pady=5)
        self.right_frame.grid_rowconfigure(1, weight=1) # Console output expands vertically
        self.right_frame.grid_columnconfigure(0, weight=1) # Content expands horizontally

        ctk.CTkLabel(self.right_frame, text="SSH Terminal", font=("Arial", 16)).pack()
        # Assuming terminal.py provides an SSHTerminal widget
        self.console_output = terminal.SSHTerminal(self.right_frame)


    def send_to_worker(self, message):
        """
        Sends a message to the SSH worker process and receives its response.

        Args:
            message (dict): The command and data to send to the worker.

        Returns:
            dict: The response from the worker process, or an error dictionary.
        """
        try:
            conn = Client(self.process_address, authkey=b'ssh')
            conn.send(message)
            response = conn.recv()
            conn.close()
            return response
        except Exception as e:
            return {"error": str(e)}

    def refresh_host_list(self):
        """Clears and repopulates the host listbox with current saved hosts."""
        self.host_listbox.delete(0, tk.END)
        for host in self.hosts:
            name = host.get("name", "Unnamed")
            display = f" {name} ({host['username']}@{host['ip']})"
            self.host_listbox.insert(tk.END, display)

    def add_host_popup(self):
        """Opens a new window to add a new SSH host configuration."""
        popup = ctk.CTkToplevel(self)
        popup.title("Add Host")
        popup.geometry("300x300")
        popup.grid_rowconfigure((0,1,2,3,4), weight=0) # Rows for entries and button (fixed height)
        popup.grid_columnconfigure(0, weight=1) # Column for entries and button (expands horizontally)

        name_entry = ctk.CTkEntry(popup, placeholder_text="Name")
        name_entry.grid(row=0, column=0, pady=5, padx=20, sticky="ew")
        ip_entry = ctk.CTkEntry(popup, placeholder_text="IP")
        ip_entry.grid(row=1, column=0, pady=5, padx=20, sticky="ew")
        user_entry = ctk.CTkEntry(popup, placeholder_text="Username")
        user_entry.grid(row=2, column=0, pady=5, padx=20, sticky="ew")
        pass_entry = ctk.CTkEntry(popup, placeholder_text="Password", show="*")
        pass_entry.grid(row=3, column=0, pady=5, padx=20, sticky="ew")

        def save_host():
            """Saves the new host details and updates the host list."""
            self.hosts.append({"name": name_entry.get(), "ip": ip_entry.get(), "username": user_entry.get(),
                               "password": pass_entry.get()})
            self.save_hosts()
            self.refresh_host_list()
            popup.destroy() # Close the popup window

        ctk.CTkButton(popup, text="Save", command=save_host).grid(row=4, column=0, pady=10)

    def connect_selected_host(self, _):
        """
        Connects to the selected host from the listbox.
        Triggers SSH connection in the terminal and lists remote directory.
        """
        sel = self.host_listbox.curselection()
        if not sel: return # Do nothing if no host is selected
        host = self.hosts[sel[0]] # Get the selected host object
        self.console_output.connect(host['ip'], host['username'], host['password']) # Connect terminal
        res = self.send_to_worker({"cmd": "connect", "host": host}) # Send connect command to worker
        self.append_console(f"Connection result: {res}")
        self.list_remote_dir() # List the remote directory after connection

    def list_remote_dir(self):
        """Lists the contents of the current remote directory."""
        res = self.send_to_worker({"cmd": "listdir", "path": self.current_path})
        if "error" in res:
            self.append_console(f"Error listing directory: {res['error']}")
            return
        self.file_listbox.delete(0, tk.END) # Clear existing file list
        self.path_label.configure(text=f"Path: {self.current_path}") # Update path label
        for icon, name in res:
            self.file_listbox.insert(tk.END, f"{icon} {name}") # Insert files/directories with icons

    def file_list_click(self, _):
        """
        Handles clicks on items in the file listbox.
        Navigates directories or opens files in the editor.
        """
        sel = self.file_listbox.curselection()
        if not sel: return
        name = self.file_listbox.get(sel[0])[2:].strip() # Extract name, removing icon
        if name == "..":
            # Navigate up one directory
            self.current_path = os.path.dirname(self.current_path) or "."
            self.list_remote_dir()
            return

        path = f"{self.current_path}/{name}".replace("//", "/") # Construct full path
        res = self.send_to_worker({"cmd": "read_file", "path": path}) # Try to read as a file
        if isinstance(res, dict) and "error" in res:
            # If it's an error, assume it's a directory and try to list it
            self.current_path = path
            self.list_remote_dir()
        else:
            # If successful, it's a file: open in editor
            self.current_file = path
            self.tabview.set("Editor") # Switch to the editor tab
            self.editor_widget.set_text(res) # Set text content using CodeEditor's method
            self.editor_widget.set_lexer(path) # Set lexer for syntax highlighting
            self.append_console(f"Opened: {path}")

    def animateButton(self,text,element):
        """
        Temporarily changes a button's text for a short duration.
        Used for feedback like "Saved!".
        """
        atext = element.cget("text") # Store original text
        def resetText():
            element.configure(text=atext) # Restore original text
        element.configure(text=text) # Set new text
        element.after(5000,resetText) # Schedule reset after 5 seconds

    def save_file_to_server(self):
        """Saves the content of the editor to the currently opened remote file."""
        if not self.current_file: return # Do nothing if no file is open
        content = self.editor_widget.get_text() # Get text content from CodeEditor
        res = self.send_to_worker({"cmd": "write_file", "path": self.current_file, "data": content})
        self.animateButton(f"Saved ! {res}",self.saveButton) # Provide feedback

    def append_console(self, text):
        """Appends text to the console output (prints to standard output for now)."""
        print(text) # In a real app, this would update a console UI widget

    def process_ui_queue(self):
        """Processes messages from the UI queue (if any)."""
        while not self.ui_queue.empty():
            msg = self.ui_queue.get()
            self.append_console(msg)
        self.after(10, self.process_ui_queue) # Schedule next check

    def on_close(self):
        """Handles application shutdown, terminating the SSH worker process."""
        try:
            self.console_output.close() # Close terminal connection
            self.worker.terminate() # Terminate the background SSH worker
        except:
            pass # Ignore errors during shutdown
        self.destroy() # Destroy the main application window


if __name__ == "__main__":
    # Essential for multiprocessing on some platforms (e.g., Windows)
    multiprocessing.set_start_method("spawn")
    app = SSHClientApp()
    app.mainloop() # Start the Tkinter event loop
