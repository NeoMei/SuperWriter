"""Synthetic acceptance driver. Uses the installed public JSON-file CLI only."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import sys

class Demo:
    def __init__(self, skill: Path, root: Path):
        self.skill = skill.resolve()
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.evidence = self.root / 'evidence'
        self.evidence.mkdir(exist_ok=True)
        self.sequence = 0
        self.history = []

    def cli(self, *args, expect_ok=True):
        run = subprocess.run([sys.executable, str(self.skill / 'scripts/collaboration_state.py'), *args,
                              '--project', str(self.root)], capture_output=True, text=True)
        if expect_ok and run.returncode:
            raise RuntimeError(run.stderr)
        if not expect_ok and run.returncode == 0:
            raise AssertionError('negative scenario unexpectedly succeeded')
        return json.loads(run.stdout) if expect_ok else run.stderr.strip()

    def initialize(self):
        self.state = self.cli('init', '--project-id', 'synthetic-collaborative-writing')
        self.checkpoint('initial')

    def checkpoint(self, label):
        self.state = self.cli('show')
        path = self.evidence / f'{len(self.history):02d}-{label}.json'
        path.write_text(json.dumps(self.state, ensure_ascii=False, indent=2) + '\n')
        self.history.append({'label': label, 'revision': self.state['revision'], 'state': str(path.relative_to(self.root))})
        (self.evidence / 'history.json').write_text(json.dumps(self.history, ensure_ascii=False, indent=2)+'\n')

    def event(self, kind, object_id=None, payload=None, text='synthetic-test explicit action', channel=None, expect_ok=True):
        self.state = self.cli('show')
        self.sequence += 1
        obj = self.state['objects'].get(object_id) if object_id else None
        if kind == 'put_object':
            obj = payload['object']
        event = {'id': f'synthetic-{self.sequence:03d}-{kind}', 'kind': kind,
                 'object_id': object_id, 'version': obj['version'] if obj else None,
                 'sha256': obj['sha256'] if obj else None,
                 'channel': channel or ('chat' if kind in {'approve','request_changes','record_preference'} else 'agent'),
                 'evidence': {'reference': f'synthetic-test:{self.sequence}', 'text': text},
                 'payload': payload or {}}
        file = self.evidence / f'event-{self.sequence:03d}.json'
        file.write_text(json.dumps(event, ensure_ascii=False, indent=2)+'\n')
        result = self.cli('apply','--event-file',str(file),'--expected-revision',str(self.state['revision']),expect_ok=expect_ok)
        if expect_ok:
            self.state = result
        else:
            (self.evidence / f'rejected-{self.sequence:03d}.txt').write_text(result+'\n')
        return result

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
        return path

    def put(self, identifier, kind, relative, content=None, dependencies=(), metadata=None):
        self.state = self.cli('show')
        previous = self.state['objects'].get(identifier)
        path = self.write(relative, content) if content is not None else self.root / relative
        obj = {'id':identifier, 'kind':kind, 'path':relative,
               'version': previous['version']+1 if previous else 1,
               'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
               'dependencies':{dep:self.state['objects'][dep]['version'] for dep in dependencies},
               'status':'draft','metadata':metadata or {}}
        self.event('put_object',identifier,{'object':obj})
        return obj

    def submit(self, identifier):
        return self.event('submit_review',identifier)

    def approve(self, identifier, text, payload=None):
        return self.event('approve',identifier,payload,text='synthetic-test '+text)

    def revise(self, identifier, text):
        return self.event(
            'request_changes', identifier, {'comment': text},
            text='synthetic-test ' + text,
        )

    def advance(self, stage):
        return self.event('advance',payload={'stage':stage})
