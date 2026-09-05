# 广告管理平台（Docker 部署）

一个基于 FastAPI 的自托管多渠道广告管理平台。目前已接入 **Meta（Facebook）广告** 全套功能，界面预留了 Google、TikTok 等渠道的入口位置，后续接入新渠道时只需在侧边栏「渠道」列表里加一组，不需要推倒重来。

支持能力（当前均为 Meta 渠道下的功能）：

- 🎨 **侧边栏式多渠道架构**：左侧「渠道」列表里，Meta 广告是一个完整分组（账户总览/广告管理/BM账号管理三个子页面），Google/TikTok 广告先以"即将推出"占位展示
- 🔐 **多用户账号 + 审核制**：任何人可以自己注册，但默认待审核、零权限；管理员账号（由 `.env` 自动同步生成）负责审核通过和分配权限
- 🎯 **按 BM / 按账户精细授权**：管理员给每个用户单独分配"某个 BM 的全部账户"或"某个 BM 下的某一个账户"，权限校验在后端强制执行
- 🏢 **多 Business Manager 管理**（管理员专属）：一个「BM账号维护配置表」，只需粘贴系统用户令牌，BM 名称和 ID 自动识别，系统自动按账户归属选用正确令牌发起操作
- 📋 **账户总览**：聚合展示当前用户有权限查看的广告账户，标注花费、花费上限、剩余可花费额度、所属 BM，可打备注
- 📊 **广告管理**：先选 BM 再选广告账户，然后逐层下钻（系列 → 组 → 广告），字段对齐 Facebook 原生 Ads Manager（花费、购物、ROAS、CPM、视频播放等）；支持排序/筛选、表格内直接改预算、暂停/启用、复制；新建广告时系列+组+广告一次性整套创建成 PAUSED 草稿，核对无误后再统一发布上线；国家/主页/像素/兴趣词等定向字段全部从 Facebook 实时读取
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
│       └── insights.py    # 原始数据洞察（当前 UI 未使用，仅供 API 直接调用）
└── static/
    ├── index.html         # 看板页面
    ├── style.css
    └── app.js
```

---

## 四、接口速览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/register` | 注册新账号（默认待审核，需管理员通过后才能登录） |
| POST | `/api/login` | 账号密码登录，返回 JWT（后续请求头 `Authorization: Bearer <token>`）和 `is_admin` |
| GET | `/api/me` | 返回当前登录用户的用户名和 `is_admin` |
| GET | `/api/accounts` | 广告账户列表（管理员看全部；普通用户只看被授权的部分） |
| GET | `/api/accounts/{id}` | 单个账户详情（花费/花费上限/剩余可花费额度） |
| GET/POST | `/api/accounts/{id}/campaigns` | 广告系列 列表/创建 |
| PATCH | `/api/accounts/{id}/campaigns/{campaign_id}` | 修改广告系列（名称/状态/预算） |
| POST | `/api/accounts/{id}/campaigns/{campaign_id}/duplicate` | 复制广告系列（Facebook 原生深拷贝） |
| GET | `/api/accounts/{id}/campaigns/overview` | 广告系列列表 + 聚合指标（花费/购物/ROAS/CPM/视频等，供「广告管理」页面用） |
| GET/POST | `/api/accounts/{id}/adsets` | 广告组 列表/创建 |
| PATCH | `/api/accounts/{id}/adsets/{adset_id}` | 修改广告组（名称/状态/预算/出价） |
| POST | `/api/accounts/{id}/adsets/{adset_id}/duplicate` | 复制广告组（Facebook 原生深拷贝，可连同其下广告一起复制） |
| GET | `/api/accounts/{id}/adsets/overview` | 广告组列表 + 聚合指标（需传 `campaign_id`） |
| POST | `/api/accounts/{id}/images` | 上传素材图片（全程内存转发，不落盘） |
| POST | `/api/accounts/{id}/creatives` | 创建广告创意 |
| GET/POST | `/api/accounts/{id}/ads` | 广告 列表/创建 |
| PATCH | `/api/accounts/{id}/ads/{ad_id}` | 修改广告（名称/状态） |
| POST | `/api/accounts/{id}/ads/{ad_id}/duplicate` | 复制广告 |
| GET | `/api/accounts/{id}/ads/overview` | 广告列表 + 聚合指标（需传 `adset_id`） |
| POST | `/api/accounts/{id}/quick_launch` | 一次性创建系列+组+素材+广告，全部落地为 PAUSED 草稿 |
| POST | `/api/accounts/{id}/publish` | 把草稿的系列/组/广告统一切到 ACTIVE，正式发布 |
| GET | `/api/accounts/{id}/pixels` | 该账户下的像素列表 |
| GET | `/api/accounts/{id}/pages` | 当前令牌可管理的 Facebook 主页列表 |
| GET | `/api/accounts/{id}/interests?q=` | 搜索 Facebook 兴趣定向库 |
| POST | `/api/accounts/{id}/objects/{object_id}/status` | 通用启停接口（Campaign/AdSet/Ad 均可用） |
| GET | `/api/accounts/{id}/insights` | 按天/按系列的原始数据洞察（**当前 UI 未使用，仅供 API 直接调用**） |
| POST | `/api/accounts/{id}/spend_cap` | 设置花费上限，传 0 = 清除上限（**当前 UI 未使用，仅供 API 直接调用**） |
| GET/POST | `/api/credentials`（**管理员专属**） | BM 凭证 列表/新增（新增时校验令牌有效性，自动识别 BM 名称/ID） |
| PATCH/DELETE | `/api/credentials/{id}`（**管理员专属**） | 更新（启停/改令牌）/删除某个 BM 凭证 |
| GET | `/api/admin/users`（**管理员专属**） | 所有用户列表（含待审核） |
| POST | `/api/admin/users/{id}/approve`（**管理员专属**） | 审核通过 |
| POST | `/api/admin/users/{id}/revoke`（**管理员专属**） | 撤销审核（打回待审核状态） |
| DELETE | `/api/admin/users/{id}`（**管理员专属**） | 删除用户（拒绝申请 / 彻底移除账号） |
| GET/POST | `/api/admin/users/{id}/access`（**管理员专属**） | 查看/新增该用户的 BM·账户访问授权 |
| DELETE | `/api/admin/access/{access_id}`（**管理员专属**） | 撤销一条访问授权 |

---

## 五、关于「余额」与花费上限（当前仅通过 API 使用，UI 已下线）

按你的要求，「数据分析」「额度管理」这两个独立标签页已经从界面里移除（相关接口 `/insights`、`/spend_cap` 仍保留在后端，未来要恢复 UI 或用脚本/第三方工具调用都可以）。

「账户总览」页面仍然展示已花费、花费上限、剩余可花费额度三列，计算方式：

```
剩余可花费额度 = 花费上限（spend_cap） − 已花费（amount_spent）
```

Facebook 原始 `balance` 字段的含义因账户资金模式而异（预付费账户＝预存余额；信用额度账户＝**待还款金额**，不是可用额度），不等于"距上限还能花多少"，所以面板不再展示这个容易引起误解的原始字段。如需通过 API 调整花费上限，仍可以直接调用 `POST /api/accounts/{id}/spend_cap`（传 0 = 清除上限）。

---

## 六、关于素材上传

上传的图片/素材全程只经过内存，直接转发给 Facebook 的 `/adimages` 接口，本服务**不会**把文件写入磁盘、也不落库保存——请求结束后数据即从内存释放，不占用服务器存储空间。

---

## 六.5、避免浏览器缓存旧的前端代码

`static/index.html` 里引用 `app.js` / `style.css` 时带了版本号（如 `?v=5`）。**以后每次改完前端代码重新部署，记得把这个版本号数字改一下**（比如 v=5 → v=6），否则用户浏览器可能还在用缓存的旧版 JS/CSS，即使容器已经是最新代码，页面表现却像"没生效"。改完 `docker compose up -d --build` 之后，用户端再强制刷新（Ctrl+Shift+R）一次即可看到最新效果。

> 如果你前面还接了 Cloudflare：Cloudflare 默认也会在边缘节点缓存 `.js`/`.css` 这类静态资源。查询字符串（`?v=5`）通常会被计入缓存 key，正常情况下换版本号就能让 Cloudflare 重新回源拉取；如果怀疑 Cloudflare 那一层也缓存住了没刷新，去 Cloudflare 后台「Caching → Configuration → Purge Everything」手动清一次缓存。

---

## 七、广告管理（点名称逐层下钻，创建也整合在这里，字段对齐 Ads Manager）

「广告管理」标签页的交互方式：

1. 右上角先选 **BM**，再选该 BM 下的**广告账户**（两级联动，选完 BM 账户下拉框自动过滤）
2. 默认看到的是**广告系列 Campaign** 列表
3. **点系列名称** → 进入该系列下的**广告组 AdSet** 列表（面包屑显示"全部广告系列 › 系列名"，点面包屑可返回上一级）
4. **点广告组名称** → 进入该组下的**广告 Ad** 列表

表格字段对齐 Facebook 原生 Ads Manager 常用列：名称、状态、预算、已花费金额、购物次数、购物转化价值、广告花费回报(ROAS)-购物、单次购物成本、频次、展示次数、CPM、链接点击量、单次链接点击费用、链接点击率、加入购物车次数、结账发起次数、视频播放量、视频播放达50%/100%次数。列很多，表格区域可以左右滑动查看。页面整体是撑满屏幕宽度的，不再是居中的窄栏。

**预算列直接在表格里编辑**（不再弹窗）：
- 如果该广告系列本身有预算（即开启了 Campaign Budget Optimization / CBO），会显示一个金额输入框和「保存」按钮，改完点保存即时生效
- 如果该广告系列没有自己的预算（预算在广告组层级，即 ABO），系列这一行显示"使用广告组预算"（纯文字，不可编辑），要改预算需要点进该系列，在广告组那一层的预算格子里改
- 广告（Ad）层级没有预算概念，该列固定显示"-"

**创建广告采用"整套草稿"模式**，不再支持单独建一个空的广告系列（Facebook 要求系列/组/广告成套配置，单独建空系列容易在 `special_ad_categories` 等必填参数上出错，也容易漏配置）：

- 在**广告系列列表**页，点「+ 新建广告（系列+组+广告一起建）」，一个表单里把系列（名称/目标）、广告组（名称/预算/定向/优化目标）、广告（素材信息+图片+广告名称）三层一次填完
- 提交后后台依次执行：创建系列 → 创建广告组 → 上传图片/创建创意 → 创建广告，全部以 **PAUSED（草稿，不会花钱）** 状态落地
- 创建成功后会出现一个「发布上线」按钮，点击后统一把系列/组/广告三者的状态切到 **ACTIVE**，正式开始投放
- 如果中途某一步失败（比如广告组建到一半失败），提示信息里会告诉你**前面已经成功创建到哪一步**（Facebook 没有跨对象事务回滚，已创建的部分不会自动撤销，需要你自己判断是否要去 Ads Manager 里清理）
- 已有的系列/组下面继续「加一个广告组」「加一个广告」，还是用点进对应层级后出现的「+ 新建广告组」「+ 新建广告」（这两个走的是原来的单独创建接口，暂时还是文本输入国家，未来可以按需扩展）

**表单里的定向字段都是从 Facebook 实时读取的真实数据**，不是让你手打：
- **投放国家**：输入国家名称或代码，从内置的常用国家列表里搜索、点选，可多选，支持删除
- **兴趣定向**：输入关键词（如"瑜伽""跑步鞋"），实时调用 Facebook 的兴趣定向库搜索（`GET /search?type=adinterest`），点选加入，可多选
- **Facebook 主页**：下拉框读取当前系统用户令牌被授权管理的所有主页（`GET /me/accounts`），不用再去 Facebook 后台复制 Page ID
- **像素 + 转化事件**：优化目标选择「转化」时才会出现。像素下拉框读取该广告账户下真实存在的像素（`GET /{account_id}/adspixels`）；转化事件是 Facebook 标准事件列表（Purchase/Lead/AddToCart 等），提交时会作为 `promoted_object` 绑定到广告组上
- **转化位置**：目前面板的广告创建走的是网页链接创意（`link_data`），所以固定显示"网站"，还没做 App/Messenger 等其他转化位置的支持

**落地页链接会自动补全协议头**：Facebook 要求 `link` 字段必须是完整合法 URL，如果你只填了 `www.example.com` 没带 `http(s)://`，前端失焦时和后端保存时都会自动补成 `https://www.example.com`，不用自己记得加。

**报错信息更详细了**：调用 Facebook API 失败时，除了顶层的 `message`（经常很笼统，比如"Invalid parameter"），面板现在还会把 `error_user_msg`（用户可读提示）、`error_subcode`（子错误码）、`fbtrace_id`（可拿去找 Facebook 支持排查）一并显示出来，方便下次报错时一眼看出具体是哪个字段的问题。

每一行都支持**暂停/启用**一键切换和**复制**（调用 Facebook 原生 `/copies` 深拷贝接口，复制出来的默认是 PAUSED，避免误开花钱；AdSet/Campaign 复制时会连同子对象一起复制）。

**排序 / 筛选**（纯前端处理，当前这一层的数据已经在浏览器里，不用再打接口）：
- 点任意列的表头即可按该列排序，再点一次切换升序/降序
- 上方有一个按名称筛选的输入框和一个状态筛选下拉框，**默认只显示 ACTIVE 状态**（下拉框可以切到"全部状态"或"仅PAUSED"），随打字即时生效
- 切换 BM/账户，或者点名称往下钻/点面包屑往上返回时，筛选条件、排序和"新建..."表单都会自动清空收起，避免"上一层筛的关键字"带到下一层去

> **口径说明**：购物次数/购物转化价值/ROAS/加入购物车/结账发起这些指标，是按 Facebook 常见的 `omni_purchase`、`omni_add_to_cart` 等 action_type 从 Insights 接口解析出来的，实际数值可能因你的像素归因窗口设置等原因，与 Ads Manager 页面显示略有出入，仅供参考对齐，不代表官方最终结算口径。

---

## 八、如何接入新渠道（Google / TikTok 等）

当前架构已经按"多渠道"的方式搭好了骨架，Meta 只是其中一个渠道分组。接入新渠道时建议按这个模式走：

**前端**：
- 侧边栏里把对应渠道的 `.channel-group.is-disabled` 拿掉 `is-disabled`，`channel-header` 加上点击展开逻辑，仿照 Meta 那样在下面挂一组 `.channel-subnav` 子页面按钮
- 新渠道自己的页面内容放到新的 `<section id="tab-xxx" class="tab-panel hidden">`，复用现有的 `.card`、`.grid`、`.btn` 等样式类，视觉上会自动保持一致

**后端**：
- 参照 `app/fb_client.py` 的模式，新建一个 `app/google_client.py`（或对应渠道），封装该平台的账户/广告系列/广告组/广告/洞察等 API 调用
- 参照 `app/models.py` 里的 `BMCredential`，为新渠道建一张独立的凭证表（比如 Google Ads 的 refresh token / developer token），不要复用 Meta 的表，因为字段结构、鉴权方式通常都不一样
- 参照 `app/resolver.py` 的模式，为新渠道写一个"按账户 ID 找到该用哪个凭证"的 resolver
- 新建 `app/routers/google_xxx.py`，接口路径建议加渠道前缀区分，如 `/api/google/accounts`、`/api/google/campaigns` 等，避免和 Meta 的 `/api/accounts/...` 混在一起

## 九、多用户 + 审核制 + 按账户分权限

面板现在支持多人使用，不再是单一管理员账号：

**注册与审核**：
- 登录页有"注册"入口，任何人可以自己注册账号，但注册后默认是**待审核状态，看不到任何数据**
- `.env` 里的 `ADMIN_USERNAME`/`ADMIN_PASSWORD` 会在每次启动时自动同步成一个 `is_admin=True` 的超级管理员账号，免审核，永远能登录
- 管理员登录后到侧边栏「系统管理 → 用户管理」，能看到所有注册申请，点「通过」批准、点「拒绝」直接删除这条申请

**默认零权限，按需分配**：
- 一个用户即使被批准通过，**默认也看不到任何广告账户**——账户总览、广告管理里都是空的
- 管理员需要在「用户管理」页面里，对每个已通过审核的用户点「分配权限」，选择：
  - 某个 BM 的**全部账户**（授权整个 BM），或者
  - 某个 BM 下的**某一个具体广告账户**（细粒度授权）
  - 可以给同一个用户分配多条授权（比如"BM-A 全部账户" + "BM-B 下的某一个账户"）
- 权限校验是后端强制的，不只是前端隐藏：普通用户即使直接拿 API 去请求一个没被授权的 `account_id`，也会被拒绝（403）
- 管理员账号不受此限制，永远能看到所有已配置 BM 下的所有账户

**权限管理相关的操作**：
- 「用户管理」页面里，已通过的用户还能"撤销通过"（打回待审核状态，暂时不能登录）或"删除"（彻底移除账号和其所有授权记录）
- 「BM账号管理」标签页现在**只有管理员能看到**，普通用户的侧边栏里不会出现这一项，后端接口也做了同样的管理员限制

---

## 十、后续可扩展方向

- Webhook 接收 Facebook 账户状态变更、预算耗尽等通知
- 定时任务：每日自动拉取并落库 insights，做历史趋势分析
- 审批流：创建/修改预算需要二次确认或多人审批
- 用户分组/角色（目前是"管理员 / 普通用户"两级，没有更细的角色划分）

---

## 十一、安全提醒

- 每个 BM 系统用户令牌权限很高，可直接花钱投放广告，请勿泄露、不要提交到公开仓库（`.env` 已在 `.gitignore` 里，令牌本身存在 SQLite `data/panel.db` 中，同样注意不要把 `data/` 目录提交或公开）。
- 建议只通过 Apache/Nginx 加 HTTPS 之后对外暴露，不要把容器端口直接绑定在公网网卡上（`docker-compose.yml` 里已改成 `127.0.0.1:8811:8000`，宿主机只在本机回环地址监听 8811，AWS Security Group 无需为此端口开放任何入站规则）。
- `ADMIN_PASSWORD`、`JWT_SECRET` 请务必改成强随机值，不要使用默认值上线。
- 新注册的用户默认看不到任何数据，但**账号本身是任何人都能自己注册的**（不需要邀请码）。如果不希望面板对外公开注册入口，考虑在 Apache/Cloudflare 那一层单独限制 `/api/register` 的访问来源，或者后续在代码里加一个"是否开放注册"的开关。
