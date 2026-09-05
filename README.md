# Facebook 广告管理面板（Docker 部署）

一个基于 FastAPI + Facebook Marketing (Graph) API 的自托管广告管理面板，支持：

- 🔐 **账号密码登录**：JWT 会话，非公开的单一口令
- 🏢 **多 Business Manager 管理**：一个「BM账号维护配置表」，可添加多个 BM 的系统用户令牌，系统自动按账户归属选用正确令牌发起操作
- 📋 **账户总览**：聚合展示所有已配置 BM 下的广告账户，标注花费、余额、花费上限、所属 BM，可打备注
- 🛠 **创建广告**：按 Campaign → AdSet → Creative → Ad 的顺序完整走完广告创建流程
- 📈 **数据分析**：按日期区间 / 按广告系列查看花费、曝光、点击、CTR、CPC，并有图表
- 💰 **额度管理**：查看并调整账户的花费上限（spend cap）
- 📝 操作日志会写入本地 SQLite（`data/panel.db`），便于审计

> 这是一个可用的**脚手架 / 起点**，覆盖了 Marketing API 最核心的流程。生产环境请按需加固鉴权、审批流程、多用户权限等。

---

## 一、前置准备（Facebook 侧，每个 Business Manager 都要做一遍）

1. 在 [Facebook for Developers](https://developers.facebook.com/) 创建一个应用（类型选 Business），添加 **Marketing API** 产品。
2. 在每个要接入的 Meta Business Manager 里，进入 **商务设置 → 系统用户**，创建一个系统用户，生成**长效访问令牌**，授予以下权限：
   - `ads_management`
   - `ads_read`
   - `business_management`
3. 把该系统用户加入到该 BM 下要管理的广告账户，赋予"广告管理员"角色。
4. 部署完面板后，登录进去，到「BM账号管理」页面把这个令牌连同一个便于识别的名称（如"客户A-主BM"）添加进去。系统会先校验令牌有效再保存。
5. 有几个 Business Manager，就重复第 2~4 步添加几条记录即可，账户总览会自动把所有 BM 下的账户聚合展示。

> 注意：新账户/新应用可能需要先通过 Facebook 的 App Review 才能在生产环境使用全部权限。

---

## 二、部署步骤

```bash
# 1. 克隆/解压项目后进入目录
cd fb-ads-panel

# 2. 复制环境变量文件并填入真实值
cp .env.example .env
vim .env    # 填入 ADMIN_USERNAME / ADMIN_PASSWORD / JWT_SECRET

# 3. 构建并启动
docker compose up -d --build

# 4. 查看日志
docker compose logs -f
```

启动后访问：`http://<服务器IP>:8811`（若走 Apache 反代 + 域名，见 `deploy/README-deploy.md`），用 `.env` 中设置的 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 登录。登录后先到「BM账号管理」添加各个 Business Manager 的系统用户令牌。

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
| POST | `/api/login` | 账号密码登录，返回 JWT（后续请求头 `Authorization: Bearer <token>`） |
| GET | `/api/accounts` | 广告账户列表（聚合所有 BM，含 `remaining_budget` 剩余可花费额度） |
| GET | `/api/accounts/{id}` | 单个账户详情（花费/花费上限/剩余可花费额度） |
| POST | `/api/accounts/{id}/spend_cap` | 设置花费上限（传 0 = 清除上限） |
| GET/POST | `/api/accounts/{id}/campaigns` | 广告系列 列表/创建 |
| PATCH | `/api/accounts/{id}/campaigns/{campaign_id}` | 修改广告系列（名称/状态/预算） |
| POST | `/api/accounts/{id}/campaigns/{campaign_id}/duplicate` | 复制广告系列（Facebook 原生深拷贝） |
| GET/POST | `/api/accounts/{id}/adsets` | 广告组 列表/创建 |
| PATCH | `/api/accounts/{id}/adsets/{adset_id}` | 修改广告组（名称/状态/预算/出价） |
| POST | `/api/accounts/{id}/adsets/{adset_id}/duplicate` | 复制广告组（Facebook 原生深拷贝，可连同其下广告一起复制） |
| POST | `/api/accounts/{id}/images` | 上传素材图片（全程内存转发，不落盘） |
| POST | `/api/accounts/{id}/creatives` | 创建广告创意 |
| GET/POST | `/api/accounts/{id}/ads` | 广告 列表/创建 |
| PATCH | `/api/accounts/{id}/ads/{ad_id}` | 修改广告（名称/状态） |
| POST | `/api/accounts/{id}/ads/{ad_id}/duplicate` | 复制广告 |
| POST | `/api/accounts/{id}/objects/{object_id}/status` | 通用启停接口（Campaign/AdSet/Ad 均可用） |
| GET | `/api/accounts/{id}/insights` | 数据洞察（`date_preset`, `by_campaign`） |
| GET/POST | `/api/credentials` | BM 凭证 列表/新增（新增时会先校验令牌有效性） |
| PATCH/DELETE | `/api/credentials/{id}` | 更新（启停/改令牌）/删除某个 BM 凭证 |


---

## 五、关于「余额」字段的重要说明

Facebook 原始 `balance` 字段的含义因账户资金模式而异：
- 预付费账户：代表账户预存的余额
- 信用额度账户：代表**当前待还款金额**（不是可用额度！）

这两种含义都**不等于**"距花费上限还能花多少"。因此面板改为额外计算一个真正有用的字段：

```
剩余可花费额度 = 花费上限（spend_cap） − 已花费（amount_spent）
```

「额度管理」页面同时展示这个计算值和 Facebook 原始 `balance`（仅供参考），避免混淆。
更新花费上限失败时，面板会把 Facebook 返回的具体错误原因直接展示出来（常见原因：新上限低于已花费金额、令牌权限不足、账户资金模式不支持通过 API 改上限等）。

---

## 六、关于素材上传

上传的图片/素材全程只经过内存，直接转发给 Facebook 的 `/adimages` 接口，本服务**不会**把文件写入磁盘、也不落库保存——请求结束后数据即从内存释放，不占用服务器存储空间。

---

## 六.5、避免浏览器缓存旧的前端代码

`static/index.html` 里引用 `app.js` / `style.css` 时带了版本号（如 `?v=3`）。**以后每次改完前端代码重新部署，记得把这个版本号数字改一下**（比如 v=3 → v=4），否则用户浏览器可能还在用缓存的旧版 JS/CSS，即使容器已经是最新代码，页面表现却像"没生效"。改完 `docker compose up -d --build` 之后，用户端再强制刷新（Ctrl+Shift+R）一次即可看到最新效果。

> 如果你前面还接了 Cloudflare：Cloudflare 默认也会在边缘节点缓存 `.js`/`.css` 这类静态资源。查询字符串（`?v=3`）通常会被计入缓存 key，正常情况下换版本号就能让 Cloudflare 重新回源拉取；如果怀疑 Cloudflare 那一层也缓存住了没刷新，去 Cloudflare 后台「Caching → Configuration → Purge Everything」手动清一次缓存。

---

## 七、广告管理（对齐 Ads Manager 常用操作）

「广告管理」标签页支持：选择账户 → 看该账户下所有 Campaign → 点进去看其 AdSet → 再点进去看其 Ad。每一级都可以：

- **暂停/启用**（一键切换状态）
- **改预算**（Campaign/AdSet 级别的每日预算）
- **复制**（调用 Facebook 原生的 `/copies` 深拷贝接口，AdSet/Campaign 复制时可选是否连同子对象一起复制，默认复制出来的状态是 PAUSED，避免误开花钱）

---

## 八、后续可扩展方向

- 多用户账号体系（目前是单管理员账号密码登录，适合个人/小团队自用）
- Webhook 接收 Facebook 账户状态变更、预算耗尽等通知
- 定时任务：每日自动拉取并落库 insights，做历史趋势分析
- 审批流：创建/修改预算需要二次确认或多人审批
- 按 BM/账户维度做操作权限隔离（目前登录后可看到所有已配置 BM 的账户）

---

## 九、安全提醒

- 每个 BM 系统用户令牌权限很高，可直接花钱投放广告，请勿泄露、不要提交到公开仓库（`.env` 已在 `.gitignore` 里，令牌本身存在 SQLite `data/panel.db` 中，同样注意不要把 `data/` 目录提交或公开）。
- 建议只通过 Apache/Nginx 加 HTTPS 之后对外暴露，不要把容器端口直接绑定在公网网卡上（`docker-compose.yml` 里已改成 `127.0.0.1:8811:8000`，宿主机只在本机回环地址监听 8811，AWS Security Group 无需为此端口开放任何入站规则）。
- `ADMIN_PASSWORD`、`JWT_SECRET` 请务必改成强随机值，不要使用默认值上线。
