"""ICT 운영 지원 실습용 MCP 서버 초기화.

현재는 서버 인스턴스와 로컬 데이터 경로만 정의한다.
"""

from pathlib import Path

from fastmcp import FastMCP

mcp = FastMCP(name="ict-operations-support")

DATA_DIR = Path(__file__).parent / "data"
