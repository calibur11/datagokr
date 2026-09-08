# =========================================================================
# 🛠️ 지방행정 인허가정보 API 프록시 서버 및 웹 대시보드 (v18 최종 무결성 자동 복원 판)
# =========================================================================
# 이 프로그램은 공공데이터포털(data.go.kr)의 지방행정 인허가정보 Open API(195개 업종)를
# 로컬 환경에서 부하 및 인코딩 한계를 우회하여 대용량으로 수집하고, 브라우저 화면 상에
# 한글이 깨지지 않는 CSV 및 JSON 포맷으로 저장할 수 있도록 돕는 풀스택 프록시 시스템입니다.

import os            # 파일 경로 탐색 및 환경변수 감지용 표준 라이브러리
import sys           # 시스템 관련 설정 및 파이썬 정보 제어용 라이브러리
import json          # API 응답 결과 데이터(JSON) 처리 및 구조화용 라이브러리
import urllib.parse  # 공공 API 특화 특수문자 인증키 자동 디코딩 및 파라미터 파싱용 라이브러리
import re            # 응답 데이터 내 개수(totalCount) 정규식 추출용 라이브러리
import datetime      # 오늘 날짜 계산 및 타임스탬프 처리용 표준 라이브러리
import pandas as pd  # 로컬 업종 CSV 데이터프레임 처리용 라이브러리
import requests      # 공공데이터포털 원격 서버로 HTTP API 호출을 날리는 핵심 라이브러리
from flask import Flask, jsonify, request, render_template_string  # Flask 가벼운 백엔드 서버 웹 프레임워크

# -------------------------------------------------------------------------
# 1. Flask 애플리케이션 생성 및 전역 설정
# -------------------------------------------------------------------------
app = Flask(__name__)

# 서버 사이드 전역 메모리 저장소 설정 (사용자의 API 인증키를 저장)
# 브라우저(클라이언트) 단에 인증키를 전혀 노출하지 않아 키 탈취 및 보안 유출을 원천 방어합니다.
# 서버 사이드 전역 메모리 저장소 설정 (사용자의 API 인증키를 저장)
CONFIG = {
    "service_key": "",
    "key_source": None
}

# 로컬 설정 파일 및 환경변수에서 키를 읽어오는 통합 복원 함수
def load_cached_api_key():
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        key_file_path = os.path.join(script_dir, "public_data_api_key.txt")
        if os.path.exists(key_file_path):
            with open(key_file_path, "r", encoding="utf-8") as f:
                key = f.read().strip()
                if key:
                    print(f"[Success] 로컬 텍스트 파일(public_data_api_key.txt)에서 인증키를 성공적으로 복원했습니다.")
                    return key, "로컬 파일 (public_data_api_key.txt)"
    except Exception as e:
        print(f"[Warning] 로컬 텍스트 파일 읽기 실패: {e}")
    
    # 윈도우 시스템 환경변수에서 읽기 시도
    env_key = os.environ.get("PUBLIC_DATA_API_KEY", "").strip()
    if env_key:
        print(f"[Success] 시스템 환경 변수(PUBLIC_DATA_API_KEY)에서 인증키를 로드했습니다.")
        # 환경변수에서 읽어온 키를 파일로 자동 캐싱해 두어, 다음번에는 환경변수가 없는 실행창(더블클릭 등)에서도 작동하도록 백업
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            key_file_path = os.path.join(script_dir, "public_data_api_key.txt")
            with open(key_file_path, "w", encoding="utf-8") as f:
                f.write(env_key)
            print(f"[Success] 환경변수에서 가져온 인증키를 로컬 파일에 백업(캐싱) 완료했습니다.")
        except Exception:
            pass
        return env_key, "시스템 환경 변수"
        
    return "", None

# 프로그램 가동 시 자동 인증키 스캔 및 초기 로드 실행
loaded_key, loaded_source = load_cached_api_key()
CONFIG["service_key"] = loaded_key
CONFIG["key_source"] = loaded_source

# -------------------------------------------------------------------------
# 2. 로컬 CSV 파일 자동 탐색 함수 (플랫폼 호환성 및 오프라인 대응 핵심)
# -------------------------------------------------------------------------
# 사용자의 PC OS 환경(Windows/Linux)이나 파일명 변형(공백 <-> 언더바)에 상관없이
# 스크립트와 동일한 폴더 혹은 하위 폴더에서 지방행정 인허가정보 CSV 데이터베이스 목록을 찾아냅니다.
def find_csv_files_robustly():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dirs_to_check = [script_dir, ".", "/workspace/knowledge", ".."]
    info_path = None
    history_path = None
    
    # 1. Exact match lists for both space-separated (typical local downloads) and underscore-replaced (platform specific) files
    exact_info_names = [
        "붙임2. 공공데이터포털 지방행정 인허가정보 API 호출 URL 목록_20260727수정_조회.csv",
        "붙임2._공공데이터포털_지방행정_인허가정보_API_호출_URL_목록_20260727수정_조회.csv",
        "붙임2_공공데이터포털_지방행정_인허가정보_API_호출_URL_목록_20260727수정_조회.csv"
    ]
    exact_history_names = [
        "붙임2. 공공데이터포털 지방행정 인허가정보 API 호출 URL 목록_20260727수정_조회_이력조회.csv",
        "붙임2._공공데이터포털_지방행정_인허가정보_API_호출_URL_목록_20260727수정_조회_이력조회.csv",
        "붙임2_공공데이터포털_지방행정_인허가정보_API_호출_URL_목록_20260727수정_조회_이력조회.csv"
    ]
    
    # Try exact matches first
    for d in dirs_to_check:
        if not os.path.exists(d):
            continue
        for name in exact_info_names:
            p = os.path.join(d, name)
            if os.path.exists(p):
                info_path = p
                break
        if info_path:
            break
            
    for d in dirs_to_check:
        if not os.path.exists(d):
            continue
        for name in exact_history_names:
            p = os.path.join(d, name)
            if os.path.exists(p):
                history_path = p
                break
        if history_path:
            break
            
    # 2. Dynamic Scan Fallback: If any file wasn't found, scan folders for files with relevant keywords
    if not info_path or not history_path:
        for d in dirs_to_check:
            if not os.path.exists(d):
                continue
            try:
                for f in os.listdir(d):
                    full_p = os.path.join(d, f)
                    if not os.path.isfile(full_p) or not f.lower().endswith(".csv"):
                        continue
                    
                    # File containing both '이력' and '지방행정' is history
                    if "이력" in f and "지방행정" in f:
                        if not history_path:
                            history_path = full_p
                    # File containing both '지방행정' and '조회' but NOT '이력' is info
                    elif "조회" in f and "지방행정" in f and "이력" not in f:
                        if not info_path:
                            info_path = full_p
            except Exception:
                pass
                
    return info_path, history_path

info_file_path, history_file_path = find_csv_files_robustly()

# Global sectors cache
SECTORS_DATA = []


# -------------------------------------------------------------------------
# 3. 공공 API 응답용 데이터 개수(totalCount) 정밀 파싱 함수 (예외 안전 필터)
# -------------------------------------------------------------------------
# 원격 공공포털 서버에서 받은 원본 데이터가 JSON 형식이든, 오류로 인한 XML 형식이든 상관없이
# 정규식 패턴 탐색을 이용하여 "전체 행 수(totalCount)" 정보만 콕 집어 정밀 파싱해냅니다.
def extract_total_count(resp_text):
    # Match standard totalCount in JSON or XML (using hex for quotes to avoid string break)
    match = re.search(r'[\x22\x27<]totalCount[\x22\x27\s>:]*(\d+)', resp_text, re.IGNORECASE)
    if match:
        return int(match.group(1))
    # Fallbacks (total_count, list_total_count, total)
    match2 = re.search(r'[\x22\x27<](total_count|list_total_count|total)[\x22\x27\s>:]*(\d+)', resp_text, re.IGNORECASE)
    if match2:
        return int(match2.group(2))
    return None

# -------------------------------------------------------------------------
# 4. 공공 API JSON 응답 본문에서 실제 데이터 목록(배열) 추출 함수
# -------------------------------------------------------------------------
# 공공데이터포털의 중첩된 response -> body -> items -> item 트리 구조에서 실제 정보 배열을 추출합니다.
# 만약 데이터가 단 1건만 있어 배열이 아닌 단일 객체(Dict)로 리턴될 경우에도 1칸짜리 배열로 동적 보정해 주며,
# 예외적인 응답 형식을 대비해 데이터가 들어있는 첫 번째 사전의 리스트를 찾아내는 백업 스캐너가 함께 가동됩니다.
def extract_items_list(json_data):
    if not isinstance(json_data, dict):
        return None
    try:
        res = json_data.get("response", {})
        body = res.get("body", {})
        items_container = body.get("items", {})
        if isinstance(items_container, dict):
            item = items_container.get("item")
            if isinstance(item, list):
                return item
            elif isinstance(item, dict):
                return [item]
        return find_first_array_of_dicts(json_data)
    except Exception:
        return None

def find_first_array_of_dicts(obj):
    if isinstance(obj, list):
        if len(obj) > 0 and isinstance(obj[0], dict):
            return obj
        return None
    if isinstance(obj, dict):
        for k, v in obj.items():
            res = find_first_array_of_dicts(v)
            if res is not None:
                return res
    return None

def inject_items_list(json_data, items_list):
    try:
        res = json_data.setdefault("response", {})
        body = res.setdefault("body", {})
        items_container = body.setdefault("items", {})
        items_container["item"] = items_list
        return True
    except Exception:
        return inject_first_array_of_dicts(json_data, items_list)

def inject_first_array_of_dicts(obj, items_list):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, list) and len(v) > 0 and isinstance(v[0], dict):
                obj[k] = items_list
                return True
            if isinstance(v, dict):
                if inject_first_array_of_dicts(v, items_list):
                    return True
    return False

# -------------------------------------------------------------------------
# 5. 195개 지방행정 업종 메타 데이터 로딩 및 분야 분리 함수
# -------------------------------------------------------------------------
# 프로그램이 켜지는 시점에 딱 1번 실행되며, 탐색된 CSV 파일을 읽어
# "행정안전부_건강_병원 조회서비스" 와 같은 원본명을 ["건강"(대분류 분야), "병원"(상세 업종)]으로
# 완벽히 정제하여 메모리에 올려 브라우저가 화면을 그릴 수 있도록 드롭박스 원본 사전을 만듭니다.
def load_sectors_data():
    global SECTORS_DATA
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    print(f"\n[Debug] Script location: {script_dir}")
    print(f"[Debug] Current Working Directory: {os.getcwd()}")
    print(f"[Debug] Info file path determined as: {info_file_path}")
    print(f"[Debug] History file path determined as: {history_file_path}")
    
    if not info_file_path or not os.path.exists(info_file_path):
        print(f"[Error] Info CSV file not found! Placed CSVs should be in the same folder as this script.")
        return
    if not history_file_path or not os.path.exists(history_file_path):
        print(f"[Error] History CSV file not found! Placed CSVs should be in the same folder as this script.")
        return

    def read_csv_with_fallback(filepath):
        encodings = ['utf-8-sig', 'cp949', 'utf-8', 'euc-kr']
        for enc in encodings:
            try:
                df = pd.read_csv(filepath, encoding=enc)
                print(f"[Debug] Successfully loaded {os.path.basename(filepath)} using encoding: {enc}")
                return df
            except UnicodeDecodeError:
                continue
            except Exception as e:
                print(f"[Warning] Failed to read {os.path.basename(filepath)} with {enc}: {e}")
        raise ValueError(f"Could not decode {filepath} with any of {encodings}")

    try:
        df_info = read_csv_with_fallback(info_file_path)
        df_history = read_csv_with_fallback(history_file_path)
        
        mapping = []
        for idx, row in df_info.iterrows():
            raw_name = row['목록명(서비스명)']
            parts = raw_name.split('_')
            
            category = "기타"
            sector = raw_name
            if len(parts) >= 3:
                category = parts[1]
                sector = parts[2].replace(" 조회서비스", "").replace("조회서비스", "").replace(" 등록서비스", "").replace("등록서비스", "")
            
            info_url = row['API 호출 URL'].strip()
            
            # Find history URL
            hist_row = df_history[df_history['순번'] == row['순번']]
            if not hist_row.empty:
                history_url = hist_row.iloc[0]['API 호출 URL'].strip()
            else:
                history_url = info_url.replace('/info', '/history')
                
            mapping.append({
                'id': int(row['순번']),
                'raw_name': raw_name,
                'category': category,
                'sector': sector,
                'info_url': info_url,
                'history_url': history_url
            })
        SECTORS_DATA = mapping
        print(f"[Success] Loaded {len(SECTORS_DATA)} sectors successfully.")
    except Exception as e:
        print(f"[Error] Critical error loading sectors CSV: {e}")
load_sectors_data()

# -----------------
# HTML Frontend Template
# -----------------
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ko">
<head>
    <!-- 0. BULLETPROOF ON-SCREEN DEBUGGER (Injected in v9) -->
    <script>
        (function() {
            const queue = [];
            function pushQueue(type, args) {
                queue.push({ type, args, time: new Date().toLocaleTimeString() });
            }

            const originalLog = console.log;
            const originalError = console.error;
            const originalWarn = console.warn;

            console.log = function() { originalLog.apply(console, arguments); pushQueue('log', arguments); };
            console.error = function() { originalError.apply(console, arguments); pushQueue('error', arguments); };
            console.warn = function() { originalWarn.apply(console, arguments); pushQueue('warn', arguments); };

            window.addEventListener('error', function(e) {
                pushQueue('error', [`Global Error: ${e.message} at ${e.filename}:${e.lineno}:${e.colno}`]);
            });
            window.addEventListener('unhandledrejection', function(e) {
                pushQueue('error', [`Unhandled Promise Rejection: ${e.reason}`]);
            });

            window.addEventListener('DOMContentLoaded', () => {
                const panel = document.createElement('div');
                panel.id = 'debug-log-panel';
                panel.style.cssText = "position: fixed; bottom: 0; left: 0; right: 0; height: 180px; background: #0f172a; color: #38bdf8; font-family: monospace; font-size: 11px; padding: 10px; overflow-y: auto; border-top: 3px solid #f87171; z-index: 99999; box-shadow: 0 -4px 15px rgba(0,0,0,0.6);";
                panel.innerHTML = `
                    <div style="display: flex; justify-content: space-between; border-b: 1px solid #334155; padding-bottom: 5px; margin-bottom: 5px; font-weight: bold; color: #94a3b8;">
                        <span style="color: #f87171;">🕵️ 실시간 브라우저 콘솔 디버그 모니터 (v14)</span>
                        <span style="font-size: 10px; color: #64748b;">(화면에 붉은색 오류가 뜨면 전체 복사하여 알려주세요)</span>
                        <button onclick="document.getElementById('debug-log-panel').style.display='none'" style="background:#ef4444; color:white; border:none; padding:2px 8px; border-radius:4px; cursor:pointer; font-weight:bold;">디버거 닫기</button>
                    </div>
                    <div id="debug-log-content" style="max-height: 140px; overflow-y: auto;"></div>
                `;
                document.body.appendChild(panel);

                const content = document.getElementById('debug-log-content');
                
                function renderLine(item) {
                    const line = document.createElement('div');
                    line.style.marginBottom = '4px';
                    line.style.whiteSpace = 'pre-wrap';
                    line.style.wordBreak = 'break-all';
                    if (item.type === 'error') line.style.color = '#f87171';
                    else if (item.type === 'warn') line.style.color = '#fbbf24';
                    else line.style.color = '#38bdf8';
                    
                    line.innerText = `[${item.time}] [${item.type.toUpperCase()}] ` + Array.from(item.args).map(arg => {
                        if (arg instanceof Error) return arg.stack || arg.message;
                        if (typeof arg === 'object') {
                            try { return JSON.stringify(arg); } catch(e) { return String(arg); }
                        }
                        return String(arg);
                    }).join(' ');
                    content.appendChild(line);
                }

                queue.forEach(renderLine);

                console.log = function() {
                    originalLog.apply(console, arguments);
                    renderLine({ type: 'log', args: arguments, time: new Date().toLocaleTimeString() });
                    content.scrollTop = content.scrollHeight;
                };
                console.error = function() {
                    originalError.apply(console, arguments);
                    renderLine({ type: 'error', args: arguments, time: new Date().toLocaleTimeString() });
                    content.scrollTop = content.scrollHeight;
                };
                console.warn = function() {
                    originalWarn.apply(console, arguments);
                    renderLine({ type: 'warn', args: arguments, time: new Date().toLocaleTimeString() });
                    content.scrollTop = content.scrollHeight;
                };
                
                content.scrollTop = content.scrollHeight;
                console.log("디버그 모니터 활성화 완료. 포트: " + window.location.port);
            });
        })();
    </script>

    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>지방행정 인허가정보 API 다운로더</title>
    
    <!-- 1. INSTANT JS FETCH: Execute immediately before any external CDN script blocks the thread -->
    <script>
        console.log("[Debug JS] Firing instant parallel fetches immediately as HTML is being parsed...");
        window.sectorsPromise = fetch('/api/sectors?_t=' + Date.now())
            .then(res => {
                console.log("[Debug JS] /api/sectors raw response received:", res.status);
                return res.json();
            })
            .catch(err => {
                console.error("[Debug JS] Sectors fetch failed:", err);
                return [];
            });
            
        window.keyStatusPromise = fetch('/api/key_status?_t=' + Date.now())
            .then(res => res.json())
            .catch(err => {
                console.error("[Debug JS] Key status fetch failed:", err);
                return { has_key: false };
            });
    </script>

    <!-- 2. NON-BLOCKING CDNs (defer and onload media swap ensures zero parse blocking) -->
    <!-- Tailwind with defer -->
    <script src="https://cdn.tailwindcss.com" defer></script>
    <!-- FontAwesome stylesheet with print-media onload fallback to prevent blocking CSS render -->
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" media="print" onload="this.media='all'">
    
    <!-- 3. OFFLINE STYLE FALLBACK: Ensure dashboard layout remains completely usable if offline/CDNs fail -->
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Pretendard:wght@400;600;700&display=swap');
        body {
            font-family: 'Pretendard', system-ui, -apple-system, sans-serif;
        }
        .custom-scrollbar::-webkit-scrollbar {
            width: 10px;
            height: 10px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
            background: #f1f1f1;
            border-radius: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
            background: #cbd5e1;
            border-radius: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb:hover {
            background: #94a3b8;
        }
    </style>
</head>
<body class="bg-slate-50 min-h-screen text-slate-800">

    <div class="max-w-7xl mx-auto px-4 py-8">
        <!-- Header -->
        <header class="flex items-center justify-between mb-8 pb-4 border-b border-slate-200">
            <div class="flex items-center space-x-3">
                <div class="bg-blue-600 text-white p-3 rounded-xl shadow-md shadow-blue-200">
                    <i class="fa-solid fa-server text-xl"></i>
                </div>
                <div>
                    <h1 class="text-2xl font-bold text-slate-900">지방행정 인허가정보 API 다운로더</h1>
                    <p class="text-sm text-slate-500">공공데이터포털 195개 업종별 실시간 조회 및 이력조회 로컬 프록시 서버</p>
                </div>
            </div>
            <div class="flex items-center space-x-2 text-xs bg-emerald-50 text-emerald-700 px-3 py-1.5 rounded-full font-semibold border border-emerald-200">
                <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                로컬 프록시 작동 중 (Port: <span id="current-port">{{ port }}</span>)
            </div>
        </header>

        <!-- API Key Status Banner -->
        <div id="key-banner" class="mb-6 p-4 rounded-xl border flex items-center justify-between transition-all duration-300">
            <div class="flex items-center space-x-3">
                <span id="key-icon-container" class="text-xl"></span>
                <div>
                    <h4 id="key-status-title" class="font-bold text-sm"></h4>
                    <p id="key-status-desc" class="text-xs text-slate-500"></p>
                </div>
            </div>
            <div class="flex items-center space-x-2">
                <input type="password" id="key-input" placeholder="인증키(Service Key) 입력" class="text-xs px-3 py-2 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 w-64 shadow-sm">
                <button onclick="setApiKey()" class="bg-slate-950 text-white text-xs font-semibold px-4 py-2 rounded-lg hover:bg-slate-850 transition">
                    키 저장
                </button>
            </div>
        </div>

        <div class="grid grid-cols-1 lg:grid-cols-12 gap-8">
            <!-- Left Panel: Control Box -->
            <div class="lg:col-span-4 space-y-6">
                <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-150">
                    <h3 class="text-lg font-bold text-slate-900 mb-5 flex items-center space-x-2">
                        <i class="fa-solid fa-sliders text-blue-600"></i>
                        <span>API 호출 옵션 설정</span>
                    </h3>
                    
                    <div class="space-y-4">
                        <!-- Dropdown 1: 분야 -->
                        <div>
                            <label class="block text-xs font-bold text-slate-500 mb-2 uppercase tracking-wider">1. 대분류 분야</label>
                            <select id="category-select" onchange="onCategoryChange()" class="w-full px-3 py-2.5 bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 shadow-sm transition">
                                <option value="">분야 선택</option>
                            </select>
                        </div>

                        <!-- Dropdown 2: 업종 -->
                        <div>
                            <label class="block text-xs font-bold text-slate-500 mb-2 uppercase tracking-wider">2. 상세 업종</label>
                            <select id="sector-select" onchange="onSectorChange()" class="w-full px-3 py-2.5 bg-white border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 shadow-sm transition disabled:bg-slate-100 disabled:text-slate-400" disabled>
                                <option value="">업종 선택</option>
                            </select>
                        </div>

                        <!-- Dropdown 3: 조회유형 (이력조회 비활성화에 따른 숨김 처리) -->
                        <div class="hidden">
                            <label class="block text-xs font-bold text-slate-500 mb-2 uppercase tracking-wider">3. 데이터 조회 구분</label>
                            <div class="grid grid-cols-2 gap-2">
                                <button id="type-info" onclick="setType('info')" class="py-2.5 border border-blue-500 bg-blue-50 text-blue-700 font-bold rounded-xl text-sm transition flex items-center justify-center space-x-2 shadow-sm">
                                    <i class="fa-solid fa-list-check"></i>
                                    <span>현재 조회 (Info)</span>
                                </button>
                                <button id="type-history" onclick="setType('history')" class="py-2.5 border border-slate-200 text-slate-600 hover:bg-slate-50 rounded-xl text-sm transition flex items-center justify-center space-x-2 shadow-sm">
                                    <i class="fa-solid fa-clock-rotate-left"></i>
                                    <span>이력 조회 (History)</span>
                                </button>
                            </div>
                        </div>

                        <!-- History Date Range Container (Hidden by default, shown when 'history' is selected) -->
                        <div id="history-date-container" class="hidden space-y-3 p-3 bg-slate-50 rounded-xl border border-slate-150 transition-all duration-300">
                            <label class="block text-xs font-bold text-slate-500 uppercase tracking-wider">📅 이력 조회 기간 설정</label>
                            <div class="grid grid-cols-2 gap-2">
                                <div>
                                    <label class="block text-xxs font-semibold text-slate-400 mb-1">시작일자</label>
                                    <input type="date" id="param-bgn-date" onchange="updateTotalCountDisplay()" class="w-full px-2 py-1.5 border border-slate-200 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 focus:outline-none">
                                </div>
                                <div>
                                    <label class="block text-xxs font-semibold text-slate-400 mb-1">종료일자</label>
                                    <input type="date" id="param-end-date" onchange="updateTotalCountDisplay()" class="w-full px-2 py-1.5 border border-slate-200 rounded-lg text-xs focus:ring-2 focus:ring-blue-500 focus:outline-none">
                                </div>
                            </div>
                            <p class="text-xxs text-slate-400">※ 이력조회는 검색 기간(최대 31일 권장)이 필수입니다.</p>
                        </div>

                        <hr class="border-slate-100 my-4">

                        <!-- API Params -->
                        <div class="space-y-3">
                            <label class="block text-xs font-bold text-slate-500 uppercase tracking-wider">3. 요청 파라미터 설정</label>
                            
                            <div>
                                <div class="flex items-center justify-between mb-1.5">
                                    <label class="block text-xxs font-bold text-slate-500 uppercase tracking-wider">가져올 데이터 개수 (처음부터)</label>
                                    <!-- Pre-informed total count indicator -->
                                    <div class="flex items-center space-x-1 bg-slate-50 px-2 py-0.5 rounded-md border border-slate-150">
                                        <span class="text-slate-400 text-xxs font-semibold">총 데이터 수:</span>
                                        <span id="total-count-display" class="text-xxs font-bold text-slate-400">업종을 선택해 주세요.</span>
                                    </div>
                                </div>
                                
                                <div class="flex space-x-2">
                                    <input type="number" id="param-limit" value="10" min="1" class="flex-1 px-3 py-2 border border-slate-200 rounded-xl text-sm focus:ring-2 focus:ring-blue-500 focus:outline-none shadow-sm">
                                    <button id="set-max-btn" onclick="setLimitToMax()" class="bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-bold px-3 py-2 rounded-xl border border-slate-250 transition disabled:opacity-50 disabled:pointer-events-none shadow-sm" disabled>
                                        전체 개수로 설정
                                    </button>
                                </div>
                            </div>

                            <div>
                                <label class="block text-xxs font-bold text-slate-400 mb-1">응답 형식 (resultType)</label>
                                <div class="flex items-center space-x-4 mt-1 bg-slate-50 p-2.5 rounded-xl border border-slate-150">
                                    <label class="flex items-center space-x-2 text-sm text-slate-700 font-medium cursor-pointer">
                                        <input type="radio" name="param-format" value="json" checked class="text-blue-600 focus:ring-blue-500">
                                        <span>JSON (권장)</span>
                                    </label>
                                    <label class="flex items-center space-x-2 text-sm text-slate-700 font-medium cursor-pointer">
                                        <input type="radio" name="param-format" value="xml" class="text-blue-600 focus:ring-blue-500">
                                        <span>XML</span>
                                    </label>
                                </div>
                            </div>
                        </div>

                        <!-- Target URL display (readonly) -->
                        <div class="mt-4 p-3 bg-slate-50 rounded-xl border border-slate-150 text-xs">
                            <div class="font-bold text-slate-400 mb-1 uppercase tracking-wider text-xxs">대상 공공 API URL (서버측 호출)</div>
                            <div id="target-url-display" class="font-mono text-slate-600 break-all select-all">분야와 업종을 선택해 주세요.</div>
                        </div>

                        <!-- Fetch Buttons -->
                        <div class="grid grid-cols-1 gap-2 mt-4">
                            <!-- Regular fetch button -->
                            <button id="fetch-btn" onclick="fetchData()" class="w-full bg-blue-600 text-white font-bold py-3 rounded-xl hover:bg-blue-700 active:scale-98 transition shadow-lg shadow-blue-200 flex items-center justify-center space-x-2 disabled:bg-slate-300 disabled:shadow-none disabled:pointer-events-none">
                                <i class="fa-solid fa-cloud-arrow-down"></i>
                                <span>지정한 개수만큼 가져오기</span>
                            </button>
                            <!-- Fetch all button -->
                            <button id="fetch-all-btn" onclick="fetchDataAll()" class="w-full bg-emerald-600 text-white font-bold py-2.5 rounded-xl hover:bg-emerald-700 active:scale-98 transition shadow-lg shadow-emerald-100 flex items-center justify-center space-x-2 disabled:bg-slate-200 disabled:text-slate-400 disabled:shadow-none disabled:pointer-events-none" disabled>
                                <i class="fa-solid fa-database"></i>
                                <span>전체 데이터 한번에 가져오기</span>
                            </button>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Right Panel: Data Display & Preview -->
            <div class="lg:col-span-8 space-y-6">
                <!-- Response Header and Toolbar -->
                <div class="bg-white rounded-2xl shadow-sm border border-slate-150 overflow-hidden flex flex-col min-h-[600px]">
                    <div class="bg-slate-50 px-6 py-4 border-b border-slate-150 flex items-center justify-between">
                        <div class="flex items-center space-x-2">
                            <span class="w-3 h-3 rounded-full bg-blue-500"></span>
                            <h3 class="text-md font-bold text-slate-800">응답 결과 데이터 뷰어</h3>
                        </div>
                        <div class="flex items-center space-x-2">
                            <button id="download-json-btn" onclick="downloadDataFile('json')" class="hidden bg-slate-100 border border-slate-200 text-slate-700 text-xs font-semibold px-3 py-1.5 rounded-lg hover:bg-slate-200 transition flex items-center space-x-1.5">
                                <i class="fa-solid fa-file-arrow-down"></i>
                                <span>JSON/XML 다운로드</span>
                            </button>
                            <button id="download-csv-btn" onclick="downloadDataFile('csv')" class="hidden bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-semibold px-3 py-1.5 rounded-lg hover:bg-emerald-100 transition flex items-center space-x-1.5">
                                <i class="fa-solid fa-file-excel"></i>
                                <span>CSV 다운로드</span>
                            </button>
                            <button onclick="clearConsole()" class="bg-slate-100 border border-slate-200 text-slate-700 text-xs font-semibold px-3 py-1.5 rounded-lg hover:bg-slate-200 transition flex items-center space-x-1.5">
                                <i class="fa-solid fa-trash-can"></i>
                                <span>결과 지우기</span>
                            </button>
                        </div>
                    </div>

                    <!-- Inner tab headers for Raw VS Preview Table -->
                    <div class="border-b border-slate-150 flex bg-white text-sm">
                        <button id="tab-table" onclick="switchTab('table')" class="px-5 py-3 border-b-2 border-blue-600 text-blue-600 font-bold flex items-center space-x-2 transition">
                            <i class="fa-solid fa-table"></i>
                            <span>데이터 표로 미리보기</span>
                        </button>
                        <button id="tab-raw" onclick="switchTab('raw')" class="px-5 py-3 border-b-2 border-transparent text-slate-500 font-semibold flex items-center space-x-2 hover:text-slate-800 transition">
                            <i class="fa-solid fa-code"></i>
                            <span>Raw 응답 데이터</span>
                        </button>
                    </div>

                    <!-- Content Panel -->
                    <div class="flex-1 p-6 relative bg-white overflow-hidden flex flex-col">
                        <!-- Loading Overlay -->
                        <div id="loading" class="hidden absolute inset-0 bg-white bg-opacity-80 flex flex-col items-center justify-center z-10">
                            <div class="w-12 h-12 border-4 border-blue-200 border-t-blue-600 rounded-full animate-spin mb-4"></div>
                            <p class="text-sm font-semibold text-slate-600 animate-pulse">로컬 서버를 통해 공공데이터 API를 호출하고 있습니다...</p>
                            <p class="text-xs text-slate-400 mt-1">서버에서 공공데이터포털 인증키 보안 주입 중</p>
                        </div>

                        <!-- Empty State -->
                        <div id="empty-state" class="flex flex-col items-center justify-center py-20 text-slate-400">
                            <i class="fa-solid fa-database text-5xl mb-4 text-slate-300"></i>
                            <h4 class="font-bold text-slate-600">불러온 데이터가 없습니다.</h4>
                            <p class="text-sm text-slate-400 mt-1 text-center">좌측에서 업종과 조회 구분을 선택하고<br>'데이터 호출하기' 버튼을 눌러주세요.</p>
                        </div>

                        <!-- Tab 1: Preview Table Container with Custom Max-Height Scroll and Sticky Header -->
                        <div id="tab-content-table" class="hidden">
                            <div class="mb-4 flex items-center justify-between text-xs text-slate-500">
                                <div id="table-summary-count" class="font-semibold text-blue-600"></div>
                                <div class="text-slate-400 text-right">※ 위아래/좌우 스크롤바를 사용하여 표 전체 데이터를 조회하실 수 있습니다.</div>
                            </div>
                            <div class="overflow-auto max-h-[620px] border border-slate-200 rounded-xl custom-scrollbar shadow-sm bg-slate-50 relative">
                                <table id="preview-table" class="min-w-full divide-y divide-slate-200 text-left text-xs table-auto">
                                    <thead class="bg-slate-100 sticky top-0 z-10 shadow-sm">
                                        <tr id="preview-table-header"></tr>
                                    </thead>
                                    <tbody id="preview-table-body" class="bg-white divide-y divide-slate-200 text-slate-600"></tbody>
                                </table>
                            </div>
                        </div>

                        <!-- Tab 2: Raw Code Container -->
                        <div id="tab-content-raw" class="hidden">
                            <div class="bg-slate-900 rounded-xl p-4 text-emerald-400 font-mono text-xs overflow-auto max-h-[500px] custom-scrollbar shadow-inner select-all">
                                <pre id="raw-display">Waiting for request...</pre>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    
    <!-- JavaScript logic -->
    <script>
        let categories = {}; // category -> [sectors]
        let selectedCategory = '';
        let selectedSector = null;
        let selectedType = 'info'; // 'info' or 'history'
        let cachedRawResponse = null;

        // Clean & fast initialization. Do not wait for DOMContentLoaded if it has already fired,
        // and resolve the instant parallel promises started in the head.
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', initializeUI);
        } else {
            initializeUI();
        }

        // Check if Tailwind is loaded, if not, display fallback warning or minor adjustments
        function checkTailwindLoaded() {
            setTimeout(() => {
                // If tailwind cdn script didn't load (offline), log it and show a small notification banner
                if (typeof tailwind === 'undefined') {
                    console.warn("[Debug JS] Tailwind CSS CDN failed to load (possibly offline). App remains 100% functional, but stylesheet styles will be standard browser default.");
                    const banner = document.createElement('div');
                    banner.style.cssText = "background: #fffbeb; color: #b55309; border: 1px solid #fef3c7; padding: 12px; margin: 15px; border-radius: 12px; font-size: 13px; font-weight: 500; text-align: center;";
                    banner.innerHTML = "⚠️ <strong>로컬 환경 안내:</strong> 인터넷이 연결되지 않은 오프라인 환경입니다. 웹 스타일링(CSS)은 기본 브라우저 스타일로 간소화되지만, <strong>API 수집 및 프록시 중계 기능은 100% 정상 작동합니다.</strong>";
                    document.body.insertBefore(banner, document.body.firstChild);
                }
            }, 1000);
        }

        function initializeUI() {
            console.log("[Debug JS] DOM is ready. Resolving pre-fetched promises...");
            // Set dynamic port text
            const portSpan = document.getElementById('current-port');
            if (portSpan) {
                portSpan.innerText = window.location.port || '5001';
            }
            checkTailwindLoaded();
            resolveKeyStatus();
            resolveSectors();
        }

        // 1. Resolve key status on local server
        function resolveKeyStatus() {
            if (!window.keyStatusPromise) {
                console.warn("[Debug JS] keyStatusPromise is undefined. Fetching manually...");
                window.keyStatusPromise = fetch('/api/key_status?_t=' + Date.now()).then(r => r.json());
            }
            window.keyStatusPromise.then(data => {
                console.log("[Debug JS] Key status promise resolved:", data);
                const banner = document.getElementById('key-banner');
                const title = document.getElementById('key-status-title');
                const desc = document.getElementById('key-status-desc');
                const iconContainer = document.getElementById('key-icon-container');
                if(!banner) return;

                if (data.has_key) {
                    banner.className = "mb-6 p-4 rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-800 flex items-center justify-between transition-all duration-300";
                    title.innerText = "API 인증키가 안전하게 설정되었습니다";
                    desc.innerText = "서버 로컬 메모리에 저장되어 클라이언트에 유출되지 않습니다. (" + data.key_source + ")";
                    iconContainer.innerHTML = '<i class="fa-solid fa-circle-check text-emerald-500"></i>';\n                    updateTotalCountDisplay();
                } else {
                    banner.className = "mb-6 p-4 rounded-xl border border-rose-200 bg-rose-50 text-rose-800 flex items-center justify-between transition-all duration-300";
                    title.innerText = "API 인증키(Service Key)가 설정되지 않았습니다";
                    desc.innerText = "공공데이터포털(data.go.kr)에서 발급받은 인허가 정보 API 인증키를 우측창에 입력해 주세요.";
                    iconContainer.innerHTML = '<i class="fa-solid fa-triangle-exclamation text-rose-500 animate-bounce"></i>';
                }
            }).catch(err => {
                console.error("Error resolving key status:", err);
            });
        }

        // Helper to query key status manually (e.g. after updating key)
        function checkApiKeyStatus() {
            window.keyStatusPromise = fetch('/api/key_status?_t=' + Date.now()).then(r => r.json());
            resolveKeyStatus();
        }

        // 2. Resolve sectors and categories
        function resolveSectors() {
            if (!window.sectorsPromise) {
                console.warn("[Debug JS] sectorsPromise is undefined. Fetching manually...");
                window.sectorsPromise = fetch('/api/sectors?_t=' + Date.now()).then(r => r.json());
            }
            window.sectorsPromise.then(data => {
                console.log("[Debug JS] Sectors data promise resolved. Count:", data.length);
                if (!data || data.length === 0) {
                    alert("서버가 CSV 파일 분석에 실패했거나 데이터가 비어 있습니다.\\n지방행정 인허가정보 CSV 파일 2개가 파이썬 스크립트와 동일한 폴더에 존재하는지 확인해 주세요.");
                    return;
                }

                // Group sectors by category
                data.forEach(item => {
                    if (!categories[item.category]) {
                        categories[item.category] = [];
                    }
                    categories[item.category].push(item);
                });

                // Populate Category dropdown
                const catSelect = document.getElementById('category-select');
                catSelect.innerHTML = '<option value="">분야 선택 (총 ' + Object.keys(categories).length + '개)</option>';
                Object.keys(categories).sort().forEach(cat => {
                    const opt = document.createElement('option');
                    opt.value = cat;
                    opt.innerText = cat;
                    catSelect.appendChild(opt);
                });
            }).catch(err => {
                console.error("Error resolving sectors data:", err);
                alert("업종 데이터를 읽어오는 중 에러가 발생했습니다: " + err.message);
            });
        }

        // Manual refresh if needed (not called by default)
        
        // Fetch and show pre-informed total count for selected sector and query type
        function updateTotalCountDisplay() {
            const display = document.getElementById('total-count-display');
            const setMaxBtn = document.getElementById('set-max-btn');
            const fetchAllBtn = document.getElementById('fetch-all-btn');
            
            if (!selectedSector) {
                display.innerText = "업종을 선택해 주세요.";
                display.className = "text-xxs font-bold text-slate-400";
                if (setMaxBtn) setMaxBtn.disabled = true;
                if (fetchAllBtn) fetchAllBtn.disabled = true;
                return;
            }
            
            display.innerText = "총 개수 조회 중...";
            display.className = "text-xxs font-bold text-blue-500 animate-pulse";
            if (setMaxBtn) setMaxBtn.disabled = true;
            if (fetchAllBtn) fetchAllBtn.disabled = true;
            
            const targetUrl = selectedType === 'info' ? selectedSector.info_url : selectedSector.history_url;
            
            let bgnDate = '';
            let endDate = '';
            if (selectedType === 'history') {
                const bgnInput = document.getElementById('param-bgn-date');
                const endInput = document.getElementById('param-end-date');
                if (bgnInput && bgnInput.value) bgnDate = bgnInput.value.replace(/-/g, '');
                if (endInput && endInput.value) endDate = endInput.value.replace(/-/g, '');
            }
            
            fetch('/api/total_count', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    url: targetUrl,
                    lastModTsBgn: bgnDate,
                    lastModTsEnd: endDate
                })
            })
            .then(res => res.json())
            .then(data => {
                if (data.success) {
                    window.currentTotalCount = data.total_count;
                    display.innerText = "총 " + data.total_count.toLocaleString() + "개";
                    display.className = "text-xxs font-bold text-emerald-600";
                    if (setMaxBtn) setMaxBtn.disabled = false;
                    if (fetchAllBtn) fetchAllBtn.disabled = false;
                } else {
                    window.currentTotalCount = null;
                    if (data.no_key) {
                        display.innerText = "인증키가 필요합니다.";
                        display.className = "text-xxs font-bold text-rose-500";
                        if (setMaxBtn) setMaxBtn.disabled = true;
                        if (fetchAllBtn) fetchAllBtn.disabled = true;
                    } else {
                        // Safe Fallback: if timeout or error, show clean message but KEEP buttons active
                        display.innerText = "타임아웃 (수동조회 권장)";
                        display.className = "text-xxs font-bold text-amber-500";
                        console.warn("[Debug JS] Pre-fetch total count failed: ", data.error);
                        if (setMaxBtn) setMaxBtn.disabled = false;
                        if (fetchAllBtn) fetchAllBtn.disabled = false;
                    }
                }
            })
            .catch(err => {
                console.error("Error checking total count:", err);
                window.currentTotalCount = null;
                display.innerText = "연결 지연 (수동조회 권장)";
                display.className = "text-xxs font-bold text-amber-500";
                if (setMaxBtn) setMaxBtn.disabled = false;
                if (fetchAllBtn) fetchAllBtn.disabled = false;
            });
        }

        // Set the limit input box value to the verified total count
        function setLimitToMax() {
            if (window.currentTotalCount) {
                document.getElementById('param-limit').value = window.currentTotalCount;
                console.log("[Debug JS] Set limit to pre-fetched max: " + window.currentTotalCount);
            } else {
                document.getElementById('param-limit').value = 999999;
                console.log("[Debug JS] Pre-fetched count not available. Fallback to 999999 (Will fetch all).");
            }
        }

        // Set maximum limit and trigger data call immediately
        function fetchDataAll() {
            if (!window.currentTotalCount) {
                console.log("[Debug JS] Pre-fetched count not available. Proceeding with 999999 (Will fetch all).");
                document.getElementById('param-limit').value = 999999;
            } else {
                document.getElementById('param-limit').value = window.currentTotalCount;
            }
            fetchData();
        }

        function fetchSectors() {
            window.sectorsPromise = fetch('/api/sectors?_t=' + Date.now()).then(r => r.json());
            resolveSectors();
        }

        // Save key on local server
        function setApiKey() {
            const key = document.getElementById('key-input').value.trim();
            if(!key) {
                alert("인증키를 입력해 주세요.");
                return;
            }
            fetch('/api/set_key', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ key: key })
            })
            .then(r => r.json())
            .then(data => {
                if(data.success) {
                    alert("인증키가 로컬 서버 메모리에 안전하게 등록되었습니다!");
                    document.getElementById('key-input').value = '';
                    checkApiKeyStatus();
                } else {
                    alert("인증키 설정에 실패했습니다.");
                }
            });
        }

        // On Category Dropdown Change
        function onCategoryChange() {
            selectedCategory = document.getElementById('category-select').value;
            const secSelect = document.getElementById('sector-select');
            
            if (!selectedCategory) {
                secSelect.innerHTML = '<option value="">업종 선택</option>';
                secSelect.disabled = true;
                selectedSector = null;
                updateTargetUrlDisplay();
                return;
            }

            secSelect.disabled = false;
            secSelect.innerHTML = '<option value="">업종 선택 (총 ' + categories[selectedCategory].length + '개)</option>';
            
            // Sort sectors alphabetically
            const sortedSectors = categories[selectedCategory].sort((a,b) => a.sector.localeCompare(b.sector));
            sortedSectors.forEach(sec => {
                const opt = document.createElement('option');
                opt.value = sec.id;
                opt.innerText = sec.sector;
                secSelect.appendChild(opt);
            });
            selectedSector = null;
            updateTargetUrlDisplay();
            updateTotalCountDisplay();
        }

        // On Sector Dropdown Change
        function onSectorChange() {
            const secId = document.getElementById('sector-select').value;
            if (!secId) {
                selectedSector = null;
                updateTargetUrlDisplay();
                return;
            }
            selectedSector = categories[selectedCategory].find(s => s.id == secId);
            updateTargetUrlDisplay();
            updateTotalCountDisplay();
        }

        // Change between info / history
        function setType(type) {
            selectedType = type;
            const infoBtn = document.getElementById('type-info');
            const histBtn = document.getElementById('type-history');
            const dateContainer = document.getElementById('history-date-container');
            
            if (type === 'info') {
                infoBtn.className = "py-2.5 border border-blue-500 bg-blue-50 text-blue-700 font-bold rounded-xl text-sm transition flex items-center justify-center space-x-2 shadow-sm";
                histBtn.className = "py-2.5 border border-slate-200 text-slate-600 hover:bg-slate-50 rounded-xl text-sm transition flex items-center justify-center space-x-2 shadow-sm";
                if (dateContainer) dateContainer.classList.add('hidden');
            } else {
                histBtn.className = "py-2.5 border border-blue-500 bg-blue-50 text-blue-700 font-bold rounded-xl text-sm transition flex items-center justify-center space-x-2 shadow-sm";
                infoBtn.className = "py-2.5 border border-slate-200 text-slate-600 hover:bg-slate-50 rounded-xl text-sm transition flex items-center justify-center space-x-2 shadow-sm";
                if (dateContainer) dateContainer.classList.remove('hidden');
                
                // Initialize default dates if not set yet (last 30 days)
                const bgnInput = document.getElementById('param-bgn-date');
                const endInput = document.getElementById('param-end-date');
                if (bgnInput && endInput && (!bgnInput.value || !endInput.value)) {
                    const today = new Date();
                    const thirtyDaysAgo = new Date();
                    thirtyDaysAgo.setDate(today.getDate() - 30);
                    
                    const formatISODate = (d) => d.toISOString().split('T')[0];
                    bgnInput.value = formatISODate(thirtyDaysAgo);
                    endInput.value = formatISODate(today);
                }
            }
            updateTargetUrlDisplay();
            updateTotalCountDisplay();
        }

        // Update target URL display
        function updateTargetUrlDisplay() {
            const display = document.getElementById('target-url-display');
            if (!selectedSector) {
                display.innerText = "분야와 업종을 먼저 선택해 주세요.";
                return;
            }
            const url = selectedType === 'info' ? selectedSector.info_url : selectedSector.history_url;
            display.innerText = url;
        }

        // Tab switcher
        function switchTab(tab) {
            const tabTable = document.getElementById('tab-table');
            const tabRaw = document.getElementById('tab-raw');
            const contentTable = document.getElementById('tab-content-table');
            const contentRaw = document.getElementById('tab-content-raw');

            if (tab === 'table') {
                tabTable.className = "px-5 py-3 border-b-2 border-blue-600 text-blue-600 font-bold flex items-center space-x-2 transition";
                tabRaw.className = "px-5 py-3 border-b-2 border-transparent text-slate-500 font-semibold flex items-center space-x-2 hover:text-slate-800 transition";
                contentTable.classList.remove('hidden');
                contentRaw.classList.add('hidden');
            } else {
                tabRaw.className = "px-5 py-3 border-b-2 border-blue-600 text-blue-600 font-bold flex items-center space-x-2 transition";
                tabTable.className = "px-5 py-3 border-b-2 border-transparent text-slate-500 font-semibold flex items-center space-x-2 hover:text-slate-800 transition";
                contentRaw.classList.remove('hidden');
                contentTable.classList.add('hidden');
            }
        }

        // Recursive search to find the payload array in public API JSON response
        function findPayloadArray(obj) {
            if (!obj || typeof obj !== 'object') return null;
            
            // Check if this object itself is an array of objects
            if (Array.isArray(obj)) {
                if (obj.length > 0 && typeof obj[0] === 'object') {
                    return obj;
                }
            }
            
            // Recurse down keys
            for (let key in obj) {
                if (obj.hasOwnProperty(key)) {
                    let result = findPayloadArray(obj[key]);
                    if (result) return result;
                }
            }
            return null;
        }

        // Clear console/results
        function clearConsole() {
            cachedRawResponse = null;
            document.getElementById('raw-display').innerText = "Waiting for request...";
            document.getElementById('preview-table-header').innerHTML = '';
            document.getElementById('preview-table-body').innerHTML = '';
            document.getElementById('empty-state').classList.remove('hidden');
            document.getElementById('tab-content-table').classList.add('hidden');
            document.getElementById('tab-content-raw').classList.add('hidden');
            document.getElementById('download-json-btn').classList.add('hidden');
            document.getElementById('download-csv-btn').classList.add('hidden');
            document.getElementById('table-summary-count').innerText = '';
        }

        // Call proxy API and get data
        function fetchData() {
            if (!selectedSector) {
                alert("업종을 선택해 주세요.");
                return;
            }

            const targetUrl = selectedType === 'info' ? selectedSector.info_url : selectedSector.history_url;
            const limit = document.getElementById('param-limit').value;
            const resultType = document.querySelector('input[name="param-format"]:checked').value;

            const loader = document.getElementById('loading');
            loader.classList.remove('hidden');

            let bgnDate = '';
            let endDate = '';
            if (selectedType === 'history') {
                const bgnInput = document.getElementById('param-bgn-date');
                const endInput = document.getElementById('param-end-date');
                if (bgnInput && bgnInput.value) bgnDate = bgnInput.value.replace(/-/g, '');
                if (endInput && endInput.value) endDate = endInput.value.replace(/-/g, '');
            }
            
            fetch('/api/proxy', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    url: targetUrl,
                    limit: limit,
                    resultType: resultType,
                    lastModTsBgn: bgnDate,
                    lastModTsEnd: endDate
                })
            })
            .then(res => {
                if (!res.ok) {
                    throw new Error("HTTP 오류 상태코드: " + res.status);
                }
                return res.json();
            })
            .then(data => {
                loader.classList.add('hidden');
                document.getElementById('empty-state').classList.add('hidden');
                
                cachedRawResponse = data.data; // Server returns raw response inside .data

                // Handle XML/HTML string or JSON
                if (typeof cachedRawResponse === 'string') {
                    document.getElementById('raw-display').innerText = cachedRawResponse;
                    document.getElementById('download-json-btn').classList.remove('hidden');
                    document.getElementById('download-csv-btn').classList.add('hidden');
                    
                    // Simple table for raw strings or XML errors
                    document.getElementById('preview-table-header').innerHTML = '<th class="px-6 py-3 font-bold">응답 형식</th>';
                    document.getElementById('preview-table-body').innerHTML = '<tr><td class="px-6 py-4 font-mono break-all text-xs bg-slate-50">' + escapeHtml(cachedRawResponse.substring(0, 1000)) + (cachedRawResponse.length > 1000 ? '...' : '') + '</td></tr>';
                    
                    document.getElementById('table-summary-count').innerText = "결과가 XML/문자열 형식입니다.";
                    switchTab('raw');
                } else {
                    // Pretty-print JSON
                    const jsonStr = JSON.stringify(cachedRawResponse, null, 2);
                    document.getElementById('raw-display').innerText = jsonStr;
                    document.getElementById('download-json-btn').classList.remove('hidden');

                    // Try to extract an array for dynamic table preview
                    const records = findPayloadArray(cachedRawResponse);
                    
                    if (records && records.length > 0) {
                        renderTable(records);
                        document.getElementById('download-csv-btn').classList.remove('hidden');
                        document.getElementById('table-summary-count').innerText = "총 " + records.length.toLocaleString() + "개의 데이터 행(Row)을 수집하여 표시 중입니다.";
                        switchTab('table');
                    } else {
                        // fallback if no array found in JSON
                        document.getElementById('download-csv-btn').classList.add('hidden');
                        document.getElementById('preview-table-header').innerHTML = '<th class="px-6 py-3 font-bold">오류 또는 결과 없음</th>';
                        document.getElementById('preview-table-body').innerHTML = '<tr><td class="px-6 py-4 text-rose-500 font-semibold text-center">미리보기 가능한 레코드 배열을 찾을 수 없습니다. (혹은 빈 결과입니다)</td></tr>';
                        document.getElementById('table-summary-count').innerText = "데이터가 없거나 다른 데이터 구조를 가지고 있습니다.";
                        switchTab('raw');
                    }
                }
            })
            .catch(err => {
                loader.classList.add('hidden');
                alert("API 호출 중 로컬 서버에서 에러가 발생했습니다: \\n" + err.message);
                console.error(err);
            });
        }

        function escapeHtml(str) {
            return str.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#039;");
        }

        // Render extracted list into HTML Table
        function renderTable(array) {
            const headerRow = document.getElementById('preview-table-header');
            const body = document.getElementById('preview-table-body');
            headerRow.innerHTML = '';
            body.innerHTML = '';

            // Extract all keys from the objects (in case keys differ)
            let keysSet = new Set();
            array.forEach(item => {
                Object.keys(item).forEach(k => keysSet.add(k));
            });
            const keys = Array.from(keysSet).slice(0, 10); // max 10 columns for safety and styling

            // Create Headers
            keys.forEach(key => {
                const th = document.createElement('th');
                th.className = "px-6 py-3.5 bg-slate-50 font-bold text-slate-600 border-b border-slate-200 uppercase tracking-wider text-xxs";
                th.innerText = key;
                headerRow.appendChild(th);
            });

            // Create Rows
            array.forEach(item => {
                const tr = document.createElement('tr');
                tr.className = "hover:bg-slate-50 transition border-b border-slate-100";
                
                keys.forEach(key => {
                    const td = document.createElement('td');
                    td.className = "px-6 py-3 break-all max-w-[200px] text-slate-700 text-xs";
                    let val = item[key] !== undefined ? item[key] : '';
                    if (typeof val === 'object') val = JSON.stringify(val);
                    td.innerText = val;
                    tr.appendChild(td);
                });
                body.appendChild(tr);
            });
        }

        // Download data response as file (supports JSON and CSV)
        function downloadDataFile(format) {
            if (!cachedRawResponse) return;
            
            if (format === 'csv') {
                const records = findPayloadArray(cachedRawResponse);
                if (!records || records.length === 0) {
                    alert("CSV로 변환할 테이블 형태의 데이터가 없습니다.");
                    return;
                }
                
                // Get all unique keys in records
                let keysSet = new Set();
                records.forEach(item => {
                    Object.keys(item).forEach(k => keysSet.add(k));
                });
                const keys = Array.from(keysSet);
                
                // Construct CSV with UTF-8 BOM (\\uFEFF) for proper Korean encoding in Excel
                let csvContent = "\\uFEFF";
                
                // Headers
                csvContent += keys.map(k => `"${String(k).replace(/"/g, '""')}"`).join(",") + "\\r\\n";
                
                // Rows
                records.forEach(item => {
                    let row = keys.map(key => {
                        let val = item[key] !== undefined ? item[key] : '';
                        if (typeof val === 'object') val = JSON.stringify(val);
                        // Escape quotes and wrap in quotes
                        return `"${String(val).replace(/"/g, '""')}"`;
                    });
                    csvContent += row.join(",") + "\\r\\n";
                });
                
                const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
                const link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                
                const filename = (selectedSector ? selectedSector.sector : "지방행정인허가") + "_" + selectedType + ".csv";
                link.download = filename;
                link.click();
            } else {
                // Download original json or xml
                const resultType = document.querySelector('input[name="param-format"]:checked').value;
                const blobType = resultType === 'json' ? 'application/json' : 'application/xml';
                const fileExt = resultType === 'json' ? 'json' : 'xml';
                
                const fileData = typeof cachedRawResponse === 'string' 
                    ? cachedRawResponse 
                    : JSON.stringify(cachedRawResponse, null, 4);

                const blob = new Blob([fileData], { type: blobType });
                const link = document.createElement('a');
                link.href = URL.createObjectURL(blob);
                
                const filename = (selectedSector ? selectedSector.sector : "지방행정인허가") + "_" + selectedType + "." + fileExt;
                link.download = filename;
                link.click();
            }
        }
    </script>

</body>
</html>
"""

# -----------------
# Flask Routes
# -----------------

# -------------------------------------------------------------------------
# 6. Flask 웹 컨트롤러 라우트 (Backend API Endpoint)
# -------------------------------------------------------------------------
# 6-1. 메인 웹 대시보드 화면 송출 라우트
@app.route('/')
def home():
    # Pass the actual port dynamically
    port = request.host.split(':')[-1] if ':' in request.host else '5001'
    from flask import make_response
    response = make_response(render_template_string(HTML_TEMPLATE, port=port))
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

    # 6-2. 로딩된 195개 업종 메타데이터 전송 라우트 (브라우저 초기화 시 호출)
@app.route('/api/sectors')
def get_sectors():
    print(f"[Debug API] /api/sectors requested! Current SECTORS_DATA count: {len(SECTORS_DATA)}")
    response = jsonify(SECTORS_DATA)
    # Prevent browser caching of API responses
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response

    # 6-3. 서버의 API 키 등록 상태 검증 라우트 (화면 상단 빨간색/초록색 배너 연동)
@app.route('/api/key_status')
def key_status():
    print(f"[Debug API] /api/key_status requested!")
    # 만약 메모리 상에 키가 비어있다면 로컬 파일이나 환경변수 실시간 다시 체크 시도
    if not CONFIG["service_key"]:
        loaded_key, loaded_source = load_cached_api_key()
        if loaded_key:
            CONFIG["service_key"] = loaded_key
            CONFIG["key_source"] = loaded_source

    has_key = bool(CONFIG["service_key"])
    key_source = CONFIG.get("key_source") or "자동 등록 키"
    response = jsonify({
        "has_key": has_key,
        "key_source": key_source if has_key else None
    })
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    return response

    # 6-4. 브라우저에서 입력한 API 인증키를 서버 메모리에 휘발성으로 보관 및 세팅하는 라우트
@app.route('/api/set_key', methods=['POST'])
def set_key():
    data = request.json or {}
    key = data.get('key', '').strip()
    if key:
        CONFIG["service_key"] = key
        CONFIG["key_source"] = "로컬 파일 (public_data_api_key.txt)"
        # 사용자가 키 저장 버튼을 누르는 즉시 동일 디렉토리 파일로 자동 영구 영속화 보존
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            key_file_path = os.path.join(script_dir, "public_data_api_key.txt")
            with open(key_file_path, "w", encoding="utf-8") as f:
                f.write(key)
            print(f"[Success] 사용자가 입력한 인증키를 로컬 파일 '{key_file_path}'에 영구 보존 완료했습니다.")
        except Exception as e:
            print(f"[Error] 인증키 로컬 파일 저장 실패: {e}")
        return jsonify({"success": True})
    return jsonify({"success": False}), 400


    # 6-5. 지정 업종의 공공데이터 원격 개수를 사전 쿼리(Pre-fetch) 해 오는 백엔드 라우트
@app.route('/api/total_count', methods=['POST'])
def get_total_count():
    req_data = request.json or {}
    target_url = req_data.get('url')
    if not target_url:
        return jsonify({"success": False, "error": "URL이 누락되었습니다."}), 400
        
    service_key = CONFIG["service_key"]
    if not service_key:
        return jsonify({"success": False, "no_key": True, "error": "인증키가 필요합니다."})
        
    try:
        decoded_key = urllib.parse.unquote(service_key)
    except Exception:
        decoded_key = service_key
        
    last_mod_ts_bgn = req_data.get('lastModTsBgn', '').strip()
    last_mod_ts_end = req_data.get('lastModTsEnd', '').strip()
    
    # Auto default date range for history if missing
    if "/history" in target_url:
        if not last_mod_ts_bgn or not last_mod_ts_end:
            today = datetime.datetime.now()
            thirty_days_ago = today - datetime.timedelta(days=30)
            if not last_mod_ts_bgn:
                last_mod_ts_bgn = thirty_days_ago.strftime("%Y%m%d")
            if not last_mod_ts_end:
                last_mod_ts_end = today.strftime("%Y%m%d")
                
    params = {
        "serviceKey": decoded_key,
        "pageNo": 1,
        "numOfRows": 1,
        "resultType": "json"
    }
    if "/history" in target_url:
        if last_mod_ts_bgn:
            params["lastModTsBgn"] = last_mod_ts_bgn
        if last_mod_ts_end:
            params["lastModTsEnd"] = last_mod_ts_end
    
    print(f"[Debug API] Requesting total count from: {target_url}")
    
    try:
        response = requests.get(target_url, params=params, timeout=15)
        resp_text = response.text
        
        # Safe check for typical registered key error
        if "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in resp_text:
            return jsonify({"success": False, "error": "미승인 인증키입니다."})
            
        total_count = extract_total_count(resp_text)
        if total_count is not None:
            return jsonify({"success": True, "total_count": total_count})
        else:
            return jsonify({"success": False, "error": "총 개수 추출 불가"})
            
    except Exception as e:
        return jsonify({"success": False, "error": f"네트워크 통신 실패: {str(e)}"})

    # 6-6. [핵심 브레인] 공공데이터포털 분할 병합 대용량 수집 프록시 라우트
    # 공공데이터포털의 1회 100건 조회 한계 및 서버 부하 차단 기능을 완전히 우회합니다.
    # 만약 사용자가 처음부터 300개의 조회를 원할 경우 백엔드가 알아서 100개씩 3번 자동 페이지 루프를 돌며
    # 수집한 뒤, 하나의 완벽한 대용량 JSON 데이터셋으로 정교하게 병합하여 클라이언트에 쏟아줍니다.
@app.route('/api/proxy', methods=['POST'])
def proxy_api():
    # 1. Verification of the service key
    service_key = CONFIG["service_key"]
    if not service_key:
        return jsonify({"success": False, "error": "API 인증키가 설정되지 않았습니다. 인증키를 먼저 입력하세요."}), 400

    # 2. Extract parameters from the request
    req_data = request.json or {}
    target_url = req_data.get('url')
    limit_val = req_data.get('limit')
    result_type = req_data.get('resultType', 'json')
    last_mod_ts_bgn = req_data.get('lastModTsBgn', '').strip()
    last_mod_ts_end = req_data.get('lastModTsEnd', '').strip()

    if not target_url:
        return jsonify({"success": False, "error": "API 호출 대상 URL이 없습니다."}), 400

    try:
        limit = int(limit_val)
    except (ValueError, TypeError):
        limit = 10
        
    if limit <= 0:
        limit = 10

    # Auto default date range for history if missing
    if "/history" in target_url:
        if not last_mod_ts_bgn or not last_mod_ts_end:
            today = datetime.datetime.now()
            thirty_days_ago = today - datetime.timedelta(days=30)
            if not last_mod_ts_bgn:
                last_mod_ts_bgn = thirty_days_ago.strftime("%Y%m%d")
            if not last_mod_ts_end:
                last_mod_ts_end = today.strftime("%Y%m%d")

    # 3. Robust decoding of the Service Key to prevent double encoding issues
    try:
        decoded_key = urllib.parse.unquote(service_key)
    except Exception:
        decoded_key = service_key

    PAGE_SIZE = 100
    gathered_items = []
    page_no = 1
    
    headers = {
        "Accept": "application/json, application/xml, text/html"
    }
    
    first_page_json = None
    
    print(f"[Debug API] Multi-page fetch requested for: {target_url} with limit: {limit}")
    
    # Loop to fetch and merge all items up to the requested limit (Chunking of 1000)
    while len(gathered_items) < limit:
        items_to_fetch = min(PAGE_SIZE, limit - len(gathered_items))
        
        params = {
            "serviceKey": decoded_key,
            "pageNo": page_no,
            "numOfRows": items_to_fetch,
            "resultType": result_type,
        }
        if "/history" in target_url:
            if last_mod_ts_bgn:
                params["lastModTsBgn"] = last_mod_ts_bgn
            if last_mod_ts_end:
                params["lastModTsEnd"] = last_mod_ts_end
        
        print(f" -> Fetching page {page_no} with size {items_to_fetch}")
        
        try:
            response = requests.get(target_url, params=params, headers=headers, timeout=20)
            
            if response.status_code != 200:
                return jsonify({
                    "success": False, 
                    "error": f"공공데이터포털 API가 비정상 상태코드({response.status_code})를 반환했습니다."
                }), 500
                
            resp_text = response.text
            
            if "SERVICE_KEY_IS_NOT_REGISTERED_ERROR" in resp_text:
                return jsonify({
                    "success": False,
                    "error": "공공데이터포털 인증키가 등록되지 않았거나 대기 상태입니다. (SERVICE_KEY_IS_NOT_REGISTERED_ERROR)"
                }), 400
                
            # If not JSON, we can't easily merge loops, so we just return the raw response
            if result_type != 'json':
                print(" -> XML response format, bypassing chunk loops and requesting single chunk.")
                params["numOfRows"] = limit
                if "/history" in target_url:
                    if last_mod_ts_bgn:
                        params["lastModTsBgn"] = last_mod_ts_bgn
                    if last_mod_ts_end:
                        params["lastModTsEnd"] = last_mod_ts_end
                xml_response = requests.get(target_url, params=params, headers=headers, timeout=20)
                return jsonify({
                    "success": True,
                    "status_code": xml_response.status_code,
                    "data": xml_response.text
                })
                
            try:
                res_json = response.json()
            except ValueError:
                # Returned invalid JSON or text error
                return jsonify({
                    "success": True,
                    "status_code": response.status_code,
                    "data": resp_text
                })
                
            items = extract_items_list(res_json)
            
            if page_no == 1:
                first_page_json = res_json
                # Extract and adjust actual limit from the totalCount field in raw response
                total_count = extract_total_count(resp_text)
                if total_count is not None:
                    print(f" -> First page loaded totalCount: {total_count}")
                    limit = min(limit, total_count)
            
            if not items:
                print(" -> No more records found in this page. Stopping loops.")
                break
                
            gathered_items.extend(items)
            print(f" -> Page {page_no} gathered {len(items)} items. Total gathered: {len(gathered_items)}/{limit}")
            
            # If we received fewer items than requested, we've hit the end of the dataset
            if len(items) < items_to_fetch:
                print(" -> Received fewer items than requested size. Stopping loops.")
                break
                
            page_no += 1
            
        except requests.exceptions.RequestException as e:
            print(f"Proxy chunk request failed: {e}")
            return jsonify({
                "success": False,
                "error": f"API 호출 중 네트워크 장애가 발생했습니다: {str(e)}"
            }), 500
            
    # Assemble and return merged JSON results
    if first_page_json:
        inject_items_list(first_page_json, gathered_items)
        return jsonify({
            "success": True,
            "status_code": 200,
            "data": first_page_json
        })
        
    return jsonify({
        "success": False,
        "error": "호출된 데이터가 없거나 비어 있습니다."
    }), 400

# -------------------------------------------------------------------------
# 7. 서버 프로그램 메인 가동부 (Bootstrap)
# -------------------------------------------------------------------------
if __name__ == '__main__':
    # Try loading again in case files were copied post server start
    if not SECTORS_DATA:
        load_sectors_data()
        
    print("\n" + "="*50)
    print("  지방행정 인허가정보 API 프록시 서버 시작 (v18)")
    print("  URL: http://localhost:5000")
    print(f"  데이터 로드 상태: {len(SECTORS_DATA)}개 업종 정보 탑재 완료")
    print("="*50 + "\n")
    
    app.run(host='0.0.0.0', port=5001, debug=False)
