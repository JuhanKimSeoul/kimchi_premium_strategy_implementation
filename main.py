import importlib
import logging.config
import os
from pathlib import Path
from contextlib import asynccontextmanager
import yaml
from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI

# YAML 파일 경로
LOGGING_CONFIG_PATH = Path(__file__).resolve().parent / "logging_config.yaml"

# YAML 파일에서 로깅 설정 로드
def setup_logging():
    """
    YAML 파일에서 로깅 설정을 로드합니다.

    Args:
        None

    Returns:
        None

    Raises:
        FileNotFoundError: YAML 파일이 존재하지 않을 경우.
        yaml.YAMLError: YAML 파일 파싱 중 오류가 발생한 경우.
    """
    with open(LOGGING_CONFIG_PATH, "r", encoding="utf-8") as file:
        config = yaml.safe_load(file)
        logging.config.dictConfig(config)

# 로깅 설정 초기화
setup_logging()

# 로거 생성
logger = logging.getLogger("app")

# Lifespan 이벤트 핸들러 정의
@asynccontextmanager
async def lifespan(_app: FastAPI):
    """
    FastAPI 애플리케이션의 lifespan 이벤트를 처리합니다.

    이 함수는 애플리케이션이 시작되고 메인 로직이 실행되기 전, 그리고 종료되기 전에 필요한 로직을 삽입하기 위해 사용됩니다.

    Args:
        _app (FastAPI): FastAPI 애플리케이션 인스턴스.

    Yields:
        None: 애플리케이션 실행 중에 lifespan 이벤트를 처리합니다.

    Raises:
        None
    """
    # 애플리케이션 시작 시 실행
    logger.info("애플리케이션 시작")
   
    yield  # 애플리케이션 실행 중
   
    # 애플리케이션 종료 시 실행
    logger.info("애플리케이션 종료")

# FastAPI 애플리케이션 생성
app = FastAPI(lifespan=lifespan)

# API 라우터 등록
# api/endpoints 디렉토리에서 모든 라우터 파일을 자동으로 로드
ROUTERS_DIR = "app/api/endpoints"
for filename in os.listdir(ROUTERS_DIR):
    if filename.endswith(".py") and filename != "__init__.py":
        MODULE_NAME = f"{ROUTERS_DIR}.{filename[:-3]}".replace("/", ".")
        module = importlib.import_module(MODULE_NAME)
        app.include_router(module.router)
       
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
    