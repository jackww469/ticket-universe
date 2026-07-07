# 电子票夹博物馆系统

[![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-2.0+-green.svg)](https://flask.palletsprojects.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

为车票、演出票、景区票、证书以及自定义票据类型提供数字化珍藏与浏览，支持分类筛选、关键词搜索、时间轴日记视图、地图足迹与年度统计与 OCR 自动识别。

## 项目预览

![Ticket Universe](./static/images/phone-mockup.png)

## 技术栈

- **前端**：HTML + CSS + JavaScript
- **后端**：Python + Flask
- **数据库**：SQLite

## 功能概览

- **首页**：分类导航（全部、车票、演出票、景区票、证书、其他）、上传新票根、时间轴日记入口、足迹地图入口
- **上传页**：
  - 手动录入：票据类型（支持自定义，如"音乐节票""博物馆年卡"等）、来源平台、时间，省份、城市、地点、备注、图片上传（≤5MB），支持拖拽与预览
  - 自动识别：点击「自动识别」调用百度 OCR；**结构化字段**（类型、时间，省份、城市、地点）填入上方表单；**OCR 全文**单独显示在「识别结果」区可编辑，**不会**写入「备注」
  - **规则库主题**：根据 `data/theme_rules.json` 中的关键词匹配**建议类型**与**主题色**（列表卡片、时间轴节点、详情页左侧条会体现主题色；可自行增删规则）
- **列表页**：卡片展示，按类型筛选（全部 / 车票 / 演出票 / 景区票 / 证书 / 其他），其中"其他"自动归类所有自定义类型；支持关键词搜索，点击卡片进入详情
- **时间轴页**：按年份→月份排列，CSS 伪元素绘制红色中线，证书节点金色边框与奖杯图标，悬停显示放大的图片与完整备注
- **详情页**：展示大图与完整信息，支持编辑（含更换图片、修改自定义类型）与删除
- **足迹地图**：可视化展示去过的省份和城市，中国地图 SVG 渲染，已访问省份高亮显示，点击省份可筛选省份列表
- **年度统计**：年度趋势柱状图、每月票据分布、票据类型占比条形图、常去地点 Top 10 排行
- **账户**：**注册 / 登录**（会话 Cookie）；每个用户独立存储票据与 OCR 等数据；新上传图片保存在 `static/uploads/<用户ID>/`，访问图片时会校验是否为当前登录用户
- **登录 / 注册页**：桌面端 **左右分栏**（左侧品牌区 + 内联 SVG 票根插画与文案，右侧表单）；窄屏 **单列** 自上而下展示

## 快速开始

### 一键启动（推荐）

1. 双击项目根目录中的 `run.bat`：
   - 自动创建并激活本地虚拟环境 `.venv`
   - 自动执行 `pip install -r requirements.txt`
   - 自动启动 `python app.py`
2. 浏览器访问：<http://127.0.0.1:5000> → 首次使用请先 **注册** 账号再使用票夹功能。

### 手动启动

1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
2. 启动服务：
   ```bash
   python app.py
   ```
3. 浏览器访问：<http://127.0.0.1:5000>

## 项目结构

```
ticket-universe/
├── app.py              # Flask 应用与 API
├── config.py           # 配置（数据库路径、上传目录、票据类型、OCR 开关与密钥）
├── database.py         # SQLite：用户表 + 按 user_id 隔离的票据
├── auth_utils.py       # 登录会话、login_required 装饰器
├── ocr_service.py      # OCR 调用与关键信息抽取
├── theme_rules.py      # 关键词规则库加载与匹配
├── data/
│   └── theme_rules.json # 关键词 → 建议类型 + 主题色（可编辑）
├── requirements.txt
├── run.bat             # Windows 一键启动脚本
├── templates/          # 页面模板
│   ├── base.html       # 基础布局
│   ├── index.html      # 首页
│   ├── list.html       # 列表页
│   ├── timeline.html   # 时间轴页
│   ├── detail.html     # 详情页
│   ├── upload.html     # 上传页
│   ├── map.html        # 足迹地图页
│   ├── stats.html      # 年度统计页
│   ├── login.html      # 登录页
│   └── register.html   # 注册页
└── static/
    ├── css/style.css   # 全局与各页样式
    ├── js/
    │   ├── common.js   # Toast 等公共逻辑
    │   ├── upload.js   # 上传页逻辑
    │   ├── list.js     # 列表筛选与搜索
    │   ├── detail.js   # 详情与编辑删除
    │   ├── timeline.js # 时间轴渲染
    │   ├── map.js      # 地图页逻辑
    │   └── stats.js    # 统计页逻辑
    ├── images/          # UI 图片资源
    │   ├── logo.png
    │   ├── phone-mockup.png
    │   └── ...
    └── uploads/        # 票据图片（新数据在子目录「用户数字ID」下）
└── ticket_universe.db  # SQLite 数据库（运行后自动创建）
```

## 配置说明

### 会话密钥
生产环境请设置环境变量 `FLASK_SECRET_KEY`（随机长字符串），勿使用默认 `dev-ticket-universe-change-me`。

### OCR 配置
- 需在环境变量或 `run.bat` 中设置 `BAIDU_OCR_API_KEY` 与 `BAIDU_OCR_SECRET_KEY` 才会启用自动识别
- 识别结果中的全文会存入数据库字段 `ocr_text`，与「备注」分离；主题色存入 `theme_color`
- 修改 `data/theme_rules.json` 后需**重启服务**；进程内规则有缓存，开发时可在代码中调用 `theme_rules.reload_theme_rules()` 清空缓存

### 数据迁移
- 图片保存在本地 `static/uploads/`，数据库仅存路径；多用户下新文件按用户分子目录存储
- 若升级前已有无 `user_id` 的票据，启动时会自动创建用户 `default` / 密码 `123456`，并将旧票据归到该账号

### 地图与统计
- 上传票据时可填写省份和城市信息，便于地图展示和统计分析
- OCR 识别会自动尝试提取省份和城市信息
- 足迹地图展示去过的省份和城市分布
- 年度统计提供年度趋势、类型分布、常去地点等可视化报告

## License

MIT License
