import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import os
import threading
import queue
from pymediainfo import MediaInfo
from functools import partial # For sorting

# --- Configuration ---
MAX_VIDEO_SIZE_MB = 60
MAX_IMAGE_SIZE_KB = 150
VALID_HYPHEN_COUNTS = {3, 4}
STANDARD_RESOLUTIONS = {
    (1920, 1080), (1280, 720), (960, 540),
    (720, 1280), (1080, 1920), (540, 960),
    (1080, 607), (607, 1080) 
}
VALID_VIDEO_WIDTHS = {720, 1280}
VALID_VIDEO_HEIGHTS = {720, 1280}
MIN_FRAME_RATE = 20  # fps, less than or equal to this is red
MIN_TOTAL_BITRATE_KBPS = 1000 # kbps, less than this is red
MIN_VIDEO_BITRATE_KBPS = 64 # kbps, less than this is red
EXPECTED_VIDEO_CODECS = ["H.264", "AVC"] # Now a list, check if format is IN this list
MAX_VIDEO_DURATION_S = 60 # seconds, more than this is yellow

# --- Helper Functions ---
def format_size(size_bytes):
    if size_bytes is None: return "N/A"
    if size_bytes == 0: return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = 0
    power = 1024
    while size_bytes >= power and i < len(size_name) - 1:
        size_bytes /= power
        i += 1
    return f"{size_bytes:.2f}{size_name[i]}"

def format_duration(ms):
    if ms is None: return "N/A"
    try:
        s = int(ms) // 1000
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
    except: return "N/A"

def format_bitrate_kbps(bps):
    if bps is None: return "N/A"
    try: return f"{int(bps) // 1000:.0f} kbps"
    except: return "N/A"

def format_framerate_fps(fps_value):
    if fps_value is None: return "N/A"
    try: return f"{float(fps_value):.2f} fps"
    except: return "N/A"

# --- Core Logic ---
def get_media_info_with_rules(file_path):
    filename = os.path.basename(file_path)
    extension = os.path.splitext(filename)[1].lower()
    issues_red = []
    issues_yellow = []
    color = "green" # Default to green

    details = {
        "filename": filename,
        "size": "N/A",
        "extension": extension,
        "duration": "N/A",
        "resolution": "N/A",
        "bitrate": "N/A",
        "total_bitrate": "N/A",
        "frame_height": "N/A",
        "frame_width": "N/A",
        "frame_rate": "N/A",
        "video_codec": "N/A",
        "issues": [],
        "color": color
    }

    try:
        size_bytes = os.path.getsize(file_path)
        details["size"] = format_size(size_bytes)

        is_video = extension in (".mp4", ".mov", ".avi", ".mkv", ".flv", ".wmv", ".webm")
        is_image = extension in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff")

        # Rule: Filename hyphen count
        if filename.count('-') not in VALID_HYPHEN_COUNTS:
            issues_red.append(f"文件名'-'数量应为{VALID_HYPHEN_COUNTS}")

        # Rule: Filename contains space (excluding full-width spaces and parentheses)
        contains_half_width_space = False
        for char in filename:
            if char == ' ':
                contains_half_width_space = True
                break
        if contains_half_width_space:
            issues_yellow.append("文件名包含半角空格")

        if is_video:
            if size_bytes > MAX_VIDEO_SIZE_MB * 1024 * 1024:
                issues_red.append(f"视频文件 > {MAX_VIDEO_SIZE_MB}MB")
            
            media_info = MediaInfo.parse(file_path)
            video_track = next((t for t in media_info.tracks if t.track_type == 'Video'), None)
            general_track = next((t for t in media_info.tracks if t.track_type == 'General'), None)

            if video_track:
                details["duration"] = format_duration(video_track.duration)
                if video_track.duration and (video_track.duration / 1000) > MAX_VIDEO_DURATION_S:
                    issues_yellow.append(f"时长 > {MAX_VIDEO_DURATION_S}s")
                
                details["frame_width"] = video_track.width
                details["frame_height"] = video_track.height
                if video_track.width and video_track.height:
                    details["resolution"] = f"{video_track.width}x{video_track.height}"
                    if video_track.width not in VALID_VIDEO_WIDTHS:
                        issues_red.append(f"视频宽度非{VALID_VIDEO_WIDTHS}")
                    if video_track.height not in VALID_VIDEO_HEIGHTS:
                        issues_red.append(f"视频高度非{VALID_VIDEO_HEIGHTS}")
                else:
                    issues_red.append("无视频宽高信息")

                details["frame_rate"] = format_framerate_fps(video_track.frame_rate)
                if video_track.frame_rate and float(video_track.frame_rate) <= MIN_FRAME_RATE:
                    issues_red.append(f"帧率 <= {MIN_FRAME_RATE}fps")
                elif not video_track.frame_rate:
                     issues_red.append("无帧率信息")

                details["bitrate"] = format_bitrate_kbps(video_track.bit_rate)
                if video_track.bit_rate and (video_track.bit_rate / 1000) < MIN_VIDEO_BITRATE_KBPS:
                    issues_red.append(f"视频比特率 < {MIN_VIDEO_BITRATE_KBPS}kbps")
                elif not video_track.bit_rate:
                    issues_red.append("无视频比特率信息")
                
                details["video_codec"] = video_track.format
                if video_track.format:
                    is_expected_codec = False
                    for codec in EXPECTED_VIDEO_CODECS:
                        if codec.lower() in video_track.format.lower():
                            is_expected_codec = True
                            break
                    if not is_expected_codec:
                        issues_yellow.append(f"视频编码非 {', '.join(EXPECTED_VIDEO_CODECS)}") # Changed to issues_yellow
                elif not video_track.format:
                    issues_red.append("无视频编码信息")

            if general_track:
                details["total_bitrate"] = format_bitrate_kbps(general_track.overall_bit_rate)
                if general_track.overall_bit_rate and (general_track.overall_bit_rate / 1000) < MIN_TOTAL_BITRATE_KBPS:
                    issues_red.append(f"总比特率 < {MIN_TOTAL_BITRATE_KBPS}kbps")
                elif not general_track.overall_bit_rate and video_track: # Only red if it's a video and no overall bitrate
                    issues_red.append("无总比特率信息")
            elif video_track: # If it's a video but no general track for overall bitrate
                 issues_red.append("无总比特率信息(General Track)")

            if not video_track and not general_track:
                issues_red.append("无法解析视频信息")

        elif is_image:
            if size_bytes > MAX_IMAGE_SIZE_KB * 1024:
                issues_red.append(f"图片 > {MAX_IMAGE_SIZE_KB}KB")
            
            media_info = MediaInfo.parse(file_path)
            image_track = next((t for t in media_info.tracks if t.track_type == 'Image'), None)
            if image_track:
                details["frame_width"] = image_track.width
                details["frame_height"] = image_track.height
                if image_track.width and image_track.height:
                    details["resolution"] = f"{image_track.width}x{image_track.height}"
                    if (image_track.width, image_track.height) not in STANDARD_RESOLUTIONS:
                        issues_red.append("图片分辨率非标准")
                else:
                    issues_red.append("无图片尺寸信息")
            else:
                issues_red.append("无法解析图片信息")
        else:
            issues_red.append("非标准视频或图片文件")

    except Exception as e:
        issues_red.append(f"处理错误: {str(e)}")

    if issues_red:
        details["color"] = "red"
        details["issues"] = issues_red
    elif issues_yellow:
        details["color"] = "yellow"
        details["issues"] = issues_yellow
    else:
        details["color"] = "green"
        details["issues"] = ["无问题"]
        
    return details

class MediaAnalyzerApp:
    def __init__(self, master):
        self.master = master
        master.title("媒体文件分析器")
        master.geometry("1200x700")

        self.file_queue = queue.Queue()
        self.results_queue = queue.Queue()
        self.processing_thread = None
        self.stop_processing = threading.Event()
        self.item_id_counter = 0
        self.display_order_counter = 1 # For maintaining initial add order

        # --- UI Elements ---
        # Top frame for buttons
        top_frame = ttk.Frame(master, padding="10")
        top_frame.pack(fill=tk.X)

        self.select_files_button = ttk.Button(top_frame, text="选择文件", command=self.select_files)
        self.select_files_button.pack(side=tk.LEFT, padx=5)

        self.select_folder_button = ttk.Button(top_frame, text="选择文件夹", command=self.select_folder)
        self.select_folder_button.pack(side=tk.LEFT, padx=5)
        
        self.clear_button = ttk.Button(top_frame, text="清空列表", command=self.clear_table)
        self.clear_button.pack(side=tk.LEFT, padx=5)

        # Treeview for results
        tree_frame = ttk.Frame(master, padding="10")
        tree_frame.pack(expand=True, fill=tk.BOTH)

        self.columns = (
            "_num", "filename", "size", "extension", "duration", "resolution", 
            "bitrate", "total_bitrate", "frame_height", "frame_width", 
            "frame_rate", "video_codec", "issues"
        )
        self.column_names = (
            "序号", "文件名", "大小", "类型", "时长", "分辨率", 
            "视频码率", "总码率", "帧高度", "帧宽度", 
            "帧率", "视频编码", "问题摘要"
        )
        self.column_widths = (
            50, 250, 80, 60, 80, 100, 
            80, 80, 70, 70, 
            70, 100, 300
        )

        self.tree = ttk.Treeview(tree_frame, columns=self.columns, show="headings")
        
        for col, name, width in zip(self.columns, self.column_names, self.column_widths):
            self.tree.heading(col, text=name, command=partial(self.sort_column, col, False))
            self.tree.column(col, width=width, anchor=tk.W)

        # Scrollbars
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(expand=True, fill=tk.BOTH)

        # Drag and drop (using a Label as a drop target for simplicity)
        self.drop_target = ttk.Label(master, text="将文件或文件夹拖拽到此处", relief="solid", padding=20)
        self.drop_target.pack(fill=tk.X, padx=10, pady=5)
        # Note: Actual drag and drop requires a library like TkinterDnD2 or platform-specific code.
        # This is a placeholder label. For full drag-and-drop, you'd integrate TkinterDnD2.
        # Example (conceptual, requires TkinterDnD2):
        # from tkinterdnd2 import DND_FILES, TkinterDnD
        # self.master = TkinterDnD.Tk()
        # self.drop_target.drop_target_register(DND_FILES)
        # self.drop_target.dnd_bind('<<Drop>>', self.handle_drop)

        # Status bar
        self.status_bar = ttk.Label(master, text="准备就绪", relief=tk.SUNKEN, anchor=tk.W, padding=5)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Progress bar frame (initially hidden)
        self.progress_frame = ttk.Frame(master, padding="5")
        # self.progress_frame.pack(fill=tk.X, padx=10, pady=5, before=self.status_bar) # Pack it before status_bar
        
        self.progress_label = ttk.Label(self.progress_frame, text="")
        self.progress_label.pack(side=tk.TOP, fill=tk.X, padx=5, pady=(0,2)) # Label on top
        
        self.progress_bar = ttk.Progressbar(self.progress_frame, orient="horizontal", mode="determinate")
        self.progress_bar.pack(side=tk.TOP, expand=True, fill=tk.X, padx=5, pady=(0,5)) # Progress bar below label

        # Configure tags for row colors
        self.tree.tag_configure("red", background="#FFCDD2") # Light red
        self.tree.tag_configure("yellow", background="#FFF9C4") # Light yellow
        self.tree.tag_configure("green", background="#C8E6C9") # Light green

        self.update_results_from_queue() # Start checking the results queue

    def handle_drop(self, event):
        # This is a conceptual handler for TkinterDnD2
        # It would receive a string of file paths
        paths = self.master.tk.splitlist(event.data)
        self.process_paths(paths)

    def select_files(self):
        file_paths = filedialog.askopenfilenames(
            title="选择媒体文件",
            filetypes=(("媒体文件", "*.mp4 *.mov *.avi *.mkv *.flv *.wmv *.webm *.jpg *.jpeg *.png *.gif *.bmp *.tiff"), 
                       ("所有文件", "*.*"))
        )
        if file_paths:
            self.process_paths(file_paths)

    def select_folder(self):
        folder_path = filedialog.askdirectory(title="选择文件夹")
        if folder_path:
            self.process_paths([folder_path])

    def process_paths(self, paths):
        self.stop_processing.clear()
        self.status_bar.config(text="正在扫描文件...")
        self.master.update_idletasks()
        
        files_to_process = []
        for path in paths:
            if os.path.isdir(path):
                for root, _, files in os.walk(path):
                    for file in files:
                        files_to_process.append(os.path.join(root, file))
            elif os.path.isfile(path):
                files_to_process.append(path)
        
        if not files_to_process:
            self.status_bar.config(text="未找到有效文件或文件夹。")
            return

        for fp in files_to_process:
            self.file_queue.put(fp)
        
        self.start_processing_if_needed()

    def start_processing_if_needed(self):
        if not self.file_queue.empty() and (self.processing_thread is None or not self.processing_thread.is_alive()):
            self.stop_processing.clear()
            self.processing_thread = threading.Thread(target=self.worker_process_files, daemon=True)
            self.processing_thread.start()
            self.status_bar.config(text=f"开始处理 {self.file_queue.qsize()} 个文件...")
            self.show_progress_bar(self.file_queue.qsize())

    def worker_process_files(self):
        processed_count = 0
        total_to_process = self.file_queue.qsize() # Initial queue size for progress
        self.master.after(0, lambda: self.show_progress_bar(total_to_process))

        while not self.file_queue.empty() and not self.stop_processing.is_set():
            try:
                file_path = self.file_queue.get_nowait()
                details = get_media_info_with_rules(file_path)
                self.results_queue.put((file_path, details, self.display_order_counter))
                self.display_order_counter +=1
                self.file_queue.task_done()
                processed_count += 1
                
                filename = os.path.basename(file_path)
                self.master.after(0, lambda pc=processed_count, total=total_to_process, fn=filename: 
                                  self.update_progress_bar(pc, total, fn))
            except queue.Empty:
                break
            except Exception as e:
                print(f"Error processing {file_path}: {e}")
                # Optionally put an error entry in the results queue
                error_details = {"filename": os.path.basename(file_path), "issues": [f"处理失败: {e}"], "color": "red"}
                self.results_queue.put((file_path, error_details, self.display_order_counter))
                self.display_order_counter +=1
                if not self.file_queue.empty(): self.file_queue.task_done()
        
        final_status = "处理完成" if not self.stop_processing.is_set() else "处理已停止"
        self.master.after(0, lambda: self.status_bar.config(text=final_status))
        self.master.after(0, self.hide_progress_bar if not self.file_queue.empty() and not self.results_queue.empty() else self.perform_final_sort_if_done)
        self.processing_thread = None # Allow new thread

    def update_results_from_queue(self):
        try:
            while True:
                file_path, details, display_order = self.results_queue.get_nowait()
                self.add_result_to_tree(file_path, details, display_order)
                self.results_queue.task_done()
        except queue.Empty:
            pass # Queue is empty, do nothing
        
        self.perform_final_sort_if_done()
        self.master.after(100, self.update_results_from_queue) # Periodically check

    def add_result_to_tree(self, file_path, details, display_order):
        if not details: return

        values = [display_order] + [details.get(col, "N/A") for col in self.columns[1:-1]] # Exclude _num and issues
        values.append(", ".join(details.get("issues", [])))
        
        tag_color = details.get("color", "green")
        self.tree.insert("", tk.END, values=tuple(values), tags=(tag_color,))
        self.item_id_counter += 1

    def clear_table(self):
        self.stop_processing.set() # Signal processing thread to stop
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=1) # Wait a bit for thread to finish
        
        self.tree.delete(*self.tree.get_children())
        self.item_id_counter = 0
        self.display_order_counter = 1
        # Clear queues
        while not self.file_queue.empty():
            try: self.file_queue.get_nowait() 
            except queue.Empty: break
        while not self.results_queue.empty():
            try: self.results_queue.get_nowait()
            except queue.Empty: break
        self.status_bar.config(text="列表已清空")
        self.hide_progress_bar()

    def sort_column(self, col, reverse):
        l = [(self.tree.set(k, col), k) for k in self.tree.get_children('')]
        
        # Custom sort for numeric-like columns, color priority, then value
        def sort_key(item):
            value_str = item[0]
            # Color priority: red > yellow > green > others
            tags = self.tree.item(item[1], 'tags')
            color_priority = 4 # default/green
            if 'red' in tags: color_priority = 1
            elif 'yellow' in tags: color_priority = 2
            elif 'green' in tags: color_priority = 3

            try:
                # Attempt to convert to float for numeric sorting if possible
                # Handle cases like "100 kbps" -> 100, "00:01:30" -> 90 (seconds)
                if 'kbps' in value_str.lower():
                    numeric_val = float(value_str.lower().replace('kbps','').strip())
                elif 'fps' in value_str.lower():
                    numeric_val = float(value_str.lower().replace('fps','').strip())
                elif ':' in value_str and len(value_str.split(':')) >= 2: # Duration
                    parts = list(map(int, value_str.split(':')))
                    if len(parts) == 2: numeric_val = parts[0]*60 + parts[1]
                    elif len(parts) == 3: numeric_val = parts[0]*3600 + parts[1]*60 + parts[2]
                    else: numeric_val = float('inf') # Should not happen with format_duration
                elif 'x' in value_str and value_str.replace('x','').isdigit(): # Resolution like 1920x1080
                    w, h = map(int, value_str.split('x'))
                    numeric_val = w * h # Sort by area
                else:
                    numeric_val = float(value_str)
                return (color_priority, numeric_val)
            except (ValueError, TypeError):
                # Fallback to string sort if conversion fails
                return (color_priority, value_str.lower())

        l.sort(key=sort_key, reverse=reverse)

        for index, (val, k) in enumerate(l):
            self.tree.move(k, '', index)
        
        # Update sequence numbers after sort
        self.update_sequence_numbers()
        self.tree.heading(col, command=partial(self.sort_column, col, not reverse))

    def update_sequence_numbers(self):
        items = self.tree.get_children('')
        for index, item_id in enumerate(items, 1):
            current_values = list(self.tree.item(item_id, 'values'))
            current_values[0] = str(index)
            self.tree.item(item_id, values=tuple(current_values))
            
    def perform_final_sort_if_done(self):
        if self.file_queue.empty() and self.results_queue.empty() and \
           (self.processing_thread is None or not self.processing_thread.is_alive()):
            # Default sort by color (red, yellow, green) then by original add order (_num)
            self.sort_column("_num", False) # This will trigger color-priority sort
            self.status_bar.config(text="所有文件处理和排序完成。")
            self.hide_progress_bar()

    def show_progress_bar(self, total_files):
        if total_files > 0:
            self.progress_bar['maximum'] = total_files
            self.progress_bar['value'] = 0
            self.progress_label.config(text=f"0/{total_files} (0%)")
            # Ensure progress_frame is packed before the status_bar if not already
            self.progress_frame.pack(fill=tk.X, padx=10, pady=5, before=self.status_bar)
            self.progress_frame.lift() # Ensure it's on top of other elements if overlapping
        else:
            self.hide_progress_bar()

    def update_progress_bar(self, current_count, total_files, current_file_name=""):
        if total_files > 0:
            self.progress_bar['value'] = current_count
            percentage = (current_count / total_files) * 100
            display_name = current_file_name
            if len(display_name) > 40:
                display_name = "..." + display_name[-37:]
            self.progress_label.config(text=f"{current_count}/{total_files} ({percentage:.1f}%) - {display_name}")
        else:
            self.progress_label.config(text="")

    def hide_progress_bar(self):
        self.progress_frame.pack_forget()

if __name__ == '__main__':
    root = tk.Tk()
    # For drag and drop, you might need to initialize TkinterDnD2 here if you use it:
    # from tkinterdnd2 import TkinterDnD
    # root = TkinterDnD.Tk() # If using TkinterDnD2
    app = MediaAnalyzerApp(root)
    root.mainloop()