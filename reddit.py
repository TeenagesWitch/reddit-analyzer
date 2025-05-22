#!/usr/bin/env python3
import threading
import json
import os
import webbrowser
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


def extract_unique_authors(file_paths):
    unique_authors = set()
    for path in file_paths:
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    author = data.get("author")
                    if author:
                        unique_authors.add(author)
                except json.JSONDecodeError:
                    continue
    return sorted(unique_authors)


def load_authors_from_txt(files, skip_list=None, skip_bots=True):
    if skip_list is None:
        skip_set = {"[deleted]", "automoderator", "thesunflowerseeds", "waitingtobetriggered", "b0trank"}
    else:
        skip_set = set(skip_list)
    authors = set()
    for path in files:
        if not os.path.isfile(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                author = line.strip()
                if not author:
                    continue
                lower = author.lower()
                if lower in skip_set:
                    continue
                if skip_bots and lower.endswith("bot"):
                    continue
                authors.add(author)
    return authors


class GUIApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Author Tools GUI")
        self.default_skips = ["[deleted]", "automoderator", "thesunflowerseeds", "waitingtobetriggered", "b0trank"]
        self.skip_list = list(self.default_skips)
        self.skip_bots = tk.BooleanVar(value=True)
        self._build_ui()

    def _build_ui(self):
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True)

        tab1 = ttk.Frame(notebook)
        notebook.add(tab1, text="Extract Unique Authors")
        self._build_unique_tab(tab1)

        tab2 = ttk.Frame(notebook)
        notebook.add(tab2, text="Find Overlapping Authors")
        self._build_overlap_tab(tab2)

        tab3 = ttk.Frame(notebook)
        notebook.add(tab3, text="Settings")
        self._build_settings_tab(tab3)

    def _build_unique_tab(self, parent):
        frame = ttk.Frame(parent, padding=10)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Select JSONL files:").grid(row=0, column=0, sticky="w")
        self.jsonl_paths = [tk.StringVar(), tk.StringVar()]
        for i in range(2):
            ttk.Entry(frame, textvariable=self.jsonl_paths[i], width=50).grid(row=i+1, column=0, padx=5, pady=5)
            ttk.Button(frame, text="Browse...", command=lambda idx=i: self._browse_jsonl(idx)).grid(row=i+1, column=1)

        self.unique_count = tk.StringVar(value="Total unique authors: 0")
        ttk.Label(frame, textvariable=self.unique_count).grid(row=3, column=0, pady=10)

        self.extract_btn = ttk.Button(frame, text="Extract & Save", command=self._handle_unique_async)
        self.extract_btn.grid(row=4, column=0, columnspan=2, pady=5)

        self.progress = ttk.Progressbar(frame, mode='indeterminate')
        self.progress.grid(row=5, column=0, columnspan=2, sticky="ew", pady=5)

    def _handle_unique_async(self):
        paths = [var.get() for var in self.jsonl_paths]
        if not all(os.path.isfile(p) for p in paths):
            messagebox.showerror("Error", "Please select two valid JSONL files.")
            return

        save_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")])
        if not save_path:
            return

        self.extract_btn.config(state='disabled')
        self.progress.start(10)

        def run():
            try:
                authors = extract_unique_authors(paths)
                with open(save_path, "w", encoding="utf-8") as f:
                    for a in authors:
                        f.write(a + "\n")
                self.root.after(0, lambda: self._on_unique_done(len(authors), save_path))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))
                self.root.after(0, self._reset_progress)

        threading.Thread(target=run, daemon=True).start()

    def _on_unique_done(self, count, path):
        self.unique_count.set(f"Total unique authors: {count}")
        self._reset_progress()
        messagebox.showinfo("Saved", f"Saved to {path}")

    def _reset_progress(self):
        self.progress.stop()
        self.extract_btn.config(state='normal')

    def _build_overlap_tab(self, parent):
        frame = ttk.Frame(parent, padding=10)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Select TXT files for Set 1:").grid(row=0, column=0, sticky="w")
        self.txt_set1, self.txt_set2 = [], []
        self.set1_var = tk.StringVar(value="No files selected")
        self.set2_var = tk.StringVar(value="No files selected")
        ttk.Label(frame, textvariable=self.set1_var).grid(row=1, column=0, sticky="w")
        ttk.Button(frame, text="Browse...", command=lambda: self._browse_txt_set(1)).grid(row=1, column=1)
        ttk.Label(frame, textvariable=self.set2_var).grid(row=3, column=0, sticky="w")
        ttk.Button(frame, text="Browse...", command=lambda: self._browse_txt_set(2)).grid(row=3, column=1)

        self.overlap_count = tk.StringVar(value="Overlapping authors: 0")
        ttk.Label(frame, textvariable=self.overlap_count).grid(row=4, column=0, pady=10)
        ttk.Button(frame, text="Compute Overlap", command=self._handle_overlap).grid(row=5, column=0)

    def _build_settings_tab(self, parent):
        frame = ttk.Frame(parent, padding=10)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text="Skip List (select an item and click Delete):").pack(anchor="w")

        list_frame = ttk.Frame(frame)
        list_frame.pack(fill="both", expand=True, pady=5)
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")
        self.skip_listbox = tk.Listbox(
            list_frame,
            selectmode="browse",
            yscrollcommand=scrollbar.set,
            height=6
        )
        self.skip_listbox.pack(fill="both", expand=True)
        scrollbar.config(command=self.skip_listbox.yview)
        for item in self.skip_list:
            self.skip_listbox.insert("end", item)

        ttk.Button(frame, text="Delete Selected", command=self._delete_selected_skip).pack(pady=(0,10))

        add_frame = ttk.Frame(frame)
        add_frame.pack(fill="x", pady=5)
        self.new_skip_var = tk.StringVar()
        ttk.Entry(add_frame, textvariable=self.new_skip_var, width=30).grid(row=0, column=0)
        ttk.Button(add_frame, text="Add", command=self._add_skip).grid(row=0, column=1, padx=5)

        ttk.Checkbutton(
            frame,
            text="Skip usernames ending with 'bot'",
            variable=self.skip_bots
        ).pack(anchor="w", pady=10)

        ttk.Button(frame, text="Reset to Default", command=self._reset_settings).pack()

    def _delete_selected_skip(self):
        sel = self.skip_listbox.curselection()
        if sel:
            idx = sel[0]
            self.skip_listbox.delete(idx)
            del self.skip_list[idx]

    def _add_skip(self):
        val = self.new_skip_var.get().strip().lower()
        if val and val not in self.skip_list:
            self.skip_list.append(val)
            self.skip_listbox.insert("end", val)
        self.new_skip_var.set("")

    def _reset_settings(self):
        self.skip_list = list(self.default_skips)
        self.skip_bots.set(True)
        self.skip_listbox.delete(0, "end")
        for item in self.skip_list:
            self.skip_listbox.insert("end", item)

    def _browse_jsonl(self, idx):
        path = filedialog.askopenfilename(filetypes=[("JSONL files","*.jsonl"),("All files","*")])
        if path:
            self.jsonl_paths[idx].set(path)

    def _browse_txt_set(self, set_no):
        files = filedialog.askopenfilenames(filetypes=[("Text files","*.txt"),("All files","*")])
        if files:
            names = ", ".join(os.path.basename(f) for f in files)
            if set_no==1:
                self.txt_set1 = list(files); self.set1_var.set(names)
            else:
                self.txt_set2 = list(files); self.set2_var.set(names)

    def _handle_overlap(self):
        if not (self.txt_set1 and self.txt_set2):
            messagebox.showwarning("Missing Files","Select both sets")
            return
        skip_bots = self.skip_bots.get()
        overlap = sorted(
            load_authors_from_txt(self.txt_set1,self.skip_list,skip_bots)
            & load_authors_from_txt(self.txt_set2,self.skip_list,skip_bots)
        )
        self.overlap_count.set(f"Overlapping authors: {len(overlap)}")
        if not overlap:
            messagebox.showinfo("No Overlap","No overlapping authors")
            return
        self._show_overlap_popup(overlap)

    def _show_overlap_popup(self, overlap):
        popup = tk.Toplevel(self.root)
        popup.title("Overlapping Authors")
        popup.geometry("500x400")

        ttk.Label(popup,text="Files and Overlapping Authors:").pack(pady=5)
        fframe = ttk.Frame(popup)
        fframe.pack(fill="x",padx=10)
        ttk.Label(fframe,text="Set1:").grid(row=0,column=0,sticky="w")
        ttk.Label(fframe,text=self.set1_var.get()).grid(row=0,column=1,sticky="w")
        ttk.Label(fframe,text="Set2:").grid(row=1,column=0,sticky="w")
        ttk.Label(fframe,text=self.set2_var.get()).grid(row=1,column=1,sticky="w")

        frame = ttk.Frame(popup)
        frame.pack(fill="both",expand=True,pady=10)
        sb = ttk.Scrollbar(frame)
        sb.pack(side="right",fill="y")
        lb = tk.Listbox(frame,yscrollcommand=sb.set)
        for a in overlap: lb.insert("end",a)
        lb.pack(side="left",fill="both",expand=True)
        sb.config(command=lb.yview)
        lb.bind("<Double-1>",lambda e:self._open_profile(lb))

        btnf = ttk.Frame(popup)
        btnf.pack(pady=10)
        ttk.Button(btnf,text="Save List",command=lambda:self._save_overlap_list(overlap,popup)).grid(row=0,column=0,padx=5)
        ttk.Button(btnf,text="Close",command=popup.destroy).grid(row=0,column=1,padx=5)

    def _open_profile(self, lb):
        sel = lb.curselection()
        if sel:
            u = lb.get(sel[0])
            webbrowser.open_new_tab(f"https://www.reddit.com/user/{u}")

    def _save_overlap_list(self, overlap, pop):
        path = filedialog.asksaveasfilename(defaultextension=".txt",filetypes=[("Text files","*.txt")])
        if path:
            with open(path,"w",encoding="utf-8") as f:
                for a in overlap: f.write(a+"\n")
            messagebox.showinfo("Saved",f"Saved to {path}")
            pop.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    app = GUIApp(root)
    root.mainloop()