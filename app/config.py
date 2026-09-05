from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    fb_api_version: str = "v20.0"
    database_url: str = "sqlite:////app/data/panel.db"

    # 面板登录（账号+密码，单管理员，够小团队自用；如需多人登录可再扩展成用户表）
    admin_username: str = "admin"
    admin_password: str = "change_me"
    jwt_secret: str = "please_change_this_to_a_random_long_string"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

GRAPH_BASE = f"https://graph.facebook.com/{settings.fb_api_version}"
