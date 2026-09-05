from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    fb_app_id: str = ""
    fb_app_secret: str = ""
    fb_access_token: str = ""
    fb_api_version: str = "v20.0"
    panel_password: str = "change_me"
    database_url: str = "sqlite:////app/data/panel.db"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()

GRAPH_BASE = f"https://graph.facebook.com/{settings.fb_api_version}"
