"""配置、数据库连接及第一版数据模型；业务时间统一为 UTC Unix 秒。"""
from pathlib import Path
from sqlalchemy import Boolean, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = 'sqlite:///./data/training.db'
    data_dir: str = './data'
    admin_username: str = 'admin'
    admin_password: str = ''
    cookie_secure: bool = False
    session_hours: int = Field(default=12, ge=1, le=168)
    max_upload_mb: int = Field(default=500, ge=1, le=10240)


settings = Settings()
Path(settings.data_dir).mkdir(parents=True, exist_ok=True)
engine = create_engine(settings.database_url, connect_args={'check_same_thread': False} if settings.database_url.startswith('sqlite') else {}, pool_pre_ping=True)
if settings.database_url.startswith('sqlite'):
    @event.listens_for(engine, 'connect')
    def enable_foreign_keys(connection, _):
        connection.execute('PRAGMA foreign_keys=ON')
SessionLocal = sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(256))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class LoginSession(Base):
    __tablename__ = 'login_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    expires: Mapped[float] = mapped_column(Float)


class Course(Base):
    __tablename__ = 'courses'
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text, default='')
    video_file: Mapped[str] = mapped_column(String(100), default='')
    duration: Mapped[float] = mapped_column(Float)
    required_percent: Mapped[int] = mapped_column(Integer, default=90)
    pass_score: Mapped[int] = mapped_column(Integer, default=60)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    exam_minutes: Mapped[int] = mapped_column(Integer, default=30)
    published: Mapped[bool] = mapped_column(Boolean, default=False)


class Question(Base):
    __tablename__ = 'questions'
    id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey('courses.id'))
    text: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSON)
    answer: Mapped[int] = mapped_column(Integer)


class Progress(Base):
    __tablename__ = 'progress'
    __table_args__ = (UniqueConstraint('user_id', 'course_id'),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    course_id: Mapped[int] = mapped_column(ForeignKey('courses.id'))
    segments: Mapped[list] = mapped_column(JSON, default=list)
    watched: Mapped[float] = mapped_column(Float, default=0)
    position: Mapped[float] = mapped_column(Float, default=0)
    # 同一账号同一课程仅允许最后开启的播放会话上报。
    watch_token: Mapped[str] = mapped_column(String(64), default='')
    last_seen: Mapped[float] = mapped_column(Float, default=0)
    updated_at: Mapped[float] = mapped_column(Float, default=0)


class Attempt(Base):
    __tablename__ = 'attempts'
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    course_id: Mapped[int] = mapped_column(ForeignKey('courses.id'))
    started_at: Mapped[float] = mapped_column(Float)
    deadline: Mapped[float] = mapped_column(Float)
    # 开考时冻结题目和答案；后续新增题目不会改变本次考试。
    snapshot: Mapped[list] = mapped_column(JSON)
    pass_score: Mapped[int] = mapped_column(Integer)
    submitted_at: Mapped[float | None] = mapped_column(Float, nullable=True)
    answers: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    passed: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
