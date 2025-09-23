from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
import asyncio
import subprocess
import os
import platform
import json
import re
from typing import Dict, List, Optional
from datetime import datetime
import openai
from dotenv import load_dotenv
import psutil
try:
    import GPUtil
    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False

# Load environment variables
load_dotenv()

app = FastAPI(title="AI Terminal Enhanced", description="Advanced AI-powered terminal with system monitoring")

# Detect and store system information at startup
SYSTEM_INFO = {
    'os': platform.system(),
    'os_version': platform.version(),
    'architecture': platform.architecture()[0],
    'processor': platform.processor(),
    'python_version': platform.python_version(),
    'hostname': platform.node()
}

print("System Detection:")
print(f"   OS: {SYSTEM_INFO['os']} {SYSTEM_INFO['os_version']}")
print(f"   Architecture: {SYSTEM_INFO['architecture']}")
print(f"   Processor: {SYSTEM_INFO['processor']}")
print(f"   Hostname: {SYSTEM_INFO['hostname']}")

# Global state
active_connections: Dict[str, WebSocket] = {}
command_history: List[Dict] = []
recorded_sessions: Dict[str, List[str]] = {}
recording_clients: Dict[str, str] = {}
last_suggestion: Dict[str, str] = {}

# Initialize OpenRouter client
api_key = os.getenv("OPENROUTER_API_KEY")
if api_key:
    openai_client = openai.OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1"
    )
    AI_AVAILABLE = True
    print("AI: OpenRouter client initialized successfully")
else:
    openai_client = None
    AI_AVAILABLE = False
    print("⚠️  OpenRouter API key not found. Set OPENROUTER_API_KEY environment variable.")

def get_os_type():
    """Detect the operating system"""
    system = platform.system().lower()
    return 'windows' if system == 'windows' else 'unix'

def translate_command(command: str) -> str:
    """Translate command to platform-specific equivalent"""
    os_type = get_os_type()
    base_cmd = command.split()[0] if command else ''

    mappings = {
        'windows': {'ls': 'dir', 'cat': 'type', 'clear': 'cls', 'ps': 'tasklist'},
        'unix': {'dir': 'ls', 'type': 'cat', 'cls': 'clear', 'tasklist': 'ps'}
    }

    if base_cmd in mappings[os_type]:
        return command.replace(base_cmd, mappings[os_type][base_cmd], 1)
    return command

def enhanced_security_check(command: str) -> tuple[bool, str]:
    """Enhanced security check for command injection and dangerous operations"""
    if not command or command.isspace():
        return False, "Empty command not allowed"

    # More permissive security check that allows legitimate system commands
    dangerous_patterns = [
        r'rm\s+-rf\s+/',
        r'del\s+/[sq]',
        r'format\s+[a-z]:',
        r'mkfs\.',
        r'dd\s+if=',
        r'curl.*\|.*sh',
        r'wget.*\|.*sh',
        r'sudo\s+su',
        r'chmod\s+777',
        r'chown\s+-R.*root',
        r'kill\s+-9\s+1',
        r'killall\s+-9',
        r'reg\s+delete.*HKLM',
        r'schtasks.*system',
        r'powershell.*-enc',
        r'cmd.*\/c.*&',
        r'bash.*-c.*[;&|]',
    ]

    command_lower = command.lower()
    
    for pattern in dangerous_patterns:
        if re.search(pattern, command_lower):
            return True, f"Dangerous pattern detected: {pattern}"

    if '..' in command and command.count('..') > 3:
        return True, "Excessive path traversal detected"

    if any(keyword in command_lower for keyword in ['base64', 'encode', 'decode', 'hex']):
        if any(char in command for char in [';', '|', '&']):
            return True, "Potential encoded injection detected"

    return False, ""

def is_direct_command(command: str) -> bool:
    """Check if a command is a direct terminal command (no AI needed)"""
    if not command or len(command.split()) == 0:
        return False

    base_cmd = command.split()[0].lower()
    
    # Expanded list of direct commands that don't need AI interpretation
    direct_commands = [
        'ls', 'dir', 'cd', 'mkdir', 'rm', 'del', 'cp', 'mv',
        'cat', 'type', 'ps', 'tasklist', 'pwd', 'cls', 
        'echo', 'touch', 'grep',
        'pip', 'python', 'node', 'npm', 'git', 'docker',
        'curl', 'wget', 'ping', 'nslookup', 'traceroute',
        'systeminfo', 'hostname', 'whoami', 'date', 'time', 'disk', 'health', 'status', 'monitor'
    ]

    return base_cmd in direct_commands

async def interpret_with_ai(query: str) -> tuple[Optional[str], str]:
    """
    Use AI to interpret natural language queries
    Returns: (command, error_message)
    """
    if not AI_AVAILABLE:
        return None, "AI service is not available"

    try:
        # Determine the correct command syntax based on OS
        if SYSTEM_INFO['os'].lower() == 'windows':
            command_examples = "dir, cd, mkdir, del, copy, move, type, tasklist, cls, wmic"
        else:
            command_examples = "ls, cd, mkdir, rm, cp, mv, cat, ps, clear, df, iostat"

        prompt = f"""You are an AI assistant that converts natural language queries into safe terminal commands for {SYSTEM_INFO['os']}.

Query: "{query}"

Return ONLY the terminal command as a single line without quotes, parentheses, or extra text. For {SYSTEM_INFO['os']}, examples:

- "list files": {"dir" if SYSTEM_INFO['os'].lower() == 'windows' else "ls"}
- "show processes": {"tasklist" if SYSTEM_INFO['os'].lower() == 'windows' else "ps"}
- "clear screen": {"cls" if SYSTEM_INFO['os'].lower() == 'windows' else "clear"}

If the query cannot be safely interpreted as a terminal command, return exactly: "NOT_A_COMMAND"

Response (command only):"""

        response = openai_client.chat.completions.create(
            model="meta-llama/llama-3.3-8b-instruct:free",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=100,
            temperature=0.15
        )

        result = response.choices[0].message.content.strip()

        # Clean up the response
        result = result.replace('"', '').replace("'", "").replace('`', '').strip()

        # Remove parenthetical explanations (e.g., "(Windows)" or "(Linux)")
        if '(' in result:
            result = result.split(' (')[0].strip()
        
        # Check if it's not a command
        if "NOT_A_COMMAND" in result or "not a command" in result.lower():
            return None, "This appears to be a question or conversation rather than a command request. Try phrasing it as an action, like 'show files' or 'list processes'."
        
        # Remove any AI prefixes
        prefixes_to_remove = [
            "Command:", "command:", "COMMAND:",
            "Answer:", "Output:", "Result:",
            "Windows:", "Linux:", "macOS:",
            "Terminal:", "Shell:", "Bash:"
        ]
        
        for prefix in prefixes_to_remove:
            if result.startswith(prefix):
                result = result[len(prefix):].strip()
        
        # Validate the command isn't too long or suspicious
        if len(result.split()) > 10:
            return None, "The interpretation seems too complex. Try a simpler request."
        
        # Security check on AI output (slightly relaxed for legitimate system commands)
        is_dangerous, reason = enhanced_security_check(result)
        if is_dangerous:
            # Allow some system monitoring commands that might trigger security checks
            allowed_system_commands = ['wmic', 'iostat', 'smartctl', 'chkdsk', 'df']
            if not any(cmd in result for cmd in allowed_system_commands):
                return None, f"Security concern with generated command: {reason}"
        
        print(f"AI interpreted '{query}' as: '{result}'")
        return result, ""

    except Exception as e:
        print(f"AI interpretation error: {e}")
        return None, f"AI service error: {str(e)}"

@app.get("/", response_class=HTMLResponse)
async def get_terminal_interface():
    """Serve the enhanced terminal interface"""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>AI Terminal Enhanced</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: 'Courier New', monospace;
                background-color: #0d1117;
                color: #f0f6fc;
                height: 100vh;
                overflow: hidden;
            }
            
            .header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 10px 20px;
                background-color: #161b22;
                border-bottom: 1px solid #30363d;
            }
            
            .title {
                font-size: 18px;
                font-weight: bold;
                color: #58a6ff;
            }
            
            .system-widgets {
                display: flex;
                gap: 15px;
            }
            
            .widget {
                background-color: #21262d;
                border: 1px solid #30363d;
                border-radius: 6px;
                padding: 8px 12px;
                min-width: 80px;
                text-align: center;
                font-size: 12px;
            }
            
            .widget-label {
                color: #8b949e;
                font-size: 10px;
                margin-bottom: 2px;
            }
            
            .widget-value {
                color: #f0f6fc;
                font-weight: bold;
            }
            
            .cpu { border-left: 3px solid #f85149; }
            .ram { border-left: 3px solid #a5f3fc; }
            .gpu { border-left: 3px solid #a9dc76; }
            
            .main-container {
                display: flex;
                height: calc(100vh - 60px);
            }
            
            .terminal {
                flex: 1;
                background-color: #0d1117;
                padding: 20px;
                overflow-y: auto;
                position: relative;
            }
            
            .sidebar {
                width: 300px;
                background-color: #161b22;
                border-left: 1px solid #30363d;
                padding: 20px;
                overflow-y: auto;
            }
            
            .command-input-container {
                position: sticky;
                bottom: 0;
                background-color: #0d1117;
                padding: 10px 0;
                border-top: 1px solid #30363d;
            }
            
            .command-input {
                width: 100%;
                background: #21262d;
                border: 1px solid #30363d;
                color: #f0f6fc;
                font-family: inherit;
                font-size: 14px;
                padding: 10px;
                border-radius: 6px;
                outline: none;
            }
            
            .command-input:focus {
                border-color: #58a6ff;
                box-shadow: 0 0 0 2px rgba(88, 166, 255, 0.3);
            }
            
            .output {
                margin: 5px 0;
                white-space: pre-wrap;
                line-height: 1.4;
            }
            
            .error {
                color: #f85149;
            }
            
            .success {
                color: #56d364;
            }
            
            .info {
                color: #58a6ff;
            }
            
            .ai-suggestion {
                background-color: #1f2937;
                border: 1px solid #58a6ff;
                border-radius: 6px;
                padding: 10px;
                margin: 10px 0;
                color: #58a6ff;
            }
            
            .suggestion-header {
                font-weight: bold;
                margin-bottom: 5px;
            }
            
            .suggestion-command {
                background-color: #21262d;
                padding: 5px 8px;
                border-radius: 4px;
                font-family: monospace;
                margin: 5px 0;
                cursor: pointer;
            }
            
            .suggestion-command:hover {
                background-color: #30363d;
            }
            
            .loading {
                display: inline-block;
                width: 12px;
                height: 12px;
                border: 2px solid #30363d;
                border-radius: 50%;
                border-top-color: #58a6ff;
                animation: spin 1s ease-in-out infinite;
            }
            
            @keyframes spin {
                to { transform: rotate(360deg); }
            }
            
            .history-item, .session-item {
                color: #f0f6fc;
                cursor: pointer;
                margin: 4px 0;
                padding: 6px 8px;
                border-radius: 4px;
                font-size: 12px;
                background-color: #21262d;
                border: 1px solid #30363d;
            }
            
            .history-item:hover, .session-item:hover {
                background-color: #30363d;
            }
            
            .section-title {
                color: #58a6ff;
                font-weight: bold;
                margin: 15px 0 10px 0;
                font-size: 14px;
            }
            
            .record-controls {
                display: flex;
                gap: 5px;
                margin-bottom: 10px;
            }
            
            .btn {
                background-color: #21262d;
                border: 1px solid #30363d;
                color: #f0f6fc;
                padding: 4px 8px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 11px;
            }
            
            .btn:hover {
                background-color: #30363d;
            }
            
            .btn.recording {
                background-color: #f85149;
                border-color: #f85149;
            }
        </style>
    </head>
    <body>
        <div class="header">
            <div class="title">🤖 AI Terminal Enhanced</div>
            <div class="system-widgets">
                <div class="widget cpu">
                    <div class="widget-label">CPU</div>
                    <div class="widget-value" id="cpuUsage">0%</div>
                </div>
                <div class="widget ram">
                    <div class="widget-label">RAM</div>
                    <div class="widget-value" id="ramUsage">0%</div>
                </div>
                <div class="widget gpu">
                    <div class="widget-label">GPU</div>
                    <div class="widget-value" id="gpuUsage">N/A</div>
                </div>
            </div>
        </div>
        
        <div class="main-container">
            <div class="terminal" id="terminal">
                <div id="output"></div>
                <div class="command-input-container">
                    <input type="text" class="command-input" id="commandInput" 
                           placeholder="Type a command or describe what you want to do..." autocomplete="off">
                </div>
            </div>
            
            <div class="sidebar">
                <div class="section-title">Record & Replay</div>
                <div class="record-controls">
                    <button class="btn" id="recordBtn" onclick="toggleRecording()">Record</button>
                    <input type="text" id="sessionName" placeholder="Session name" style="flex: 1; background: #21262d; border: 1px solid #30363d; color: #f0f6fc; padding: 4px; border-radius: 4px; font-size: 11px;">
                </div>
                <div id="sessions"></div>
                
                <div class="section-title">Command History</div>
                <div id="history"></div>
            </div>
        </div>

        <script>
            const terminal = document.getElementById('terminal');
            const output = document.getElementById('output');
            const commandInput = document.getElementById('commandInput');
            const history = document.getElementById('history');
            const sessions = document.getElementById('sessions');
            const cpuUsage = document.getElementById('cpuUsage');
            const ramUsage = document.getElementById('ramUsage');
            const gpuUsage = document.getElementById('gpuUsage');
            const recordBtn = document.getElementById('recordBtn');
            const sessionName = document.getElementById('sessionName');

            let ws;
            let commandHistory = [];
            let historyIndex = -1;
            let isRecording = false;

            function connectWebSocket() {
                ws = new WebSocket('ws://localhost:8000/ws/terminal');

                ws.onopen = function(event) {
                    console.log('Connected to terminal');
                    appendOutput('🚀 Connected to AI Terminal Enhanced', 'success');
                    appendOutput('💡 Tip: You can use natural language or direct commands!', 'info');
                };

                ws.onmessage = function(event) {
                    const data = JSON.parse(event.data);
                    handleMessage(data);
                };

                ws.onclose = function(event) {
                    console.log('Disconnected from terminal');
                    appendOutput('❌ Connection lost. Reconnecting...', 'error');
                    setTimeout(connectWebSocket, 1000);
                };

                ws.onerror = function(error) {
                    console.error('WebSocket error:', error);
                };
            }

            function handleMessage(data) {
                switch(data.type) {
                    case 'output':
                        appendOutput(data.content, data.is_error ? 'error' : 'output');
                        break;
                    case 'ai_suggestion':
                        showAISuggestion(data.original, data.suggestion);
                        break;
                    case 'ai_info':
                        appendOutput(data.message, 'info');
                        break;
                    case 'loading':
                        showLoading(data.message);
                        break;
                    case 'system_info':
                        updateSystemInfo(data.cpu, data.ram, data.gpu);
                        break;
                    case 'history':
                        updateHistory(data.history);
                        break;
                    case 'sessions':
                        updateSessions(data.sessions);
                        break;
                    case 'recording_status':
                        updateRecordingStatus(data.recording);
                        break;
                }
            }

            function appendOutput(content, className = 'output') {
                const div = document.createElement('div');
                div.className = className;
                div.textContent = content;
                output.appendChild(div);
                terminal.scrollTop = terminal.scrollHeight;
            }

            function showAISuggestion(original, suggestion) {
                const div = document.createElement('div');
                div.className = 'ai-suggestion';
                
                div.innerHTML = `
                    <div class="suggestion-header">🤖 AI interpreted your request:</div>
                    <div style="margin: 5px 0;">You said: "${original}"</div>
                    <div class="suggestion-command" onclick="executeCommand('${suggestion}')">${suggestion}</div>
                    <div style="font-size: 11px; color: #8b949e; margin-top: 5px;">
                        Click to execute or press Enter to confirm
                    </div>
                `;
                output.appendChild(div);
                terminal.scrollTop = terminal.scrollHeight;
            }

            function showLoading(message) {
                const div = document.createElement('div');
                div.className = 'output';
                div.innerHTML = `<span class="loading"></span> ${message}`;
                output.appendChild(div);
                terminal.scrollTop = terminal.scrollHeight;
            }

            function updateSystemInfo(cpu, ram, gpu) {
                cpuUsage.textContent = cpu + '%';
                ramUsage.textContent = ram + '%';
                gpuUsage.textContent = gpu !== null ? gpu + '%' : 'N/A';
            }

            function updateHistory(historyList) {
                history.innerHTML = '';
                historyList.slice(-10).forEach(cmd => {
                    const div = document.createElement('div');
                    div.className = 'history-item';
                    div.textContent = cmd;
                    div.onclick = () => {
                        commandInput.value = cmd;
                        commandInput.focus();
                    };
                    history.appendChild(div);
                });
            }

            function updateSessions(sessionList) {
                sessions.innerHTML = '';
                Object.keys(sessionList).forEach(name => {
                    const div = document.createElement('div');
                    div.className = 'session-item';
                    div.innerHTML = `${name} (${sessionList[name]} commands)`;
                    div.onclick = () => replaySession(name);
                    sessions.appendChild(div);
                });
            }

            function updateRecordingStatus(recording) {
                isRecording = recording;
                recordBtn.textContent = recording ? 'Stop' : 'Record';
                recordBtn.className = recording ? 'btn recording' : 'btn';
            }

            function executeCommand(cmd) {
                commandInput.value = cmd;
                sendCommand();
            }

            function sendCommand() {
                const command = commandInput.value.trim();
                if (command) {
                    commandHistory.push(command);
                    historyIndex = commandHistory.length;
                    appendOutput('$ ' + command, 'success');
                    ws.send(JSON.stringify({type: 'command', content: command}));
                    commandInput.value = '';
                }
            }

            function toggleRecording() {
                const name = sessionName.value.trim();
                if (!isRecording && !name) {
                    alert('Please enter a session name');
                    return;
                }
                
                ws.send(JSON.stringify({
                    type: 'record',
                    action: isRecording ? 'stop' : 'start',
                    session_name: name
                }));
            }

            function replaySession(name) {
                ws.send(JSON.stringify({
                    type: 'replay',
                    session_name: name
                }));
            }

            commandInput.addEventListener('keydown', function(e) {
                if (e.key === 'Enter') {
                    sendCommand();
                } else if (e.key === 'ArrowUp') {
                    e.preventDefault();
                    if (historyIndex > 0) {
                        historyIndex--;
                        commandInput.value = commandHistory[historyIndex];
                    }
                } else if (e.key === 'ArrowDown') {
                    e.preventDefault();
                    if (historyIndex < commandHistory.length - 1) {
                        historyIndex++;
                        commandInput.value = commandHistory[historyIndex];
                    } else {
                        historyIndex = commandHistory.length;
                        commandInput.value = '';
                    }
                }
            });

            // Connect to WebSocket on page load
            connectWebSocket();

            // Focus input on page load
            commandInput.focus();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.websocket("/ws/terminal")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time terminal communication"""
    await websocket.accept()
    client_id = str(id(websocket))
    active_connections[client_id] = websocket

    try:
        # Start system monitoring
        asyncio.create_task(monitor_system(websocket))
        
        # Send initial data
        await send_history(websocket)
        await send_sessions(websocket)

        while True:
            data = await websocket.receive_json()
            
            if data['type'] == 'command':
                await handle_command(data['content'], websocket, client_id)
            elif data['type'] == 'record':
                await handle_recording(data, websocket, client_id)
            elif data['type'] == 'replay':
                await handle_replay(data['session_name'], websocket)

    except WebSocketDisconnect:
        if client_id in active_connections:
            del active_connections[client_id]
        if client_id in recording_clients:
            del recording_clients[client_id]
        if client_id in last_suggestion:
            del last_suggestion[client_id]

async def handle_command(command: str, websocket: WebSocket, client_id: str):
    """Handle incoming commands with AI processing for natural language"""
    try:
        original_command = command

        # Validate input
        if not command or command.isspace():
            await websocket.send_json({
                'type': 'output',
                'content': 'Error: Empty command not allowed.',
                'is_error': True
            })
            return

        # Security check (more permissive for system monitoring commands)
        is_dangerous, danger_reason = enhanced_security_check(command)
        if is_dangerous:
            # Allow some system monitoring commands that might trigger security checks
            allowed_system_commands = ['wmic', 'iostat', 'smartctl', 'chkdsk', 'df', 'tasklist', 'ps']
            if not any(cmd in command.lower() for cmd in allowed_system_commands):
                await websocket.send_json({
                    'type': 'output',
                    'content': f'🚫 Security Alert: {danger_reason}',
                    'is_error': True
                })
                return

        # Check if this is a confirmed AI suggestion
        if command == last_suggestion.get(client_id):
            del last_suggestion[client_id]
            # Execute the confirmed suggestion directly
            command = translate_command(command)
            result = await execute_command_async(command)
        elif is_direct_command(command):
            # Execute directly without AI
            command = translate_command(command)
            result = await execute_command_async(command)
        else:
            # Try AI interpretation for everything else
            if not AI_AVAILABLE:
                await websocket.send_json({
                    'type': 'output',
                    'content': '⚠️ AI not available. Please use direct commands like: ls, dir, cd, mkdir, etc.',
                    'is_error': True
                })
                return

            # Show loading
            await websocket.send_json({
                'type': 'loading',
                'message': 'AI is interpreting your request...'
            })

            # Get AI interpretation
            interpreted_command, error_msg = await interpret_with_ai(command)

            if interpreted_command:
                # Store the suggestion for potential confirmation
                last_suggestion[client_id] = interpreted_command
                # Show AI suggestion
                await websocket.send_json({
                    'type': 'ai_suggestion',
                    'original': command,
                    'suggestion': interpreted_command
                })

                return  # Don't execute, let user confirm
            else:
                # AI couldn't interpret - provide helpful feedback
                await websocket.send_json({
                    'type': 'ai_info',
                    'message': f'ℹ️ {error_msg}'
                })

                # Provide examples based on what they might be trying to do
                if any(word in command.lower() for word in ['file', 'folder', 'directory']):
                    await websocket.send_json({
                        'type': 'output',
                        'content': 'Try: "list files", "create folder name", "delete file.txt"',
                        'is_error': False
                    })
                elif any(word in command.lower() for word in ['process', 'running', 'program']):
                    await websocket.send_json({
                        'type': 'output',
                        'content': 'Try: "show processes", "what is running", "list programs"',
                        'is_error': False
                    })
                elif any(word in command.lower() for word in ['disk', 'health', 'check', 'scan']):
                    await websocket.send_json({
                        'type': 'output',
                        'content': 'Try: "check disk health", "scan disk", "show disk status"',
                        'is_error': False
                    })
                return

        # Add to history
        command_history.append({
            'command': original_command,
            'timestamp': datetime.now().isoformat(),
            'success': result['success']
        })

        # Add to recording if active
        if client_id in recording_clients:
            session_name = recording_clients[client_id]
            if session_name not in recorded_sessions:
                recorded_sessions[session_name] = []
            recorded_sessions[session_name].append(original_command)

        # Send result
        await websocket.send_json({
            'type': 'output',
            'content': result['output'],
            'is_error': not result['success']
        })

        # Update UI
        await send_history(websocket)
        await send_sessions(websocket)

    except Exception as e:
        await websocket.send_json({
            'type': 'output',
            'content': f'Error: {str(e)}',
            'is_error': True
        })

async def execute_command_async(command: str) -> Dict:
    """Execute command asynchronously"""
    try:
        # Ensure proper command execution on Windows
        if platform.system() == 'Windows':
            command = f'cmd /c {command}'

        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=os.getcwd()
        )

        stdout, stderr = await process.communicate()

        output = stdout.decode().strip() if stdout else ""
        error = stderr.decode().strip() if stderr else ""

        if error:
            output += f"\n{error}"

        return {
            'success': process.returncode == 0,
            'output': output or "Command executed successfully",
            'returncode': process.returncode
        }

    except Exception as e:
        return {
            'success': False,
            'output': f'Failed to execute command: {str(e)}',
            'returncode': -1
        }

async def handle_recording(data: Dict, websocket: WebSocket, client_id: str):
    """Handle recording start/stop"""
    action = data['action']
    session_name = data.get('session_name', '')

    if action == 'start':
        if session_name:
            recording_clients[client_id] = session_name
            await websocket.send_json({
                'type': 'recording_status',
                'recording': True
            })
            await websocket.send_json({
                'type': 'output',
                'content': f'🔴 Started recording session: {session_name}',
                'is_error': False
            })
    
    elif action == 'stop':
        if client_id in recording_clients:
            session_name = recording_clients[client_id]
            del recording_clients[client_id]
            await websocket.send_json({
                'type': 'recording_status',
                'recording': False
            })
            await websocket.send_json({
                'type': 'output',
                'content': f'⏹️ Stopped recording session: {session_name}',
                'is_error': False
            })
            await send_sessions(websocket)

async def handle_replay(session_name: str, websocket: WebSocket):
    """Handle session replay"""
    if session_name in recorded_sessions:
        commands = recorded_sessions[session_name]
        await websocket.send_json({
            'type': 'output',
            'content': f'▶️ Replaying session: {session_name} ({len(commands)} commands)',
            'is_error': False
        })

        for i, cmd in enumerate(commands):
            await websocket.send_json({
                'type': 'output',
                'content': f'[{i+1}/{len(commands)}] $ {cmd}',
                'is_error': False
            })

            # Execute the command
            translated_cmd = translate_command(cmd)
            result = await execute_command_async(translated_cmd)
            
            await websocket.send_json({
                'type': 'output',
                'content': result['output'],
                'is_error': not result['success']
            })

            # Small delay between commands
            await asyncio.sleep(0.5)

        await websocket.send_json({
            'type': 'output',
            'content': f'✅ Replay completed: {session_name}',
            'is_error': False
        })

async def monitor_system(websocket: WebSocket):
    """Monitor system resources and send updates"""
    while True:
        try:
            # CPU and RAM
            cpu_percent = psutil.cpu_percent(interval=1)
            memory = psutil.virtual_memory()
            
            # GPU (if available)
            gpu_percent = None
            if GPU_AVAILABLE:
                try:
                    gpus = GPUtil.getGPUs()
                    if gpus:
                        gpu_percent = int(gpus[0].load * 100)
                except:
                    pass

            await websocket.send_json({
                'type': 'system_info',
                'cpu': round(cpu_percent, 1),
                'ram': round(memory.percent, 1),
                'gpu': gpu_percent
            })

            await asyncio.sleep(2)  # Update every 2 seconds
        except:
            break  # Connection closed

async def send_history(websocket: WebSocket):
    """Send recent command history"""
    recent_commands = [entry['command'] for entry in command_history[-10:]]
    await websocket.send_json({
        'type': 'history',
        'history': recent_commands
    })

async def send_sessions(websocket: WebSocket):
    """Send recorded sessions"""
    sessions_info = {name: len(commands) for name, commands in recorded_sessions.items()}
    await websocket.send_json({
        'type': 'sessions',
        'sessions': sessions_info
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
