# 部署到 memos.dailybonushub.com（Apache + SSL）

前提：DNS 里 `memos.dailybonushub.com` 已经 A 记录指向这台服务器的公网 IP，且服务器 80/443 端口对外开放。

## 1. 先把面板容器跑起来（宿主机监听在 127.0.0.1:8811）

```bash
cd fb-ads-panel
cp .env.example .env
vim .env   # 至少改 ADMIN_USERNAME / ADMIN_PASSWORD / JWT_SECRET
docker compose up -d --build
curl http://127.0.0.1:8811/api/health   # 应返回 {"status":"ok"}
```

## 2. 安装 Apache 与 certbot（Ubuntu/Debian 示例）

```bash
sudo apt update
sudo apt install -y apache2 certbot python3-certbot-apache

# 开启反代相关模块
sudo a2enmod proxy proxy_http ssl headers rewrite
sudo systemctl restart apache2
```

## 3. 放置 HTTP 虚拟主机配置，跑通后再签证书

```bash
sudo cp deploy/memos.dailybonushub.com.conf /etc/apache2/sites-available/
sudo a2ensite memos.dailybonushub.com.conf
sudo apache2ctl configtest      # 显示 Syntax OK 再继续
sudo systemctl reload apache2
```

此时用浏览器访问 `http://memos.dailybonushub.com` 应该已经能看到登录页（还没有 HTTPS）。

## 4. 用 certbot 自动签发并升级为 HTTPS

```bash
sudo certbot --apache -d memos.dailybonushub.com
```

按提示操作（填邮箱、同意条款），certbot 会自动：
- 申请 Let's Encrypt 证书
- 生成/覆盖出一个带 SSL 的虚拟主机配置（对照本目录里的
  `memos.dailybonushub.com-le-ssl.conf` 核对即可，字段应该基本一致）
- 把 80 端口配置改成自动跳转到 443

完成后访问 `https://memos.dailybonushub.com` 应该是绿锁、直接进登录页。

证书到期前 certbot 会通过系统定时任务自动续期，可用下面命令验证续期机制是否配置好：

```bash
sudo certbot renew --dry-run
```

## 5. 首次登录

用你在 `.env` 里设置的 `ADMIN_USERNAME` / `ADMIN_PASSWORD` 登录。

登录进去后，先去 **「BM账号管理」** 标签页，把每个 Meta Business Manager 的系统用户长效令牌逐个添加进去——每条记录对应一个 BM，系统会自动校验令牌有效性，校验通过才会保存。添加完成后「账户总览」会自动聚合展示所有 BM 下的广告账户，并标注每个账户属于哪个 BM。

## 6. 常见排查

| 现象 | 排查方向 |
|---|---|
| Apache 502 | 容器没起来或端口没监听：`docker compose ps`、`docker compose logs -f` |
| certbot 报域名验证失败 | DNS 没解析到位，或 80 端口被防火墙/云安全组挡住 |
| 登录后账户总览为空 | 还没在「BM账号管理」添加任何令牌，或令牌权限不含 `ads_management`/`ads_read` |
| 某个 BM 报错但其他正常 | 看「账户总览」页面下方的错误提示，通常是该令牌过期或系统用户被移出了该 BM |
