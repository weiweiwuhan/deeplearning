/* 同源网页客户端：负责展示和上报，权限、有效时长与分数以服务器结果为准。 */
"use strict";
const $ = (id) => document.getElementById(id);
let user = null,
  courseList = [],
  reportList = [],
  watch = null,
  watchTimer = null,
  examTimer = null;
let heartbeatQueue = Promise.resolve(),
  lessonGeneration = 0;
// 动态文本统一用 textContent 写入，避免把课程名、姓名或题目当作 HTML 执行。
function node(tag, text, cls) {
  const e = document.createElement(tag);
  if (text !== undefined) e.textContent = text;
  if (cls) e.className = cls;
  return e;
}
function notify(text) {
  $("notice").textContent = text;
  $("notice").hidden = !text;
}
function button(text, handler, cls = "secondary") {
  const e = node("button", text, cls);
  e.type = "button";
  e.onclick = () =>
    Promise.resolve(handler()).catch((err) => notify(err.message));
  return e;
}
// 统一携带防跨站写入请求头；会话失效时清空登录界面中的个人数据。
async function api(url, options = {}) {
  const form = options.body instanceof FormData;
  const response = await fetch(url, {
    ...options,
    headers: {
      "X-Requested-With": "training-web",
      ...(!form && options.body ? { "Content-Type": "application/json" } : {}),
      ...options.headers,
    },
  });
  let data;
  try {
    data = await response.json();
  } catch {
    data = { detail: "请求失败，请检查服务日志" };
  }
  if (!response.ok) {
    if (response.status === 401 && user) loggedOut();
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "输入格式不正确，请检查字段长度与数值范围",
    );
  }
  return data;
}
const post = (url, body) =>
  api(url, { method: "POST", body: JSON.stringify(body) });
function timeText(seconds) {
  seconds = Math.floor(seconds || 0);
  return `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
}
function dateText(value) {
  return value
    ? new Date(value * 1000).toLocaleString("zh-CN", { hour12: false })
    : "—";
}
// 提交期间禁用按钮，集中处理输入错误，减少重复创建账号或课程。
function formHandler(id, handler) {
  $(id).onsubmit = async (event) => {
    event.preventDefault();
    const submit = event.submitter || $(id).querySelector("button");
    submit.disabled = true;
    notify("");
    try {
      await handler(new FormData($(id)));
    } catch (e) {
      notify(e.message);
    } finally {
      submit.disabled = false;
    }
  };
}
// 离开学习页时停止播放器和上报；代次标记使旧页面的异步初始化失效。
function stopVideo() {
  lessonGeneration++;
  clearInterval(watchTimer);
  watchTimer = null;
  const video = $("training-video");
  if (video) video.pause();
  watch = null;
}
function loggedOut() {
  stopVideo();
  clearInterval(examTimer);
  user = null;
  $("workspace").hidden = true;
  $("login-view").hidden = false;
  $("identity").replaceChildren();
  $("lesson").replaceChildren();
  $("exam").replaceChildren();
  $("lesson").hidden = true;
  $("exam").hidden = true;
}
async function loggedIn(me) {
  user = me;
  $("login-view").hidden = true;
  $("workspace").hidden = false;
  $("identity").replaceChildren(
    node("span", `${me.name}${me.is_admin ? " · 管理员" : ""}`),
    button("退出", async () => {
      await post("/api/logout", {});
      loggedOut();
    }),
  );
  $("admin-tab").hidden = !me.is_admin;
  $("reports-tab").hidden = !me.is_admin;
  await view("courses");
}
async function view(name) {
  if (name !== "courses") {
    stopVideo();
    clearInterval(examTimer);
    $("lesson").hidden = true;
    $("exam").hidden = true;
  }
  for (const key of ["courses", "admin", "reports", "password"])
    $(key + "-view").hidden = key !== name;
  document
    .querySelectorAll("[data-view]")
    .forEach((b) => b.classList.toggle("selected", b.dataset.view === name));
  notify("");
  if (name === "courses") await loadCourses();
  if (name === "admin") await loadAdmin();
  if (name === "reports") await loadReports();
}
document
  .querySelectorAll("[data-view]")
  .forEach(
    (b) =>
      (b.onclick = () => view(b.dataset.view).catch((e) => notify(e.message))),
  );
formHandler("login-form", async (f) => {
  await loggedIn(await post("/api/login", Object.fromEntries(f)));
  $("login-form").reset();
});
formHandler("password-form", async (f) => {
  await post("/api/password", Object.fromEntries(f));
  $("password-form").reset();
  loggedOut();
  notify("密码已修改，请重新登录。");
});
$("refresh-courses").onclick = () =>
  loadCourses().catch((e) => notify(e.message));
// 课程卡片只展示服务器返回的学习比例与成绩，前端不自行推算分数。
async function loadCourses() {
  courseList = await api("/api/courses");
  $("course-grid").replaceChildren();
  if (!courseList.length)
    $("course-grid").append(
      node("p", "暂时没有已发布课程，请等待管理员发布。", "muted"),
    );
  for (const c of courseList) {
    const card = node("article", undefined, "card");
    card.append(
      node("span", c.published ? "在线课程" : "草稿 · 仅管理员可见", "badge"),
      node("h3", c.title),
      node("p", c.description || "完成视频学习后，参加本课程考试。", "muted"),
    );
    const track = node("div", undefined, "track"),
      p = node("progress");
    p.max = 100;
    p.value = c.percent;
    p.setAttribute("aria-label", "观看进度");
    track.append(p);
    card.append(
      node(
        "span",
        `${timeText(c.duration)} · ${c.question_count} 道题`,
        "muted small",
      ),
      track,
      node(
        "span",
        `已观看 ${c.percent}% · 考试要求 ${c.required_percent}%`,
        "small",
      ),
    );
    const scores = c.attempts.filter((a) => a.submitted_at !== null);
    if (scores.length)
      card.append(
        node(
          "span",
          `最高成绩 ${Math.max(...scores.map((a) => a.score))} 分 · ${scores.some((a) => a.passed) ? "已通过" : "未通过"}`,
          "badge",
        ),
      );
    card.append(button("进入学习 →", () => openCourse(c.id), ""));
    $("course-grid").append(card);
  }
}
// 串行发送播放位置，防止异步请求乱序覆盖；每次结果都来自服务器校验。
async function sendHeartbeat(playingOverride) {
  const state = watch,
    video = $("training-video");
  if (!state || !video) return;
  const body = {
    token: state.token,
    position: video.currentTime,
    playing:
      playingOverride ??
      (!video.paused &&
        !video.seeking &&
        !document.hidden &&
        video.playbackRate === 1),
  };
  heartbeatQueue = heartbeatQueue
    .catch(() => {})
    .then(async () => {
      if (watch !== state) return;
      try {
        const result = await post(
          `/api/courses/${state.id}/watch/heartbeat`,
          body,
        );
        if (watch === state) {
          $("watch-status").textContent =
            `有效观看 ${timeText(result.watched)} · ${result.percent}%（考试要求 ${state.required_percent}%）`;
          $("exam-start").disabled = !result.eligible;
        }
      } catch (e) {
        video.pause();
        notify(e.message);
      }
    });
  return heartbeatQueue;
}
// 加载受登录保护的视频，并在元数据就绪后恢复位置、创建播放会话。
async function openCourse(id) {
  stopVideo();
  const generation = lessonGeneration;
  clearInterval(examTimer);
  $("exam").hidden = true;
  notify("");
  const c = await api(`/api/courses/${id}`);
  if (generation !== lessonGeneration) return;
  const box = $("lesson");
  box.hidden = false;
  box.replaceChildren(node("h2", c.title), node("p", c.description, "muted"));
  if (!c.has_video) {
    box.append(node("p", "管理员尚未上传视频。"));
    return;
  }
  const video = node("video");
  video.id = "training-video";
  video.controls = true;
  video.preload = "metadata";
  video.setAttribute("controlsList", "nodownload noplaybackrate");
  video.setAttribute("playsinline", "");
  video.src = `/media/${id}`;
  const status = node(
    "p",
    `有效观看 ${timeText(c.watched)} · ${c.percent}%（考试要求 ${c.required_percent}%）`,
  );
  status.id = "watch-status";
  const start = button("开始 / 继续考试", () => openExam(id), "");
  start.id = "exam-start";
  start.disabled = !c.eligible;
  box.append(
    video,
    status,
    node(
      "p",
      `请保持页面在前台并以正常速度播放。跳转的部分不会计入时长。考试限时 ${c.exam_minutes} 分钟，共 ${c.max_attempts} 次机会，${c.pass_score} 分及格。`,
      "muted small",
    ),
    start,
  );
  for (const a of c.attempts)
    box.append(
      node(
        "p",
        `考试 #${a.id} · ${a.submitted_at === null ? (a.deadline < Date.now() / 1000 ? "已超时，记 0 分" : "进行中") : a.score + " 分 · " + (a.passed ? "通过" : "未通过")}`,
        "small",
      ),
    );
  video.onloadedmetadata = async () => {
    try {
      if (Math.abs(video.duration - c.duration) > 2)
        notify(
          "视频实际时长与课程配置不一致，请联系管理员；当前统计以课程配置为准。",
        );
      video.currentTime = Math.min(
        c.position,
        Math.max(0, video.duration - 0.1),
      );
      const result = await post(`/api/courses/${id}/watch/start`, {
        position: video.currentTime,
      });
      if (generation !== lessonGeneration) return;
      watch = { id, token: result.token, required_percent: c.required_percent };
      watchTimer = setInterval(() => sendHeartbeat(), 5000);
    } catch (e) {
      notify(e.message);
    }
  };
  // 跳转、开始、暂停时刷新基准，避免把暂停时间或 seek 跨度计为观看。
  video.onseeking = () => sendHeartbeat(false);
  video.onseeked = () => sendHeartbeat(false);
  video.onplay = () => sendHeartbeat(false);
  video.onpause = () => sendHeartbeat(!video.seeking && !document.hidden);
  video.onended = () => sendHeartbeat(true);
  video.onratechange = () => {
    if (video.playbackRate !== 1) {
      video.playbackRate = 1;
      notify("本课程按正常速度统计观看时长。");
    }
  };
  box.scrollIntoView({ behavior: "smooth", block: "start" });
}
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    const video = $("training-video");
    if (video) video.pause();
    sendHeartbeat(false);
  }
});
// 开考由服务器校验观看门槛；网页计时只负责提示，最终期限由服务器判断。
async function openExam(courseId) {
  const attempt = await post(`/api/courses/${courseId}/exam`, {});
  stopVideo();
  clearInterval(examTimer);
  const box = $("exam");
  box.hidden = false;
  box.replaceChildren(node("h2", "课程考试"));
  const clock = node("p");
  clock.id = "exam-clock";
  box.append(
    clock,
    node(
      "p",
      "题目为单选，未作答按错误计分。超时提交记 0 分；刷新页面后点击“继续考试”可恢复当前试卷，未提交的选择不会自动保存。",
      "muted small",
    ),
  );
  const form = node("form");
  attempt.questions.forEach((q, i) => {
    const field = node("fieldset", undefined, "question");
    field.append(node("legend", `${i + 1}. ${q.text}`));
    q.options.forEach((text, j) => {
      const label = node("label", undefined, "option"),
        input = node("input");
      input.type = "radio";
      input.name = String(q.id);
      input.value = j;
      label.append(input, node("span", text));
      field.append(label);
    });
    form.append(field);
  });
  const submit = node("button", "提交试卷");
  submit.type = "submit";
  form.append(submit);
  box.append(form);
  const offset = attempt.server_time - Date.now() / 1000;
  const tick = () => {
    const seconds = Math.max(
      0,
      Math.floor(attempt.deadline - (Date.now() / 1000 + offset)),
    );
    clock.textContent = seconds
      ? `剩余 ${timeText(seconds)}`
      : "考试时间已结束，提交将记 0 分";
  };
  tick();
  examTimer = setInterval(tick, 1000);
  form.onsubmit = async (event) => {
    event.preventDefault();
    if (!confirm("确认提交？交卷后不能修改答案。")) return;
    submit.disabled = true;
    try {
      const answers = Object.fromEntries(
        [...new FormData(form)].map(([k, v]) => [k, Number(v)]),
      );
      const result = await post(`/api/attempts/${attempt.id}/submit`, {
        answers,
      });
      clearInterval(examTimer);
      box.replaceChildren(
        node("h2", `本次成绩：${result.score} 分`),
        node(
          "p",
          result.passed ? "恭喜，考试通过。" : "本次未通过，请复习后再试。",
        ),
        button("返回课程", async () => {
          box.hidden = true;
          await loadCourses();
          await openCourse(courseId);
        }),
      );
      await loadCourses();
    } catch (e) {
      notify(e.message);
      submit.disabled = false;
    }
  };
  box.scrollIntoView({ behavior: "smooth" });
}
function table(headers, rows) {
  const t = node("table"),
    head = node("thead"),
    hr = node("tr");
  headers.forEach((h) => hr.append(node("th", h)));
  head.append(hr);
  t.append(head);
  const body = node("tbody");
  rows.forEach((row) => {
    const tr = node("tr");
    row.forEach((value) => {
      const td = node("td");
      if (value instanceof Node) td.append(value);
      else td.textContent = String(value ?? "—");
      tr.append(td);
    });
    body.append(tr);
  });
  t.append(body);
  return t;
}
formHandler("user-form", async (f) => {
  await post("/api/admin/users", Object.fromEntries(f));
  $("user-form").reset();
  await loadAdmin();
  notify("员工账号已创建，请通过安全渠道告知本人初始密码。");
});
$("course-form").elements.video.onchange = (event) => {
  const file = event.target.files[0];
  if (!file) return;
  const v = document.createElement("video"),
    url = URL.createObjectURL(file);
  v.preload = "metadata";
  v.onloadedmetadata = () => {
    $("course-form").elements.duration.value = Number(v.duration.toFixed(3));
    URL.revokeObjectURL(url);
  };
  v.onerror = () => {
    URL.revokeObjectURL(url);
    notify("无法读取视频时长，请确认格式并手动填写。");
  };
  v.src = url;
};
async function upload(id, file) {
  const f = new FormData();
  f.append("file", file);
  await api(`/api/admin/courses/${id}/video`, { method: "POST", body: f });
}
formHandler("course-form", async (f) => {
  const fields = Object.fromEntries(f);
  delete fields.video;
  for (const key of [
    "duration",
    "required_percent",
    "pass_score",
    "max_attempts",
    "exam_minutes",
  ])
    fields[key] = Number(fields[key]);
  const course = await post("/api/admin/courses", fields);
  try {
    await upload(course.id, f.get("video"));
    $("course-form").reset();
    notify("课程与视频已保存。请添加试题后发布课程。");
  } catch (e) {
    notify(
      `课程草稿 #${course.id} 已创建，视频上传失败：${e.message}。请在课程列表重试上传。`,
    );
  }
  await loadAdmin();
});
formHandler("question-form", async (f) => {
  const options = f
    .get("options")
    .split("\n")
    .map((s) => s.trim())
    .filter(Boolean);
  await post(`/api/admin/courses/${f.get("course_id")}/questions`, {
    text: f.get("text"),
    options,
    answer: Number(f.get("answer")) - 1,
  });
  $("question-form").elements.text.value = "";
  $("question-form").elements.options.value = "";
  await loadAdmin();
  notify("题目已添加。");
});
// 管理区仅展示和调用管理接口；隐藏按钮之外，后端仍单独校验管理员权限。
async function loadAdmin() {
  const [courses, users] = await Promise.all([
    api("/api/courses"),
    api("/api/admin/users"),
  ]);
  courseList = courses;
  const selector = $("question-course"),
    selected = selector.value;
  selector.replaceChildren();
  courses
    .filter((c) => !c.published)
    .forEach((c) => {
      const option = node("option", c.title);
      option.value = c.id;
      selector.append(option);
    });
  if ([...selector.options].some((o) => o.value === selected))
    selector.value = selected;
  $("admin-courses").replaceChildren();
  for (const c of courses) {
    const row = node("div", undefined, "panel"),
      info = node("div");
    info.append(
      node("strong", c.title),
      node(
        "p",
        `#${c.id} · ${c.published ? "已发布" : "草稿"} · ${c.has_video ? "已有视频" : "缺少视频"} · ${c.question_count} 道题 · ${timeText(c.duration)}`,
        "muted small",
      ),
    );
    const actions = node("div", undefined, "actions");
    if (!c.has_video) {
      const file = node("input");
      file.type = "file";
      file.accept = ".mp4,.webm";
      file.setAttribute("aria-label", "上传课程视频");
      file.onchange = async () => {
        if (file.files[0]) {
          file.disabled = true;
          try {
            await upload(c.id, file.files[0]);
            await loadAdmin();
            notify("上传完成。");
          } catch (e) {
            notify(e.message);
            file.disabled = false;
          }
        }
      };
      actions.append(file);
    }
    actions.append(
      button(c.published ? "下架" : "发布", async () => {
        await api(`/api/admin/courses/${c.id}`, {
          method: "PATCH",
          body: JSON.stringify({ published: !c.published }),
        });
        await loadAdmin();
      }),
      button("查看试题", async () => {
        const qs = await api(`/api/admin/courses/${c.id}/questions`);
        let details = row.querySelector(".question-details");
        if (details) {
          details.remove();
          return;
        }
        details = node("div", undefined, "question-details");
        if (!qs.length) details.append(node("p", "暂无试题"));
        qs.forEach((q, i) => {
          details.append(
            node("p", `${i + 1}. ${q.text}`),
            node(
              "p",
              q.options.map((o, j) => `${j + 1}. ${o}`).join(" / "),
              "small",
            ),
            node("p", `正确选项：${q.answer + 1}`, "small"),
          );
        });
        info.append(details);
      }),
    );
    row.append(info, actions);
    $("admin-courses").append(row);
  }
  const rows = users.map((u) => {
    const actions = node("div");
    actions.append(
      button("重置密码", async () => {
        const password = prompt(`为 ${u.username} 设置新密码（至少 12 位）：`);
        if (password === null) return;
        await post(`/api/admin/users/${u.id}/password`, { password });
        notify("密码已重置，该账号原有登录已失效。");
      }),
    );
    if (!u.is_admin)
      actions.append(
        button(u.active ? "停用" : "启用", async () => {
          await api(`/api/admin/users/${u.id}`, {
            method: "PATCH",
            body: JSON.stringify({ active: !u.active }),
          });
          await loadAdmin();
        }),
      );
    return [
      u.username,
      u.name,
      u.is_admin ? "管理员" : "员工",
      u.active ? "启用" : "停用",
      actions,
    ];
  });
  $("admin-users").replaceChildren(
    table(["账号", "姓名", "角色", "状态", "操作"], rows),
  );
}
// 报表包含从未学习、考试中、已交卷或超时记录，保留每次考试而不是覆盖成绩。
async function loadReports() {
  reportList = await api("/api/admin/reports");
  renderReports();
}
function renderReports() {
  const search = $("report-search").value.toLowerCase(),
    rows = reportList.filter((r) =>
      [r.name, r.username, r.course].some((v) =>
        v.toLowerCase().includes(search),
      ),
    );
  $("report-summary").replaceChildren();
  for (const [title, value] of [
    ["员工人数", new Set(rows.map((r) => r.username)).size],
    ["已交卷 / 超时", rows.filter((r) => r.score !== null).length],
    ["通过人次", rows.filter((r) => r.passed).length],
  ]) {
    const card = node("div", undefined, "metric");
    card.append(node("span", title, "muted small"), node("strong", value));
    $("report-summary").append(card);
  }
  $("report-table").replaceChildren(
    table(
      [
        "账号",
        "姓名",
        "课程",
        "有效观看",
        "进度",
        "最近观看",
        "考试编号",
        "状态",
        "分数",
        "结果",
        "交卷时间",
      ],
      rows.map((r) => [
        r.username,
        r.name,
        r.course,
        timeText(r.watched_seconds),
        r.percent + "%",
        dateText(r.last_watched),
        r.attempt_id,
        r.status,
        r.score,
        r.passed === null ? "—" : r.passed ? "通过" : "未通过",
        dateText(r.submitted_at),
      ]),
    ),
  );
}
$("report-search").oninput = renderReports;
$("refresh-reports").onclick = () =>
  loadReports().catch((e) => notify(e.message));
api("/api/me")
  .then(loggedIn)
  .catch((e) => {
    loggedOut();
    if (e.message !== "请先登录") notify(e.message);
  });
