"""운영 매뉴얼 벡터 검색용 공개 모델 파일만 내려받습니다."""

from fastembed import TextEmbedding

from manual_vector import MODEL_NAME, _register_model


if __name__ == "__main__":
    _register_model(TextEmbedding)
    TextEmbedding(model_name=MODEL_NAME)
    print("벡터 검색 모델 준비 완료")
