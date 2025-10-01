from abc import ABC, abstractmethod
from typing import List

class EmbeddingProvider(ABC):
    @abstractmethod
    async def get_embedding_async(self, text: str) -> List[float]:
        pass