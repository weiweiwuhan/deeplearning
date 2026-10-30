/* 浏览器端到端测试，始终创建独立临时数据库并自行启动服务。
 * 前置：安装 requirements.txt、ffmpeg 与 Playwright/Chromium。
 * 例如将 Playwright 安装在仓库外：
 * npm install --prefix /tmp/training-browser-tools playwright
 * NODE_PATH=/tmp/training-browser-tools/node_modules npx --prefix /tmp/training-browser-tools playwright install chromium
 * NODE_PATH=/tmp/training-browser-tools/node_modules PYTHON=.venv/bin/python node tests/browser_smoke.cjs
 * 系统已有 Chromium 时可设置 BROWSER_EXECUTABLE=/usr/bin/chromium。
 * 测试截图保存在被 Git 忽略的 test-results/；测试结束删除临时数据库并停止服务。
 */
"use strict";
const { chromium } = require("playwright");
const { spawn, execFileSync } = require("node:child_process");
const fs = require("node:fs"),
  os = require("node:os"),
  path = require("node:path"),
  net = require("node:net");
const assert = require("node:assert/strict");
(async () => {
  const root = path.resolve(__dirname, ".."),
    temp = fs.mkdtempSync(path.join(os.tmpdir(), "training-browser-"));
  const artifacts = path.join(root, "test-results");
  fs.mkdirSync(artifacts, { recursive: true });
  const server = net.createServer();
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = server.address().port;
  await new Promise((resolve) => server.close(resolve));
  const password = "browser-admin-password-2026",
    employeePassword = "browser-employee-password-2026";
  let processLog = "",
    browser,
    child;
  try {
    execFileSync("ffmpeg", [
      "-hide_banner",
      "-loglevel",
      "error",
      "-f",
      "lavfi",
      "-i",
      "color=c=0x12685e:s=640x360:r=24",
      "-f",
      "lavfi",
      "-i",
      "sine=frequency=440:sample_rate=44100",
      "-t",
      "12",
      "-c:v",
      "libx264",
      "-pix_fmt",
      "yuv420p",
      "-c:a",
      "aac",
      "-movflags",
      "+faststart",
      path.join(temp, "lesson.mp4"),
    ]);
    child = spawn(
      process.env.PYTHON || "python",
      [
        "-m",
        "uvicorn",
        "app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        String(port),
      ],
      {
        cwd: root,
        env: {
          ...process.env,
          DATABASE_URL: "sqlite:///" + path.join(temp, "test.db"),
          DATA_DIR: temp,
          ADMIN_USERNAME: "admin",
          ADMIN_PASSWORD: password,
          COOKIE_SECURE: "false",
        },
      },
    );
    child.stdout.on("data", (d) => (processLog += d));
    child.stderr.on("data", (d) => (processLog += d));
    const base = `http://127.0.0.1:${port}`;
    for (let i = 0; i < 100; i++) {
      try {
        const response = await fetch(base + "/api/health");
        if (response.ok) break;
      } catch {}
      if (child.exitCode !== null) throw new Error("服务启动失败");
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    assert.equal((await fetch(base + "/api/health")).status, 200);
    browser = await chromium.launch({
      headless: true,
      executablePath: process.env.BROWSER_EXECUTABLE || undefined,
      args: ["--no-sandbox"],
    });
    const page = await browser.newPage({
        viewport: { width: 1440, height: 1000 },
      }),
      errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("response", (r) => {
      if (r.status() >= 500) errors.push(`${r.status()} ${r.url()}`);
    });
    await page.goto(base);
    await page.locator("#login-form").waitFor({ state: "visible" });
    await page.screenshot({
      path: path.join(artifacts, "login-desktop.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({
      path: path.join(artifacts, "login-mobile.png"),
      fullPage: true,
    });
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    );
    await page.setViewportSize({ width: 1440, height: 1000 });
    const login = async (username, pw) => {
      await page.locator("#login-form [name=username]").fill(username);
      await page.locator("#login-form [name=password]").fill(pw);
      await page.locator("#login-form button").click();
      await page.locator("#workspace").waitFor({ state: "visible" });
    };
    const logout = async () => {
      await page.getByRole("button", { name: "退出", exact: true }).click();
      await page.locator("#login-view").waitFor({ state: "visible" });
    };
    await login("admin", password);
    await page
      .getByRole("button", { name: "课程与账号管理", exact: true })
      .click();
    await page.locator("#user-form [name=username]").fill("employee");
    await page.locator("#user-form [name=name]").fill("浏览器测试员工");
    await page.locator("#user-form [name=password]").fill(employeePassword);
    await page.locator("#user-form button").click();
    await page
      .locator("#admin-users")
      .getByText("浏览器测试员工", { exact: true })
      .waitFor();
    await page.locator("#course-form [name=title]").fill("浏览器验证课程");
    await page
      .locator("#course-form [name=description]")
      .fill("正常播放视频并参加考试");
    await page
      .locator("#course-form [name=video]")
      .setInputFiles(path.join(temp, "lesson.mp4"));
    await page.waitForFunction(
      () =>
        Number(document.querySelector("#course-form [name=duration]").value) >
        11,
    );
    await page.locator("#course-form button").click();
    await page
      .locator("#admin-courses")
      .getByText("浏览器验证课程", { exact: true })
      .waitFor();
    await page
      .locator("#question-form [name=text]")
      .fill("是否应该遵守安全操作规程？");
    await page.locator("#question-form [name=options]").fill("应该\n不应该");
    await page.locator("#question-form button").click();
    await page.waitForFunction(() =>
      document.querySelector("#admin-courses").textContent.includes("1 道题"),
    );
    await page
      .locator("#admin-courses")
      .getByRole("button", { name: "发布", exact: true })
      .click();
    await page
      .locator("#admin-courses")
      .getByRole("button", { name: "下架", exact: true })
      .waitFor();
    await logout();
    await login("employee", employeePassword);
    assert.equal(await page.locator("#admin-tab").isVisible(), false);
    await page.getByRole("button", { name: "进入学习 →", exact: true }).click();
    await page.waitForFunction(
      () => document.getElementById("training-video")?.readyState >= 2,
    );
    // 等待 watch/start 完成后再播放，避免把播放前的初始化混入统计。
    await page.waitForFunction(
      () => typeof watch !== "undefined" && watch !== null,
    );
    await page.locator("#training-video").evaluate((v) => v.play());
    await page.waitForFunction(
      () => document.getElementById("training-video").ended,
      { timeout: 25000 },
    );
    await page.waitForFunction(
      () => !document.getElementById("exam-start").disabled,
      { timeout: 5000 },
    );
    assert.match(await page.locator("#watch-status").textContent(), /有效观看/);
    await page.screenshot({
      path: path.join(artifacts, "employee-progress.png"),
      fullPage: true,
    });
    await page
      .getByRole("button", { name: "开始 / 继续考试", exact: true })
      .click();
    await page.locator("#exam input[type=radio]").first().check();
    page.once("dialog", (d) => d.accept());
    await page
      .locator("#exam")
      .getByRole("button", { name: "提交试卷", exact: true })
      .click();
    await page
      .locator("#exam")
      .getByText("本次成绩：100 分", { exact: true })
      .waitFor();
    await logout();
    await login("admin", password);
    await page.getByRole("button", { name: "学习报表", exact: true }).click();
    await page
      .locator("#report-table")
      .getByText("浏览器测试员工", { exact: true })
      .waitFor();
    assert.match(await page.locator("#report-table").textContent(), /100/);
    assert.match(await page.locator("#report-table").textContent(), /通过/);
    const rows = await page.evaluate(() =>
      fetch("/api/admin/reports").then((r) => r.json()),
    );
    assert.equal(rows[0].score, 100);
    assert(rows[0].watched_seconds >= 10.8);
    assert(rows[0].watched_seconds <= 12.1);
    await page.screenshot({
      path: path.join(artifacts, "admin-report.png"),
      fullPage: true,
    });
    const csv = await page.evaluate(() =>
      fetch("/api/admin/reports.csv").then((r) => r.text()),
    );
    assert(csv.includes("浏览器测试员工"));
    assert.deepEqual(errors, []);
    console.log(
      `浏览器完整流程通过：创建账号 → 上传视频与试题 → 发布 → 员工实际播放 ${rows[0].watched_seconds} 秒 → 考试 100 分 → 后台报表与 CSV。`,
    );
  } catch (error) {
    console.error(processLog);
    throw error;
  } finally {
    if (browser) await browser.close();
    if (child && child.exitCode === null) {
      child.kill("SIGTERM");
      await new Promise((resolve) => child.once("exit", resolve));
    }
    fs.rmSync(temp, { recursive: true, force: true });
  }
})().catch((e) => {
  console.error(e);
  process.exitCode = 1;
});
