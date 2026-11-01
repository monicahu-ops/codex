import io
import tempfile
import unittest
import zipfile
from pathlib import Path

import app as module


class WorkRecordTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old_db, self.old_backups = module.DB_PATH, module.BACKUP_DIR
        module.DB_PATH = Path(self.temp.name) / "worklog.db"
        module.BACKUP_DIR = Path(self.temp.name) / "backups"
        module.init_db()
        self.client = module.app.test_client()

    def tearDown(self):
        module.DB_PATH, module.BACKUP_DIR = self.old_db, self.old_backups
        self.temp.cleanup()

    def test_todo_dates_and_project(self):
        self.client.post('/api/todos', json={'title':'本年','due_on':'2026-05-01','tags':'项目A'})
        self.client.post('/api/todos', json={'title':'无日期','tags':'项目A'})
        self.client.post('/api/todos', json={'title':'下年','due_on':'2027-01-01','tags':'项目A'})
        self.client.post('/api/todos', json={'title':'其他项目','tags':'项目B'})
        response = self.client.get('/api/todos', query_string={'due_from':'2026-01-01','due_to':'2026-12-31','include_undated':'1','project':'项目A'})
        self.assertEqual({x['title'] for x in response.json}, {'本年','无日期'})

    def test_summaries_change_and_export(self):
        log = self.client.post('/api/logs', json={'title':'进展','logged_on':'2026-05-01','tags':'项目A,项目B','work_type':'开发'}).json
        report = self.client.get('/api/reports/month/2026-05').json
        self.assertEqual(report['log_count'], 1)
        self.assertEqual(len(report['projects']), 2)
        group = next(x for x in report['projects'] if x['name']=='项目A')
        self.client.put('/api/summaries', json={'kind':'month','period':'2026-05','project':'项目A','content':'人工总结','fingerprint':group['fingerprint']})
        self.client.put('/api/logs/'+str(log['id']), json={'title':'变更','logged_on':'2026-05-01','tags':'项目A,项目B','work_type':'开发'})
        group = next(x for x in self.client.get('/api/reports/month/2026-05').json['projects'] if x['name']=='项目A')
        self.assertTrue(group['changed'])
        self.assertEqual(group['summary'], '人工总结')
        response = self.client.post('/api/report-export', json={'kind':'month','period':'2026-05','format':'docx'})
        with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
            self.assertIn('人工总结', archive.read('word/document.xml').decode())

    def test_backup_restore(self):
        self.client.post('/api/logs', json={'title':'原始'})
        backup = self.client.get('/api/backup').data
        self.client.post('/api/logs', json={'title':'之后'})
        result = self.client.post('/api/restore', data={'backup':(io.BytesIO(backup),'backup.db')})
        self.assertEqual(result.status_code, 200)
        self.assertEqual([x['title'] for x in self.client.get('/api/logs').json], ['原始'])
        self.assertEqual(len(list(module.BACKUP_DIR.glob('before-restore-*.db'))), 1)


if __name__ == '__main__':
    unittest.main()
