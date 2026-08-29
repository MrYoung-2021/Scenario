import pytest

from rag.rag import RAG


class VectorStore:
    def __init__(self, present=True, fail=False):
        self.present = present
        self.fail = fail
        self.delete_calls = []

    def get(self, ids, include):
        return {"ids": ids if self.present else []}

    async def adelete(self, ids):
        self.delete_calls.append(ids)
        if self.fail:
            raise RuntimeError("delete failed")
        self.present = False


@pytest.mark.asyncio
async def test_rag_delete_checks_existence_before_and_after() -> None:
    vector = VectorStore()
    rag = RAG(vector_store=vector, embeddings=object())
    assert await rag.adelete_text_by_id("entry") is True
    assert vector.delete_calls == [["entry"]]
    assert await rag.adelete_text_by_id("entry") is False
    assert vector.delete_calls == [["entry"]]


@pytest.mark.asyncio
async def test_rag_delete_exception_returns_false() -> None:
    rag = RAG(vector_store=VectorStore(fail=True), embeddings=object())
    assert await rag.adelete_text_by_id("entry") is False
