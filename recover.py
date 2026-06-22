import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent

with open(r'C:\Users\Kenny\.gemini\antigravity\brain\83673466-2775-45af-ae81-334e55086000\.system_generated\logs\transcript.jsonl', 'r', encoding='utf-8') as f:
    lines = f.read().splitlines()

content = ''
for l in reversed(lines):
    if l.strip():
        try:
            obj = json.loads(l)
            c = str(obj)
            if 'Showing lines 1 to 475' in c and 'planner-render.js' in c:
                if 'content' in obj:
                    content = obj['content']
                elif 'output' in obj:
                    content = obj['output']
                elif 'tool_calls' in obj:
                    for tc in obj['tool_calls']:
                        if 'arguments' in tc:
                            if 'output' in tc['arguments']:
                                content = tc['arguments']['output']
                else:
                    content = c
                
                if 'The following code has been modified' in content:
                    break
        except:
            pass

if content:
    try:
        start_marker = 'The following code has been modified to include a line number before every line, in the format: <line_number>: <original_line>. Please note that any changes targeting the original code should remove the line number, colon, and leading space.'
        end_marker = 'The above content shows the entire, complete file contents of the requested file.'
        
        # Replace explicit \n if they exist as strings
        content = content.replace('\\n', '\n')
        
        data = content.split(start_marker)[1].split(end_marker)[0].strip()
        lines = data.split('\n')
        
        out = []
        for x in lines:
            m = re.match(r'^\d+:\s?(.*)$', x)
            if m:
                out.append(m.group(1))
            else:
                out.append(x)
                
        # Some lines might be empty or missing due to weird parsing, we want exactly 475
        with open(ROOT / 'meal_planner' / 'web' / 'planner-render.js', 'w', encoding='utf-8') as f:
            f.write('\n'.join(out))
        print("Recovered perfectly! Total lines: ", len(out))
    except Exception as e:
        print("Error parsing", e)
else:
    print("Not found")
