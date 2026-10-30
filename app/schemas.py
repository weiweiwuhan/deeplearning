"""限制请求大小与取值范围；考试答案只接收选项下标，不接收客户端分数。"""
from typing import Annotated
from pydantic import BaseModel, Field, StringConstraints, model_validator

Username = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r'^[a-zA-Z0-9_.-]{3,64}$')]
Password = Annotated[str, StringConstraints(min_length=12, max_length=128)]


class LoginInput(BaseModel):
    username: Username
    password: str = Field(min_length=1, max_length=128)


class UserInput(BaseModel):
    username: Username
    name: str = Field(min_length=1, max_length=100)
    password: Password


class PasswordInput(BaseModel):
    password: Password


class ChangePassword(PasswordInput):
    old_password: str = Field(min_length=1, max_length=128)


class CourseInput(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=5000)
    duration: float = Field(gt=0, le=86400, allow_inf_nan=False)
    required_percent: int = Field(default=90, ge=1, le=100)
    pass_score: int = Field(default=60, ge=1, le=100)
    max_attempts: int = Field(default=3, ge=1, le=100)
    exam_minutes: int = Field(default=30, ge=1, le=480)


class PublishInput(BaseModel):
    published: bool


class ActiveInput(BaseModel):
    active: bool


class QuestionInput(BaseModel):
    text: str = Field(min_length=1, max_length=3000)
    options: list[Annotated[str, StringConstraints(min_length=1, max_length=1000)]] = Field(min_length=2, max_length=8)
    answer: int = Field(ge=0, le=7)

    @model_validator(mode='after')
    def check_answer(self):
        if self.answer >= len(self.options):
            raise ValueError('正确答案必须对应已有选项')
        return self


class WatchStart(BaseModel):
    position: float = Field(default=0, ge=0, allow_inf_nan=False)


class Heartbeat(WatchStart):
    token: str = Field(min_length=1, max_length=100)
    playing: bool


class AnswersInput(BaseModel):
    answers: dict[str, Annotated[int, Field(ge=0, le=7, strict=True)]] = Field(max_length=200)
