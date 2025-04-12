import tkinter as tk
from tkinter import filedialog, messagebox, ttk, scrolledtext
import os
import requests
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time
import sys
import platform
import json
from urllib.parse import urlparse
import datetime
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import re

# 检查ffmpeg是否安装
def check_ffmpeg():
    try:
        subprocess.run(['ffmpeg', '-version'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        return True
    except:
        return False

# 程序启动时检查
if not check_ffmpeg():
    messagebox.showerror("Error", "ffmpeg is not installed or not in PATH. Please install ffmpeg to use this program.")
    sys.exit(1)

# 创建一个会话对象，用于连接复用
def create_session():
    session = requests.Session()
    
    # 配置重试策略
    retry_strategy = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    
    # 配置适配器，最大连接数
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=20, pool_maxsize=50)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    
    return session

# 在程序开始时创建会话
http_session = create_session()

def normalize_m3u8_url(url):
    """标准化 .m3u8 URL，处理带查询参数的情况"""
    # 验证URL格式
    if not url or not (url.startswith('http://') or url.startswith('https://')):
        return None
    
    # 解析URL，分离查询参数
    parsed_url = urlparse(url)
    path = parsed_url.path
    query = parsed_url.query
    
    # 如果URL已经包含.m3u8（无论是否有查询参数），直接返回
    if '.m3u8' in path:
        return url
        
    if '.ts' in path:
        # 如果用户输入的是 .ts 文件地址，则尝试构造对应的 m3u8 URL
        
        # 提取基础路径（不包含文件名和查询参数）
        base_path = '/'.join(path.split('/')[:-1])
        
        # 尝试常见的m3u8文件名
        possible_m3u8_paths = [
            f"{base_path}/index.m3u8",
            f"{base_path}/playlist.m3u8",
            f"{base_path}/master.m3u8"
        ]
        
        # 如果路径中包含特定格式，尝试更具体的推断
        if 'seg-' in path or 'segment-' in path:
            # 可能是分段视频，尝试找到索引文件
            base_path = '/'.join(base_path.split('/')[:-1])  # 再上一级目录
            possible_m3u8_paths.insert(0, f"{base_path}/index.m3u8")
        
        # 构建完整URL并尝试访问
        for m3u8_path in possible_m3u8_paths:
            m3u8_url = f"{parsed_url.scheme}://{parsed_url.netloc}{m3u8_path}"
            if query:
                m3u8_url = f"{m3u8_url}?{query}"
                
            try:
                headers = {
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
                }
                response = http_session.head(m3u8_url, headers=headers, timeout=5)
                if response.status_code == 200:
                    return m3u8_url
            except:
                continue
        
        # 如果所有尝试都失败，返回一个基于原始URL的猜测
        if 'seg-' in path or 'segment-' in path:
            # 对于分段视频，尝试找到索引文件
            base_path = '/'.join(path.split('/')[:-1])  # 文件所在目录
            base_path = '/'.join(base_path.split('/')[:-1])  # 再上一级目录
            m3u8_url = f"{parsed_url.scheme}://{parsed_url.netloc}{base_path}/index.m3u8"
        else:
            # 一般情况，尝试同目录下的index.m3u8
            base_path = '/'.join(path.split('/')[:-1])
            m3u8_url = f"{parsed_url.scheme}://{parsed_url.netloc}{base_path}/index.m3u8"
            
        if query:
            m3u8_url = f"{m3u8_url}?{query}"
            
        return m3u8_url
    else:
        # 如果不是.ts也不是.m3u8，则追加 index.m3u8，保留查询参数
        base_url = url.rstrip('/')
        if query:
            # 如果URL已经有查询参数，直接返回
            return f"{base_url}/index.m3u8?{query}"
        else:
            return f"{base_url}/index.m3u8"

def download_m3u8(url, save_path):
    """下载 .m3u8 文件"""
    try:
        # 添加更完整的浏览器样式的请求头
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Referer': f"{urlparse(url).scheme}://{urlparse(url).netloc}/",
            'Origin': f"{urlparse(url).scheme}://{urlparse(url).netloc}",
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache'
        }
        
        # 使用会话对象发送请求
        response = http_session.get(url, headers=headers, timeout=15)
        
        # 如果遇到403错误，尝试使用不同的请求头
        if response.status_code == 403:
            # 尝试使用更简单的请求头
            simple_headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': '*/*'
            }
            response = http_session.get(url, headers=simple_headers, timeout=15)
            
            # 如果仍然是403，尝试从URL中提取Referer
            if response.status_code == 403:
                parsed_url = urlparse(url)
                path_parts = parsed_url.path.split('/')
                if len(path_parts) > 2:
                    # 使用路径的上一级目录作为Referer
                    referer_path = '/'.join(path_parts[:-1])
                    possible_referer = f"{parsed_url.scheme}://{parsed_url.netloc}{referer_path}/"
                    
                    custom_headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Accept': '*/*',
                        'Referer': possible_referer,
                        'Origin': f"{parsed_url.scheme}://{parsed_url.netloc}"
                    }
                    
                    response = http_session.get(url, headers=custom_headers, timeout=15)
        
        if response.status_code == 200:
            # 检查内容是否看起来像m3u8文件
            content = response.text
            if not ('#EXTM3U' in content or '.ts' in content):
                messagebox.showwarning("Warning", "Downloaded content doesn't look like a valid m3u8 file")
            
            # 检查是否已存在playlist.m3u8文件
            playlist_path = os.path.join(save_path, 'playlist.m3u8')
            if os.path.exists(playlist_path):
                # 如果文件已存在，先尝试删除
                try:
                    os.remove(playlist_path)
                except Exception as e:
                    messagebox.showerror("Error", f"Could not replace existing playlist file: {str(e)}")
                    return False
            
            # 尝试检测编码并保存文件
            try:
                # 首先尝试使用UTF-8编码保存
                with open(playlist_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            except UnicodeEncodeError:
                # 如果UTF-8失败，尝试使用二进制模式保存
                with open(playlist_path, 'wb') as f:
                    f.write(response.content)
            
            # 验证文件是否可读
            try:
                with open(playlist_path, 'r', encoding='utf-8', errors='ignore') as f:
                    test_content = f.read(100)  # 读取前100个字符进行测试
                    if not test_content or not ('#EXTM3U' in test_content):
                        # 如果读取失败或内容不正确，尝试使用二进制模式重新保存
                        with open(playlist_path, 'wb') as f:
                            f.write(response.content)
            except:
                # 如果读取失败，尝试使用二进制模式重新保存
                with open(playlist_path, 'wb') as f:
                    f.write(response.content)
            
            return True
        elif response.status_code == 403:
            messagebox.showerror("Error", "Access forbidden (HTTP 403). The server is blocking access to this resource. Try using a different URL or check if the site requires authentication.")
            return False
        elif response.status_code == 410:
            # 特别处理410错误
            messagebox.showerror("Error", "The URL has expired (HTTP 410 Gone). Please get a fresh URL and try again.")
            return False
        else:
            messagebox.showerror("Error", f"Failed to download m3u8 file. Status code: {response.status_code}")
            return False
    except Exception as e:
        messagebox.showerror("Error", f"An error occurred: {str(e)}")
        return False

def download_single_ts(ts_url, ts_file_path, max_retries=3, chunk_size=None):
    """下载单个 .ts 文件，支持重试和断点续传"""
    if chunk_size is None:
        chunk_size = settings.get('chunk_size', 1024) * 1024  # 默认1MB
        
    # 添加更完整的浏览器样式的请求头
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': '*/*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Referer': f"{urlparse(ts_url).scheme}://{urlparse(ts_url).netloc}/",
        'Origin': f"{urlparse(ts_url).scheme}://{urlparse(ts_url).netloc}",
        'Sec-Fetch-Dest': 'empty',
        'Sec-Fetch-Mode': 'cors',
        'Sec-Fetch-Site': 'same-origin',
        'Pragma': 'no-cache',
        'Cache-Control': 'no-cache'
    }
    
    # 检查文件是否已部分下载
    file_size = 0
    if os.path.exists(ts_file_path):
        file_size = os.path.getsize(ts_file_path)
        if file_size > 0:  # 文件已存在且有内容
            # 尝试使用断点续传
            for attempt in range(max_retries):
                try:
                    range_headers = headers.copy()
                    range_headers['Range'] = f'bytes={file_size}-'
                    response = http_session.get(ts_url, headers=range_headers, timeout=settings.get('timeout', 15), stream=True)
                    
                    # 如果服务器支持断点续传
                    if response.status_code == 206:
                        with open(ts_file_path, 'ab') as f:
                            for chunk in response.iter_content(chunk_size=chunk_size):
                                if chunk:
                                    f.write(chunk)
                        return True
                    else:
                        # 服务器不支持断点续传，删除现有文件重新下载
                        os.remove(ts_file_path)
                        file_size = 0
                        break
                except Exception:
                    if attempt < max_retries - 1:
                        time.sleep(1)
                    else:
                        return False
    
    # 如果文件不存在或断点续传失败，从头开始下载
    if file_size == 0:
        for attempt in range(max_retries):
            try:
                response = http_session.get(ts_url, headers=headers, timeout=settings.get('timeout', 15), stream=True)
                
                # 处理403错误 - 尝试使用不同的请求头
                if response.status_code == 403 and attempt < max_retries - 1:
                    # 尝试使用更简单的请求头
                    simple_headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Accept': '*/*'
                    }
                    response = http_session.get(ts_url, headers=simple_headers, timeout=settings.get('timeout', 15), stream=True)
                
                if response.status_code == 200:
                    with open(ts_file_path, 'wb') as f:
                        for chunk in response.iter_content(chunk_size=chunk_size):
                            if chunk:
                                f.write(chunk)
                    return True
                elif response.status_code == 403:
                    # 如果仍然是403，尝试从URL中提取Referer
                    parsed_url = urlparse(ts_url)
                    possible_referer = f"{parsed_url.scheme}://{parsed_url.netloc}/"
                    
                    # 尝试从路径中构建更具体的Referer
                    path_parts = parsed_url.path.split('/')
                    if len(path_parts) > 2:
                        # 使用路径的上一级目录作为Referer
                        referer_path = '/'.join(path_parts[:-1])
                        possible_referer = f"{parsed_url.scheme}://{parsed_url.netloc}{referer_path}/"
                    
                    custom_headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                        'Accept': '*/*',
                        'Referer': possible_referer,
                        'Origin': f"{parsed_url.scheme}://{parsed_url.netloc}"
                    }
                    
                    response = http_session.get(ts_url, headers=custom_headers, timeout=settings.get('timeout', 15), stream=True)
                    if response.status_code == 200:
                        with open(ts_file_path, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=chunk_size):
                                if chunk:
                                    f.write(chunk)
                        return True
                
                if attempt < max_retries - 1:
                    time.sleep(1)
                else:
                    return False
            except Exception:
                if attempt < max_retries - 1:
                    time.sleep(1)
                else:
                    return False
    
    return False

def check_network_speed():
    """简单检测网络下载速度"""
    try:
        start_time = time.time()
        response = requests.get("https://www.google.com", timeout=5)
        end_time = time.time()
        
        if response.status_code == 200:
            # 计算响应时间（毫秒）
            response_time = (end_time - start_time) * 1000
            
            # 根据响应时间估算网络状况
            if response_time < 100:
                return "fast"  # 快速网络
            elif response_time < 500:
                return "medium"  # 中等网络
            else:
                return "slow"  # 慢速网络
    except:
        pass
    
    return "unknown"  # 未知网络状况

def download_ts_files(m3u8_url, save_path, progress_callback, status_callback):
    """多线程下载 .ts 文件"""
    try:
        # 解析URL，保留查询参数
        parsed_url = urlparse(m3u8_url)
        
        # 获取基础URL（不包含文件名和查询参数）
        base_path = parsed_url.path
        if 'index.m3u8' in base_path or '.m3u8' in base_path:
            base_path = '/'.join(base_path.split('/')[:-1]) + '/'
        base_url = f"{parsed_url.scheme}://{parsed_url.netloc}{base_path}"
        
        # 保存查询参数，可能包含认证信息
        query_params = parsed_url.query
        
        # 添加浏览器样式的请求头
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': f"{parsed_url.scheme}://{parsed_url.netloc}/",
            'Origin': f"{parsed_url.scheme}://{parsed_url.netloc}"
        }
        
        # 获取playlist.m3u8文件内容
        playlist_path = os.path.join(save_path, 'playlist.m3u8')
        if not os.path.exists(playlist_path):
            status_callback("playlist.m3u8 file not found. Please download the m3u8 file first.")
            return False
            
        with open(playlist_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        # 处理ts文件URL，确保保留查询参数
        ts_urls = []
        ts_filenames = []  # 存储原始文件名（不含查询参数）
        
        # 改进的M3U8解析逻辑
        for i, line in enumerate(lines):
            line = line.strip()
            # 跳过注释行和空行
            if line.startswith('#') or not line:
                continue
                
            # 处理不同类型的URL
            if line.startswith('http'):
                # 绝对URL
                ts_url = line
            elif line.startswith('/'):
                # 从域名根路径开始的URL
                ts_url = f"{parsed_url.scheme}://{parsed_url.netloc}{line}"
            else:
                # 相对URL
                ts_url = f"{base_url}{line}"
            
            # 如果原始URL有查询参数，且ts_url没有，添加这些参数
            # 注意：如果ts_url已经有自己的查询参数，则不添加m3u8的查询参数
            if query_params and '?' not in ts_url:
                ts_url = f"{ts_url}?{query_params}"
            
            # 提取原始文件名（不含查询参数）
            if '?' in line:
                original_filename = line.split('?')[0]
            else:
                original_filename = line
            
            # 如果文件名包含路径，只保留文件名部分
            if '/' in original_filename:
                original_filename = original_filename.split('/')[-1]
            
            ts_filenames.append(original_filename)
            ts_urls.append(ts_url)
        
        if not ts_urls:
            status_callback("No TS files found in the m3u8 playlist.")
            return False

        total_files = len(ts_urls)
        success_files = []
        failed_files = []

        # 检查已下载的文件，跳过已存在的文件
        existing_files = set(os.listdir(save_path))
        
        # 过滤出需要下载的文件
        filtered_ts_urls = []
        for i, (ts_url, original_filename) in enumerate(zip(ts_urls, ts_filenames)):
            # 检查是否已下载（两种可能的文件名）
            numbered_filename = f"{i:04d}.ts"
            if original_filename in existing_files or numbered_filename in existing_files:
                # 文件已存在，跳过
                success_files.append((i, ts_url, original_filename))
                continue
            filtered_ts_urls.append((i, ts_url, original_filename))

        # 已下载文件的数量
        completed_files = len(success_files)
        total_files = completed_files + len(filtered_ts_urls)

        status_callback(f"Total TS files: {total_files}, Already downloaded: {completed_files}, Need to download: {len(filtered_ts_urls)}")
        progress_callback(completed_files, total_files)  # 初始化进度条

        if not filtered_ts_urls:
            status_callback("All files already downloaded. You can merge them now.")
            return True

        # 确定最佳线程数
        # 根据网络条件和文件数量动态调整线程数
        network_speed = check_network_speed()
        
        if network_speed == "fast":
            optimal_threads = settings['max_threads']
        elif network_speed == "medium":
            optimal_threads = min(20, settings['max_threads'])
        elif network_speed == "slow":
            optimal_threads = min(10, settings['max_threads'])
        else:
            optimal_threads = settings['max_threads']
        
        status_callback(f"Network condition: {network_speed}, using {optimal_threads} download threads")
        
        # 使用优化后的线程数
        with ThreadPoolExecutor(max_workers=optimal_threads) as executor:
            future_to_url = {}
            
            # 根据设置决定使用原始文件名还是序号文件名
            use_original_filenames = settings.get('use_original_filenames', False)
            
            for i, ts_url, original_filename in filtered_ts_urls:
                if use_original_filenames:
                    # 使用原始文件名
                    target_filename = original_filename
                else:
                    # 使用序号文件名
                    target_filename = f"{i:04d}.ts"
                
                future = executor.submit(
                    download_single_ts, 
                    ts_url, 
                    os.path.join(save_path, target_filename)
                )
                future_to_url[future] = (i, ts_url, target_filename)
            
            # 用于计算下载速度
            start_time = time.time()
            downloaded_bytes = 0
            last_update_time = start_time
            
            # 处理完成的任务
            for future in as_completed(future_to_url):
                i, ts_url, filename = future_to_url[future]
                try:
                    success = future.result()
                    if success:
                        success_files.append((i, ts_url, filename))
                        
                        # 更新下载进度
                        progress_callback(len(success_files), total_files)
                        
                        # 计算下载速度
                        if settings.get('show_speed', True):
                            current_time = time.time()
                            if current_time - last_update_time >= 1:  # 每秒更新一次
                                try:
                                    file_size = os.path.getsize(os.path.join(save_path, filename))
                                    downloaded_bytes += file_size
                                    elapsed_time = current_time - start_time
                                    speed = downloaded_bytes / elapsed_time / 1024  # KB/s
                                    
                                    if speed > 1024:
                                        speed_str = f"{speed/1024:.2f} MB/s"
                                    else:
                                        speed_str = f"{speed:.2f} KB/s"
                                        
                                    status_callback(f"Downloaded: {len(success_files)}/{total_files}, Speed: {speed_str}")
                                    last_update_time = current_time
                                except:
                                    pass
                    else:
                        failed_files.append((i, ts_url, filename))
                        status_callback(f"Failed to download: {filename}")
                except Exception as e:
                    failed_files.append((i, ts_url, filename))
                    status_callback(f"Error downloading {filename}: {str(e)}")
        
        # 下载完成后的统计
        if failed_files:
            status_callback(f"Download completed with errors. {len(success_files)} succeeded, {len(failed_files)} failed.")
            return False
        else:
            status_callback(f"All {len(success_files)} files downloaded successfully.")
            return True
    except Exception as e:
        status_callback(f"An error occurred: {str(e)}")
        return False

def suggest_directory_name(url):
    """根据URL或当前时间生成建议的目录名"""
    try:
        # 尝试从URL中提取有意义的名称
        parsed = urlparse(url)
        path_parts = parsed.path.split('/')
        
        # 过滤掉空字符串和常见的无意义部分
        filtered_parts = [p for p in path_parts if p and p not in ('index.m3u8', 'playlist.m3u8', 'video')]
        
        if filtered_parts:
            # 使用最后一个有意义的部分
            name = filtered_parts[-1]
            # 移除文件扩展名
            name = os.path.splitext(name)[0]
            if name and len(name) > 2:  # 确保名称有意义
                return name
    except:
        pass
        
    # 如果无法从URL提取，使用时间戳
    return f"video_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"

def start_download():
    url = entry_url.get().strip()
    save_path = entry_save_path.get().strip()

    if not url or not save_path:
        messagebox.showwarning("Warning", "Please fill in both URL and Save Path.")
        return
        
    # 验证URL格式
    if not (url.startswith('http://') or url.startswith('https://')):
        messagebox.showwarning("Warning", "Please enter a valid URL starting with http:// or https://")
        return

    # 检查目录是否已包含之前下载的文件
    if os.path.exists(save_path) and os.path.exists(os.path.join(save_path, 'playlist.m3u8')):
        # 询问用户是否要清理目录或使用新目录
        choice = messagebox.askyesnocancel(
            "Directory Already Used", 
            "This directory already contains downloaded files. Would you like to:\n\n"
            "• Yes: Continue and overwrite existing files\n"
            "• No: Create a new subdirectory\n"
            "• Cancel: Abort download"
        )
        
        if choice is None:  # Cancel
            return
        elif choice is False:  # No - create new subdirectory
            # 生成建议的目录名
            suggested_name = suggest_directory_name(url)
            new_path = os.path.join(save_path, suggested_name)
            
            # 确保目录名唯一
            counter = 1
            original_new_path = new_path
            while os.path.exists(new_path):
                new_path = f"{original_new_path}_{counter}"
                counter += 1
                
            save_path = new_path
            entry_save_path.delete(0, tk.END)
            entry_save_path.insert(0, save_path)
    
    # 创建保存目录，如果创建失败则提示错误
    try:
        if not os.path.exists(save_path):
            os.makedirs(save_path)
    except Exception as e:
        messagebox.showerror("Error", f"Failed to create directory: {str(e)}")
        return

    # 重置进度条和状态
    progress_bar['value'] = 0
    progress_label.config(text="0/0")
    status_text.config(state=tk.NORMAL)
    status_text.delete(1.0, tk.END)
    status_text.config(state=tk.DISABLED)

    # 禁用开始下载按钮，防止重复点击
    button_start.config(state=tk.DISABLED)
    
    def update_progress(success_count, total_count):
        # 使用 after 方法在主线程中更新 UI
        root.after(0, lambda: _update_progress_ui(success_count, total_count))
    
    def _update_progress_ui(success_count, total_count):
        progress_bar['value'] = success_count / total_count * 100
        progress_label.config(text=f"{success_count}/{total_count}")
        root.update_idletasks()

    def update_status(message):
        # 使用 after 方法在主线程中更新 UI
        root.after(0, lambda: _update_status_ui(message))
    
    def _update_status_ui(message):
        status_text.config(state=tk.NORMAL)
        status_text.insert(tk.END, message + "\n")
        status_text.see(tk.END)  # 自动滚动到底部
        status_text.config(state=tk.DISABLED)

    # 检查URL是否包含查询参数，这可能表示它是一个临时URL
    if '?' in url and ('t=' in url or 'token=' in url or 'expire=' in url):
        if not messagebox.askyesno("URL Check", 
                                  "The URL appears to contain authentication tokens which may expire.\n"
                                  "If the download fails, you may need to get a fresh URL.\n\n"
                                  "Continue with download?"):
            return
    
    # 标准化 .m3u8 URL
    normalized_url = normalize_m3u8_url(url)
    if not normalized_url:
        messagebox.showwarning("Warning", "Invalid URL format.")
        button_start.config(state=tk.NORMAL)  # 重新启用按钮
        return
        
    update_status(f"Downloading playlist from: {normalized_url}")

    # 创建一个新线程来执行下载操作
    def download_thread():
        try:
            if download_m3u8(normalized_url, save_path):
                update_status("Playlist downloaded. Starting TS file download...")
                download_result = download_ts_files(normalized_url, save_path, update_progress, update_status)
                if download_result:
                    update_status("Download completed. You can now merge the files.")
                else:
                    update_status("Download failed or was interrupted.")
            else:
                update_status("Failed to download playlist.")
        finally:
            # 无论下载成功还是失败，都重新启用按钮
            root.after(0, lambda: button_start.config(state=tk.NORMAL))
    
    # 启动下载线程
    threading.Thread(target=download_thread, daemon=True).start()

def browse_save_path():
    # 使用上次的目录作为起点
    initial_dir = settings['last_directory'] if settings['last_directory'] else os.path.expanduser("~")
    path = filedialog.askdirectory(initialdir=initial_dir)
    if path:
        entry_save_path.delete(0, tk.END)
        entry_save_path.insert(0, path)
        # 更新上次使用的目录
        settings['last_directory'] = path
        save_settings()

def new_download():
    """重置界面，准备新的下载"""
    # 清空URL输入框
    entry_url.delete(0, tk.END)
    
    # 重置进度条
    progress_bar['value'] = 0
    progress_label.config(text="0/0")
    
    # 清空状态文本
    status_text.config(state=tk.NORMAL)
    status_text.delete(1.0, tk.END)
    status_text.config(state=tk.DISABLED)
    
    # 提示用户
    status_text.config(state=tk.NORMAL)
    status_text.insert(tk.END, "Ready for new download. Please enter a URL and select a save path.\n")
    status_text.config(state=tk.DISABLED)
    
    # 可选：询问用户是否要选择新的保存路径
    if messagebox.askyesno("New Download", "Would you like to select a new save directory?"):
        browse_save_path()

def merge_to_mp4():
    """将下载的 .ts 文件合并为 .mp4 文件"""
    save_path = entry_save_path.get().strip()
    if not save_path or not os.path.exists(save_path):
        messagebox.showwarning("Warning", "Please select a valid save path.")
        return
    
    # 检查是否有 .ts 文件
    ts_files = [f for f in os.listdir(save_path) if f.endswith('.ts')]
    if not ts_files:
        messagebox.showwarning("Warning", "No .ts files found in the selected directory.")
        return
    
    # 更智能地确定文件命名方式和排序
    def extract_sequence_number(filename):
        """从文件名中提取序列号"""
        # 首先检查是否是标准的数字格式（如0000.ts）
        if filename[:4].isdigit() and len(filename) >= 8:
            return int(filename[:4])
        
        # 检查常见的分段格式
        patterns = [
            # seg-数字-其他.ts 格式
            r'seg-(\d+)',
            # segment数字.ts 格式
            r'segment(\d+)',
            # index数字.ts 格式
            r'index(\d+)',
            # 处理类似 "index2.ts" 这样的格式 - 字母后面直接跟数字
            r'([a-zA-Z]+)(\d+)\.ts$',
            # 处理类似 "720P_4000K_441496441_2.ts" 这样的格式 - 下划线后跟数字.ts
            r'_(\d+)\.ts$',
            # 处理类似 "video_2.ts" 这样的格式 - 字母_数字.ts
            r'[a-zA-Z]+_(\d+)\.ts$',
            # 处理类似 "part-2.ts" 这样的格式 - 字母-数字.ts
            r'[a-zA-Z]+-(\d+)\.ts$',
            # 文件名中的任何数字序列
            r'(\d+)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, filename)
            if matches:
                # 根据模式的不同处理匹配结果
                if pattern == r'([a-zA-Z]+)(\d+)\.ts$':
                    # 对于 "index2.ts" 这样的格式，第二个捕获组是数字
                    return int(matches[0][1])
                elif isinstance(matches[0], tuple):
                    # 如果匹配结果是元组，取最后一个元素（通常是数字部分）
                    return int(matches[0][-1])
                else:
                    # 对于简单模式，直接取第一个匹配
                    return int(matches[0])
        
        # 尝试更复杂的分析 - 查找文件名中的所有数字序列
        all_numbers = re.findall(r'\d+', filename)
        if all_numbers:
            # 启发式规则：如果有多个数字，优先选择：
            # 1. 如果文件名以数字开头，选择第一个数字
            if filename[0].isdigit():
                return int(all_numbers[0])
            # 2. 如果文件名以字母开头且包含数字，选择第一个数字
            elif filename[0].isalpha():
                # 查找第一个数字的位置
                for i, char in enumerate(filename):
                    if char.isdigit():
                        # 找到数字开始的位置
                        start_pos = i
                        # 找到数字结束的位置
                        end_pos = start_pos
                        while end_pos < len(filename) and filename[end_pos].isdigit():
                            end_pos += 1
                        return int(filename[start_pos:end_pos])
            # 3. 否则，选择最后一个数字（通常是序列号）
            return int(all_numbers[-1])
        
        # 如果没有找到任何数字，返回文件名本身
        # 这样至少会按字母顺序排序
        return filename
    
    # 按提取的序列号排序
    ts_files.sort(key=extract_sequence_number)
    
    # 创建文件列表
    file_list_path = os.path.join(save_path, 'filelist.txt')
    with open(file_list_path, 'w', encoding='utf-8') as f:
        for ts_file in ts_files:
            f.write(f"file '{ts_file}'\n")
    
    # 设置输出文件名
    output_file = os.path.join(save_path, 'output.mp4')
    
    # 如果输出文件已存在，询问是否覆盖
    if os.path.exists(output_file):
        if not messagebox.askyesno("File Exists", "Output file already exists. Overwrite?"):
            # 用户选择不覆盖，提示选择新文件名
            new_output_file = filedialog.asksaveasfilename(
                initialdir=save_path,
                title="Save As",
                filetypes=(("MP4 files", "*.mp4"), ("All files", "*.*")),
                defaultextension=".mp4"
            )
            if not new_output_file:
                return  # 用户取消了操作
            output_file = new_output_file
    
    # 禁用合并按钮，防止重复点击
    button_merge.config(state=tk.DISABLED)
    
    # 更新状态
    def update_merge_status(message):
        status_text.config(state=tk.NORMAL)
        status_text.insert(tk.END, message + "\n")
        status_text.see(tk.END)  # 自动滚动到底部
        status_text.config(state=tk.DISABLED)
    
    # 显示排序信息
    update_merge_status(f"Found {len(ts_files)} TS files. Sorting by sequence number...")
    
    # 显示前几个文件的排序结果，帮助用户确认排序是否正确
    if len(ts_files) > 0:
        preview_count = min(5, len(ts_files))
        update_merge_status(f"First {preview_count} files in sequence:")
        for i in range(preview_count):
            update_merge_status(f"  {i+1}. {ts_files[i]}")
        
        if len(ts_files) > 10:
            update_merge_status("...")
            for i in range(max(preview_count, len(ts_files)-3), len(ts_files)):
                update_merge_status(f"  {i+1}. {ts_files[i]}")
    
    update_merge_status("Merging files...")
    
    # 创建一个新线程来执行合并操作
    def merge_thread():
        try:
            # 使用ffmpeg合并文件
            cmd = [
                'ffmpeg',
                '-f', 'concat',
                '-safe', '0',
                '-i', file_list_path,
                '-c', 'copy',
                '-y',  # 覆盖输出文件（如果存在）
                output_file
            ]
            
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                universal_newlines=True
            )
            
            # 读取输出并更新状态
            for line in process.stderr:
                # 使用 after 方法在主线程中更新 UI
                root.after(0, lambda l=line: update_merge_status(l))
            
            process.wait()
            
            if process.returncode == 0:
                # 合并成功
                root.after(0, lambda: update_merge_status("Merge completed successfully."))
                # 询问是否打开文件
                if messagebox.askyesno("Merge Complete", "Merge completed successfully. Open the file?"):
                    open_file(output_file)
            else:
                # 合并失败
                root.after(0, lambda: update_merge_status("Merge failed."))
        finally:
            # 无论合并成功还是失败，都重新启用按钮
            root.after(0, lambda: button_merge.config(state=tk.NORMAL))
            # 删除临时文件列表
            try:
                os.remove(file_list_path)
            except:
                pass
    
    # 启动合并线程
    threading.Thread(target=merge_thread, daemon=True).start()

# GUI setup
root = tk.Tk()
root.title("TS to MP4 Downloader")

frame = tk.Frame(root)
frame.pack(padx=10, pady=10)

label_url = tk.Label(frame, text="M3U8 URL:")
label_url.grid(row=0, column=0, sticky=tk.W)

entry_url = tk.Entry(frame, width=50)
entry_url.grid(row=0, column=1)

label_save_path = tk.Label(frame, text="Save Path:")
label_save_path.grid(row=1, column=0, sticky=tk.W)

entry_save_path = tk.Entry(frame, width=50)
entry_save_path.grid(row=1, column=1)

button_browse = tk.Button(frame, text="Browse", command=browse_save_path)
button_browse.grid(row=1, column=2)

button_start = tk.Button(frame, text="Start Download", command=start_download)
button_start.grid(row=2, column=1, pady=10)

button_merge = tk.Button(frame, text="Merge to MP4", command=merge_to_mp4)
button_merge.grid(row=2, column=2, pady=10)

# Progress Bar
progress_bar = ttk.Progressbar(frame, orient="horizontal", length=300, mode="determinate")
progress_bar.grid(row=3, column=0, columnspan=3, pady=10)

# Progress Label
progress_label = tk.Label(frame, text="0/0")
progress_label.grid(row=3, column=3, pady=10)

# Status Text Area
status_label = tk.Label(frame, text="Status Log:")
status_label.grid(row=4, column=0, sticky=tk.W)

status_text = scrolledtext.ScrolledText(frame, width=80, height=10, state=tk.DISABLED)
status_text.grid(row=5, column=0, columnspan=4, pady=10)

# 添加设置变量
settings = {
    'last_directory': '',
    'max_threads': 10,
    'delete_ts_after_merge': False,
    'chunk_size': 1024,
    'show_speed': True,
    'use_original_filenames': False
}

# 加载上次使用的目录
def load_settings():
    try:
        if os.path.exists('settings.json'):
            with open('settings.json', 'r') as f:
                loaded_settings = json.load(f)
                settings.update(loaded_settings)
    except:
        pass  # 如果加载失败，使用默认设置

# 保存设置
def save_settings():
    try:
        with open('settings.json', 'w') as f:
            json.dump(settings, f)
    except:
        pass

# 创建菜单
def create_menu():
    menu_bar = tk.Menu(root)
    
    # 文件菜单
    file_menu = tk.Menu(menu_bar, tearoff=0)
    file_menu.add_command(label="Exit", command=root.quit)
    menu_bar.add_cascade(label="File", menu=file_menu)
    
    # 设置菜单
    settings_menu = tk.Menu(menu_bar, tearoff=0)
    settings_menu.add_command(label="Thread Count", command=set_thread_count)
    settings_menu.add_command(label="Chunk Size", command=set_chunk_size)
    settings_menu.add_command(label="Connection Timeout", command=set_timeout)
    settings_menu.add_separator()
    settings_menu.add_checkbutton(label="Use Original Filenames", 
                                 variable=tk.BooleanVar(value=settings.get('use_original_filenames', False)),
                                 command=lambda: toggle_setting('use_original_filenames'))
    settings_menu.add_checkbutton(label="Enable Speed Monitor", 
                                 variable=tk.BooleanVar(value=settings.get('show_speed', True)),
                                 command=lambda: toggle_setting('show_speed'))
    menu_bar.add_cascade(label="Settings", menu=settings_menu)
    
    # 帮助菜单
    help_menu = tk.Menu(menu_bar, tearoff=0)
    help_menu.add_command(label="Help", command=show_help)
    help_menu.add_command(label="About", command=show_about)
    menu_bar.add_cascade(label="Help", menu=help_menu)
    
    root.config(menu=menu_bar)

def set_thread_count():
    # 创建线程数设置对话框
    thread_dialog = tk.Toplevel(root)
    thread_dialog.title("Set Thread Count")
    thread_dialog.geometry("300x100")
    thread_dialog.resizable(False, False)
    
    tk.Label(thread_dialog, text="Number of download threads (1-20):").pack(pady=5)
    
    thread_var = tk.StringVar(value=str(settings['max_threads']))
    thread_entry = tk.Entry(thread_dialog, textvariable=thread_var, width=5)
    thread_entry.pack(pady=5)
    
    def save_thread_count():
        try:
            count = int(thread_var.get())
            if 1 <= count <= 20:
                settings['max_threads'] = count
                save_settings()
                thread_dialog.destroy()
            else:
                messagebox.showwarning("Invalid Value", "Please enter a number between 1 and 20.")
        except ValueError:
            messagebox.showwarning("Invalid Value", "Please enter a valid number.")
    
    tk.Button(thread_dialog, text="Save", command=save_thread_count).pack(pady=5)

def set_chunk_size():
    # 创建块大小设置对话框
    chunk_dialog = tk.Toplevel(root)
    chunk_dialog.title("Set Download Chunk Size")
    chunk_dialog.geometry("300x120")
    chunk_dialog.resizable(False, False)
    
    tk.Label(chunk_dialog, text="Chunk size in KB (256-4096):").pack(pady=5)
    
    chunk_var = tk.StringVar(value=str(settings.get('chunk_size', 1024)))
    chunk_entry = tk.Entry(chunk_dialog, textvariable=chunk_var, width=6)
    chunk_entry.pack(pady=5)
    
    def save_chunk_size():
        try:
            size = int(chunk_var.get())
            if 256 <= size <= 4096:
                settings['chunk_size'] = size
                save_settings()
                chunk_dialog.destroy()
            else:
                messagebox.showwarning("Invalid Value", "Please enter a number between 256 and 4096.")
        except ValueError:
            messagebox.showwarning("Invalid Value", "Please enter a valid number.")
    
    tk.Button(chunk_dialog, text="Save", command=save_chunk_size).pack(pady=5)

def set_timeout():
    # 创建连接超时设置对话框
    timeout_dialog = tk.Toplevel(root)
    timeout_dialog.title("Set Connection Timeout")
    timeout_dialog.geometry("300x100")
    timeout_dialog.resizable(False, False)
    
    tk.Label(timeout_dialog, text="Connection timeout in seconds (5-30):").pack(pady=5)
    
    timeout_var = tk.StringVar(value=str(settings.get('timeout', 15)))
    timeout_entry = tk.Entry(timeout_dialog, textvariable=timeout_var, width=5)
    timeout_entry.pack(pady=5)
    
    def save_timeout():
        try:
            timeout = int(timeout_var.get())
            if 5 <= timeout <= 30:
                settings['timeout'] = timeout
                save_settings()
                timeout_dialog.destroy()
            else:
                messagebox.showwarning("Invalid Value", "Please enter a number between 5 and 30.")
        except ValueError:
            messagebox.showwarning("Invalid Value", "Please enter a valid number.")
    
    tk.Button(timeout_dialog, text="Save", command=save_timeout).pack(pady=5)

def toggle_setting(setting):
    # 创建设置切换对话框
    toggle_dialog = tk.Toplevel(root)
    toggle_dialog.title("Toggle Setting")
    toggle_dialog.geometry("300x100")
    toggle_dialog.resizable(False, False)
    
    tk.Label(toggle_dialog, text=f"Current value: {settings[setting]}").pack(pady=5)
    
    def save_toggle():
        settings[setting] = not settings[setting]
        save_settings()
        toggle_dialog.destroy()
    
    tk.Button(toggle_dialog, text="Toggle", command=save_toggle).pack(pady=5)

def show_help():
    help_text = """
    How to use this program:
    
    1. Enter the M3U8 URL in the URL field.
    2. Choose a save directory for the downloaded files.
    3. Click "Start Download" to begin downloading.
    4. After download completes, click "Merge to MP4" to create the final video.
    
    Tips:
    - The program will automatically skip already downloaded files.
    - Make sure ffmpeg is installed on your system.
    - If you get a "URL has expired" error, you need to get a fresh URL from the source.
      These URLs often contain authentication tokens that expire after some time.
    """
    
    help_dialog = tk.Toplevel(root)
    help_dialog.title("Help")
    help_dialog.geometry("500x300")
    
    help_text_widget = scrolledtext.ScrolledText(help_dialog, wrap=tk.WORD)
    help_text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    help_text_widget.insert(tk.END, help_text)
    help_text_widget.config(state=tk.DISABLED)

def show_about():
    about_text = """
    TS to MP4 Downloader
    Version 1.0
    
    A tool for downloading and merging TS video segments.
    
    Requirements:
    - Python 3.6+
    - ffmpeg
    """
    
    messagebox.showinfo("About", about_text)

# 在GUI设置中添加新按钮
button_new = tk.Button(frame, text="New Download", command=new_download)
button_new.grid(row=2, column=0, pady=10)

def open_file(file_path):
    """打开指定的文件"""
    try:
        if os.name == 'nt':  # Windows
            os.startfile(file_path)
        elif os.name == 'posix':  # macOS or Linux
            if sys.platform == 'darwin':  # macOS
                subprocess.call(['open', file_path])
            else:  # Linux
                subprocess.call(['xdg-open', file_path])
    except Exception as e:
        messagebox.showerror("Error", f"Could not open file: {str(e)}")

root.mainloop()



