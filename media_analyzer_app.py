import tkinter as tk
from tkinter import filedialog, ttk, messagebox
from pymediainfo import MediaInfo
import os
import queue
import threading
import time
from functools import partial # For sorting

# --- Formatting Helpers ---
def format_size(size_bytes):
    if size_bytes is None: return "N/A"
    if size_bytes == 0: return "0B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    i = 0
    while size_bytes >= 1024 and i < len(size_name) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.2f}{size_name[i]}"

def format_duration(ms):
    if ms is None: return "N/A"
    try:
        ms = int(ms)
        s = ms // 1000
        m, s = divmod(s, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
    except (ValueError, TypeError): return "N/A"

def format_bitrate_kbps(bps):
    if bps is None: return "N/A"
    try:
        kbps = int(bps) / 1000
        return f"{kbps:.0f} kbps"
    except (ValueError, TypeError): return "N/A"

def format_framerate_fps(fps_value):
    if fps_value is None: return "N/A"
    try: return f"{float(fps_value):.2f} fps"
    except (ValueError, TypeError): return "N/A"

# --- Validation Rules ---
VALID_WIDTHS = {540, 720, 960, 1080, 1280}
VALID_HEIGHTS = {540, 607, 720, 960, 1280, 1920}

# --- Simplified Issue Descriptions ---
ISSUE_DESCRIPTIONS = {
    "文件名包含空格": "文件名空格",
    "帧率过低": "帧率低",
    "帧率数据无效": "帧率无效",
    "视频码率过低": "视码率低",
    "视频码率数据无效": "视码率无效",
    "音频码率过低": "音码率低",
    "音频码率数据无效": "音码率无效",
    "宽度不符合标准": "宽度异常",
    "高度不符合标准": "高度异常",
    "处理错误": "处理错误",
    "视频文件过大": "视频过大",
    "图片文件过大": "图片过大"
}

# --- Core Media Info Extraction Logic ---
def get_media_details(file_path):
    details = {
        'file_name': os.path.basename(file_path),
        # 'file_extension': os.path.splitext(file_path)[1].lower(), # Removed as per request
        'file_size': None, 'duration': None, 'width': None, 'height': None,
        'frame_rate': None, 'bit_rate_video': None, 'bit_rate_audio': None,
        'issues': [], 'simplified_issues': [], 'has_issues': False,
        'is_video': False, 'is_image': False # Add flags to identify file type
    }
    try:
        if os.path.exists(file_path):
            details['file_size'] = os.path.getsize(file_path)

        media_info = MediaInfo.parse(file_path)
        general_track = next((t for t in media_info.tracks if t.track_type == 'General'), None)
        video_track = next((t for t in media_info.tracks if t.track_type == 'Video'), None)
        image_track = next((t for t in media_info.tracks if t.track_type == 'Image'), None)
        audio_track = next((t for t in media_info.tracks if t.track_type == 'Audio'), None)

        if video_track:
            details['is_video'] = True
        elif image_track: # Only consider it an image if there's no video track
            details['is_image'] = True

        if general_track:
            details['duration'] = getattr(general_track, 'duration', None)
        if video_track and details['duration'] is None:
            details['duration'] = getattr(video_track, 'duration', None)

        if video_track:
            details['width'] = getattr(video_track, 'width', None)
            details['height'] = getattr(video_track, 'height', None)
            details['frame_rate'] = getattr(video_track, 'frame_rate', None)
            details['bit_rate_video'] = getattr(video_track, 'bit_rate', None)
        elif image_track:
            details['width'] = getattr(image_track, 'width', None)
            details['height'] = getattr(image_track, 'height', None)
        
        if audio_track:
            details['bit_rate_audio'] = getattr(audio_track, 'bit_rate', None)

        # Validation Checks - Store full issues and simplified issues
        raw_issues = []
        # Check for half-width space only, excluding common full-width punctuation
        full_width_chars_to_exclude = ['　', '，', '。', '；', '：', '（', '）', '【', '】', '（', '）'] # Added full-width parentheses
        if ' ' in details['file_name'] and not any(char in details['file_name'] for char in full_width_chars_to_exclude):
            raw_issues.append("文件名包含空格")
        
        if details['frame_rate'] is not None:
            try:
                if float(details['frame_rate']) <= 20:
                    raw_issues.append("帧率过低")
            except ValueError:
                raw_issues.append("帧率数据无效")

        if details['bit_rate_video'] is not None:
            try:
                # Assuming bit_rate_video is in bps, so 1000 kbps = 1,000,000 bps
                if int(details['bit_rate_video']) < 1000 * 1000: 
                    raw_issues.append("视频码率过低")
            except ValueError:
                 raw_issues.append("视频码率数据无效")

        if details['bit_rate_audio'] is not None:
            try:
                # Assuming bit_rate_audio is in bps, so 64 kbps = 64,000 bps
                if int(details['bit_rate_audio']) < 64 * 1000: 
                    raw_issues.append("音频码率过低")
            except ValueError:
                raw_issues.append("音频码率数据无效")

        if details['width'] is not None and details['width'] not in VALID_WIDTHS:
            raw_issues.append("宽度不符合标准")
        
        if details['height'] is not None and details['height'] not in VALID_HEIGHTS:
            raw_issues.append("高度不符合标准")

        # File size checks
        if details['file_size'] is not None:
            if details['is_video'] and details['file_size'] > 60 * 1024 * 1024: # 60MB for videos
                raw_issues.append("视频文件过大")
            elif details['is_image'] and details['file_size'] > 150 * 1024: # 150KB for images
                raw_issues.append("图片文件过大")

        details['issues'] = raw_issues # Keep original full issues for tooltip or detailed view if needed later
        details['simplified_issues'] = [ISSUE_DESCRIPTIONS.get(issue, issue) for issue in raw_issues]

        if details['simplified_issues']:
            details['has_issues'] = True
        
        return details

    except Exception as e:
        error_msg = f"处理错误: {str(e)[:50]}..." # Truncate long error messages
        details['issues'].append(error_msg)
        details['simplified_issues'].append(ISSUE_DESCRIPTIONS.get("处理错误", "处理错误"))
        details['has_issues'] = True
        for key in ['duration', 'width', 'height', 'frame_rate', 'bit_rate_video', 'bit_rate_audio']:
            if details[key] is None: details[key] = 'Error'
        return details

# --- GUI Application --- 
class MediaAnalyzerApp:
    def __init__(self, root_window):
        self.root = root_window
        self.root.title("媒体文件分析器 Pro v1.2")
        self.root.geometry("1350x750")

        self.file_queue = queue.Queue()
        self.results_queue = queue.Queue()
        self.processing_thread = None
        self.stop_processing = threading.Event()
        self.item_id_counter = 0
        self.display_order_counter = 1
        self.item_issues_map = {} 

        self.video_file_count = 0
        self.image_file_count = 0
        self.problem_file_count = 0

        # --- Stats Bar ---
        stats_frame = ttk.Frame(self.root)
        stats_frame.pack(fill=tk.X, padx=10, pady=(5,0))
        self.stats_label = ttk.Label(stats_frame, text="统计: 视频 0 | 图片 0 | 问题 0 | 总计 0")
        self.stats_label.pack(side=tk.LEFT)

        # --- UI Elements (Buttons) ---
        top_frame = ttk.Frame(self.root)
        top_frame.pack(fill=tk.X, padx=10, pady=5)
        self.select_files_button = ttk.Button(top_frame, text="选择文件", command=self.select_files)
        self.select_files_button.pack(side=tk.LEFT, padx=(0, 5))
        self.select_folder_button = ttk.Button(top_frame, text="选择文件夹", command=self.select_folder)
        self.select_folder_button.pack(side=tk.LEFT)
        self.clear_button = ttk.Button(top_frame, text="清空列表", command=self.clear_table)
        self.clear_button.pack(side=tk.RIGHT)

        # --- Treeview ---
        self.tree_frame = ttk.Frame(self.root)
        self.tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.columns = {
            "#0": ("路径", 250),
            "_num": ("序号", 40), # Adjusted width
            "file_name": ("文件名", 220),
            # "file_extension": ("拓展名", 70), # Removed
            "file_size": ("大小", 90),
            "duration": ("时长", 90),
            "width": ("宽度", 70),
            "height": ("高度", 70),
            "frame_rate": ("帧率 (fps)", 100),
            "bit_rate_video": ("视频码率 (kbps)", 130),
            "bit_rate_audio": ("音频码率 (kbps)", 130),
            "issue_summary": ("问题原因", 150) # Added new column
        }
        self.tree = ttk.Treeview(self.tree_frame, columns=list(self.columns.keys())[1:], show="headings")
        self.tree.tag_configure('problem_file', foreground='red')
        self.tree.tag_configure('no_issue_file', foreground='green') # For '通过初审'
        self.tree.tag_configure('has_issues_sort_key', foreground='black') # Invisible tag for sorting

        self.tree.heading("#0", text=self.columns["#0"][0], command=partial(self.sort_column, "#0", False))
        self.tree.column("#0", width=self.columns["#0"][1], anchor=tk.W)
        
        for col_id in list(self.columns.keys())[1:]:
            text, width = self.columns[col_id]
            self.tree.heading(col_id, text=text, command=partial(self.sort_column, col_id, False))
            if col_id == "_num":
                self.tree.column(col_id, width=width, anchor=tk.CENTER, stretch=tk.NO, minwidth=width) # Fixed width for _num
            else:
                self.tree.column(col_id, width=width, anchor=tk.W)

        vsb = ttk.Scrollbar(self.tree_frame, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(self.tree_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        hsb.pack(side=tk.BOTTOM, fill=tk.X)
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind('<<TreeviewSelect>>', self.on_tree_select)

        # --- Status Bar ---
        self.status_bar = ttk.Label(self.root, text="准备就绪", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.update_results_from_queue()
        self.sort_state = {}
        self.update_stats_label()

    def update_stats_label(self):
        total_files = self.video_file_count + self.image_file_count
        self.stats_label.config(text=f"统计: 视频 {self.video_file_count} | 图片 {self.image_file_count} | 问题 {self.problem_file_count} | 总计 {total_files}")

    def on_tree_select(self, event):
        selected_item = self.tree.focus() # Get selected item
        if selected_item:
            item_data = self.tree.item(selected_item)
            # The 'values' tuple contains the display values for explicit columns.
            # The 'text' attribute contains the path (our #0 column data).
            # We need to retrieve the original 'details' dictionary associated with this item
            # This requires storing it or re-fetching. For simplicity, let's assume we stored 'issues' as a hidden value or can reconstruct.
            # A better way: store the full details dict or issues list with the item when inserting.
            # For now, let's just show a generic message if it's red.
            tags = item_data.get('tags', [])
            if 'problem_file' in tags:
                # To get specific issues, we'd need to have stored them. 
                # Let's try to retrieve from a (hypothetical) stored issues list. 
                # This part needs proper implementation by storing issues with items.
                # For this iteration, we'll just indicate it has problems.
                # A more robust way is to store the issues list in the item itself, e.g., self.tree.item(iid, values=(..., issues_list_as_string))
                # Or, keep a mapping from iid to details dict.
                self.status_bar.config(text=f"文件 '{item_data['text']}' 存在问题. (详细信息需进一步实现)")
            else:
                self.status_bar.config(text=f"已选择: {item_data['text']}")
        else:
            self.status_bar.config(text="准备就绪")

    def sort_column(self, col, reverse):
        items = list(self.tree.get_children(''))
        
        # Create a list of tuples: (sort_key_primary, sort_key_secondary, item_id)
        # sort_key_primary: 0 if has_issues, 1 if not (to put issues on top when reverse=False)
        # sort_key_secondary: the actual column value
        l = []
        for k in items:
            has_issues = 'problem_file' in self.tree.item(k, 'tags')
            primary_sort_key = 0 if has_issues else 1
            
            if col == "#0": val_str = self.tree.item(k, 'text')
            else: val_str = self.tree.set(k, col)

            secondary_sort_key = val_str # Default
            if col == "_num": 
                try: secondary_sort_key = int(val_str)
                except: secondary_sort_key = float('inf') # Errors/NAs last
            elif col in ["file_size", "width", "height"]:
                try: 
                    num_part = val_str.split()[0]
                    if num_part == "N/A" or num_part == "Error": secondary_sort_key = float('-inf') if reverse else float('inf') 
                    else: secondary_sort_key = float(num_part)
                except: secondary_sort_key = val_str # Fallback
            elif col in ["duration", "frame_rate", "bit_rate_video", "bit_rate_audio"]:
                 try: # Attempt to extract number for sorting, handling N/A or Error
                    num_part = val_str.split()[0]
                    if num_part == "N/A" or num_part == "Error": secondary_sort_key = float('-inf') if reverse else float('inf') 
                    else: secondary_sort_key = float(num_part)
                 except: secondary_sort_key = val_str
            
            l.append((primary_sort_key, secondary_sort_key, k))

        # Sort: first by primary_sort_key, then by secondary_sort_key
        try:
            l.sort(key=lambda t: (t[0], t[1]), reverse=reverse)
        except TypeError: # Fallback for mixed types in secondary key
            l.sort(key=lambda t: (t[0], str(t[1])), reverse=reverse)

        for index, (p_key, s_key, k) in enumerate(l):
            self.tree.move(k, '', index)

        self.tree.heading(col, command=partial(self.sort_column, col, not reverse))
        self.sort_state[col] = not reverse

    def select_files(self, *args):
        file_paths = filedialog.askopenfilenames(
            title="选择一个或多个媒体文件",
            filetypes=(("媒体文件", "*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm *.mp3 *.wav *.aac *.flac *.jpg *.jpeg *.png *.gif"),
                       ("所有文件", "*.*"))
        )
        if file_paths:
            print(f"[DEBUG] Selected files: {file_paths}") # DEBUG
            for fp in file_paths:
                print(f"[DEBUG] Adding to file_queue: {fp}") # DEBUG
                self.file_queue.put(fp)
            self.start_processing_if_needed()

    def select_folder(self, *args): # Add this missing method
        folder_path = filedialog.askdirectory(title="选择一个文件夹")
        if folder_path:
            self.status_bar.config(text=f"正在扫描文件夹: {folder_path}...")
            self.root.update_idletasks()
            self.select_files_button.config(state=tk.DISABLED)
            self.select_folder_button.config(state=tk.DISABLED)
            threading.Thread(target=self._scan_folder_and_queue_files, args=(folder_path,), daemon=True).start()

    def _scan_folder_and_queue_files(self, folder_path):
        count = 0
        allowed_extensions = (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".mp3", ".wav", ".aac", ".flac", ".jpg", ".jpeg", ".png", ".gif")
        print(f"[DEBUG] Scanning folder: {folder_path}") # DEBUG
        for root_dir, _, files in os.walk(folder_path):
            if self.stop_processing.is_set(): break
            for file in files:
                if self.stop_processing.is_set(): break
                if file.lower().endswith(allowed_extensions):
                    file_path_to_queue = os.path.join(root_dir, file)
                    print(f"[DEBUG] Adding from folder to file_queue: {file_path_to_queue}") # DEBUG
                    self.file_queue.put(file_path_to_queue)
                    count += 1
                    if count % 20 == 0:
                        self.root.after(0, lambda current_count=count: self.status_bar.config(text=f"已找到 {current_count} 个文件，正在加入队列..."))
        
        self.root.after(0, lambda final_count=count: self.status_bar.config(text=f"文件夹扫描完成，共找到 {final_count} 个文件待处理。") if final_count > 0 else self.status_bar.config(text="文件夹扫描完成，未找到符合条件的文件。"))
        self.root.after(0, self.start_processing_if_needed)
        self.root.after(0, lambda: self.select_files_button.config(state=tk.NORMAL))
        self.root.after(0, lambda: self.select_folder_button.config(state=tk.NORMAL))

    def worker_process_files(self):
        processed_count = 0
        while not self.file_queue.empty() and not self.stop_processing.is_set():
            file_path = None # Initialize file_path
            try:
                file_path = self.file_queue.get_nowait()
                print(f"[DEBUG] Worker: Processing {file_path}") # DEBUG
                details = get_media_details(file_path)
                print(f"[DEBUG] Worker: Details for {file_path}: {details}") # DEBUG
                self.results_queue.put((file_path, details, self.display_order_counter))
                self.file_queue.task_done()
                processed_count +=1
                q_size = self.file_queue.qsize()
                self.root.after(0, lambda pc=processed_count, tq=q_size, fn=os.path.basename(file_path if file_path else 'Unknown'): 
                                self.status_bar.config(text=f"正在处理: {pc} / {pc + tq} | {fn}"))
            except queue.Empty:
                break
            except Exception as e:
                print(f"[DEBUG] Worker: Error processing {file_path if file_path else 'Unknown'}: {e}") # DEBUG
                if file_path: # Ensure file_path is not None
                    error_details = get_media_details(file_path) # Re-call to get structured error
                    self.results_queue.put((file_path, error_details, self.display_order_counter))
                    self.file_queue.task_done() # Mark task done even if there was an error during processing
        
        if not self.stop_processing.is_set():
             self.root.after(0, lambda: self.status_bar.config(text="所有文件处理完毕。"))
        else:
             self.root.after(0, lambda: self.status_bar.config(text="处理已停止。"))
        self.processing_thread = None

    def start_processing_if_needed(self):
        if not self.file_queue.empty() and (self.processing_thread is None or not self.processing_thread.is_alive()):
            self.stop_processing.clear()
            self.processing_thread = threading.Thread(target=self.worker_process_files, daemon=True)
            self.processing_thread.start()
            self.status_bar.config(text="开始处理文件...")

    # Store issues with item for later retrieval in on_tree_select
    # self.item_issues_map = {} # Map iid to issues list

    def update_results_from_queue(self):
        try:
            while True:
                original_path, details, _ = self.results_queue.get_nowait()
                print(f"[DEBUG] UI Update: Got from results_queue: {original_path}, Details: {details}") # DEBUG
                
                current_display_num = self.display_order_counter
                self.display_order_counter += 1

                iid = f"item_{self.item_id_counter}"
                self.item_id_counter += 1
                self.item_issues_map[iid] = details.get('issues', []) 

                tags_to_apply = ()
                issue_summary_text = "通过初审"
                if details.get('has_issues', False):
                    tags_to_apply = ('problem_file',)
                    self.problem_file_count +=1
                    issue_summary_text = ", ".join(details.get('simplified_issues', ['未知问题']))
                else:
                    tags_to_apply = ('no_issue_file',)
                
                # ext = details.get('file_extension', '') # No longer needed for display
                # Update video/image counts based on actual tracks or refined logic if needed
                # For now, using a simple heuristic based on what pymediainfo provides for video/image tracks
                if any(track.track_type == 'Video' for track in MediaInfo.parse(original_path).tracks):
                    self.video_file_count +=1
                elif any(track.track_type == 'Image' for track in MediaInfo.parse(original_path).tracks):
                    self.image_file_count +=1

                values = [
                    current_display_num,
                    details.get('file_name', 'N/A'),
                    # details.get('file_extension', 'N/A'), # Removed
                    format_size(details.get('file_size')),
                    format_duration(details.get('duration')),
                    details.get('width', 'N/A'),
                    details.get('height', 'N/A'),
                    format_framerate_fps(details.get('frame_rate')),
                    format_bitrate_kbps(details.get('bit_rate_video')),
                    format_bitrate_kbps(details.get('bit_rate_audio')),
                    issue_summary_text # Added value for new column
                ]
                print(f"[DEBUG] UI Update: Inserting into tree: iid={iid}, path={original_path}, values={values}, tags={tags_to_apply}") # DEBUG
                self.tree.insert("", tk.END, iid=iid, text=original_path, values=values, tags=tags_to_apply)
                if 'problem_file' in tags_to_apply: # Keep problem files at top if that's still desired
                    self.tree.move(iid, '', 0)
                
                self.update_stats_label()

        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.update_results_from_queue)
    
    # Modify on_tree_select to use the stored issues
    def on_tree_select(self, event):
        selected_item_id = self.tree.focus()
        if selected_item_id:
            item_text = self.tree.item(selected_item_id, 'text')
            issues = self.item_issues_map.get(selected_item_id, [])
            if issues:
                self.status_bar.config(text=f"文件 '{os.path.basename(item_text)}' 问题: {'; '.join(issues)}")
            else:
                self.status_bar.config(text=f"已选择: {os.path.basename(item_text)}")
        else:
            self.status_bar.config(text="准备就绪")

    def clear_table(self):
        if self.processing_thread and self.processing_thread.is_alive():
            if messagebox.askyesno("确认", "正在处理文件，确定要停止并清空列表吗？"):
                self.stop_processing.set()
            else:
                return
        
        for i in self.tree.get_children():
            self.tree.delete(i)
        
        self.display_order_counter = 1
        self.item_id_counter = 0
        self.video_file_count = 0
        self.image_file_count = 0
        self.problem_file_count = 0
        self.item_issues_map.clear()
        self.update_stats_label()

        while not self.file_queue.empty(): # Clear queues
            try: self.file_queue.get_nowait()
            except queue.Empty: break
        while not self.results_queue.empty():
            try: self.results_queue.get_nowait()
            except queue.Empty: break
        self.status_bar.config(text="列表已清空。准备就绪。")

    def on_closing(self):
        if self.processing_thread and self.processing_thread.is_alive():
            if messagebox.askyesno("退出", "文件仍在处理中。确定要退出吗？"):
                self.stop_processing.set()
                self.root.destroy()
            else:
                return
        else:
            self.root.destroy()

if __name__ == "__main__":
    # Ensure MediaInfo.dll is accessible. 
    # This might involve setting PATH or placing it with the script/executable.
    # For PyInstaller, you'd add it as a datafile.
    # print(f"pymediainfo library path: {MediaInfo.library_file}") # For debugging DLL path
    # print(f"MediaInfo.can_parse(): {MediaInfo.can_parse()}")

    main_window = tk.Tk()
    app = MediaAnalyzerApp(main_window)
    main_window.mainloop()