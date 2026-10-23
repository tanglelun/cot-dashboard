import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT=Path(__file__).resolve().parents[1]/'publish_data.sh'

class PublishingTests(unittest.TestCase):
    def test_rebase_and_autostash_without_configured_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            env={k:v for k,v in os.environ.items() if not k.startswith('GIT_')}
            env.update(GIT_CONFIG_GLOBAL=os.devnull,GIT_CONFIG_SYSTEM=os.devnull,GIT_TERMINAL_PROMPT='0')
            def git(*args,cwd=root):
                return subprocess.check_output(['git',*args],cwd=cwd,env=env,stderr=subprocess.PIPE,text=True)
            def commit(path,message):
                git('add','.',cwd=path)
                git('-c','user.name=Test','-c','user.email=test@example.com','commit','-m',message,cwd=path)
            git('init','--bare','origin.git')
            git('clone',str(root/'origin.git'),'a');a=root/'a'
            git('checkout','-b','main',cwd=a)
            (a/'scratch').write_text('base');commit(a,'base');git('push','-u','origin','main',cwd=a)
            git('clone','-b','main',str(root/'origin.git'),'b');b=root/'b'
            (a/'insight.json').write_text('fresh insight');commit(a,'insight');git('push',cwd=a)
            (b/'stocks.json').write_text('fresh stocks');commit(b,'stocks')
            (b/'scratch').write_text('uncommitted unrelated work')
            subprocess.run(['bash',str(SCRIPT)],cwd=b,env=env,check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            self.assertEqual((b/'insight.json').read_text(),'fresh insight')
            self.assertEqual((b/'scratch').read_text(),'uncommitted unrelated work')
            self.assertEqual(git('show','origin/main:stocks.json',cwd=b),'fresh stocks')
            self.assertEqual(git('log','-1','--format=%cn',cwd=b).strip(),'github-actions[bot]')
            # A failed publish can be recovered from the generated-commit bundle.
            git('bundle','create','update.bundle','HEAD^..HEAD',cwd=b)
            git('bundle','verify','update.bundle',cwd=b)

if __name__=='__main__':unittest.main()
