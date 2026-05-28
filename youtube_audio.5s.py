#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# <swiftbar.title>YouTube Simples Player</swiftbar.title>
# <swiftbar.version>1.0</swiftbar.version>
# <swiftbar.author>Antigravity</swiftbar.author>
# <swiftbar.desc>YouTube Audio-Only Background Player (Apple Silicon M1 optimized)</swiftbar.desc>

import sys
import os
import json
import socket
import subprocess
import time
import shutil

# Prevent python from creating __pycache__ folders and .pyc files in the plugins folder
sys.dont_write_bytecode = True

# 1. PATH Setup
# When executed from SwiftBar, the environment PATH might be restricted.
# Prepend typical Homebrew folders to make sure we find 'mpv' and 'yt-dlp'.
for path in ["/opt/homebrew/bin", "/usr/local/bin"]:
    if path not in os.environ["PATH"]:
        os.environ["PATH"] = path + os.path.pathsep + os.environ["PATH"]

# Constants
SOCKET_PATH = "/tmp/yt-audio-player.sock"
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
STATE_FILE = os.path.join(SCRIPT_DIR, ".yt_audio_state.json")
HISTORY_FILE = os.path.join(SCRIPT_DIR, ".yt_audio_history.json")
IDLE_TITLE = "Em Espera (Sem faixa ativa)"

# 2. Dependency Verification
def check_dependencies():
    mpv_ok = shutil.which("mpv") is not None
    ytdl_ok = shutil.which("yt-dlp") is not None
    return mpv_ok, ytdl_ok

# 3. macOS Native Notifications & Dialogs
def show_notification(title, message):
    escaped_title = title.replace('"', '\\"')
    escaped_message = message.replace('"', '\\"')
    applescript = f'display notification "{escaped_message}" with title "{escaped_title}"'
    subprocess.run(["osascript", "-e", applescript])

def get_clipboard_url():
    try:
        proc = subprocess.run(
            ["/usr/bin/pbpaste"],
            capture_output=True,
            text=True
        )
        url = proc.stdout.strip()
        if "youtube.com" in url or "youtu.be" in url:
            return url
    except Exception:
        pass
    return None

def add_via_clipboard():
    url = get_clipboard_url()
    if url:
        if add_url(url):
            show_notification("Vídeo Adicionado", "O vídeo foi adicionado à fila com sucesso.")
        else:
            show_notification("Erro", "Não foi possível carregar o vídeo.")
    else:
        show_notification("Clipboard Vazio", "Nenhum URL do YouTube válido no clipboard.")

def add_via_applescript():
    applescript = """
    tell application "System Events"
        activate
        try
            set theResponse to display dialog "Insira o URL do YouTube (vídeos ou playlists):" default answer "" with title "YouTube Simples" buttons {"Cancelar", "Adicionar"} default button "Adicionar"
            return text returned of theResponse
        on error
            return ""
        end try
    end tell
    """
    try:
        proc = subprocess.run(
            ["osascript", "-e", applescript],
            capture_output=True,
            text=True
        )
        if proc.returncode == 0:
            url = proc.stdout.strip()
            if url:
                if add_url(url):
                    show_notification("Vídeo Adicionado", "O URL do YouTube foi adicionado com sucesso.")
                else:
                    show_notification("Erro", "Não foi possível adicionar o vídeo.")
    except Exception as e:
        show_notification("Erro de Script", str(e))

# 4. IPC Communication with mpv
def send_mpv_command(command_list):
    if not os.path.exists(SOCKET_PATH):
        return {"error": "socket_not_found"}
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(1.2)
        s.connect(SOCKET_PATH)
        
        request_id = int(time.time() * 1000)
        payload = {"command": command_list, "request_id": request_id}
        s.sendall((json.dumps(payload) + "\n").encode("utf-8"))
        
        buffer = ""
        while True:
            chunk = s.recv(4096).decode("utf-8", errors="ignore")
            if not chunk:
                break
            buffer += chunk
            while "\n" in buffer:
                line, buffer = buffer.split("\n", 1)
                try:
                    data = json.loads(line)
                    if data.get("request_id") == request_id:
                        s.close()
                        return data
                except json.JSONDecodeError:
                    continue
        s.close()
        return {"error": "no_response"}
    except ConnectionRefusedError:
        # Socket file is stale, delete it
        try:
            os.remove(SOCKET_PATH)
        except OSError:
            pass
        return {"error": "connection_refused"}
    except Exception as e:
        return {"error": str(e)}

def is_mpv_running():
    if not os.path.exists(SOCKET_PATH):
        return False
    res = send_mpv_command(["get_property", "mpv-version"])
    return res.get("error") == "success"

def resolve_missing_titles():
    python_bin = sys.executable
    script = f"""
import subprocess, json, os, sys, time
state_file = {repr(STATE_FILE)}
history_file = {repr(HISTORY_FILE)}

for path in ["/opt/homebrew/bin", "/usr/local/bin"]:
    if path not in os.environ["PATH"]:
        os.environ["PATH"] = path + os.path.pathsep + os.environ["PATH"]

try:
    if not os.path.exists(state_file):
        sys.exit(0)
        
    with open(state_file, "r") as f:
        state = json.load(f)
        
    urls = state.get("urls", [])
    cache = state.setdefault("titles_cache", {{}})
    
    missing_urls = [u for u in urls if u and u not in cache]
    if not missing_urls:
        sys.exit(0)
        
    # Resolve first 15 missing URLs in this background run to keep it fast
    updated = False
    for url in missing_urls[:15]:
        title = None
        if os.path.exists(history_file):
            try:
                with open(history_file, "r") as f:
                    history = json.load(f)
                for item in history:
                    if item.get("url") == url:
                        t = item.get("title")
                        if t and not t.startswith("http"):
                            title = t
                            break
            except Exception:
                pass
                
        if not title:
            proc = subprocess.run(
                ["yt-dlp", "--get-title", "--no-warnings", "--playlist-items", "1", url],
                capture_output=True,
                text=True,
                timeout=8
            )
            if proc.returncode == 0:
                title = proc.stdout.strip()
                
        if title:
            try:
                with open(state_file, "r") as f:
                    curr_state = json.load(f)
            except Exception:
                curr_state = state
            
            curr_cache = curr_state.setdefault("titles_cache", {{}})
            curr_cache[url] = title
            state = curr_state
            updated = True
            
            try:
                with open(state_file, "w") as f:
                    json.dump(state, f, indent=2)
            except Exception:
                pass
                
            time.sleep(0.5)
except Exception:
    pass
"""
    subprocess.Popen(
        [python_bin, "-c", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True
    )


# 5. Persistent Playlist Cache
def save_current_playlist():
    if not os.path.exists(SOCKET_PATH):
        return
    res = send_mpv_command(["get_property", "playlist"])
    if res.get("error") == "success" and res.get("data"):
        playlist = res.get("data")
        urls = [item.get("filename") for item in playlist if item.get("filename")]
        current_index = 0
        for i, item in enumerate(playlist):
            if item.get("current"):
                current_index = i
                break
        
        # Load existing state to check changes and preserve cache
        existing_state = {}
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r") as f:
                    existing_state = json.load(f)
            except Exception:
                pass
                
        # Avoid redundant disk writes if playlist & current index haven't changed
        if existing_state.get("urls") == urls and existing_state.get("current_index") == current_index:
            return

        # Prepare new state preserving titles_cache
        state = {
            "urls": urls,
            "current_index": current_index,
            "updated_at": time.time(),
            "titles_cache": existing_state.get("titles_cache", {})
        }
        
        # We can also harvest any newly resolved titles from the mpv playlist property!
        titles_cache = state["titles_cache"]
        for item in playlist:
            f_name = item.get("filename")
            t_title = item.get("title")
            if f_name and t_title and not t_title.startswith("http"):
                titles_cache[f_name] = t_title
                
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(state, f, indent=2)
            resolve_missing_titles()
        except Exception:
            pass

def load_saved_playlist():
    if not os.path.exists(STATE_FILE):
        return
    try:
        with open(STATE_FILE, "r") as f:
            state = json.load(f)
        urls = state.get("urls", [])
        current_index = state.get("current_index", 0)
        
        if not urls:
            return
            
        # Add files to mpv silently
        for i, url in enumerate(urls):
            mode = "replace" if i == 0 else "append"
            send_mpv_command(["loadfile", url, mode])
            
        # Jump to last active track if index is within boundaries
        if current_index > 0 and current_index < len(urls):
            send_mpv_command(["set_property", "playlist-pos", current_index])
    except Exception:
        pass

# 5b. Playback History Cache
def load_history():
    if not os.path.exists(HISTORY_FILE):
        return []
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return []

def save_history(history):
    try:
        with open(HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
    except Exception:
        pass

def resolve_title_background(url):
    python_bin = sys.executable
    script = f"""
import subprocess, json, os, sys
url = {repr(url)}
state_file = {repr(STATE_FILE)}
history_file = {repr(HISTORY_FILE)}

for path in ["/opt/homebrew/bin", "/usr/local/bin"]:
    if path not in os.environ["PATH"]:
        os.environ["PATH"] = path + os.path.pathsep + os.environ["PATH"]

try:
    title = None
    entries_map = {{}}
    
    # 1. Check if it's a playlist URL
    if "list=" in url or "playlist" in url:
        proc_pl = subprocess.run(
            ["yt-dlp", "--flat-playlist", "-J", url],
            capture_output=True,
            text=True,
            timeout=15
        )
        if proc_pl.returncode == 0:
            data = json.loads(proc_pl.stdout)
            title = data.get("title")
            for entry in data.get("entries", []):
                e_url = entry.get("url") or (f"https://www.youtube.com/watch?v={{entry.get('id')}}" if entry.get("id") else None)
                e_title = entry.get("title")
                if e_url and e_title:
                    entries_map[e_url] = e_title
                    
    # 2. If not a playlist, or if playlist title fetch failed, treat as single video
    if not title:
        proc = subprocess.run(
            ["yt-dlp", "--get-title", "--no-warnings", "--playlist-items", "1", url],
            capture_output=True,
            text=True,
            timeout=10
        )
        if proc.returncode == 0:
            title = proc.stdout.strip()
            if title:
                entries_map[url] = title

    # 3. Update titles_cache in state_file
    if entries_map or title:
        state = {{}}
        if os.path.exists(state_file):
            try:
                with open(state_file, "r") as f:
                    state = json.load(f)
            except Exception:
                pass
                
        cache = state.setdefault("titles_cache", {{}})
        updated = False
        
        # Add playlist/video title itself to cache
        if title and url not in cache:
            cache[url] = title
            updated = True
            
        # Add all individual playlist entries to cache
        for e_url, e_title in entries_map.items():
            if cache.get(e_url) != e_title:
                cache[e_url] = e_title
                updated = True
                
        if updated:
            try:
                with open(state_file, "w") as f:
                    json.dump(state, f, indent=2)
            except Exception:
                pass

        # 4. Also update history file safely for any matching URLs
        if os.path.exists(history_file):
            try:
                with open(history_file, "r") as f:
                    history = json.load(f)
                h_updated = False
                for item in history:
                    item_url = item.get("url")
                    if item_url == url and title and (item.get("title") == url or item.get("title", "").startswith("http")):
                        item["title"] = title
                        h_updated = True
                    elif item_url in entries_map and (item.get("title") == item_url or item.get("title", "").startswith("http")):
                        item["title"] = entries_map[item_url]
                        h_updated = True
                if h_updated:
                    with open(history_file, "w") as f:
                        json.dump(history, f, indent=2)
            except Exception:
                pass
except Exception:
    pass
"""
    subprocess.Popen(
        [python_bin, "-c", script],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True
    )

def add_to_history(url, title=None):
    if not url:
        return
    history = load_history()
    url = url.strip()
    
    # Avoid adding internal or non-youtube paths
    if not (url.startswith("http://") or url.startswith("https://") or "youtube.com" in url or "youtu.be" in url):
        return
        
    # Check if the most recent item is already this URL
    if history and history[0].get("url") == url:
        # If the title is now resolved but was previously just the URL, update it
        if title and not title.startswith("http") and (history[0].get("title") == url or history[0].get("title", "").startswith("http")):
            history[0]["title"] = title
            save_history(history)
        return
        
    existing_item = None
    for item in history:
        if item.get("url") == url:
            existing_item = item
            break
            
    if existing_item:
        history.remove(existing_item)
        existing_item["timestamp"] = time.time()
        if title and not title.startswith("http") and (existing_item.get("title") == url or existing_item.get("title", "").startswith("http")):
            existing_item["title"] = title
        history.insert(0, existing_item)
    else:
        if not title:
            title = url
        new_item = {
            "url": url,
            "title": title,
            "timestamp": time.time()
        }
        history.insert(0, new_item)
        
    save_history(history[:50])
    
    if not title or title == url or title.startswith("http"):
        resolve_title_background(url)

def clear_history_command():
    try:
        if os.path.exists(HISTORY_FILE):
            os.remove(HISTORY_FILE)
        show_notification("Histórico Limpo", "O histórico de reprodução foi apagado.")
    except Exception as e:
        show_notification("Erro", f"Não foi possível limpar o histórico: {e}")

def remove_history_item(url):
    try:
        history = load_history()
        new_history = [item for item in history if item.get("url") != url]
        save_history(new_history)
        show_notification("Item Removido", "O item foi removido do histórico.")
    except Exception as e:
        show_notification("Erro", f"Não foi possível remover o item: {e}")

# 6. Core Controls
def start_mpv():
    if is_mpv_running():
        return True
        
    mpv_bin = shutil.which("mpv")
    if not mpv_bin:
        return False
        
    if os.path.exists(SOCKET_PATH):
        try:
            os.remove(SOCKET_PATH)
        except OSError:
            pass
            
    # Optimize flags for Apple Silicon M1 (bestaudio forces yt-dlp to stream audio only, extremely lightweight!)
    cmd = [
        mpv_bin,
        "--no-video",
        f"--input-ipc-server={SOCKET_PATH}",
        "--idle=yes",
        "--loop-playlist=force",
        # Force yt-dlp to parse and load full playlists when loading watch + playlist URLs
        "--ytdl-raw-options=yes-playlist=",
        # Prioritize AAC (m4a) which uses Apple Silicon hardware audio decoders (extremely low CPU)
        "--ytdl-format=bestaudio[ext=m4a]/bestaudio",
        # Restrict the demuxer lookahead & back cache sizes to keep RAM footprint extremely tiny (~30MB)
        "--demuxer-max-bytes=5M",
        "--demuxer-max-back-bytes=1M",
        # Disable audio pitch correction DSP to save minor CPU cycles
        "--audio-pitch-correction=no",
    ]
    
    subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        start_new_session=True
    )
    
    # Wait for the player to boot and establish socket
    for _ in range(30):
        if is_mpv_running():
            load_saved_playlist()
            return True
        time.sleep(0.1)
        
    return False

def play_command(url=None):
    if not url:
        if not start_mpv():
            return False
        res = send_mpv_command(["set_property", "pause", False])
        return res.get("error") == "success"
    else:
        if not start_mpv():
            return False
        res = send_mpv_command(["loadfile", url, "replace"])
        time.sleep(0.2)
        save_current_playlist()
        add_to_history(url)
        return res.get("error") == "success"

def pause_command():
    return send_mpv_command(["set_property", "pause", True]).get("error") == "success"

def toggle_command():
    if not is_mpv_running():
        return start_mpv()
    res = send_mpv_command(["cycle", "pause"])
    return res.get("error") == "success"

def mute_command():
    if not is_mpv_running():
        return False
    res = send_mpv_command(["cycle", "mute"])
    return res.get("error") == "success"

def stop_command():
    if not is_mpv_running():
        return True
    send_mpv_command(["quit"])
    if os.path.exists(SOCKET_PATH):
        try:
            os.remove(SOCKET_PATH)
        except OSError:
            pass
    return True

def next_command():
    if not is_mpv_running():
        return False
    res = send_mpv_command(["playlist-next"])
    return res.get("error") == "success"

def prev_command():
    if not is_mpv_running():
        return False
    res = send_mpv_command(["playlist-prev"])
    return res.get("error") == "success"

def clear_command():
    if not is_mpv_running():
        return False
    res = send_mpv_command(["playlist-clear"])
    save_current_playlist()
    return res.get("error") == "success"

def add_url(url):
    if not start_mpv():
        return False
    res = send_mpv_command(["loadfile", url, "append-play"])
    time.sleep(0.25)
    save_current_playlist()
    add_to_history(url)
    return res.get("error") == "success"

def select_track(index):
    if not is_mpv_running():
        return False
    try:
        idx = int(index)
        res = send_mpv_command(["set_property", "playlist-pos", idx])
        return res.get("error") == "success"
    except ValueError:
        return False

# 7. Helper Utilities
def format_time(seconds):
    if seconds is None:
        return "00:00"
    seconds = int(seconds)
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    secs = seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    else:
        return f"{minutes:02d}:{secs:02d}"

def update_title_cache(url, title):
    if not url or not title or title.startswith(("http://", "https://", "A carregar stream")):
        return
    try:
        state = {}
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
        
        cache = state.setdefault("titles_cache", {})
        if cache.get(url) != title:
            cache[url] = title
            with open(STATE_FILE, "w") as f:
                json.dump(state, f, indent=2)
    except Exception:
        pass

def get_cached_title(url, mpv_title=None):
    if mpv_title and not mpv_title.startswith(("http://", "https://", "A carregar stream")):
        # Update cache with recently resolved mpv title
        update_title_cache(url, mpv_title)
        return mpv_title
        
    # Check STATE_FILE cache
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                state = json.load(f)
            cache = state.get("titles_cache", {})
            if url in cache:
                title = cache[url]
                if title and not title.startswith(("http://", "https://", "A carregar stream")):
                    return title
        except Exception:
            pass
            
    # Check history file
    history = load_history()
    for item in history:
        if item.get("url") == url:
            title = item.get("title")
            if title and not title.startswith(("http://", "https://", "A carregar stream")):
                update_title_cache(url, title)
                return title
                
    return None

def get_player_status():
    if not is_mpv_running():
        return {"status": "stopped", "paused": True, "muted": False, "title": "", "time_pos": 0.0, "duration": 0.0}
    
    pause_res = send_mpv_command(["get_property", "pause"])
    mute_res = send_mpv_command(["get_property", "mute"])
    title_res = send_mpv_command(["get_property", "media-title"])
    time_res = send_mpv_command(["get_property", "time-pos"])
    duration_res = send_mpv_command(["get_property", "duration"])
    
    is_paused = pause_res.get("data", False) if pause_res.get("error") == "success" else False
    is_muted = mute_res.get("data", False) if mute_res.get("error") == "success" else False
    title = title_res.get("data", "") if title_res.get("error") == "success" else ""
    time_pos = time_res.get("data", 0.0) if time_res.get("error") == "success" else 0.0
    duration = duration_res.get("data", 0.0) if duration_res.get("error") == "success" else 0.0
    
    # Try resolving friendly title
    path_res = send_mpv_command(["get_property", "path"])
    current_path = path_res.get("data") if path_res.get("error") == "success" else None
    
    friendly_title = None
    if current_path:
        friendly_title = get_cached_title(current_path, title)
        
    if friendly_title:
        title = friendly_title
    elif title and title.startswith(("http://", "https://")):
        title = "A carregar stream do YouTube..."
        
    # Automatically update and save the persistent playlist state/index
    save_current_playlist()
    
    # Automatically log the currently playing track to the history
    try:
        if current_path:
            friendly_title = title if (title and not title.startswith(("http://", "https://", "A carregar stream"))) else None
            add_to_history(current_path, friendly_title)
    except Exception:
        pass
    
    # Update history entry titles from the playing/playlist files if they resolve
    try:
        playlist_res = send_mpv_command(["get_property", "playlist"])
        if playlist_res.get("error") == "success" and playlist_res.get("data"):
            playlist = playlist_res.get("data")
            history = load_history()
            history_updated = False
            for item in playlist:
                filename = item.get("filename")
                t = item.get("title")
                if filename and t and not t.startswith("http"):
                    for h_item in history:
                        if h_item.get("url") == filename and (h_item.get("title") == filename or h_item.get("title", "").startswith("http")):
                            h_item["title"] = t
                            history_updated = True
            if history_updated:
                save_history(history)
    except Exception:
        pass
        
    return {
        "status": "paused" if is_paused else "playing",
        "paused": is_paused,
        "muted": is_muted,
        "title": title or IDLE_TITLE,
        "time_pos": time_pos,
        "duration": duration
    }

# 8. Dependency Installer Helper
def install_dependencies():
    print("=" * 60)
    print(" YouTube Simples - Instalação de Dependências ".center(60, "="))
    print("=" * 60)
    print("Este assistente irá instalar o 'mpv' e o 'yt-dlp' via Homebrew.")
    print("Por favor, aguarde...")
    print()
    
    # Search for valid Homebrew path
    brew_bin = shutil.which("brew")
    if not brew_bin:
        for p in ["/opt/homebrew/bin/brew", "/usr/local/bin/brew"]:
            if os.path.exists(p):
                brew_bin = p
                break
    if not brew_bin:
        brew_bin = "/opt/homebrew/bin/brew" # fallback
        
    if not os.path.exists(brew_bin):
        print("Homebrew não encontrado!")
        print("Por favor, instale o Homebrew acedendo a https://brew.sh e depois volte a tentar.")
        print()
        print("Pressione ENTER para fechar esta janela...")
        input()
        return
        
    cmd = [brew_bin, "install", "mpv", "yt-dlp"]
    print(f"A executar: {' '.join(cmd)}")
    subprocess.run(cmd)
    
    print()
    print("=" * 60)
    print("Instalação concluída com sucesso! Já pode abrir o player.")
    print("Pressione ENTER para fechar esta janela...")
    input()

# 9. CLI/TUI Terminal Dashboard
def draw_tui():
    status = get_player_status()
    mpv_ok, ytdl_ok = check_dependencies()
    
    lines = []
    lines.append("\033[H\033[2J") # Clear console screen & move cursor to top-left
    lines.append("=" * 65)
    lines.append(" 🎧  YOUTUBE SIMPLES - LEITOR DE ÁUDIO BACKGROUND (M1) ".center(65, "="))
    lines.append("=" * 65)
    lines.append("")
    
    if not mpv_ok or not ytdl_ok:
        lines.append("⚠️  ATENÇÃO: Faltam dependências essenciais no seu sistema!")
        if not mpv_ok:
            lines.append("   [X] mpv está em falta")
        if not ytdl_ok:
            lines.append("   [X] yt-dlp está em falta")
        lines.append("")
        lines.append("Pressione 's' para fechar e execute o comando:")
        lines.append("   ./yt_audio_player.py install-deps")
        lines.append("para instalar automaticamente utilizando o Homebrew.")
        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()
        return

    if status["status"] == "stopped":
        lines.append("  Estado: ⏹️  PARADO (O leitor mpv não está a correr)")
        lines.append("  Música: Nenhuma faixa de áudio selecionada")
        lines.append("")
        lines.append("  [A] Adicionar URL do YouTube    [C] Adicionar do Clipboard")
        lines.append("  [S] Sair e parar player         [Q] Fechar TUI (continua em background)")
    else:
        state_str = "▶️  A TOCAR" if status["status"] == "playing" else "⏸️  PAUSADO"
        if status["muted"]:
            state_str += " (🔇 SILENCIADO)"
            
        lines.append(f"  Estado: {state_str}")
        
        title = status["title"]
        if len(title) > 55:
            title = title[:52] + "..."
        lines.append(f"  Áudio: 🎵  {title}")
        
        # Calculate progress
        time_pos = status["time_pos"]
        duration = status["duration"]
        
        time_str = format_time(time_pos)
        duration_str = format_time(duration)
        
        percent = 0.0
        if duration and duration > 0:
            percent = (time_pos / duration) * 100.0
            
        bar_width = 40
        filled = int(percent / 100.0 * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        
        lines.append(f"  Progresso: [{bar}] {percent:.1f}%")
        lines.append(f"             {time_str} / {duration_str}")
        lines.append("")
        
        # Fila de reprodução (Playlist Queue)
        lines.append("--- Fila de Reprodução (Top 5) ---")
        playlist_res = send_mpv_command(["get_property", "playlist"])
        if playlist_res.get("error") == "success" and playlist_res.get("data"):
            playlist = playlist_res.get("data")
            for i, item in enumerate(playlist[:5]):
                filename = item.get("filename")
                t = item.get("title")
                
                cached_t = get_cached_title(filename, t)
                if cached_t:
                    t = cached_t
                elif not t or t.startswith("http"):
                    t = filename or "Sem título"
                    
                if t.startswith("http"):
                    t = "A carregar stream do YouTube..."
                    
                if len(t) > 48:
                    t = t[:45] + "..."
                marker = "👉" if item.get("current") else "  "
                lines.append(f"  {marker} {i+1}. {t}")
            if len(playlist) > 5:
                lines.append(f"     ... e mais {len(playlist) - 5} vídeos na fila.")
        else:
            lines.append("  (A fila está vazia. Adicione um URL para começar)")
            
        lines.append("-" * 65)
        lines.append("  [Espaço] Play/Pause    [M] Mute/Unmute    [N] Seguinte    [P] Anterior")
        lines.append("  [A] Adicionar URL      [C] Adicionar do Clipboard   [X] Limpar Fila")
        lines.append("  [S] Sair e parar       [Q] Fechar TUI (continua background)")
        
    lines.append("")
    lines.append("=" * 65)
    sys.stdout.write("\n".join(lines))
    sys.stdout.flush()

def resize_terminal():
    # Only try to resize if we are running in Terminal.app on macOS
    if os.environ.get("TERM_PROGRAM") == "Apple_Terminal" or "TERM" in os.environ:
        applescript = """
        tell application "Terminal"
            try
                set number of columns of window 1 to 70
                set number of rows of window 1 to 22
            end try
        end tell
        """
        try:
            subprocess.run(["osascript", "-e", applescript], capture_output=True)
        except Exception:
            pass

def run_tui():
    import select
    
    # Try importing terminal utilities
    try:
        import tty
        import termios
    except ImportError:
        print("Erro: Este terminal não suporta o modo raw interativo do TUI.")
        print("Use via CLI (e.g. ./yt_audio_player.py play <url>) ou através do SwiftBar.")
        return

    # Resize terminal window to perfect dimensions to show TUI dashboard beautifully
    resize_terminal()

    # Auto-start player
    start_mpv()
    
    # Configure low-level stdin terminal controls for single key presses
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    
    try:
        tty.setraw(fd)
        last_refresh = 0
        
        while True:
            now = time.time()
            if now - last_refresh >= 1.0:
                draw_tui()
                last_refresh = now
                
            rlist, _, _ = select.select([sys.stdin], [], [], 0.2)
            if rlist:
                ch = sys.stdin.read(1)
                
                # Command bindings
                if ch == ' ':
                    toggle_command()
                    draw_tui()
                elif ch.lower() == 'm':
                    mute_command()
                    draw_tui()
                elif ch.lower() == 'n':
                    next_command()
                    draw_tui()
                elif ch.lower() == 'p':
                    prev_command()
                    draw_tui()
                elif ch.lower() == 'x':
                    clear_command()
                    draw_tui()
                elif ch.lower() == 'c':
                    # Add from clipboard
                    url = get_clipboard_url()
                    if url:
                        add_url(url)
                    draw_tui()
                elif ch.lower() == 'a':
                    # Temporarily restore standard terminal mode for text entry
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    print("\n")
                    url_input = input("Cole o URL do YouTube: ").strip()
                    if url_input:
                        print("A ligar ao YouTube e a carregar áudio...")
                        add_url(url_input)
                    tty.setraw(fd)
                    last_refresh = 0
                elif ch.lower() == 's':
                    stop_command()
                    break
                elif ch.lower() == 'q':
                    # Exit GUI but keep stream playing in background
                    break
                elif ord(ch) == 3: # Ctrl+C
                    break
                    
    except Exception as e:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        print(f"\nErro fatal na execução da TUI: {e}")
        time.sleep(2)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        # Clear terminal screen and exit cleanly
        sys.stdout.write("\033[H\033[2J")
        sys.stdout.flush()
        print("TUI fechada. O áudio do YouTube continua a tocar no fundo!")
        print("Pode controlar a reprodução pelo SwiftBar ou reabrir o TUI quando quiser.")

# 10. SwiftBar Menu Standard Output Generation
def run_swiftbar():
    mpv_ok, ytdl_ok = check_dependencies()
    
    # Use sys.argv[0] so that SwiftBar executes the symlink path (which doesn't contain spaces)
    script_path = os.path.abspath(sys.argv[0])
    if " " in script_path:
        symlink_path = "/Users/andresousa/swiftbar-plugins/youtube_audio.5s.py"
        if os.path.exists(symlink_path):
            script_path = symlink_path
            
    if not mpv_ok or not ytdl_ok:
        print("⚠️ YouTube Player (Faltam Dependências) | color=#FF3333")
        print("---")
        print("Instalar mpv e yt-dlp via Homebrew | bash=%s param1=install-deps terminal=true refresh=true" % script_path)
        return
        
    status = get_player_status()
    
    # Query current playlist queue once for performance and conditional logic
    playlist_res = send_mpv_command(["get_property", "playlist"])
    playlist = playlist_res.get("data", []) if playlist_res.get("error") == "success" else []
    playlist_len = len(playlist)
    
    # Top Menu bar text display
    if status["status"] == "stopped" or status["title"] == IDLE_TITLE:
        print("🎧 Youtube: Sem Música | color=#888888")
    else:
        if status["muted"]:
            print("🔇 Youtube Muted | color=#FF3366")
        elif status["status"] == "playing":
            print("🔴 Youtube Playing... | color=#FF3366")
        else:
            print("⏸️ Youtube Paused | color=#FFCC00")
        
    print("---")
    
    # Dropdown Options - MOVED MUTE TO THE VERY TOP FOR INSTANT DOUBLE-TAP CLICKS!
    if status["status"] != "stopped" and status["title"] != IDLE_TITLE:
        mute_label = "🔊 Desativar Mudo" if status["muted"] else "🔇 Ativar Mudo"
        print(f"{mute_label} | bash={script_path} param1=mute terminal=false refresh=true shortcut=ctrl+option+m size=14 color=#FF3366")
        
        print("---")
        print(f"🎵 {status['title']} | color=#00E5FF size=12")
        
        # Display elapsed time progress bar
        time_pos = status["time_pos"]
        duration = status["duration"]
        if duration and duration > 0:
            percent = (time_pos / duration) * 100.0
            time_str = format_time(time_pos)
            duration_str = format_time(duration)
            print(f"⏱️ {time_str} / {duration_str} ({percent:.1f}%) | color=#AAAAAA")
            
        print("---")
        
        # Action controls grouped beautifully together
        play_pause_label = "⏸️ Pausar Áudio" if status["status"] == "playing" else "▶️ Retomar Áudio"
        print(f"{play_pause_label} | bash={script_path} param1=toggle terminal=false refresh=true shortcut=ctrl+option+space")
        
        # Only display skip controls if there is actually a playlist of multiple files
        if playlist_len > 1:
            print(f"⏭️ Próximo Vídeo (Fila) | bash={script_path} param1=next terminal=false refresh=true")
            print(f"⏮️ Vídeo Anterior | bash={script_path} param1=prev terminal=false refresh=true")
            
        print(f"⏹️ Parar Player (Sair) | bash={script_path} param1=stop terminal=false refresh=true")
    else:
        print("▶️ Iniciar Player (Idle) | bash={script_path} param1=play terminal=false refresh=true")
        
    print("---")

    # Display Playback History in a beautiful submenu
    history = load_history()
    print("📜 Histórico de Reprodução | color=#FFCC00")
    if history:
        playlists = []
        songs = []
        for item in history:
            h_url = item.get("url")
            if "list=" in h_url or "playlist" in h_url:
                playlists.append(item)
            else:
                songs.append(item)
                
        # 1. Playlists
        if playlists:
            print("-- 📁 Playlists Recentes: | color=#888888")
            for item in playlists[:10]: # Show top 10 recent playlists
                h_url = item.get("url")
                h_title = item.get("title", h_url)
                if len(h_title) > 40:
                    h_title = h_title[:37] + "..."
                print(f"--   • {h_title} | bash={script_path} param1=play param2={h_url} terminal=false refresh=true")
                print(f"--   • ❌ Remover: {h_title} | bash={script_path} param1=remove-history-item param2={h_url} terminal=false refresh=true alternate=true")
                
        # Separator if both exist
        if playlists and songs:
            print("-- ---")
            
        # 2. Songs
        if songs:
            print("-- 🎵 Músicas Recentes: | color=#888888")
            for item in songs[:15]: # Show top 15 recent songs
                h_url = item.get("url")
                h_title = item.get("title", h_url)
                if len(h_title) > 40:
                    h_title = h_title[:37] + "..."
                print(f"--   • {h_title} | bash={script_path} param1=play param2={h_url} terminal=false refresh=true")
                print(f"--   • ❌ Remover: {h_title} | bash={script_path} param1=remove-history-item param2={h_url} terminal=false refresh=true alternate=true")
            
        print("-- ---")
        print(f"-- 🧹 Limpar Histórico | bash={script_path} param1=clear-history terminal=false refresh=true")
    else:
        print("-- 🚫 Nenhum item recente | color=#888888")

    print("---")
    
    # Adding options
    print(f"📋 Adicionar URL do Clipboard | bash={script_path} param1=add-clipboard terminal=false refresh=true")
    print(f"✍️ Adicionar URL Manualmente... | bash={script_path} param1=add-gui terminal=false refresh=true")
    print(f"🧹 Limpar Toda a Fila | bash={script_path} param1=clear terminal=false refresh=true")
    
    # Display the current playlist active queue inside SwiftBar dropdown
    if playlist_len > 0:
        print("---")
        print("Fila de Reprodução (Queue): | color=#888888")
        for i, item in enumerate(playlist):
            filename = item.get("filename")
            t = item.get("title")
            
            cached_t = get_cached_title(filename, t)
            if cached_t:
                t = cached_t
            elif not t or t.startswith("http"):
                t = filename or "Sem título"
                
            if t.startswith("http"):
                t = "⏳ A carregar stream..."
                
            if len(t) > 35:
                t = t[:32] + "..."
            bullet = "👉" if item.get("current") else "•"
            # Selecting a track from the dropdown will instantly skip to it!
            print(f"{bullet} {t} | bash={script_path} param1=select-track param2={i} terminal=false refresh=true")
                
    print("---")
    # Quick launcher to spawn the interactive CLI terminal interface
    print(f"🛠️ Abrir Dashboard TUI Interativo | bash=open param1=-a param2=Terminal.app param3={script_path} terminal=false")

# 11. Command Router / Main Entry
def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "play":
            url = sys.argv[2] if len(sys.argv) > 2 else None
            play_command(url)
        elif cmd == "pause":
            pause_command()
        elif cmd == "toggle":
            toggle_command()
        elif cmd == "mute":
            mute_command()
        elif cmd == "stop":
            stop_command()
        elif cmd == "next":
            next_command()
        elif cmd == "prev":
            prev_command()
        elif cmd == "clear":
            clear_command()
        elif cmd == "clear-history":
            clear_history_command()
        elif cmd == "remove-history-item":
            if len(sys.argv) > 2:
                remove_history_item(sys.argv[2])
        elif cmd == "add":
            if len(sys.argv) > 2:
                add_url(sys.argv[2])
        elif cmd == "add-clipboard":
            add_via_clipboard()
        elif cmd == "add-gui":
            add_via_applescript()
        elif cmd == "select-track":
            if len(sys.argv) > 2:
                select_track(sys.argv[2])
        elif cmd == "install-deps":
            install_dependencies()
        elif cmd == "swiftbar":
            run_swiftbar()
        else:
            print(f"Comando '{cmd}' desconhecido.")
            print("Comandos suportados: play, pause, toggle, mute, stop, next, prev, clear, clear-history, remove-history-item, add, add-clipboard, add-gui, select-track, install-deps, swiftbar")
    else:
        # Standard fallback: detect TTY for TUI, else output SwiftBar
        if sys.stdin.isatty():
            run_tui()
        else:
            run_swiftbar()

if __name__ == "__main__":
    main()
