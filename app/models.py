from sqlalchemy import Column, Integer, String, DateTime, Text
from datetime import datetime
from app.database import Base


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
