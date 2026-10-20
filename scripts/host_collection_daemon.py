"""Per-user daily host collector; no administrator privileges or service restart."""
import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
def read(path):
    try:return json.loads(path.read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}

def due(now,at,status,history):
    today=now.date().isoformat()
    finished=status.get('finished_at',0)
    if status.get('state') in {'success','partial'} and datetime.fromtimestamp(finished).date()==now.date():return False
    if status.get('state')=='processing' and now.timestamp()-status.get('started_at',0)<1800:return False
    if now.strftime('%H:%M')<at:return False
    if history.get('day')==today and (history.get('attempts',0)>=3 or now.timestamp()-history.get('last_attempt',0)<900):return False
    return True

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--state-dir',type=Path,default=ROOT/'.install/host-discovery');parser.add_argument('--at',default='09:10')
    args=parser.parse_args();directory=args.state_dir.resolve();directory.mkdir(parents=True,exist_ok=True)
    import msvcrt
    with (directory/'daemon.lock').open('a+b') as lock:
        lock.seek(0);lock.write(b'1');lock.flush();lock.seek(0)
        try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        except OSError:return
        history_path=directory/'schedule-state.json'
        while True:
            now=datetime.now();status=read(directory/'status.json');history=read(history_path)
            if due(now,args.at,status,history):
                today=now.date().isoformat();history={'day':today,'attempts':history.get('attempts',0)+1 if history.get('day')==today else 1,'last_attempt':now.timestamp()}
                history_path.write_text(json.dumps(history),encoding='utf-8')
                with (directory/('worker-'+today+'.log')).open('ab') as log:
                    try:
                        python=ROOT/'.venv/Scripts/python.exe'
                        subprocess.run([str(python),str(ROOT/'scripts/run_host_collection.py'),'--state-dir',str(directory),'--schedule','每日 '+args.at+'（主机当前用户后台）'],
                                       cwd=ROOT,stdout=log,stderr=log,timeout=1800,creationflags=subprocess.CREATE_NO_WINDOW)
                    except (OSError,subprocess.TimeoutExpired) as error:log.write((str(error)+'\n').encode())
            heartbeat={'pid':os.getpid(),'checked_at':time.time(),'daily_at':args.at,'mode':'current_user_background','requires':'Windows user session and Docker running'}
            (directory/'daemon-status.json').write_text(json.dumps(heartbeat),encoding='utf-8')
            time.sleep(30)

if __name__=='__main__':main()
