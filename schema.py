from pydantic import BaseModel, Field
from typing import Dict, Optional

class ProductExtraction(BaseModel):
    model_name: Optional[str] = None
    brand: Optional[str] = None
    additional_specs: Dict[str, str] = Field(default_factory=dict)