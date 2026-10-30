"""真实 API 集成测试；使用独立临时数据库，绝不访问用户的正式数据。"""
import concurrent.futures
import os
from pathlib import Path
import tempfile
import time
import unittest

TEMP = tempfile.TemporaryDirectory()
os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(TEMP.name) / 'test.db')
os.environ['DATA_DIR'] = TEMP.name
os.environ['ADMIN_USERNAME'] = 'admin'
os.environ['ADMIN_PASSWORD'] = 'test-admin-password-2026'
os.environ['COOKIE_SECURE'] = 'false'
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from app.database import Attempt, Base, Course, LoginSession, Progress, SessionLocal, User
from app.main import app, bootstrap, login_failures, merged_segments
from app.security import verify_password

HEADERS = {'X-Requested-With': 'training-web'}
PASSWORD = 'employee-password-2026'
VIDEO = b'\x00\x00\x00\x18ftypmp42' + b'\0' * 100


class TrainingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        bootstrap()

    def setUp(self):
        login_failures.clear()
        with SessionLocal() as db:
            for table in reversed(Base.metadata.sorted_tables):
                db.execute(delete(table))
            db.commit()
        self.admin = TestClient(app, headers=HEADERS)
        self.admin.__enter__()
        response = self.admin.post('/api/login', json={'username':'admin','password':os.environ['ADMIN_PASSWORD']})
        self.assertEqual(response.status_code, 200)
        self.employee = TestClient(app, headers=HEADERS)
        response = self.admin.post('/api/admin/users', json={'username':'employee','name':'张三','password':PASSWORD})
        self.assertEqual(response.status_code,201)
        self.uid=response.json()['id']
        self.assertEqual(self.employee.post('/api/login',json={'username':'employee','password':PASSWORD}).status_code,200)

    def tearDown(self):
        self.employee.close()
        self.admin.__exit__(None,None,None)

    def make_course(self, publish=True):
        response=self.admin.post('/api/admin/courses',json={'title':'安全培训','description':'岗位学习','duration':10,'required_percent':90,'pass_score':60,'max_attempts':2,'exam_minutes':1})
        self.assertEqual(response.status_code,201)
        cid=response.json()['id']
        self.assertEqual(self.admin.post(f'/api/admin/courses/{cid}/video',files={'file':('lesson.mp4',VIDEO,'video/mp4')}).status_code,200)
        self.assertEqual(self.admin.post(f'/api/admin/courses/{cid}/questions',json={'text':'哪项是正确操作？','options':['正确','错误'],'answer':0}).status_code,201)
        if publish:self.assertEqual(self.admin.patch(f'/api/admin/courses/{cid}',json={'published':True}).status_code,200)
        return cid

    def start_watch(self,cid,position=0):
        r=self.employee.post(f'/api/courses/{cid}/watch/start',json={'position':position})
        self.assertEqual(r.status_code,200)
        return r.json()['token']

    def heartbeat(self,cid,token,position,elapsed=5,playing=True):
        # 推进服务器计时基准，测试不必真的等待数十秒。
        with SessionLocal() as db:
            p=db.scalar(select(Progress).where(Progress.user_id==self.uid,Progress.course_id==cid))
            p.last_seen=time.time()-elapsed;db.commit()
        return self.employee.post(f'/api/courses/{cid}/watch/heartbeat',json={'token':token,'position':position,'playing':playing})

    def finish_video(self,cid):
        token=self.start_watch(cid)
        for pos in (5,10):
            response=self.heartbeat(cid,token,pos)
            self.assertEqual(response.status_code,200)
        self.assertTrue(response.json()['eligible'])

    def test_health_home_and_login_cookie(self):
        self.assertEqual(self.admin.get('/api/health').json()['status'],'ok')
        self.assertIn('学程',self.admin.get('/').text)
        self.assertIn('HttpOnly',self.admin.post('/api/login',json={'username':'admin','password':os.environ['ADMIN_PASSWORD']}).headers['set-cookie'])
        with SessionLocal() as db:
            user=db.get(User,self.uid)
            self.assertNotEqual(user.password_hash,PASSWORD)
            self.assertTrue(verify_password(PASSWORD,user.password_hash))

    def test_permissions_and_csrf(self):
        self.assertEqual(TestClient(app).get('/api/me').status_code,401)
        for path in ('/api/admin/users','/api/admin/reports','/api/admin/reports.csv'):
            self.assertEqual(self.employee.get(path).status_code,403)
        self.assertEqual(self.employee.post('/api/admin/courses',json={'title':'bad'}).status_code,403)
        self.assertEqual(TestClient(app).post('/api/login',json={}).status_code,403)
        self.assertEqual(self.employee.post('/api/logout',json={},headers={'sec-fetch-site':'cross-site'}).status_code,403)

    def test_drafts_and_video_protection(self):
        cid=self.make_course(False)
        self.assertEqual(self.employee.get('/api/courses').json(),[])
        self.assertEqual(self.employee.get(f'/media/{cid}').status_code,404)
        self.admin.patch(f'/api/admin/courses/{cid}',json={'published':True})
        self.assertEqual(TestClient(app).get(f'/media/{cid}').status_code,401)
        response=self.employee.get(f'/media/{cid}',headers={'Range':'bytes=0-9'})
        self.assertEqual(response.status_code,206)
        self.assertEqual(response.content,VIDEO[:10])
        self.assertEqual(self.admin.post(f'/api/admin/courses/{cid}/video',files={'file':('x.mp4',VIDEO)}).status_code,409)

    def test_watch_seek_pause_stale_and_dedup(self):
        cid=self.make_course();token=self.start_watch(cid)
        self.assertEqual(self.heartbeat(cid,token,9,elapsed=1).json()['watched'],0)
        self.assertEqual(self.heartbeat(cid,token,10,playing=False).json()['watched'],0)
        self.assertEqual(self.heartbeat(cid,token,5,elapsed=20).json()['watched'],0)
        token=self.start_watch(cid)
        first=self.heartbeat(cid,token,5).json()['watched']
        self.assertAlmostEqual(first,5,places=1)
        self.heartbeat(cid,token,0,playing=False)
        self.assertAlmostEqual(self.heartbeat(cid,token,5).json()['watched'],5,places=1)
        new=self.start_watch(cid,5)
        self.assertEqual(self.heartbeat(cid,token,10).status_code,409)
        self.assertTrue(self.heartbeat(cid,new,10).json()['eligible'])
        self.assertEqual(self.employee.post(f'/api/courses/{cid}/watch/start',json={'position':-1}).status_code,422)
        self.assertEqual(merged_segments([[0,5],[3,8],[9,10]]),[[0,8],[9,10]])

    def test_end_to_end_scoring_and_reports(self):
        cid=self.make_course()
        self.assertEqual(self.employee.post(f'/api/courses/{cid}/exam').status_code,403)
        self.finish_video(cid)
        response=self.employee.post(f'/api/courses/{cid}/exam');self.assertEqual(response.status_code,200)
        exam=response.json();self.assertNotIn('answer',exam['questions'][0])
        self.assertEqual(self.employee.post(f'/api/courses/{cid}/exam').json()['id'],exam['id'])
        qid=exam['questions'][0]['id']
        score=self.employee.post(f"/api/attempts/{exam['id']}/submit",json={'answers':{str(qid):0},'score':0}).json()
        self.assertEqual(score['score'],100);self.assertTrue(score['passed'])
        again=self.employee.post(f"/api/attempts/{exam['id']}/submit",json={'answers':{str(qid):1}}).json()
        self.assertEqual(again['score'],100)
        rows=self.admin.get('/api/admin/reports').json();self.assertEqual(rows[0]['score'],100)
        self.assertAlmostEqual(rows[0]['watched_seconds'],10,places=1)
        self.assertIn('张三',self.admin.get('/api/admin/reports.csv').content.decode('utf-8-sig'))

    def test_exam_validation_ownership_timeout_and_limit(self):
        cid=self.make_course();self.finish_video(cid)
        exam=self.employee.post(f'/api/courses/{cid}/exam').json();aid=exam['id']
        self.assertEqual(self.admin.post(f'/api/attempts/{aid}/submit',json={'answers':{}}).status_code,404)
        self.assertEqual(self.employee.post(f'/api/attempts/{aid}/submit',json={'answers':{'999':0}}).status_code,400)
        self.assertEqual(self.employee.post(f'/api/attempts/{aid}/submit',json={'answers':{str(exam['questions'][0]['id']):7}}).status_code,400)
        with SessionLocal() as db:
            db.get(Attempt,aid).deadline=time.time()-1;db.commit()
        result=self.employee.post(f'/api/attempts/{aid}/submit',json={'answers':{str(exam['questions'][0]['id']):0}}).json()
        self.assertEqual(result['score'],0)
        second=self.employee.post(f'/api/courses/{cid}/exam').json()
        self.employee.post(f"/api/attempts/{second['id']}/submit",json={'answers':{}})
        self.assertEqual(self.employee.post(f'/api/courses/{cid}/exam').status_code,409)

    def test_expired_unsubmitted_attempt_reports(self):
        cid=self.make_course();self.finish_video(cid)
        aid=self.employee.post(f'/api/courses/{cid}/exam').json()['id']
        with SessionLocal() as db:
            db.get(Attempt,aid).deadline=time.time()-1;db.commit()
        report=self.admin.get('/api/admin/reports').json()[0]
        self.assertEqual((report['status'],report['score']),('已超时',0))
        self.assertNotEqual(self.employee.post(f'/api/courses/{cid}/exam').json()['id'],aid)

    def test_password_reset_revoke_and_disable(self):
        self.assertEqual(self.admin.post(f'/api/admin/users/{self.uid}/password',json={'password':'new-password-2026'}).status_code,200)
        self.assertEqual(self.employee.get('/api/me').status_code,401)
        self.assertEqual(self.employee.post('/api/login',json={'username':'employee','password':PASSWORD}).status_code,401)
        self.assertEqual(self.employee.post('/api/login',json={'username':'employee','password':'new-password-2026'}).status_code,200)
        self.admin.patch(f'/api/admin/users/{self.uid}',json={'active':False})
        self.assertEqual(self.employee.get('/api/me').status_code,401)
        self.assertEqual(self.employee.post('/api/login',json={'username':'employee','password':'new-password-2026'}).status_code,401)

    def test_change_password_and_logout(self):
        self.assertEqual(self.employee.post('/api/password',json={'old_password':'bad','password':'new-password-2026'}).status_code,400)
        self.assertEqual(self.employee.post('/api/password',json={'old_password':PASSWORD,'password':'new-password-2026'}).status_code,200)
        self.assertEqual(self.employee.get('/api/me').status_code,401)
        self.employee.post('/api/login',json={'username':'employee','password':'new-password-2026'})
        self.employee.post('/api/logout')
        self.assertEqual(self.employee.get('/api/me').status_code,401)

    def test_invalid_inputs_and_uploads(self):
        self.assertEqual(self.admin.post('/api/admin/users',json={'username':'xx','name':'a','password':'short'}).status_code,422)
        self.assertEqual(self.admin.post('/api/admin/users',json={'username':'employee','name':'a','password':PASSWORD}).status_code,409)
        self.assertEqual(self.admin.post('/api/admin/courses',json={'title':'a','duration':0}).status_code,422)
        cid=self.admin.post('/api/admin/courses',json={'title':'a','duration':10}).json()['id']
        self.assertEqual(self.admin.patch(f'/api/admin/courses/{cid}',json={'published':True}).status_code,400)
        for filename,content in [('x.mp4',b'fake'),('x.html',VIDEO)]:
            self.assertEqual(self.admin.post(f'/api/admin/courses/{cid}/video',files={'file':(filename,content)}).status_code,400)
        self.assertEqual(self.admin.post(f'/api/admin/courses/{cid}/questions',json={'text':'a','options':['a','b'],'answer':2}).status_code,422)

    def test_rate_limit_and_csv_formula_safety(self):
        for _ in range(10):
            self.assertEqual(self.employee.post('/api/login',json={'username':'unknown','password':'wrong'}).status_code,401)
        self.assertEqual(self.employee.post('/api/login',json={'username':'unknown','password':'wrong'}).status_code,429)
        self.make_course()
        with SessionLocal() as db:
            db.get(User,self.uid).name='=HYPERLINK("bad")';db.commit()
        self.assertIn("'=HYPERLINK",self.admin.get('/api/admin/reports.csv').content.decode('utf-8-sig'))

    def test_concurrent_exam_start_and_submit(self):
        cid=self.make_course();self.finish_video(cid)
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda _:self.employee.post(f'/api/courses/{cid}/exam').json(),range(2)))
        self.assertEqual(results[0]['id'],results[1]['id'])
        aid=results[0]['id'];qid=str(results[0]['questions'][0]['id'])
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda answer:self.employee.post(f'/api/attempts/{aid}/submit',json={'answers':{qid:answer}}).json(),[0,1]))
        self.assertEqual(results[0]['score'],results[1]['score'])


if __name__=='__main__':
    unittest.main()
