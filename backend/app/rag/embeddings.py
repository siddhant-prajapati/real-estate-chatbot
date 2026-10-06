_local_embedding = None


def dense_embedding_function():
    from chromadb.utils.embedding_functions.chroma_cloud_qwen_embedding_function import (
        ChromaCloudQwenEmbeddingFunction,
        ChromaCloudQwenEmbeddingModel,
        ChromaCloudQwenEmbeddingTarget,
    )

    instructions = {
        "retrieval_document": {
            ChromaCloudQwenEmbeddingTarget.DOCUMENTS: "",
            ChromaCloudQwenEmbeddingTarget.QUERY: (
                "Given a real estate search query, retrieve matching property listings"
            ),
        }
    }
    return ChromaCloudQwenEmbeddingFunction(
        model=ChromaCloudQwenEmbeddingModel.QWEN3_EMBEDDING_0p6B,
        task="retrieval_document",
        instructions=instructions,
        api_key_env_var="CHROMA_API_KEY",
    )


def sparse_embedding_function():
    from chromadb.utils.embedding_functions.chroma_cloud_splade_embedding_function import (
        ChromaCloudSpladeEmbeddingFunction,
        ChromaCloudSpladeEmbeddingModel,
    )

    return ChromaCloudSpladeEmbeddingFunction(
        api_key_env_var="CHROMA_API_KEY",
        model=ChromaCloudSpladeEmbeddingModel.SPLADE_PP_EN_V1,
    )


def local_embedding_function():
    global _local_embedding
    if _local_embedding is None:
        from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

        _local_embedding = ONNXMiniLM_L6_V2()
    return _local_embedding
