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
