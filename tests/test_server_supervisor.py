"""Windows integration tests on isolated ports and disposable fake servers."""
import json
import os
from pathlib import Path
import socket
import shutil
import subprocess
import tempfile
import time
import unittest
import urllib.request


SCRIPT = Path(__file__).resolve().parents[1] / 'start_server_hidden.ps1'
FAKE_SERVER = '''import http.server, json, os, pathlib, sys
root = pathlib.Path(os.environ['MENU_PROJECT_ROOT'])
(root / 'child.pid').write_text(str(os.getpid()))
print('fake server stdout', flush=True)
print('fake server stderr', file=sys.stderr, flush=True)
class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        payload = {'status': 'ok', 'project_root': str(root), 'pid': os.getpid(), 'no_kill': os.environ.get('MENU_API_NO_KILL')}
        if (root / 'unhealthy').exists(): payload['status'] = 'busy'
        if (root / 'foreign').exists(): payload['project_root'] = 'other-project'
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))
http.server.HTTPServer(('127.0.0.1', int(os.environ['MENU_API_PORT'])), Handler).serve_forever()
'''


def wait_for(check, timeout=25):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            result = check()
            if result:
                return result
        except (OSError, ValueError):
            pass
        time.sleep(0.2)
    raise AssertionError('Timed out waiting for isolated supervisor condition')


@unittest.skipUnless(os.name == 'nt', 'Windows PowerShell supervisor')
class SupervisorIntegrationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='餐單 supervisor ')
        self.root = Path(self.temp.name)
        (self.root / 'fake_server.py').write_text(FAKE_SERVER, encoding='utf-8')
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            self.port = sock.getsockname()[1]
        self.processes = []
        self.child_pids = set()
        self.supervisor_pids = set()

    def tearDown(self):
        for supervisor_pid in self.supervisor_pids:
            try:
                os.kill(supervisor_pid, 15)
            except OSError:
                pass
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=10)
        pid_file = self.root / 'child.pid'
        if pid_file.exists():
            self.child_pids.add(int(pid_file.read_text()))
        for child_pid in self.child_pids:
            try:
                os.kill(child_pid, 15)
            except OSError:
                pass
        time.sleep(0.5)
        self.temp.cleanup()

    def launch(self, restart=False):
        args = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(SCRIPT),
                '-ProjectRoot', str(self.root), '-Port', str(self.port), '-ServerModule', 'fake_server',
                '-PollSeconds', '1', '-StartupTimeoutSeconds', '10']
        if restart:
            args.append('-Restart')
        process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        self.processes.append(process)
        return process

    def health(self):
        with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/api/health', timeout=1) as response:
            data = json.load(response)
        self.child_pids.add(data['pid'])
        return data

    def log(self):
        return (self.root / 'logs' / 'server_autostart.log').read_text(encoding='utf-8-sig')

    def test_crash_recovery_singleton_busy_health_manual_restart_and_logs(self):
        supervisor = self.launch()
        first_pid = wait_for(self.health)['pid']
        self.assertEqual(self.health()['no_kill'], '1')
        wait_for(lambda: 'continuous supervision active' in self.log())
        duplicate = self.launch()
        self.assertEqual(duplicate.wait(timeout=10), 0)
        self.assertEqual(self.health()['pid'], first_pid)
        (self.root / 'unhealthy').touch()
        wait_for(lambda: 'still running. Leaving it running' in self.log())
        time.sleep(3)
        self.assertEqual(self.health()['pid'], first_pid)
        (self.root / 'unhealthy').unlink()
        os.kill(first_pid, 15)
        second_pid = wait_for(lambda: (data := self.health())['pid'] != first_pid and data)['pid']
        self.assertIn('exit code=', self.log())
        self.assertIn('fake server stderr', ''.join(p.read_text() for p in (self.root / 'logs').glob('*.stderr.log')))
        request = self.launch(restart=True)
        self.assertEqual(request.wait(timeout=10), 0)
        third_pid = wait_for(lambda: (data := self.health())['pid'] != second_pid and data)['pid']
        self.assertNotEqual(second_pid, third_pid)
        self.assertIsNone(supervisor.poll())
        # Losing the supervisor alone must leave the report server running.
        supervisor.terminate(); supervisor.wait(timeout=10)
        self.assertEqual(self.health()['pid'], third_pid)
        self.launch()
        wait_for(lambda: f'Attached to healthy server PID {third_pid}' in self.log())
        self.assertEqual(self.health()['pid'], third_pid)

    def test_foreign_listener_is_never_stopped(self):
        (self.root / 'foreign').touch()
        env = dict(os.environ, MENU_PROJECT_ROOT=str(self.root), MENU_API_PORT=str(self.port))
        foreign = subprocess.Popen([os.sys.executable, '-m', 'fake_server'], cwd=self.root, env=env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        self.processes.append(foreign)
        first_pid = wait_for(self.health)['pid']
        self.launch(restart=True)
        wait_for(lambda: 'leaving it untouched' in self.log())
        self.assertEqual(self.health()['pid'], first_pid)
        self.assertIsNone(foreign.poll())

    def test_batch_launchers_with_chinese_path_and_spaces(self):
        package = self.root / 'meal_planner'
        package.mkdir()
        (package / '__init__.py').touch()
        (package / 'app.py').write_text(FAKE_SERVER, encoding='utf-8')
        for name in ('start_server_hidden.ps1', 'restart_server.bat', 'start_website.bat'):
            shutil.copyfile(SCRIPT.parent / name, self.root / name)
        # Exercise the actual readiness command without opening a test browser tab.
        website = self.root / 'start_website.bat'
        text = website.read_text()
        website.write_text('\n'.join(line for line in text.splitlines() if not line.startswith('start "" ')))
        env = dict(os.environ, MENU_API_PORT=str(self.port))
        try:
            opened = subprocess.run(['cmd.exe', '/c', str(website)], env=env, cwd=self.root,
                                    capture_output=True, timeout=30, creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(opened.returncode, 0, opened.stderr)
            first_pid = wait_for(self.health)['pid']
            restarted = subprocess.run(['cmd.exe', '/c', str(self.root / 'restart_server.bat')],
                                       env=env, cwd=self.root, capture_output=True, timeout=10,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
            self.assertEqual(restarted.returncode, 0, restarted.stderr)
            wait_for(lambda: (data := self.health())['pid'] != first_pid and data)
        finally:
            log = self.log()
            import re
            self.supervisor_pids.update(int(pid) for pid in re.findall(r'Supervisor PID (\d+) started', log))


if __name__ == '__main__':
    unittest.main()
