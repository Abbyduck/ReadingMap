# Reading Map · Catalog v1

童书与学习资源目录、阅读地图、儿童个人资料，以及 Research 人工审核工作台。当前后端使用 Django + Django REST Framework，前端使用 React + TypeScript + Vite，开发数据库使用 MySQL。

## 目录

```text
frontend/     前端源码、静态资源、构建脚本
backend/      Django 应用、迁移、测试与维护脚本
docs/         领域设计、审核行为约定与开发文档
scripts/      数据工具与提交前检查
skills/       Research / 书单整理协作规则
data/         导入模板
source_data/  构建所需的一份书单样例与 JSON Schema
```

本地的环境配置、数据库备份、浏览器配置、个人购书记录、采集资料与根目录验证截图由 `.gitignore` 排除，保留在开发电脑上。

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

## 领域约定

- `catalog_entities` 统一标识 book、animation、reading_system、series、level、set；ISBN 属于独立作品 Work。
- Collection 支持嵌套，`collection_items` 只保存直接成员关系。
- 来源资料先进入 Research 和审核暂存，人工确认后才写入正式 Catalog。
- 一条书单推荐记录代表来源真正推荐的对象；强推只由来源明确强调或人工确认产生。
- 人工草稿、推荐语与图片选择必须保留，客观 Research 和 AI 推导分别存储。

修改审核、Research、Catalog 写入或推荐行为前，阅读 [审核工作台稳定行为约定](docs/review-workflow-contract.md)。流程说明见 [审核实现文档](docs/review-workflow-v1-implementation.md)，Research Worker 规则见 [项目技能](skills/catalog-research-worker/SKILL.md)。

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

从项目根目录检查首版候选文件，包括本地凭据的误复制：

```powershell
backend\.venv\Scripts\python.exe scripts\check_release.py
```

该脚本遵循 Git 忽略规则，在尚未初始化 Git 时也可运行；只报告路径、行号和问题类别。初始化 Git 并暂存后，再检查实际 Git 索引：

```powershell
backend\.venv\Scripts\python.exe scripts\check_release.py --staged
```

检查覆盖常见令牌、私钥、带密码的连接 URL 和本地已知凭据，不能替代人工检查。首版准备范围与排除策略见 [GitHub 发布说明](docs/github-first-release.md)。

## 部署配置

公开部署时设置 `DJANGO_DEBUG=false`，使用独立随机 `DJANGO_SECRET_KEY`、专用数据库凭据、明确的 `DJANGO_ALLOWED_HOSTS` 和 HTTPS 同源反向代理；配置实际邮件服务。Research 浏览器助手目前依赖开发机上的 Chrome 会话。当前发布准备验证的是源码与本地回归，尚未验证生产部署。
