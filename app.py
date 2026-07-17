from flask import Flask, render_template, jsonify, Response, send_from_directory
import subprocess
import threading
import queue
import os
import sys
from supabase import create_client, Client

app = Flask(__name__)
log_queue = queue.Queue()
running_process = None

def read_process_stdout(proc):
    global running_process
    # Read line by line in real-time
    for line in iter(proc.stdout.readline, b''):
        decoded_line = line.decode('utf-8', errors='replace')
        # Filter out event bus messages to keep it neat
        if "Sync handler error" not in decoded_line:
            log_queue.put(decoded_line)
    proc.wait()
    running_process = None
    log_queue.put("---PROCESS_FINISHED---")

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/ping')
def ping():
    return jsonify({"status": "ok"}), 200

@app.route('/api/run', methods=['POST'])
def run_desk():
    global running_process
    if running_process is not None:
        return jsonify({"status": "already_running"}), 400
    
    # Clear the queue before starting
    while not log_queue.empty():
        try:
            log_queue.get_nowait()
        except queue.Empty:
            break
            
    # Start main.py as a subprocess
    try:
        proc = subprocess.Popen(
            [sys.executable, 'main.py'],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=os.getcwd()
        )
        running_process = proc
        
        # Start a thread to read stdout
        t = threading.Thread(target=read_process_stdout, args=(proc,))
        t.daemon = True
        t.start()
        return jsonify({"status": "started"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/logs')
def get_logs():
    def generate():
        while True:
            try:
                line = log_queue.get(timeout=30)
                # Format SSE data
                yield f"data: {line.strip()}\n\n"
                if line == "---PROCESS_FINISHED---":
                    break
            except queue.Empty:
                yield "data: \n\n"
    return Response(generate(), mimetype='text/event-stream')

def get_supabase_client():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if url and key:
        try:
            return create_client(url, key)
        except Exception as e:
            print(f"Supabase connection init failed: {e}")
    return None

@app.route('/api/reports')
def list_reports():
    supabase = get_supabase_client()
    if supabase:
        try:
            res = supabase.table('reports').select('filename').execute()
            if res.data is not None:
                filenames = [row['filename'] for row in res.data]
                try:
                    filenames.sort(key=lambda x: int(x.split('_')[-1].split('.')[0]) if '_' in x else 0)
                except Exception:
                    filenames.sort()
                return jsonify(filenames)
        except Exception as e:
            print(f"Supabase list error: {e}")

    reports_dir = "reports"
    if not os.path.exists(reports_dir):
        return jsonify([])
    files = [f for f in os.listdir(reports_dir) if f.endswith('.md')]
    # Sort files by their incremented number (macro_report_1.md, macro_report_2.md)
    try:
        files.sort(key=lambda x: int(x.split('_')[-1].split('.')[0]) if '_' in x else 0)
    except Exception:
        files.sort()
    return jsonify(files)

@app.route('/api/reports/<filename>')
def get_report(filename):
    supabase = get_supabase_client()
    if supabase:
        try:
            res = supabase.table('reports').select('content').eq('filename', filename).execute()
            if res.data and len(res.data) > 0:
                return jsonify({"content": res.data[0]['content']})
        except Exception as e:
            print(f"Supabase get error: {e}")

    reports_dir = "reports"
    file_path = os.path.join(reports_dir, filename)
    if not os.path.exists(file_path):
        return jsonify({"error": "not_found"}), 404
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({"content": content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Allow network access
    print("Serving Monko Executive Suite on http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=True)
