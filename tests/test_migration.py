import hashlib,json,sqlite3,tempfile,unittest
from pathlib import Path
from yutong_teams.config import Config
from yutong_teams.control import Coordinator


class MigrationTest(unittest.TestCase):
    def test_old_db_preserved_one_time_and_no_invented_receipts(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);config=Config(root)
            group=dict(id='old',name='old team',workspace=temp,leader='claude',review=True,max_turns=12,created='2026-01-01T00:00:00Z',members=['claude'],goal='preserve',
                messages=[dict(id='m',author='user',text='history',targets=['claude'],time='2026-01-01T00:00:00Z')],
                tasks=[dict(id='t',title='unfinished',agent_id='claude',description='',status='running',result='',depends_on=[],created='2026-01-01T00:00:00Z')])
            old=root/'teams.db';db=sqlite3.connect(str(old));db.execute('CREATE TABLE state(id INTEGER PRIMARY KEY,body TEXT)');db.execute('INSERT INTO state VALUES(1,?)',(json.dumps({'groups':[group]}),));db.commit();db.close()
            before=hashlib.sha256(old.read_bytes()).hexdigest()
            c=Coordinator(config,start=False)
            self.assertTrue(c.repo.require('group','old')['paused']);self.assertEqual('interrupted',c.repo.require('task','t')['status'])
            self.assertEqual('human',c.repo.require('message','m')['author']);self.assertEqual([],c.repo.list('delivery'))
            rev=c.repo.revision();c.close()
            c=Coordinator(config,start=False);self.assertEqual(rev,c.repo.revision());c.close()
            self.assertEqual(before,hashlib.sha256(old.read_bytes()).hexdigest())


if __name__=='__main__':unittest.main()
