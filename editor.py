import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import customtkinter as ctk
import os
import shutil
from pygments import lex
from pygments.lexers import get_lexer_for_filename, guess_lexer_for_filename, TextLexer
from pygments.token import Token, Text
from pygments.util import ClassNotFound
from pygments.styles import get_style_by_name


class CodeEditor(ctk.CTkFrame):
    """
    A custom code editor widget for customtkinter applications,
    featuring line numbers and syntax highlighting using Pygments.
    """

    def __init__(self, master, pygments_style, **kwargs):
        """
        Initializes the CodeEditor widget.

        Args:
            master: The parent widget.
            pygments_style: The Pygments style object to use for syntax highlighting.
            **kwargs: Additional keyword arguments for CTkFrame.
        """
        super().__init__(master, **kwargs)
        self.pygments_style = pygments_style
        self.current_lexer = None
        self.current_filepath = None  # To store the path of the currently open file

        # Variables for search functionality
        self.search_term = None
        self.last_search_index = "1.0"
        self.search_dialog = None
        self.current_search_match_indices = None  # Stores (start, end) of the current search highlight

        # Configure grid for the editor frame:
        # Column 0 for line numbers (fixed width), Column 1 for editor (expands)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        # Line numbers widget (tk.Text for precise control)
        self.line_numbers = tk.Text(self, width=4, padx=3, takefocus=0, border=0,
                                    background="#282C34", foreground="#606060", state="disabled",
                                    font=("Courier New", 13, "normal"))
        self.line_numbers.grid(row=0, column=0, sticky="ns")

        # Frame to hold the main text editor and its scrollbars
        self.editor_inner_frame = ctk.CTkFrame(self)
        self.editor_inner_frame.grid(row=0, column=1, sticky="nsew")
        self.editor_inner_frame.grid_rowconfigure(0, weight=1)  # Editor row expands vertically
        self.editor_inner_frame.grid_columnconfigure(0, weight=1)  # Editor column expands horizontally
        self.editor_inner_frame.grid_columnconfigure(1, weight=0)  # Vertical scrollbar fixed width

        # File editor (tk.Text for detailed control over text and tags)
        self.file_editor = tk.Text(self.editor_inner_frame, wrap="none",
                                   font=("Courier New", 13, "bold"),
                                   background=self.pygments_style.background_color or "#282C34",
                                   foreground="#ABB2BF",  # Default readable foreground
                                   insertbackground="white",  # Cursor color
                                   selectbackground="#3A3F4B",  # Selection background
                                   selectforeground="white",  # Selection foreground
                                   border=0, relief="flat")
        self.file_editor.grid(row=0, column=0, sticky="nsew")

        # Vertical Scrollbar for the editor
        self.v_scrollbar = ctk.CTkScrollbar(self.editor_inner_frame, orientation="vertical",
                                            command=self.file_editor.yview)
        self.v_scrollbar.grid(row=0, column=1, sticky="ns")
        self.file_editor.config(yscrollcommand=self.v_scrollbar.set)

        # Horizontal Scrollbar for the editor
        self.h_scrollbar = ctk.CTkScrollbar(self.editor_inner_frame, orientation="horizontal",
                                            command=self.file_editor.xview)
        self.h_scrollbar.grid(row=1, column=0, sticky="ew")
        self.file_editor.config(xscrollcommand=self.h_scrollbar.set)

        # Chained yscrollcommand to synchronize line numbers with editor scrolling
        def chained_yview_command(*args):
            self.v_scrollbar.set(*args)
            self._on_editor_scroll_text_widget(*args)

        self.file_editor.config(yscrollcommand=chained_yview_command)

        # Set up Pygments-based text tags for syntax highlighting
        self.setup_tags()

        # Bind events to trigger highlighting and line number updates
        self.file_editor.bind("<KeyRelease>", self._on_editor_content_change)
        self.file_editor.bind("<ButtonRelease-1>", self._on_editor_content_change)
        self.file_editor.bind("<Configure>", self._on_editor_content_change)

        # Bind for occurrence highlighting on selection change
        self.file_editor.bind("<<Selection>>", self._on_selection_change)
        # Bind for search dialog
        self.file_editor.bind("<Control-f>", self._show_search_dialog)
        self.file_editor.bind("<Control-F>", self._show_search_dialog)  # For caps lock

        # Initial call to update line numbers after a short delay
        self.after(200, self._update_line_numbers_content)

    def setup_tags(self):
        """
        Configures text tags in the tk.Text widget based on the Pygments style.
        Each token type from Pygments gets a corresponding tag with its color,
        background, and font styles. Also sets up tags for occurrence and search highlighting.
        """
        text_widget = self.file_editor
        default_font_family = "Courier New"
        default_font_size = 13
        default_font_base_styles = ["normal"]  # Changed to normal for default text
        default_font = (default_font_family, default_font_size, " ".join(default_font_base_styles))

        # Set the background color of the editor based on the Pygments style
        if self.pygments_style.background_color:
            text_widget.config(bg=self.pygments_style.background_color)
        else:
            text_widget.config(bg="#282C34")  # Fallback background color

        # Configure a default tag for plain text
        text_widget.tag_config(str(Token.Text), foreground="#ABB2BF", font=default_font)

        # Iterate through Pygments style definitions and create corresponding Tkinter tags
        for token_type, style_options in self.pygments_style:
            tag_name = str(token_type)
            tk_tag_options = {}

            if style_options['color']:
                hex_color = "#" + style_options['color']
                # Special handling for black text on dark background to ensure readability
                if token_type is Token.Text and hex_color == "#000000" and text_widget.cget("bg") != "#FFFFFF":
                    tk_tag_options['foreground'] = "#ABB2BF"
                else:
                    tk_tag_options['foreground'] = hex_color

            if style_options['bgcolor']:
                tk_tag_options['background'] = "#" + style_options['bgcolor']

            current_styles_list = list(default_font_base_styles)
            if style_options['bold']:  # Check for bold style
                current_styles_list.append("bold")
            if style_options['italic']:
                current_styles_list.append("italic")
            if style_options['underline']:
                current_styles_list.append("underline")

            font_styles_string = " ".join(current_styles_list)
            tk_tag_options['font'] = (default_font_family, default_font_size, font_styles_string)

            # Apply the tag configuration if any options were set
            if tk_tag_options:
                text_widget.tag_config(tag_name, **tk_tag_options)

        # Configure a specific tag for Pygments Generic.Error tokens
        text_widget.tag_config(str(Token.Generic.Error), foreground="#FF0000", underline=True,
                               font=(default_font_family, default_font_size, "bold"))

        # Add tags for occurrence highlighting and search highlighting
        text_widget.tag_config("occurrence_highlight", background="#4A4A4A", foreground="#FFFFFF")
        text_widget.tag_config("search_highlight", background="#FFD700", foreground="#000000")  # Gold color for search

    def get_lexer_from_filename(self, filepath):
        """
        Determines the appropriate Pygments lexer based on the file extension.

        Args:
            filepath (str): The path to the file.

        Returns:
            pygments.lexer.Lexer: The determined lexer, or TextLexer if not found.
        """
        try:
            lexer = get_lexer_for_filename(filepath)
            return lexer
        except ClassNotFound:
            # Fallback to a plain text lexer if no specific lexer is found
            return TextLexer()

    def set_lexer(self, filename=''):
        """
        Sets the current lexer for the editor and re-highlights the text.

        Args:
            filename (str): The name of the file (used to determine the lexer).
        """
        self.current_lexer = self.get_lexer_from_filename(filename)
        self.highlight_text()

    def highlight_text(self, event=None):
        """
        Applies syntax highlighting to the text in the editor using the current lexer.
        Removes existing Pygments-related tags and re-applies them based on token types.
        Preserves selection, occurrence, and search highlight tags.
        """
        if not self.current_lexer:
            return

        # Remove all existing Pygments-related tags from the text
        # Exclude 'sel', 'found', 'occurrence_highlight', 'search_highlight'
        tags_to_preserve = ('sel', 'found', 'occurrence_highlight', 'search_highlight')
        for tag_name in self.file_editor.tag_names():
            if tag_name not in tags_to_preserve:
                self.file_editor.tag_remove(tag_name, "1.0", tk.END)

        code = self.file_editor.get("1.0", tk.END)
        start_index = "1.0"

        # Lex the code and apply tags based on token types
        for token_type, content in lex(code, self.current_lexer):
            end_index = self.file_editor.index(f"{start_index} + {len(content)}c")
            self.file_editor.tag_add(str(token_type), start_index, end_index)
            start_index = end_index

        # Update line numbers after highlighting (in case content changed line count)
        self._update_line_numbers_content()

    def _on_editor_content_change(self, event=None):
        """
        Event handler for content changes in the editor.
        Triggers re-highlighting and line number updates.
        """
        self.highlight_text()
        self._update_line_numbers_content()
        # The occurrence highlights are now cleared only when selection changes,
        # or when a new file is loaded, or when search dialog is closed.
        # This keeps them persistent while typing or scrolling without selection.

    def _on_editor_scroll_text_widget(self, *args):
        """
        Synchronizes the scrolling of the line number widget with the main editor.
        """
        self.line_numbers.yview("moveto", args[0])

    def _update_line_numbers_content(self):
        """
        Updates the content of the line number widget.
        Calculates the total number of lines in the editor and displays them.
        """
        self.line_numbers.config(state="normal")  # Enable editing to update content
        self.line_numbers.delete("1.0", tk.END)  # Clear existing line numbers

        # Get the total number of lines in the main editor
        total_lines = int(self.file_editor.index('end-1c').split('.')[0])
        for i in range(1, total_lines + 1):
            self.line_numbers.insert(tk.END, f"{i}\n")

        self.line_numbers.config(state="disabled")  # Disable editing after update

    def get_text(self):
        """
        Retrieves the entire text content from the editor.

        Returns:
            str: The text content of the editor.
        """
        return self.file_editor.get("1.0", tk.END)

    def set_text(self, text, filepath=None):
        """
        Sets the text content of the editor and updates the current file path.

        Args:
            text (str): The text to set in the editor.
            filepath (str, optional): The path of the file being loaded. Defaults to None.
        """
        self.file_editor.delete("1.0", tk.END)  # Clear existing content
        self.file_editor.insert("1.0", text)  # Insert new content
        self.current_filepath = filepath
        if filepath:
            self.set_lexer(filepath)
        else:
            self.set_lexer('')  # Reset lexer if no file path

        # Clear any search or occurrence highlights when new text is set
        self.file_editor.tag_remove("occurrence_highlight", "1.0", tk.END)
        self.file_editor.tag_remove("search_highlight", "1.0", tk.END)
        self.search_term = None
        self.last_search_index = "1.0"
        self.current_search_match_indices = None

    def _on_selection_change(self, event=None):
        """
        Highlights all occurrences of the selected text in the editor.
        This is triggered by the '<<Selection>>' event, which fires when the selection changes.
        """
        # Clear previous occurrence highlights
        self.file_editor.tag_remove("occurrence_highlight", "1.0", tk.END)

        try:
            # Get the indices of the current selection
            start_sel = self.file_editor.index(tk.SEL_FIRST)
            end_sel = self.file_editor.index(tk.SEL_LAST)
            selected_text = self.file_editor.get(start_sel, end_sel)

            # Only highlight if there's a non-empty, single-line selection
            if selected_text and len(selected_text) > 0 and '\n' not in selected_text:
                self._highlight_occurrences(selected_text)
        except tk.TclError:
            # This error occurs if there is no selection (e.g., after clicking away)
            # In this case, we want the highlights to persist, so do nothing here.
            pass

    def _highlight_occurrences(self, text_to_highlight):
        """
        Finds and highlights all occurrences of a given text in the editor.
        """
        if not text_to_highlight:
            return

        start_index = "1.0"
        while True:
            # Use self.file_editor.search to find occurrences
            start_index = self.file_editor.search(text_to_highlight, start_index, stopindex=tk.END, nocase=True)
            if not start_index:
                break
            end_index = f"{start_index}+{len(text_to_highlight)}c"
            self.file_editor.tag_add("occurrence_highlight", start_index, end_index)
            start_index = end_index  # Continue search from the end of the current match

    def _show_search_dialog(self, event=None):
        """
        Displays a search and replace dialog for finding text in the editor.
        """
        if self.search_dialog and self.search_dialog.winfo_exists():
            self.search_dialog.lift()  # Bring to front if already open
            return "break"  # Prevent default Ctrl-F behavior

        self.search_dialog = ctk.CTkToplevel(self)
        self.search_dialog.title("Find/Replace")
        self.search_dialog.geometry("350x200")  # Adjusted size for new elements
        self.search_dialog.transient(self)  # Make dialog transient to the main window
        self.search_dialog.grab_set()  # Grab focus
        self.search_dialog.resizable(False, False)

        # Center the dialog on the main window
        main_x = self.winfo_x()
        main_y = self.winfo_y()
        main_width = self.winfo_width()
        main_height = self.winfo_height()

        dialog_width = 350
        dialog_height = 200
        x = main_x + (main_width // 2) - (dialog_width // 2)
        y = main_y + (main_height // 2) - (dialog_height // 2)
        self.search_dialog.geometry(f"{dialog_width}x{dialog_height}+{x}+{y}")

        # Search entry
        search_label = ctk.CTkLabel(self.search_dialog, text="Find:")
        search_label.pack(pady=(10, 0))

        self.search_entry = ctk.CTkEntry(self.search_dialog, width=300)
        self.search_entry.pack(pady=5)
        self.search_entry.focus_set()
        self.search_entry.bind("<Return>", self._find_next)  # Find next on Enter key

        # Replace entry
        replace_label = ctk.CTkLabel(self.search_dialog, text="Replace with:")
        replace_label.pack(pady=(5, 0))
        self.replace_entry = ctk.CTkEntry(self.search_dialog, width=300)
        self.replace_entry.pack(pady=5)

        # Buttons frame
        button_frame = ctk.CTkFrame(self.search_dialog, fg_color="transparent")
        button_frame.pack(pady=10)

        find_next_button = ctk.CTkButton(button_frame, text="Find Next", command=self._find_next)
        find_next_button.pack(side="left", padx=5)

        find_prev_button = ctk.CTkButton(button_frame, text="Find Previous", command=self._find_previous)
        find_prev_button.pack(side="left", padx=5)

        replace_button = ctk.CTkButton(button_frame, text="Replace", command=self._replace_text)
        replace_button.pack(side="left", padx=5)

        replace_all_button = ctk.CTkButton(button_frame, text="Replace All", command=self._replace_all_text)
        replace_all_button.pack(side="left", padx=5)

        see_all_button = ctk.CTkButton(button_frame, text="See All", command=self._see_all_occurrences)
        see_all_button.pack(side="left", padx=5)

        self.search_dialog.protocol("WM_DELETE_WINDOW", self._on_search_dialog_close)

        # Return "break" to prevent the default Ctrl-F behavior (e.g., browser find)
        return "break"

    def _on_search_dialog_close(self):
        """Handles closing the search dialog."""
        self.file_editor.tag_remove("search_highlight", "1.0", tk.END)  # Clear highlights
        self.search_term = None
        self.last_search_index = "1.0"
        self.current_search_match_indices = None
        if self.search_dialog:
            self.search_dialog.destroy()
        self.search_dialog = None

    def _find_text(self, direction="forward"):
        """
        Performs the search operation in the text editor.
        Highlights the found text.
        """
        query = self.search_entry.get()
        if not query:
            return

        # Clear previous search highlights
        self.file_editor.tag_remove("search_highlight", "1.0", tk.END)
        self.current_search_match_indices = None

        if self.search_term != query:
            # New search term, reset starting point
            self.search_term = query
            self.last_search_index = "1.0"

        start_index = self.last_search_index
        if direction == "backward":
            # When searching backward, start from the current cursor position
            # If no last_search_index, start from end.
            if self.last_search_index == "1.0":  # If at the beginning, wrap around to end for backward search
                start_index = tk.END
            else:
                # To find the *previous* occurrence, we need to start searching
                # from just before the *start* of the current match.
                # If there was no previous match, this will be the end of the text.
                if self.current_search_match_indices:
                    start_index = self.current_search_match_indices[0]
                else:
                    start_index = tk.END
                start_index = self.file_editor.index(f"{start_index} - 1c")

        # Perform the search
        found_index = self.file_editor.search(
            query,
            start_index,
            stopindex="1.0" if direction == "backward" else tk.END,
            nocase=True,
            backwards=(direction == "backward"),
            count=tk.StringVar()  # Required for search to return a valid index
        )

        if found_index:
            end_index = f"{found_index}+{len(query)}c"
            self.file_editor.tag_add("search_highlight", found_index, end_index)
            self.file_editor.mark_set(tk.INSERT, found_index)  # Move cursor to start of found text
            self.file_editor.see(found_index)  # Scroll to the found text
            self.last_search_index = end_index  # Update for next search
            self.current_search_match_indices = (found_index, end_index)
        else:
            messagebox.showinfo("Search", f"'{query}' not found.", parent=self.search_dialog)
            # Reset search index if not found to allow wrapping around for next search
            self.last_search_index = "1.0" if direction == "forward" else tk.END
            self.current_search_match_indices = None

    def _find_next(self, event=None):
        """Finds the next occurrence of the search term."""
        self._find_text(direction="forward")

    def _find_previous(self, event=None):
        """Finds the previous occurrence of the search term."""
        self._find_text(direction="backward")

    def _replace_text(self):
        """
        Replaces the current highlighted search match with the replacement text.
        """
        if not self.current_search_match_indices:
            messagebox.showinfo("Replace", "No text found to replace. Please use 'Find Next' first.",
                                parent=self.search_dialog)
            return

        replace_with = self.replace_entry.get()
        start_index, end_index = self.current_search_match_indices

        try:
            self.file_editor.delete(start_index, end_index)
            self.file_editor.insert(start_index, replace_with)

            # After replacement, clear highlight and find the next occurrence
            self.file_editor.tag_remove("search_highlight", "1.0", tk.END)
            self.current_search_match_indices = None
            # Adjust last_search_index to continue search from after the replacement
            self.last_search_index = f"{start_index}+{len(replace_with)}c"
            self._find_next()  # Automatically find the next one
            self._on_editor_content_change()  # Re-highlight syntax
        except Exception as e:
            messagebox.showerror("Replace Error", f"Could not replace text: {e}", parent=self.search_dialog)

    def _replace_all_text(self):
        """
        Replaces all occurrences of the search term with the replacement text.
        """
        query = self.search_entry.get()
        replace_with = self.replace_entry.get()
        if not query:
            messagebox.showinfo("Replace All", "Please enter text to find.", parent=self.search_dialog)
            return

        confirm = messagebox.askyesno("Replace All",
                                      f"Are you sure you want to replace all occurrences of '{query}' with '{replace_with}'?",
                                      parent=self.search_dialog)
        if not confirm:
            return

        self.file_editor.tag_remove("search_highlight", "1.0", tk.END)  # Clear all search highlights first
        self.file_editor.mark_set(tk.INSERT, "1.0")  # Move cursor to beginning for replace all
        self.last_search_index = "1.0"
        self.current_search_match_indices = None

        count = 0
        while True:
            start_index = self.file_editor.search(query, "1.0", stopindex=tk.END, nocase=True)
            if not start_index:
                break
            end_index = f"{start_index}+{len(query)}c"

            self.file_editor.delete(start_index, end_index)
            self.file_editor.insert(start_index, replace_with)
            count += 1

            # After insertion, the text shifts, so we need to adjust the starting point for the next search
            # to be after the newly inserted text.
            self.file_editor.update_idletasks()  # Ensure text widget updates its internal state
            self.last_search_index = f"{start_index}+{len(replace_with)}c"
            # Since we are modifying the text, the indices might shift.
            # It's safer to restart the search from the beginning or use a more robust search mechanism
            # that accounts for text changes. For simplicity here, we'll continue from the new position.
            # A full-featured editor might re-scan the entire text after each replacement or use a regex-based approach.

        messagebox.showinfo("Replace All", f"Replaced {count} occurrences.", parent=self.search_dialog)
        self._on_editor_content_change()  # Re-highlight syntax and update line numbers

    def _see_all_occurrences(self):
        """
        Highlights all occurrences of the text in the search entry.
        """
        query = self.search_entry.get()
        if not query:
            messagebox.showinfo("See All", "Please enter text to find.", parent=self.search_dialog)
            return

        self.file_editor.tag_remove("search_highlight", "1.0", tk.END)  # Clear previous highlights
        self.current_search_match_indices = None

        start_index = "1.0"
        count = 0
        while True:
            start_index = self.file_editor.search(query, start_index, stopindex=tk.END, nocase=True)
            if not start_index:
                break
            end_index = f"{start_index}+{len(query)}c"
            self.file_editor.tag_add("search_highlight", start_index, end_index)
            start_index = end_index  # Continue search from the end of the current match
            count += 1

        if count == 0:
            messagebox.showinfo("See All", f"'{query}' not found.", parent=self.search_dialog)
        else:
            messagebox.showinfo("See All", f"Found {count} occurrences of '{query}'.", parent=self.search_dialog)


class FileExplorer(ctk.CTkFrame):
    """
    A file explorer widget for customtkinter applications,
    displaying a tree view of files and directories.
    """

    def __init__(self, master, root_path, editor_widget, **kwargs):
        super().__init__(master, **kwargs)
        self.root_path = os.path.abspath(root_path)
        self.editor_widget = editor_widget
        self.current_selected_path = None  # To store the path of the currently selected item in the treeview

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Configure ttk.Treeview style to match customtkinter dark theme
        style = ttk.Style()
        style.theme_use("default")  # Use default theme as a base
        style.configure("Treeview",
                        background="#2B2B2B",
                        foreground="#DCE0E4",
                        fieldbackground="#2B2B2B",
                        bordercolor="#2B2B2B",
                        lightcolor="#2B2B2B",
                        darkcolor="#2B2B2B",
                        rowheight=25,
                        font=("Segoe UI", 11))
        style.map('Treeview',
                  background=[('selected', '#1F6AA5')],  # Selection background
                  foreground=[('selected', '#FFFFFF')])  # Selection foreground

        style.configure("Treeview.Heading",
                        background="#343638",
                        foreground="#DCE0E4",
                        font=("Segoe UI", 11, "bold"))
        style.map("Treeview.Heading",
                  background=[('active', '#3C3F41')])

        # Treeview widget for file exploration
        self.tree = ttk.Treeview(self, show="tree", selectmode="browse")
        self.tree.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        # Scrollbars for the Treeview
        self.vsb = ctk.CTkScrollbar(self, orientation="vertical", command=self.tree.yview)
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=self.vsb.set)

        self.hsb = ctk.CTkScrollbar(self, orientation="horizontal", command=self.tree.xview)
        self.hsb.grid(row=1, column=0, sticky="ew", padx=5)
        self.tree.configure(xscrollcommand=self.hsb.set)

        # Bind selection and right-click events
        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.bind("<Button-3>", self._show_context_menu)  # Right-click

        self._populate_tree()

    def _populate_tree(self, path=None, parent_iid=''):
        """
        Populates the Treeview with files and directories from the given path.
        """
        if path is None:
            path = self.root_path
            self.tree.delete(*self.tree.get_children())  # Clear existing tree for root
            self.tree.insert('', 'end', iid=path, text=os.path.basename(path) or path, open=True, tags=('dir',))
            parent_iid = path

        try:
            for item in sorted(os.listdir(path), key=lambda s: (not os.path.isdir(os.path.join(path, s)), s.lower())):
                item_path = os.path.join(path, item)
                if os.path.isdir(item_path):
                    iid = self.tree.insert(parent_iid, 'end', iid=item_path, text=item, open=False, tags=('dir',))
                    # Add a dummy child to indicate it's a directory and can be expanded
                    self.tree.insert(iid, 'end', text='dummy')
                elif os.path.isfile(item_path):
                    self.tree.insert(parent_iid, 'end', iid=item_path, text=item, tags=('file',))
        except OSError as e:
            messagebox.showerror("File System Error", f"Could not read directory {path}: {e}")

        self.tree.bind('<<TreeviewOpen>>', self._on_tree_open)

    def _on_tree_open(self, event):
        """
        Handles the expansion of a directory in the Treeview.
        Populates the expanded directory with its contents.
        """
        item_iid = self.tree.focus()
        if not item_iid:
            return

        item_path = item_iid
        if os.path.isdir(item_path):
            # Remove dummy child if it exists
            if self.tree.get_children(item_iid) and self.tree.item(self.tree.get_children(item_iid)[0],
                                                                   'text') == 'dummy':
                self.tree.delete(self.tree.get_children(item_iid)[0])
            self._populate_tree(path=item_path, parent_iid=item_iid)

    def _on_tree_select(self, event):
        """
        Handles selection of an item in the Treeview.
        If a file is selected, its content is loaded into the CodeEditor.
        """
        selected_item_iid = self.tree.focus()
        if not selected_item_iid:
            self.current_selected_path = None
            return

        self.current_selected_path = selected_item_iid
        if os.path.isfile(selected_item_iid):
            try:
                with open(selected_item_iid, 'r', encoding='utf-8') as f:
                    content = f.read()
                self.editor_widget.set_text(content, selected_item_iid)
            except Exception as e:
                messagebox.showerror("Error Opening File", f"Could not open {selected_item_iid}: {e}")
                self.editor_widget.set_text("")  # Clear editor on error
        else:
            self.editor_widget.set_text("")  # Clear editor if a directory is selected

    def _show_context_menu(self, event):
        """
        Displays a context menu on right-click in the Treeview.
        """
        # Select the item that was right-clicked
        item_id = self.tree.identify_row(event.y)
        if item_id:
            self.tree.selection_set(item_id)
            self.tree.focus(item_id)
            self.current_selected_path = item_id  # Update selected path for context menu actions

        context_menu = tk.Menu(self.tree, tearoff=0, bg="#2B2B2B", fg="#DCE0E4",
                               activebackground="#1F6AA5", activeforeground="#FFFFFF")

        # Determine if a file or directory is selected
        is_directory = False
        is_file = False
        if item_id:
            tags = self.tree.item(item_id, 'tags')
            if 'dir' in tags:
                is_directory = True
            elif 'file' in tags:
                is_file = True

        # Always offer "New File" and "New Directory" on the root or any directory
        if item_id == self.root_path or is_directory:
            context_menu.add_command(label="New File", command=self._create_new_file)
            context_menu.add_command(label="New Directory", command=self._create_new_directory)
            context_menu.add_separator()

        # Offer "Rename" and "Delete" for any selected item (file or directory)
        if item_id and item_id != self.root_path:  # Cannot delete/rename the root path itself
            context_menu.add_command(label="Rename", command=self._rename_item)
            context_menu.add_command(label="Delete", command=self._delete_item)

        try:
            context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            context_menu.grab_release()

    def _get_target_path_for_new_item(self):
        """
        Determines the parent directory for a new file/directory.
        If a directory is selected, it's the parent. If a file is selected, its parent is the target.
        """
        if self.current_selected_path:
            if os.path.isdir(self.current_selected_path):
                return self.current_selected_path
            else:  # It's a file, so the parent directory is the target
                return os.path.dirname(self.current_selected_path)
        return self.root_path  # Fallback to root if nothing selected

    def _create_new_file(self):
        """Creates a new empty file."""
        target_dir = self._get_target_path_for_new_item()
        new_filename = simpledialog.askstring("New File", "Enter new file name:", parent=self)
        if new_filename:
            new_filepath = os.path.join(target_dir, new_filename)
            if os.path.exists(new_filepath):
                messagebox.showerror("Error", f"File '{new_filename}' already exists.")
                return
            try:
                with open(new_filepath, 'w') as f:
                    pass  # Create an empty file
                self.refresh_tree_at_path(target_dir)
                messagebox.showinfo("Success", f"File '{new_filename}' created.")
            except Exception as e:
                messagebox.showerror("Error", f"Could not create file: {e}")

    def _create_new_directory(self):
        """Creates a new empty directory."""
        target_dir = self._get_target_path_for_new_item()
        new_dirname = simpledialog.askstring("New Directory", "Enter new directory name:", parent=self)
        if new_dirname:
            new_dirpath = os.path.join(target_dir, new_dirname)
            if os.path.exists(new_dirpath):
                messagebox.showerror("Error", f"Directory '{new_dirname}' already exists.")
                return
            try:
                os.makedirs(new_dirpath)
                self.refresh_tree_at_path(target_dir)
                messagebox.showinfo("Success", f"Directory '{new_dirname}' created.")
            except Exception as e:
                messagebox.showerror("Error", f"Could not create directory: {e}")

    def _rename_item(self):
        """Renames the selected file or directory."""
        if not self.current_selected_path or self.current_selected_path == self.root_path:
            return

        old_path = self.current_selected_path
        old_name = os.path.basename(old_path)
        new_name = simpledialog.askstring("Rename", f"Rename '{old_name}' to:", initialvalue=old_name, parent=self)

        if new_name and new_name != old_name:
            parent_dir = os.path.dirname(old_path)
            new_path = os.path.join(parent_dir, new_name)
            if os.path.exists(new_path):
                messagebox.showerror("Error", f"An item named '{new_name}' already exists in this location.")
                return
            try:
                os.rename(old_path, new_path)
                # If the renamed item was the one open in editor, update editor's path
                if self.editor_widget.current_filepath == old_path:
                    self.editor_widget.current_filepath = new_path
                self.refresh_tree_at_path(parent_dir)
                messagebox.showinfo("Success", f"'{old_name}' renamed to '{new_name}'.")
            except Exception as e:
                messagebox.showerror("Error", f"Could not rename '{old_name}': {e}")

    def _delete_item(self):
        """Deletes the selected file or directory."""
        if not self.current_selected_path or self.current_selected_path == self.root_path:
            return

        item_to_delete = self.current_selected_path
        item_name = os.path.basename(item_to_delete)

        confirm = messagebox.askyesno("Confirm Delete", f"Are you sure you want to delete '{item_name}'?", parent=self)
        if confirm:
            try:
                if os.path.isdir(item_to_delete):
                    shutil.rmtree(item_to_delete)  # Delete directory and its contents
                else:
                    os.remove(item_to_delete)  # Delete file

                # If the deleted item was open in the editor, clear the editor
                if self.editor_widget.current_filepath == item_to_delete:
                    self.editor_widget.set_text("")
                    self.editor_widget.current_filepath = None

                parent_dir = os.path.dirname(item_to_delete)
                self.refresh_tree_at_path(parent_dir)
                messagebox.showinfo("Success", f"'{item_name}' deleted.")
            except Exception as e:
                messagebox.showerror("Error", f"Could not delete '{item_name}': {e}")

    def refresh_tree_at_path(self, path_to_refresh):
        """
        Refreshes a specific part of the treeview after a file system change.
        This involves deleting and re-inserting children of the parent directory.
        """
        # Find the parent of the path_to_refresh in the tree
        parent_iid = self.tree.parent(path_to_refresh)
        if not parent_iid and path_to_refresh == self.root_path:
            # If refreshing the root, just re-populate the entire tree
            self._populate_tree()
            return
        elif not parent_iid:  # This means path_to_refresh is likely the root itself, but not explicitly handled by the first condition
            parent_iid = self.root_path  # Assume root if not found and not the root itself

        # Clear existing children of the parent
        for child in self.tree.get_children(parent_iid):
            self.tree.delete(child)

        # Re-populate the parent directory
        self._populate_tree(path=parent_iid, parent_iid=parent_iid)
        self.tree.item(parent_iid, open=True)  # Ensure the parent stays open


class App(ctk.CTk):
    """
    Main application window for the Code Editor and File Explorer.
    """

    def __init__(self):
        super().__init__()

        self.title("Code Editor & File Explorer")
        self.geometry("1200x800")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=0)  # File Explorer column (fixed width)
        self.grid_columnconfigure(1, weight=1)  # Code Editor column (expands)

        # Get Pygments style
        self.pygments_style = get_style_by_name("monokai")  # Or any other preferred style

        # Code Editor instance
        self.code_editor = CodeEditor(self, pygments_style=self.pygments_style, corner_radius=0)
        self.code_editor.grid(row=0, column=1, sticky="nsew")

        # File Explorer instance
        # Use a temporary directory for demonstration, or let the user choose
        self.initial_dir = os.path.join(os.path.expanduser("~"), "code_editor_files")
        os.makedirs(self.initial_dir, exist_ok=True)  # Ensure the directory exists

        self.file_explorer = FileExplorer(self, root_path=self.initial_dir, editor_widget=self.code_editor,
                                          corner_radius=0)
        self.file_explorer.grid(row=0, column=0, sticky="nswe")

        # Frame for editor controls (Save button)
        self.editor_controls_frame = ctk.CTkFrame(self, height=50, corner_radius=0)
        self.editor_controls_frame.grid(row=1, column=1, sticky="ew", padx=5, pady=5)
        self.editor_controls_frame.grid_columnconfigure(0, weight=1)  # Makes the save button align left

        self.save_button = ctk.CTkButton(self.editor_controls_frame, text="Save File", command=self.save_current_file)
        self.save_button.pack(side="left", padx=10, pady=5)

    def save_current_file(self):
        """
        Saves the content of the current file editor to its associated file path.
        If no file is open, it prompts the user to save as a new file.
        """
        filepath = self.code_editor.current_filepath
        content = self.code_editor.get_text()

        if filepath:
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
                messagebox.showinfo("Save File", f"File saved successfully to {os.path.basename(filepath)}")
            except Exception as e:
                messagebox.showerror("Save Error", f"Could not save file: {e}")
        else:
            self._save_file_as()

    def _save_file_as(self):
        """Prompts the user to save the current editor content to a new file."""
        filepath = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("All Files", "*.*"), ("Text Documents", "*.txt"), ("Python Files", "*.py")],
            parent=self
        )
        if filepath:
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(self.code_editor.get_text())
                self.code_editor.set_text(self.code_editor.get_text(), filepath)  # Update editor's current_filepath
                self.file_explorer.refresh_tree_at_path(os.path.dirname(filepath))  # Refresh explorer
                messagebox.showinfo("Save File", f"File saved as {os.path.basename(filepath)}")
            except Exception as e:
                messagebox.showerror("Save Error", f"Could not save file: {e}")


if __name__ == "__main__":
    ctk.set_appearance_mode("dark")  # Modes: "System" (default), "Dark", "Light"
    ctk.set_default_color_theme("blue")  # Themes: "blue" (default), "green", "dark-blue"

    app = App()
    app.mainloop()
