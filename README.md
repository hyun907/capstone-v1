# AI Agent 개인 실습

AI Agent 서비스를 단계별로 직접 구현하고 검증하는 개인 실습 저장소입니다. 현재는 작업 규칙과 협업 양식, MCP 서버 초기화 코드만 준비되어 있습니다.

## 진행 범위

- MCP 도구와 FastAPI 연동
- SSE 스트리밍과 Supervisor 기반 에이전트 흐름
- 평가, 오류 처리, 성능 측정, 세션 저장
- 필요하면 구조 개선과 리팩터링

구현 단계와 실제 완료 여부는 이후 이슈와 PR에서 기록합니다.

## 작업 방식

- [코드·Git 컨벤션](docs/CONVENTIONS.md)을 따릅니다.
- [에이전트 작업 지침](AGENTS.md)을 작업 전에 확인합니다.
- 기능은 작은 단위로 구현하고, PR에 검증 명령과 결과를 남깁니다.
- 별도로 제공된 참조 자료는 학습·비교에만 사용합니다. 참조 구현이나 파일을 이 저장소에 복사해 공개하지 않습니다.

## 로컬 환경

Python 3.11과 `uv`를 사용합니다. 프로젝트 루트에서 `uv sync --locked`로 MCP 서버 의존성을 설치하고, `uv run python -c "from fastmcp import FastMCP; from pydantic import BaseModel"`로 import를 확인할 수 있습니다. MCP 서버 실행 방법은 실행 구문을 구현한 뒤 추가합니다. API 키와 연결 정보는 `.env` 같은 추적 제외 파일에 보관합니다.

## 실습 데이터

별도로 받은 `data-2`의 `monitoring.json`과 `runbooks/`는 로컬의 `mcp-server/data/`에 둡니다. 이 디렉터리는 Git 추적에서 제외되어 있으므로 새 환경에서는 데이터를 다시 배치해야 합니다. 참조 자료의 공유 권한을 확인하기 전에는 원본 파일을 커밋하지 않습니다.
