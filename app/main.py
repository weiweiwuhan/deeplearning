"""同源网页与培训 API。所有权限、观看进度和考试评分均在服务器端校验。"""
import csv
import io
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config

from fastapi import Depends, FastAPI, HTTPException, Request, Response, UploadFile, File
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .database import Attempt, Course, LoginSession, Progress, Question, SessionLocal, User, engine, settings
from .schemas import ActiveInput, AnswersInput, ChangePassword, CourseInput, Heartbeat, LoginInput, PasswordInput, PublishInput, QuestionInput, UserInput, WatchStart
from .security import hash_password, token_hash, verify_password

STATIC = Path(__file__).parent / 'static'
VIDEOS = Path(settings.data_dir).resolve() / 'videos'
COOKIE = 'training_session'
# 单进程内登录限流；多副本部署需在反向代理统一限流。
login_failures = defaultdict(deque)
login_lock = threading.Lock()
DUMMY_HASH = hash_password(secrets.token_urlsafe(24))


def bootstrap():
    """启动时升级数据库到仓库中已有的迁移版本，不在运行时自动生成迁移。"""
    project = Path(__file__).resolve().parent.parent
    config = Config(str(project / 'alembic.ini'))
    config.set_main_option('script_location', str(project / 'alembic'))
    command.upgrade(config, 'head')
    VIDEOS.mkdir(parents=True, exist_ok=True)
    with SessionLocal() as db:
        if not db.scalar(select(User.id).where(User.is_admin.is_(True))):
            if not re.fullmatch(r'[a-zA-Z0-9_.-]{3,64}', settings.admin_username):
                raise RuntimeError('ADMIN_USERNAME 需为 3–64 位字母、数字或 _. -')
            if not 12 <= len(settings.admin_password) <= 128 or settings.admin_password.startswith('CHANGE_'):
                raise RuntimeError('首次启动前请在 .env 设置12–128 位的独立 ADMIN_PASSWORD')
            db.add(User(username=settings.admin_username, name='管理员', password_hash=hash_password(settings.admin_password), is_admin=True))
            db.commit()


@asynccontextmanager
async def lifespan(_):
    bootstrap()
    yield


app = FastAPI(title='员工培训与考试', version='1.0.0', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=STATIC), name='static')


@app.middleware('http')
async def browser_security(request: Request, call_next):
    # 浏览器跨站表单无法设置此自定义头，结合 SameSite cookie 防止 CSRF。
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        if request.headers.get('X-Requested-With') != 'training-web' or request.headers.get('sec-fetch-site') == 'cross-site':
            return Response('禁止跨站写入，请使用本站网页', status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'self'"
    if request.url.path.startswith(('/api/', '/media/')):
        response.headers['Cache-Control'] = 'no-store'
    return response


def get_db():
    with SessionLocal() as db:
        yield db


def current_user(request: Request, db: Session = Depends(get_db)):
    session = db.get(LoginSession, token_hash(request.cookies.get(COOKIE, '')))
    user = db.get(User, session.user_id) if session and session.expires > time.time() else None
    if not user or not user.active:
        raise HTTPException(401, '请先登录')
    return user


def admin(user: User = Depends(current_user)):
    if not user.is_admin:
        raise HTTPException(403, '仅管理员可执行此操作')
    return user


def user_data(user):
    return {'id': user.id, 'username': user.username, 'name': user.name, 'is_admin': user.is_admin, 'active': user.active}


def course_or_404(db, course_id, user):
    course = db.get(Course, course_id)
    if not course or (not course.published and not user.is_admin):
        raise HTTPException(404, '课程不存在或尚未发布')
    return course


def progress_for(db, user_id, course_id):
    return db.scalar(select(Progress).where(Progress.user_id == user_id, Progress.course_id == course_id))


def lock_user(db, user_id):
    # PostgreSQL 使用行锁；SQLite 用 BEGIN IMMEDIATE 串行化写入。
    # 所有进度/考试写入都先锁用户，避免重复开考、并发覆盖观看区间。
    if engine.dialect.name == 'sqlite':
        db.rollback()
        db.execute(text('BEGIN IMMEDIATE'))
    else:
        db.scalar(select(User).where(User.id == user_id).with_for_update())


def course_data(db, course, user):
    progress = progress_for(db, user.id, course.id)
    attempts = db.scalars(select(Attempt).where(Attempt.user_id == user.id, Attempt.course_id == course.id).order_by(Attempt.id)).all()
    watched = min(progress.watched, course.duration) if progress else 0
    return {'id': course.id, 'title': course.title, 'description': course.description, 'duration': course.duration,
            'required_percent': course.required_percent, 'pass_score': course.pass_score, 'max_attempts': course.max_attempts,
            'exam_minutes': course.exam_minutes, 'published': course.published, 'has_video': bool(course.video_file),
            'question_count': db.scalar(select(func.count()).select_from(Question).where(Question.course_id == course.id)),
            'watched': watched, 'percent': round(watched / course.duration * 100, 2), 'position': progress.position if progress else 0,
            'eligible': watched + 0.01 >= course.duration * course.required_percent / 100,
            'attempts': [attempt_data(a) for a in attempts]}


def attempt_data(attempt):
    return {'id': attempt.id, 'course_id': attempt.course_id, 'started_at': attempt.started_at, 'deadline': attempt.deadline,
            'submitted_at': attempt.submitted_at, 'score': attempt.score, 'passed': attempt.passed, 'pass_score': attempt.pass_score}


@app.get('/', include_in_schema=False)
def index():
    return FileResponse(STATIC / 'index.html')


@app.get('/api/health')
def health(db: Session = Depends(get_db)):
    try:
        db.execute(text('SELECT 1'))
        return {'status': 'ok', 'database': 'up'}
    except Exception:
        raise HTTPException(503, '数据库不可用')


@app.post('/api/login')
def login(body: LoginInput, request: Request, response: Response, db: Session = Depends(get_db)):
    now = time.time()
    keys = [('username', body.username), ('ip', request.client.host if request.client else 'unknown')]
    with login_lock:
        # 丢弃过期键，限制长期进程内存；IP 限流用于限制随机用户名攻击。
        for key in list(login_failures):
            while login_failures[key] and login_failures[key][0] < now - 600:
                login_failures[key].popleft()
            if not login_failures[key]:
                del login_failures[key]
        if len(login_failures) > 10000 or any(len(login_failures.get(key, ())) >= (10 if key[0] == 'username' else 40) for key in keys):
            raise HTTPException(429, '登录尝试过多，请 10 分钟后重试')
        # 先预留尝试次数，避免并发请求在密码校验期间绕过限流。
        for key in keys:
            login_failures[key].append(now)
    user = db.scalar(select(User).where(User.username == body.username))
    valid = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid or not user.active:
        raise HTTPException(401, '账号或密码错误，或账号已停用')
    with login_lock:
        login_failures.pop(keys[0], None)
    raw = secrets.token_urlsafe(32)
    db.execute(delete(LoginSession).where(LoginSession.expires < now))
    # 替换当前浏览器已有 cookie 时，同时撤销对应旧会话。
    db.execute(delete(LoginSession).where(LoginSession.token_hash == token_hash(request.cookies.get(COOKIE, ''))))
    db.add(LoginSession(token_hash=token_hash(raw), user_id=user.id, expires=now + settings.session_hours * 3600))
    db.commit()
    response.set_cookie(COOKIE, raw, httponly=True, secure=settings.cookie_secure, samesite='strict', max_age=settings.session_hours * 3600)
    return user_data(user)


@app.post('/api/logout')
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    db.execute(delete(LoginSession).where(LoginSession.token_hash == token_hash(request.cookies.get(COOKIE, ''))))
    db.commit()
    response.delete_cookie(COOKIE)
    return {'ok': True}


@app.get('/api/me')
def me(user: User = Depends(current_user)):
    return user_data(user)


@app.post('/api/password')
def change_password(body: ChangePassword, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(400, '原密码错误')
    user.password_hash = hash_password(body.password)
    db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    db.commit()
    return {'ok': True, 'message': '密码已修改，请重新登录'}


@app.get('/api/courses')
def courses(user: User = Depends(current_user), db: Session = Depends(get_db)):
    query = select(Course).order_by(Course.id.desc())
    if not user.is_admin:
        query = query.where(Course.published.is_(True))
    return [course_data(db, c, user) for c in db.scalars(query)]


@app.get('/api/courses/{course_id}')
def course_detail(course_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return course_data(db, course_or_404(db, course_id, user), user)


@app.get('/media/{course_id}')
def video(course_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    course = course_or_404(db, course_id, user)
    path = VIDEOS / course.video_file
    if not course.video_file or not path.is_file():
        raise HTTPException(404, '视频尚未上传')
    return FileResponse(path, media_type='video/mp4' if path.suffix == '.mp4' else 'video/webm')


@app.post('/api/courses/{course_id}/watch/start')
def watch_start(course_id: int, body: WatchStart, user: User = Depends(current_user), db: Session = Depends(get_db)):
    uid = user.id
    lock_user(db, uid)
    course = course_or_404(db, course_id, user)
    if body.position > course.duration:
        raise HTTPException(400, '播放位置超过视频时长')
    progress = progress_for(db, uid, course_id)
    if not progress:
        progress = Progress(user_id=uid, course_id=course_id, segments=[], watched=0)
        db.add(progress)
    token = secrets.token_urlsafe(24)
    progress.watch_token = token_hash(token)
    progress.position = body.position
    progress.last_seen = time.time()
    db.commit()
    return {'token': token}


def merged_segments(segments):
    result = []
    for start, end in sorted(segments):
        if end <= start:
            continue
        if result and start <= result[-1][1]:
            result[-1][1] = max(result[-1][1], end)
        else:
            result.append([start, end])
    return result


@app.post('/api/courses/{course_id}/watch/heartbeat')
def watch_heartbeat(course_id: int, body: Heartbeat, user: User = Depends(current_user), db: Session = Depends(get_db)):
    uid = user.id
    lock_user(db, uid)
    course = course_or_404(db, course_id, user)
    progress = progress_for(db, uid, course_id)
    if not progress or not secrets.compare_digest(progress.watch_token, token_hash(body.token)):
        raise HTTPException(409, '播放会话已被另一个窗口替换，请重新打开课程')
    if body.position > course.duration + 1:
        raise HTTPException(400, '播放位置超过课程设置时长，请联系管理员检查视频时长')
    now = time.time()
    elapsed = now - progress.last_seen
    position = min(body.position, course.duration)
    delta = position - progress.position
    # 正常网页每 5 秒上报；超过 15 秒、倒退或明显跳跃均不计时。
    # 即使允许网络抖动，累计秒数也不能超过服务器实际经过时间。
    if body.playing and 0 < elapsed <= 15 and 0 < delta <= elapsed + 1:
        end = min(position, progress.position + elapsed)
        progress.segments = merged_segments([*progress.segments, [progress.position, end]])
        progress.watched = min(course.duration, sum(b - a for a, b in progress.segments))
    progress.position = position
    progress.last_seen = now
    progress.updated_at = now
    db.commit()
    return {'watched': progress.watched, 'percent': round(progress.watched / course.duration * 100, 2),
            'eligible': progress.watched + 0.01 >= course.duration * course.required_percent / 100}


@app.post('/api/courses/{course_id}/exam')
def start_exam(course_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    uid = user.id
    lock_user(db, uid)
    course = course_or_404(db, course_id, user)
    progress = progress_for(db, uid, course_id)
    if not progress or progress.watched + 0.01 < course.duration * course.required_percent / 100:
        raise HTTPException(403, '请先达到课程要求的观看比例')
    attempts = db.scalars(select(Attempt).where(Attempt.user_id == uid, Attempt.course_id == course_id).order_by(Attempt.id)).all()
    now = time.time()
    for previous in attempts:
        if previous.submitted_at is None:
            if previous.deadline >= now:
                return exam_data(previous)
            # 过期且从未提交的考试按零分记录，并占用一次机会。
            previous.score, previous.passed, previous.submitted_at, previous.answers = 0, False, previous.deadline, {}
    if len(attempts) >= course.max_attempts:
        db.commit()
        raise HTTPException(409, '考试次数已用完，请联系管理员')
    questions = db.scalars(select(Question).where(Question.course_id == course_id).order_by(Question.id)).all()
    if not questions:
        raise HTTPException(400, '管理员尚未添加试题')
    attempt = Attempt(user_id=uid, course_id=course_id, started_at=now, deadline=now + course.exam_minutes * 60,
                      pass_score=course.pass_score, snapshot=[{'id': q.id, 'text': q.text, 'options': q.options, 'answer': q.answer} for q in questions])
    db.add(attempt)
    db.commit()
    return exam_data(attempt)


def exam_data(attempt):
    # 绝不将 snapshot 中的正确答案发送给学员。
    return {**attempt_data(attempt), 'server_time': time.time(), 'questions': [{k: q[k] for k in ('id', 'text', 'options')} for q in attempt.snapshot]}


@app.post('/api/attempts/{attempt_id}/submit')
def submit_exam(attempt_id: int, body: AnswersInput, user: User = Depends(current_user), db: Session = Depends(get_db)):
    uid = user.id
    lock_user(db, uid)
    attempt = db.get(Attempt, attempt_id)
    if not attempt or attempt.user_id != uid:
        raise HTTPException(404, '考试记录不存在')
    if attempt.submitted_at is not None:
        return attempt_data(attempt)
    questions = {str(q['id']): q for q in attempt.snapshot}
    if any(key not in questions or value >= len(questions[key]['options']) for key, value in body.answers.items()):
        raise HTTPException(400, '答案包含无效题目或选项')
    now = time.time()
    # 超时提交按零分；空题和未提交答案均视为错误。
    correct = sum(body.answers.get(str(q['id'])) == q['answer'] for q in attempt.snapshot) if now <= attempt.deadline else 0
    attempt.score = round(100 * correct / len(attempt.snapshot), 2)
    attempt.passed = attempt.score >= attempt.pass_score
    attempt.submitted_at = now
    attempt.answers = body.answers
    db.commit()
    return attempt_data(attempt)


@app.get('/api/admin/users', dependencies=[Depends(admin)])
def users(db: Session = Depends(get_db)):
    return [user_data(u) for u in db.scalars(select(User).order_by(User.id))]


@app.post('/api/admin/users', dependencies=[Depends(admin)], status_code=201)
def add_user(body: UserInput, db: Session = Depends(get_db)):
    user = User(username=body.username, name=body.name, password_hash=hash_password(body.password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, '账号已存在')
    return user_data(user)


@app.patch('/api/admin/users/{user_id}', dependencies=[Depends(admin)])
def set_active(user_id: int, body: ActiveInput, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, '账号不存在')
    if user.is_admin:
        raise HTTPException(400, '不能停用管理员')
    user.active = body.active
    db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    db.commit()
    return user_data(user)


@app.post('/api/admin/users/{user_id}/password', dependencies=[Depends(admin)])
def reset_password(user_id: int, body: PasswordInput, db: Session = Depends(get_db)):
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(404, '账号不存在')
    user.password_hash = hash_password(body.password)
    db.execute(delete(LoginSession).where(LoginSession.user_id == user.id))
    db.commit()
    return {'ok': True}


@app.post('/api/admin/courses', dependencies=[Depends(admin)], status_code=201)
def add_course(body: CourseInput, db: Session = Depends(get_db)):
    course = Course(**body.model_dump())
    db.add(course)
    db.commit()
    return {'id': course.id}


@app.post('/api/admin/courses/{course_id}/video', dependencies=[Depends(admin)])
def upload_video(course_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(404, '课程不存在')
    if course.published or course.video_file:
        raise HTTPException(409, '视频不可替换，请新建课程以保留已有观看记录的含义')
    suffix = Path(file.filename or '').suffix.lower()
    if suffix not in ('.mp4', '.webm'):
        raise HTTPException(400, '仅支持 MP4 或 WebM 视频')
    head = file.file.read(32)
    if not ((suffix == '.mp4' and head[4:8] == b'ftyp') or (suffix == '.webm' and head[:4] == b'\x1aE\xdf\xa3')):
        raise HTTPException(400, '视频文件头与格式不符')
    filename = secrets.token_hex(16) + suffix
    path = VIDEOS / filename
    size = 0
    try:
        with path.open('xb') as output:
            chunk = head
            while chunk:
                size += len(chunk)
                if size > settings.max_upload_mb * 1024 * 1024:
                    raise HTTPException(413, '视频超过上传大小限制')
                output.write(chunk)
                chunk = file.file.read(1024 * 1024)
        course.video_file = filename
        db.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        file.file.close()
    return {'ok': True, 'bytes': size}


@app.post('/api/admin/courses/{course_id}/questions', dependencies=[Depends(admin)], status_code=201)
def add_question(course_id: int, body: QuestionInput, db: Session = Depends(get_db)):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(404, '课程不存在')
    if course.published:
        raise HTTPException(409, '请先下架课程再添加题目；已开考的试卷不受影响')
    if db.scalar(select(func.count()).select_from(Question).where(Question.course_id == course_id)) >= 200:
        raise HTTPException(400, '每门课程最多 200 道题')
    question = Question(course_id=course_id, **body.model_dump())
    db.add(question)
    db.commit()
    return {'id': question.id}


@app.get('/api/admin/courses/{course_id}/questions', dependencies=[Depends(admin)])
def admin_questions(course_id: int, db: Session = Depends(get_db)):
    return [{'id': q.id, 'text': q.text, 'options': q.options, 'answer': q.answer} for q in db.scalars(select(Question).where(Question.course_id == course_id).order_by(Question.id))]


@app.patch('/api/admin/courses/{course_id}', dependencies=[Depends(admin)])
def publish_course(course_id: int, body: PublishInput, db: Session = Depends(get_db)):
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(404, '课程不存在')
    if body.published and (not course.video_file or not db.scalar(select(Question.id).where(Question.course_id == course_id))):
        raise HTTPException(400, '发布前必须上传视频并至少添加一道题')
    course.published = body.published
    db.commit()
    return {'ok': True}


def report_rows(db):
    """所有员工 × 所有课程均显示，包含从未学习的员工与每次考试。"""
    rows = []
    for user in db.scalars(select(User).where(User.is_admin.is_(False)).order_by(User.id)):
        for course in db.scalars(select(Course).order_by(Course.id)):
            progress = progress_for(db, user.id, course.id)
            attempts = db.scalars(select(Attempt).where(Attempt.user_id == user.id, Attempt.course_id == course.id).order_by(Attempt.id)).all()
            for attempt in attempts or [None]:
                expired = attempt and attempt.submitted_at is None and attempt.deadline < time.time()
                rows.append({'username': user.username, 'name': user.name, 'course': course.title,
                    'watched_seconds': round(progress.watched, 1) if progress else 0, 'duration_seconds': course.duration,
                    'percent': round(progress.watched / course.duration * 100, 2) if progress else 0,
                    'last_watched': progress.updated_at if progress else None,
                    'attempt_id': attempt.id if attempt else None,
                    'score': (0 if expired else attempt.score) if attempt else None,
                    'passed': (False if expired else attempt.passed) if attempt else None,
                    'status': ('已超时' if expired else '已交卷' if attempt.submitted_at else '考试中') if attempt else '未考试',
                    'submitted_at': (attempt.deadline if expired else attempt.submitted_at) if attempt else None})
    return rows


@app.get('/api/admin/reports', dependencies=[Depends(admin)])
def reports(db: Session = Depends(get_db)):
    return report_rows(db)


@app.get('/api/admin/reports.csv', dependencies=[Depends(admin)])
def export_report(db: Session = Depends(get_db)):
    output = io.StringIO(newline='')
    keys = ['username', 'name', 'course', 'watched_seconds', 'duration_seconds', 'percent', 'last_watched', 'attempt_id', 'score', 'passed', 'status', 'submitted_at']
    writer = csv.writer(output)
    writer.writerow(['账号', '姓名', '课程', '有效观看秒数', '课程秒数', '观看百分比', '最近观看UTC时间戳', '考试编号', '分数', '通过', '考试状态', '交卷UTC时间戳'])
    for row in report_rows(db):
        # 防止员工姓名、课程标题被表格软件解释成公式。
        values = [row[k] for k in keys]
        writer.writerow(["'" + v if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')) else v for v in values])
    return StreamingResponse(iter([output.getvalue().encode('utf-8-sig')]), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename="training-report.csv"'})
