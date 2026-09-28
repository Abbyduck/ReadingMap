# GitHub 首版准备

本文记录源码首版的提交范围与验证结果。项目使用 `main` 分支；实际提交与远程推送状态以 Git 记录为准。

## 提交范围

保留前后端源码、当前 Django 迁移与测试、依赖锁文件、项目文档、工具脚本、导入模板和项目技能。`source_data/` 只保留 JSON Schema 和前端构建依赖的一份 incremental-v2 书单样例，避免漏掉构建输入。

根目录的 43 张 `implementation-*.png` 是开发界面验证记录，未发现代码或文档引用；已加入忽略规则，文件保留在本地。`frontend/src/assets/` 与 `frontend/public/` 的图片作为前端资源保留。

以下内容留在本地：环境配置、私钥、数据库及备份、依赖与构建结果、浏览器配置与日志、原始书单图片、采集资料、个人购书数据，以及其余本地来源数据。空数据库启动后，个人数据和旧审核证据需要由开发者另行导入。

## 已处理的问题

- 移除 `.env.example`、旧配置默认值及 Alembic 配置中写死的数据库凭据。当前模板匹配 Django 配置；本地 `.env` 未改写。
- 历史 `app.main:app` 入口转到 Django ASGI 应用，旧 FastAPI 路由不会再通过该入口绕过会话、管理员与儿童资料归属检查。
- 登录/注册后的 `next` 参数拒绝控制字符，并要求解析后的 URL 与当前页面同源。
- 更新 README 的 Django 安装、迁移、启动和测试步骤。
- 增加 `scripts/check_release.py`，扫描可提交文件、实际 Git 索引和本地已知凭据误复制；报告不回显秘密值。
- 审核回归测试改用临时目录中的固定 JSON 样例，保留真实导入、哈希、路径与五位达人恢复断言，不依赖开发机的原始书单。

审核工作台、Research、Catalog 写入和推荐事实的既定产品行为没有改动。

## 验证

- Django 原有 85 项回归测试通过；另加 2 项真实 ASGI 请求测试，验证历史入口拒绝匿名读取儿童资料与审核批次。
- 15 个登录跳转用例通过，包括编码换行绕过和正常站内路径。
- 6 项发布检查测试通过，包括强制暂存私密文件、暂存秘密后清理工作副本、UTF-16 令牌和本地凭据误复制；输出均验证不包含秘密值。
- TypeScript 检查与 Vite 生产构建通过。本机原构建目录写入受限，使用以下命令输出到忽略的临时目录：

  ```powershell
  cd frontend
  npm run build -- --configLoader runner --outDir ../tmp/github-first-release-build-20260928
  ```

- Git 忽略规则下的候选文件检查通过：没有常见令牌、私钥、带密码连接 URL 或已知本地凭据命中；根目录截图和本地私密数据均不在候选集合中。
- 将仅含 187 个候选文件的副本放入 `tmp/github-first-release-candidate-20260928/`，未复制本地 `.env`、私密数据或依赖目录；该副本的 87 项 Django 测试、前端 mock 生成与登录跳转检查也通过。测试解释器复用本机已安装的依赖。

当前 bundle 仍有体积提示；未执行真实外网采集、生产部署验证或全量依赖漏洞审计。商品采集助手的目标地址、重定向和下载大小限制可在扩大部署前单独加固。本轮未确认其存在普通用户可利用的秘密泄露路径。

## 首次提交步骤

在项目根目录执行：

```powershell
git init --initial-branch=main
git add .
backend\.venv\Scripts\python.exe scripts\check_release.py --staged
git diff --cached --stat
```

发布检查必须成功，再检查暂存列表。`.gitignore` 不能保护已被强制加入索引的秘密文件，检查脚本会拦截这些路径；不要使用 `git add -f` 将本地私密目录加入首版。

确认后创建本地提交，并使用自己创建的 GitHub 仓库地址：

```powershell
git commit -m "Initial Reading Map source release"
git remote add origin <your-github-repository-url>
git push -u origin main
```

如果旧凭据曾公开、分享给他人或与其他环境共用，应轮换实际凭据；从源码移除不会使旧值失效。自动检查不能识别所有秘密编码或所有个人信息，发布前仍需人工查看候选内容。

Codex Security 报告对应修正前的目录快照，记录 3 个已在本轮处理的问题，覆盖为有限范围。本地回归与发布检查对应修正后的源码。插件统计本轮扫描总计 5,718,261 tokens，其中缓存输入 5,364,864 tokens；统计覆盖 5 个线程。
