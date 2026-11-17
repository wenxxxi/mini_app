# 每日复盘小程序

基于微信小程序 + 树莓派后端的个人作息与工作复盘工具。

## 功能模块

| 模块 | 说明 |
| --- | --- |
| 每日复盘 | 起床时间、三餐时间、食物与营养摄入、工时/娱乐时长、STAR 法则工作记录 |
| 倒计时 | 独立倒计时卡片，支持多个目标 |
| 统计 | 周/月时长趋势、起床时间分布、饮食热量概览 |
| 我的 | 基本信息、日界设置、数据导出 |

## 技术栈

**后端**

- FastAPI + Uvicorn
- SQLAlchemy 2.0 + SQLite（WAL 模式）
- PyJWT 鉴权
- httpx 调用微信 `code2session`

**小程序**

- 原生 WXML / WXSS / JS
- TabBar 四页：今日、倒计时、统计、我的

**部署**

- systemd 托管后端服务
- Tailscale Funnel 提供公网 HTTPS（`*.ts.net` 域名）

## 目录结构

```
review-miniapp/
├── backend/                 # FastAPI 后端
│   ├── app/
│   │   ├── main.py          # 入口
│   │   ├── models.py        # 数据库模型
│   │   ├── schemas.py       # Pydantic 数据模型
│   │   ├── security.py      # JWT
│   │   ├── services.py      # 业务逻辑（营养重算、日界校验等）
│   │   └── routers/         # 路由：auth / me / reviews / meals / star / countdowns / stats
│   ├── data/app.db          # SQLite 数据库（不入库）
│   ├── .env                 # 环境变量（不入库）
│   ├── .env.example         # 环境变量模板
│   └── requirements.txt
├── miniprogram/             # 微信小程序
│   ├── app.js / app.json / app.wxss
│   ├── pages/               # today / review / countdown / countdown-edit / stats / me
│   └── utils/               # request / date / store / config
├── deploy/
│   └── review-api.service   # systemd 单元文件
└── .gitignore
```

## 后端部署

### 1. 安装依赖

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入 WX_APPID、WX_SECRET、JWT_SECRET
chmod 600 .env
```

### 3. 注册 systemd 服务

```bash
sudo cp deploy/review-api.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now review-api
```

服务默认监听 `127.0.0.1:8081`，数据库自动创建在 `backend/data/app.db`。

### 4. 公网访问（Tailscale Funnel）

```bash
sudo tailscale set --operator=$USER
tailscale funnel --bg 8081
tailscale funnel status   # 查看分配的 https://<host>.ts.net 地址
```

把得到的地址填入 `miniprogram/utils/config.js` 的 `baseUrl`。

## 小程序

1. 用微信开发者工具打开 `miniprogram/` 目录
2. AppID 填入你的小程序 AppID
3. 「详情 → 本地设置」勾选「不校验合法域名」
4. 编译、预览或上传为体验版

> 当前通过 Tailscale Funnel 暴露 `*.ts.net` 域名，未备案，**仅适用于体验版**（手机端需打开调试模式）。正式发布需切换到已备案域名 + 云服务器反代方案。

## 环境变量说明

| 变量 | 说明 |
| --- | --- |
| WX_APPID | 小程序 AppID |
| WX_SECRET | 小程序 AppSecret |
| JWT_SECRET | JWT 签名密钥，生产环境务必更换 |
| JWT_EXPIRE_DAYS | Token 有效期（天），默认 7 |
| DB_PATH | SQLite 文件路径 |
| TZ | 时区，默认 Asia/Shanghai |
| DEV_LOGIN | 设为 1 时允许 `dev:` 前缀的 code 直接登录（仅开发） |

## 不纳入版本控制的文件

- `backend/.env`（密钥）
- `backend/data/*.db`（数据库）
- `backend/.venv/`（虚拟环境）
