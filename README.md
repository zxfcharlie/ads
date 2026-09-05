# Facebook 广告管理面板（Docker 部署）

一个基于 FastAPI + Facebook Marketing (Graph) API 的自托管广告管理面板，支持：

- 📋 **账户总览**：列出你有权限管理的所有广告账户，展示花费、余额、花费上限，可打备注
- 🛠 **创建广告**：按 Campaign → AdSet → Creative → Ad 的顺序完整走完广告创建流程
- 📈 **数据分析**：按日期区间 / 按广告系列查看花费、曝光、点击、CTR、CPC，并有图表
- 💰 **额度管理**：查看并调整账户的花费上限（spend cap）
- 📝 操作日志会写入本地 SQLite（`data/panel.db`），便于审计

> 这是一个可用的**脚手架 / 起点**，覆盖了 Marketing API 最核心的流程。生产环境请按需加固鉴权、审批流程、多用户权限等。

---

## 一、前置准备（Facebook 侧）

1. 在 [Facebook for Developers](https://developers.facebook.com/) 创建一个应用，类型选 **Business**。
2. 在应用中添加 **Marketing API** 产品。
3. 获取长效访问令牌，推荐使用 **系统用户（System User）令牌**（在 Business Manager → 商务设置 → 系统用户中创建），并授予以下权限：
   - `ads_management`
   - `ads_read`
   - `business_management`
4. 把该系统用户加入到你要管理的广告账户，赋予"广告管理员"角色。
5. 拿到：
   - `FB_APP_ID`
   - `FB_APP_SECRET`
   - `FB_ACCESS_TOKEN`（系统用户长效令牌，注意保密，不要提交到 git）

> 注意：Facebook 广告账户操作（尤其创建广告、修改预算）受平台风控和审核规则约束，新账户/新应用可能需要先通过 Facebook 的 App Review 才能在生产环境使用全部权限。

---

## 二、部署步骤

```bash
# 1. 克隆/解压项目后进入目录
cd fb-ads-panel

# 2. 复制环境变量文件并填入真实值
cp .env.example .env
vim .env    # 填入 FB_APP_ID / FB_APP_SECRET / FB_ACCESS_TOKEN / PANEL_PASSWORD

# 3. 构建并启动
docker compose up -d --build

# 4. 查看日志
docker compose logs -f
```

启动后访问：`http://<服务器IP>:8000`，用 `.env` 中设置的 `PANEL_PASSWORD` 登录。

---

## 三、目录结构

```
fb-ads-panel/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
├── app/
│   ├── main.py           # FastAPI 入口 + 简单口令鉴权
│   ├── config.py         # 环境变量配置
│   ├── database.py       # SQLite 连接
│   ├── models.py         # 本地表：账户备注、操作日志
│   ├── fb_client.py       # Graph API 封装（账户/系列/广告组/素材/广告/洞察）
│   └── routers/
│       ├── accounts.py    # 账户列表、详情、花费上限
│       ├── campaigns.py   # Campaign/AdSet/Creative/Ad 增删改
│       └── insights.py    # 数据分析
└── static/
    ├── index.html         # 看板页面
    ├── style.css
    └── app.js
```

---

## 四、接口速览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/login` | 登录，返回 token（用于后续请求头 `X-Panel-Token`） |
| GET | `/api/accounts` | 广告账户列表 |
| GET | `/api/accounts/{id}` | 单个账户详情（花费/余额/上限） |
| POST | `/api/accounts/{id}/spend_cap` | 设置花费上限 |
| GET/POST | `/api/accounts/{id}/campaigns` | 广告系列 列表/创建 |
| GET/POST | `/api/accounts/{id}/adsets` | 广告组 列表/创建 |
| POST | `/api/accounts/{id}/images` | 上传素材图片 |
| POST | `/api/accounts/{id}/creatives` | 创建广告创意 |
| GET/POST | `/api/accounts/{id}/ads` | 广告 列表/创建 |
| POST | `/api/objects/{id}/status` | 启用/暂停/归档任意对象（Campaign/AdSet/Ad） |
| GET | `/api/accounts/{id}/insights` | 数据洞察（`date_preset`, `by_campaign`） |

---

## 五、后续可扩展方向

- 多用户账号体系（目前是单一口令，适合个人/小团队自用）
- 令牌按账户维度存储（目前用一个全局 `FB_ACCESS_TOKEN` 管理所有已授权账户）
- Webhook 接收 Facebook 账户状态变更、预算耗尽等通知
- 定时任务：每日自动拉取并落库 insights，做历史趋势分析
- 审批流：创建/修改预算需要二次确认或多人审批
- 反向代理 + HTTPS（Nginx / Caddy）+ 更强的登录鉴权（JWT + 多用户）

---

## 六、安全提醒

- `FB_ACCESS_TOKEN` 权限很高，可直接花钱投放广告，请勿泄露、不要提交到公开仓库。
- 建议只在内网或加了 HTTPS + 强密码的环境暴露此面板。
- `PANEL_PASSWORD` 仅做了最基础的口令保护，敏感/多人场景请自行加固为正式的用户体系。
