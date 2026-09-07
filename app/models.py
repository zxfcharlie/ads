from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean
from datetime import datetime
from app.database import Base


class BMCredential(Base):
    """
    Business Manager 凭证维护配置表。
    每一行代表一个 Meta Business Manager 的系统用户长效令牌，
    系统据此聚合、管理该 BM 下的所有广告账户。
    """
    __tablename__ = "bm_credentials"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String, index=True)          # BM 名称/备注，如 "客户A - BM"
    bm_id = Column(String, default="")           # Business Manager ID（可选，便于核对）
    access_token = Column(Text)                  # 系统用户长效令牌
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AccountCredentialMap(Base):
    """
    记录每个广告账户属于哪个 BM 凭证，用于后续对该账户发起操作时
    自动选用正确的 access_token，无需用户每次手动指定。
    """
    __tablename__ = "account_credential_map"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(String, unique=True, index=True)  # act_xxx
    credential_id = Column(Integer, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AccountNote(Base):
    """本地补充信息：给某个 FB 广告账户打标签/备注/分组，不存令牌"""
    __tablename__ = "account_notes"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(String, unique=True, index=True)  # act_xxx
    label = Column(String, default="")
    group = Column(String, default="")
    note = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class OperationLog(Base):
    """操作日志：谁在什么时候对哪个账户做了什么操作"""
    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(String, index=True)
    action = Column(String)          # create_campaign / create_adset / create_ad / update_budget ...
    detail = Column(Text, default="")
    status = Column(String, default="success")  # success / failed
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    """
    面板登录账号。管理员账号由 .env 里的 ADMIN_USERNAME/ADMIN_PASSWORD 自动同步生成，
    其余账号通过注册流程创建，默认 is_approved=False，需要管理员审核通过才能登录使用。
    """
    __tablename__ = "app_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password_hash = Column(String)
    is_admin = Column(Boolean, default=False)
    is_approved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserAccess(Base):
    """
    用户访问权限授权表：管理员给某个用户开通某个 BM 的访问权限，
    account_id 留空 = 该 BM 下所有广告账户都能看；account_id 非空 = 只能看这一个账户。
    普通用户默认（没有任何授权记录时）看不到任何广告账户。
    """
    __tablename__ = "user_access"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, index=True)
    credential_id = Column(Integer, index=True)   # 对应 BMCredential.id
    account_id = Column(String, nullable=True)    # act_xxx，留空代表整个 BM
    created_at = Column(DateTime, default=datetime.utcnow)


class GoogleCredential(Base):
    """
    Google Ads 凭证维护配置表（对应 Meta 的 BMCredential）。
    Google Ads API 走 OAuth2 refresh token 的模式，不像 Meta 系统用户令牌那样一个
    字符串就够，需要 developer_token / client_id / client_secret / refresh_token
    这四样，外加可选的 login_customer_id（如果这个 refresh token 挂在一个 MCC 经理账户下）。
    """
    __tablename__ = "google_credentials"

    id = Column(Integer, primary_key=True, index=True)
    label = Column(String, index=True)              # 名称/备注，如 "客户A - Google Ads"
    developer_token = Column(String)
    client_id = Column(String)
    client_secret = Column(String)
    refresh_token = Column(Text)
    login_customer_id = Column(String, default="")  # MCC 经理账户 ID，可选，纯数字不带横线
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
