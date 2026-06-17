import sqlite3
import json
import uuid
from typing import List, Dict, Any, Optional

class WorkflowManager:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS workflows (
                    workflow_id TEXT PRIMARY KEY,
                    objective TEXT,
                    status TEXT
                )
            ''')
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS dag_nodes (
                    node_id TEXT PRIMARY KEY,
                    workflow_id TEXT,
                    name TEXT,
                    status TEXT,
                    dependencies TEXT, -- JSON list of node_ids
                    payload TEXT, -- JSON dict of inputs/outputs
                    FOREIGN KEY(workflow_id) REFERENCES workflows(workflow_id)
                )
            ''')
            conn.commit()

    def create_workflow(self, objective: str, nodes: List[Dict[str, Any]]) -> str:
        """
        Creates a workflow and its DAG nodes.
        nodes format: [{"name": "step1", "dependencies": [], "payload": {...}}, ...]
        """
        workflow_id = str(uuid.uuid4())
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('INSERT INTO workflows (workflow_id, objective, status) VALUES (?, ?, ?)',
                           (workflow_id, objective, 'RUNNING'))
            
            for node in nodes:
                node_id = str(uuid.uuid4())
                deps = json.dumps(node.get("dependencies", []))
                payload = json.dumps(node.get("payload", {}))
                cursor.execute('''
                    INSERT INTO dag_nodes (node_id, workflow_id, name, status, dependencies, payload)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (node_id, workflow_id, node["name"], 'PENDING', deps, payload))
            conn.commit()
        return workflow_id

    def get_next_runnable_node(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """
        Finds a PENDING node whose dependencies are all COMPLETED.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Fetch all nodes for this workflow
            cursor.execute('SELECT * FROM dag_nodes WHERE workflow_id = ?', (workflow_id,))
            nodes = cursor.fetchall()
            
            # Build status map
            status_map = {n['node_id']: n['status'] for n in nodes}
            
            for n in nodes:
                if n['status'] == 'PENDING':
                    deps = json.loads(n['dependencies'])
                    # Check if all dependencies are COMPLETED
                    if all(status_map.get(dep) == 'COMPLETED' for dep in deps):
                        return dict(n)
        return None

    def update_node_status(self, node_id: str, status: str, payload_update: Optional[Dict[str, Any]] = None):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            if payload_update is not None:
                # Fetch existing payload, merge
                cursor.execute('SELECT payload FROM dag_nodes WHERE node_id = ?', (node_id,))
                row = cursor.fetchone()
                if row:
                    payload = json.loads(row[0])
                    payload.update(payload_update)
                    cursor.execute('UPDATE dag_nodes SET status = ?, payload = ? WHERE node_id = ?',
                                   (status, json.dumps(payload), node_id))
            else:
                cursor.execute('UPDATE dag_nodes SET status = ? WHERE node_id = ?', (status, node_id))
            conn.commit()

    def mark_workflow_completed(self, workflow_id: str, status: str = 'COMPLETED'):
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('UPDATE workflows SET status = ? WHERE workflow_id = ?', (status, workflow_id))
            conn.commit()
