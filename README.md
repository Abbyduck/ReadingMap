# Reading Map · Catalog v1

童书与学习资源目录、阅读地图、儿童个人资料，以及 Research 人工审核工作台。当前后端使用 Django + Django REST Framework，前端使用 React + TypeScript + Vite，开发数据库使用 MySQL。

## 目录

```text
frontend/     前端源码、静态资源、构建脚本
backend/      Django 应用、迁移、测试与维护脚本
.codex/       Codex 项目级 Skills
skills/       旧 Skill 目录（迁移完成后移除）
docs/         来源资料、达人笔记、导入格式等参考材料
scripts/      数据工具与提交前检查
data/         导入模板
source_data/  书单来源数据与 JSON Schema
```

本地环境配置、数据库备份、浏览器配置、个人购书记录、采集资料与根目录验证截图由 `.gitignore` 排除，保留在开发电脑上。

## 产品 / 领域文档

Reading Map 的当前业务语义以项目级 Domain Skill 为准：

`.codex/skills/reading-map-domain-model/SKILL.md`

仓库协作与优先级规则见 `AGENTS.md`。`docs/` 中的文件是来源/操作参考，不是产品架构权威；旧架构、旧 handoff 与一次性 QA 通过 Git history 追溯，不应被用来恢复当前行为。

Research 和来源书单整理的具体工作流分别位于：

- `.codex/skills/catalog-research-worker/SKILL.md`
- `.codex/skills/wild-reading-list-to-json/SKILL.md`

## 本地启动

需要 Python 3.12、Node.js 24，以及 MySQL。先为本项目创建空数据库 `reading_map_django` 和专用数据库用户，再配置本地连接。已有开发环境无需重建或覆盖 `.env`。

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe scripts\configure_django.py --apply
```

编辑 `backend/.env`，填写 `DATABASE_USER` 与 `DATABASE_PASSWORD`。初始化脚本只补充缺失的 Django 配置，不打印秘密值。数据库名和连接信息通过 `DATABASE_*` 配置读取。

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8010
```

在另一个终端启动前端：

```powershell
cd frontend
npm ci
npm run dev
```

前端地址：`http://127.0.0.1:53180`。审核工作台：`/admin`；Django 管理后台：`/django-admin/`。公开 Catalog 可匿名读取；审核和 Catalog 写入需要管理员账号，儿童资料与个人标记按账号隔离。

`backend/app/`、`backend/alembic/`、`backend/tests/` 以及部分旧维护脚本来自迁移前的 FastAPI 实现，保留供历史参考；历史 ASGI 路径 `app.main:app` 现在也指向 Django，避免绕过现有鉴权。不要运行旧数据库重置脚本来初始化当前系统。

## 检查

Django 测试使用内存 SQLite，不连接或修改开发 MySQL：

```powershell
cd backend
.\.venv\Scripts\python.exe manage.py test accounts catalog reviews --settings=config.settings_test
```

```powershell
cd frontend
npm run build
node scripts/check-auth-redirect.mjs
```

从项目根目录检查候选提交文件，包括本地凭据误复制：

```powershell
backend\.venv\Scripts\python.exe scripts\check_release.py
```

初始化 Git 并暂存后，再检查实际 Git 索引：

```powershell
backend\.venv\Scripts\python.exe scripts\check_release.py --staged
```

检查覆盖常见令牌、私钥、带密码的连接 URL 和本地已知凭据；自动检查不能替代人工检查。

## 部署配置

公开部署时设置 `DJANGO_DEBUG=false`，使用独立随机 `DJANGO_SECRET_KEY`、专用数据库凭据、明确的 `DJANGO_ALLOWED_HOSTS` 和 HTTPS 同源反向代理；配置实际邮件服务。Research 浏览器助手目前依赖开发机上的 Chrome 会话。