from dataclasses import dataclass, field
from typing import Dict, Any, Optional
from datetime import datetime

@dataclass
class AgentMessage:
    """
    Mensaje estandarizado para comunicación entre agentes.
    
    Attributes:
        sender: Nombre del agente emisor
        content: Contenido principal del mensaje
        metadata: Información adicional (contexto, IDs, etc.)
        timestamp: Momento de creación
        success: Indica si la operación fue exitosa
    """
    sender: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    timestamp: Optional[datetime] = None
    success: bool = True
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()
    
    def to_dict(self) -> Dict[str, Any]:
        """Serializa a diccionario"""
        return {
            "sender": self.sender,
            "content": self.content,
            "metadata": self.metadata,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "success": self.success
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentMessage':
        """Deserializa desde diccionario"""
        if 'timestamp' in data and isinstance(data['timestamp'], str):
            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)