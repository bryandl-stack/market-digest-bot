"""의존성 없이 프로젝트 루트의 .env 를 os.environ 으로 로드한다.

cron/systemd 처럼 환경변수가 비어 있는 환경에서 시크릿을 주입하기 위함.
이미 설정된 실제 환경변수는 덮어쓰지 않는다(실 환경 우선). python-dotenv 같은
외부 의존성을 추가하지 않으려고 최소 구현만 둔다."""
import os


def load_env(path=None):
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and val and key not in os.environ:
                os.environ[key] = val
