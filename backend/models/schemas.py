from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class AnalysisCreate(BaseModel):
    company_name: str
    file_name: str
    raw_text: str

class AnalysisResponse(BaseModel):
    id: int
    company_name: str
    file_name: str
    summary: Optional[str]
    risks: Optional[str]
    benefits: Optional[str]
    financial_data: Optional[str]
    ipo_details: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True
```
